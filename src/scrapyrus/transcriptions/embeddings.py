from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
import requests
from tqdm import tqdm

from scrapyrus.transcriptions.core import (
    MAXIMUM_TRANSCRIPTION_OPTIONS,
    TRANSCRIPTIONS_TABLE,
    epidoc_xml_to_text,
    transcription_language,
    translation_epidoc_xml_to_text,
)
from scrapyrus.transcriptions.llms import LLMProviderBase, initialize_llm_provider


TRANSCRIPTION_EMBEDDINGS_TABLE = "transcription_embeddings"
TRANSLATION_EMBEDDINGS_TABLE = "translation_embeddings"
EMBEDDING_TABLES = {
    "transcription": TRANSCRIPTION_EMBEDDINGS_TABLE,
    "translation": TRANSLATION_EMBEDDINGS_TABLE,
}
EMBEDDING_KIND_ALIASES = {
    "transcription": "transcription",
    "translation": "translation",
    "transcriptions": "transcription",
    "translations": "translation",
}
EMBEDDING_DUMP_COLUMNS = (
    "xml_id",
    "model_name",
    "chunk_index",
    "source_path",
    "tm_id",
    "language",
    "document_text",
    "input_hash",
    "embedding",
    "updated_at",
)

PGVECTOR_UNAVAILABLE_MESSAGE = (
    "PostgreSQL extension 'vector' is not available. Install pgvector on the "
    "database server before using embeddings, or use a pgvector-enabled "
    "PostgreSQL image such as pgvector/pgvector:pg16."
)
TRANSCRIPTIONS_UNAVAILABLE_MESSAGE = (
    f"PostgreSQL table '{TRANSCRIPTIONS_TABLE}' does not exist. Run "
    "'scrapyrus transcriptions ingest' against this database before using "
    "embeddings."
)
HNSW_VECTOR_MAX_DIMENSIONS = 2_000
HNSW_HALFVEC_MAX_DIMENSIONS = 4_000


class PgvectorUnavailableError(RuntimeError):
    """Raised when the PostgreSQL server does not provide pgvector."""


class TranscriptionsUnavailableError(RuntimeError):
    """Raised when transcription XML has not been ingested into PostgreSQL."""


@dataclass(frozen=True)
class _EmbeddingJob:
    ordinal: int
    store: "EmbeddingStore"
    row: dict[str, Any]
    table: str


@dataclass(frozen=True)
class _EmbeddedDocument:
    job: _EmbeddingJob
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class _SkippedEmbeddingDocument:
    job: _EmbeddingJob
    message: str


class EmbeddingStore:
    """Generate embeddings from transcription XML already stored in PostgreSQL."""

    def __init__(self, inference_server_url: str, modelname: str, api_key: str) -> None:
        self.inference_server_url = inference_server_url
        self.modelname = modelname
        self.provider: LLMProviderBase = initialize_llm_provider(
            inference_server_url, modelname, api_key
        )

    def setup_store(
        self,
        conninfo: str = "",
        progressbar: bool = True,
        /,
        *,
        stale_only: bool = False,
        sample: int | None = None,
        seed: int = 0,
        chunk_size: int = 500,
    ) -> int:
        """Embed transcription/translation XML rows in PostgreSQL.

        Transcriptions always use the maximum text variant. Translations use
        their complete plain-text rendering. Rows are stored in separate tables.
        When ``stale_only`` is true, unchanged rows are not sent to the model.
        When ``sample`` is set, deterministically select that many ``tm_id``
        records using ``seed`` from those which have both a transcription and
        a translation, and embed all XML rows belonging to those records.
        Text size and overlap are measured in whitespace-delimited words.
        """

        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")

        jobs: list[_EmbeddingJob] = []
        seen_ids = {kind: set() for kind in EMBEDDING_TABLES}
        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                _ensure_embedding_schema(cursor)
                try:
                    sources = _select_xml_rows(cursor, sample=sample, seed=seed)
                except psycopg.errors.UndefinedTable as error:
                    raise TranscriptionsUnavailableError(
                        TRANSCRIPTIONS_UNAVAILABLE_MESSAGE
                    ) from error
                source_rows = (
                    tqdm(
                        sources,
                        total=len(sources),
                        unit="row",
                        desc="Preparing XML rows",
                    )
                    if progressbar
                    else sources
                )
                for source in source_rows:
                    document_kind = str(source["type"])
                    if document_kind not in EMBEDDING_TABLES:
                        continue
                    xml_id = int(source["transcription_id"])
                    document_text = _xml_to_embedding_text(
                        str(source["xml_content"]), document_kind
                    )
                    if not document_text.strip():
                        continue
                    table = EMBEDDING_TABLES[document_kind]
                    seen_ids[document_kind].add(xml_id)
                    chunks = chunk_embedding_text(document_text, chunk_size)
                    _delete_extra_chunks(
                        cursor, table, xml_id, self.modelname, len(chunks)
                    )
                    language = (
                        transcription_language(str(source["xml_content"]))
                        if document_kind == "transcription"
                        else source["language"]
                    )
                    for chunk_index, chunk in enumerate(chunks):
                        row = {
                            "xml_id": xml_id,
                            "model_name": self.modelname,
                            "chunk_index": chunk_index,
                            "source_path": str(source["source_path"]),
                            "tm_id": str(source["tm_id"]),
                            "language": language,
                            "document_text": chunk,
                            "input_hash": _input_hash(chunk),
                        }
                        if not stale_only:
                            jobs.append(_EmbeddingJob(len(jobs), self, row, table))
                            continue
                        stored_row = _select_stored_source(
                            cursor,
                            table,
                            xml_id,
                            self.modelname,
                            chunk_index,
                        )
                        current_source = (
                            row["input_hash"],
                            row["source_path"],
                            row["tm_id"],
                            row["language"],
                        )
                        if stored_row == current_source:
                            continue
                        jobs.append(_EmbeddingJob(len(jobs), self, row, table))

                embedded = _embed_documents(
                    jobs,
                    progressbar=progressbar,
                    progressbar_title="Embedding XML rows",
                )
                dimensions: dict[str, int] = {}
                for document in embedded:
                    dimension = len(document.embedding)
                    previous = dimensions.setdefault(document.job.table, dimension)
                    if previous != dimension:
                        raise ValueError(
                            f"Embedding model {self.modelname!r} returned vectors "
                            "with inconsistent dimensions"
                        )
                    _upsert_embedding(
                        cursor,
                        document.job.table,
                        {
                            **document.job.row,
                            "embedding": _vector_literal(document.embedding),
                        },
                    )

                for kind, table in EMBEDDING_TABLES.items():
                    _delete_missing_source_rows(
                        cursor, table, self.modelname, seen_ids[kind]
                    )
                    if table in dimensions:
                        _recreate_embedding_index(
                            cursor, table, self.modelname, dimensions[table]
                        )

        return len(embedded)

    def _embed(self, text: str) -> tuple[float, ...]:
        return self.provider.embed(text)


def update_embeddings(
    conninfo: str = "",
    progressbar: bool = True,
    /,
    *,
    inference_server_url: str,
    modelname: str,
    api_key: str,
    chunk_size: int = 500,
) -> int:
    """Compute missing or stale embeddings for one model from database XML."""

    return EmbeddingStore(inference_server_url, modelname, api_key).setup_store(
        conninfo, progressbar, stale_only=True, chunk_size=chunk_size
    )


def delete_embeddings(conninfo: str = "", /, *, modelname: str) -> int:
    """Delete one model's transcription and translation embeddings."""

    deleted = 0
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            _ensure_embedding_schema(cursor)
            for table in EMBEDDING_TABLES.values():
                _drop_embedding_index(cursor, table, modelname)
                cursor.execute(
                    sql.SQL("DELETE FROM {} WHERE model_name = %s").format(
                        sql.Identifier(table)
                    ),
                    (modelname,),
                )
                deleted += max(cursor.rowcount, 0)
    return deleted


def dump_embeddings(
    target: str | Path,
    conninfo: str = "",
    /,
    *,
    modelname: str,
    document_kind: str = "transcription",
) -> int:
    """Dump one model's embedding rows in PostgreSQL binary COPY format."""

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    table = _embedding_table(document_kind)
    columns = _embedding_columns_sql()

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            _ensure_embedding_schema(cursor)
            cursor.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE model_name = %s").format(
                    sql.Identifier(table)
                ),
                (modelname,),
            )
            row_count = int(_first_column(cursor.fetchone()))
            with target.open("wb") as output:
                with cursor.copy(
                    sql.SQL(
                        "COPY (SELECT {columns} FROM {table} "
                        "WHERE model_name = {modelname} "
                        "ORDER BY xml_id, chunk_index) "
                        "TO STDOUT WITH (FORMAT binary)"
                    ).format(
                        columns=columns,
                        table=sql.Identifier(table),
                        modelname=sql.Literal(modelname),
                    )
                ) as copy:
                    for chunk in copy:
                        output.write(chunk)
    return row_count


def import_embeddings(
    source: str | Path,
    conninfo: str = "",
    /,
    *,
    modelname: str,
    document_kind: str = "transcription",
) -> int:
    """Import one model's embedding rows from PostgreSQL binary COPY format."""

    source = Path(source)
    table = _embedding_table(document_kind)
    temporary_table = f"{table}_import"
    columns = _embedding_columns_sql()

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            _ensure_embedding_schema(cursor)
            cursor.execute(
                sql.SQL(
                    "CREATE TEMP TABLE {} "
                    "(LIKE {} INCLUDING DEFAULTS INCLUDING CONSTRAINTS) "
                    "ON COMMIT DROP"
                ).format(sql.Identifier(temporary_table), sql.Identifier(table))
            )
            with source.open("rb") as input_file:
                with cursor.copy(
                    sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT binary)").format(
                        sql.Identifier(temporary_table),
                        columns,
                    )
                ) as copy:
                    while True:
                        chunk = input_file.read(1024 * 1024)
                        if not chunk:
                            break
                        copy.write(chunk)

            imported_models = _imported_model_names(cursor, temporary_table)
            unexpected_models = [
                imported_model
                for imported_model in imported_models
                if imported_model != modelname
            ]
            if unexpected_models:
                raise ValueError(
                    "Imported embeddings contain model names other than "
                    f"{modelname!r}: {', '.join(unexpected_models)}"
                )

            row_count, dimensions = _imported_embedding_stats(cursor, temporary_table)
            _drop_embedding_index(cursor, table, modelname)
            cursor.execute(
                sql.SQL("DELETE FROM {} WHERE model_name = %s").format(
                    sql.Identifier(table)
                ),
                (modelname,),
            )
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {table} ({columns}) "
                    "SELECT {columns} FROM {temporary_table} "
                    "ORDER BY xml_id, chunk_index"
                ).format(
                    table=sql.Identifier(table),
                    columns=columns,
                    temporary_table=sql.Identifier(temporary_table),
                )
            )
            if dimensions is not None:
                _recreate_embedding_index(cursor, table, modelname, dimensions)
    return row_count


def retrieve_embedding(
    conninfo: str = "",
    /,
    *,
    modelname: str,
    document_path: str | Path,
    translation: bool = False,
) -> tuple[float, ...] | None:
    """Return an embedding selected by model, kind, and XML source path."""

    table = EMBEDDING_TABLES["translation" if translation else "transcription"]
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "SELECT embedding::text FROM {} "
                    "WHERE model_name = %s AND source_path = %s "
                    "ORDER BY xml_id, chunk_index LIMIT 1"
                ).format(sql.Identifier(table)),
                (modelname, _document_path(document_path)),
            )
            row = cursor.fetchone()
    return None if row is None else _parse_vector(_first_column(row))


def _xml_to_embedding_text(xml: str, document_kind: str) -> str:
    if document_kind == "translation":
        return translation_epidoc_xml_to_text(xml)
    return epidoc_xml_to_text(xml, **MAXIMUM_TRANSCRIPTION_OPTIONS)


def chunk_embedding_text(document_text: str, chunk_size: int = 500) -> tuple[str, ...]:
    """Split text into deterministic word chunks with a ten-percent overlap.

    Documents no longer than 150 percent of ``chunk_size`` remain untouched.
    Chunked text has whitespace normalized between words; unchunked text is
    returned exactly as supplied.
    """

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    words = document_text.split()
    if len(words) * 2 <= chunk_size * 3:
        return (document_text,)

    overlap = chunk_size // 10
    step = chunk_size - overlap
    chunks: list[str] = []
    start = 0
    while True:
        chunks.append(" ".join(words[start : start + chunk_size]))
        if start + chunk_size >= len(words):
            return tuple(chunks)
        start += step


def _embedding_table(document_kind: str) -> str:
    try:
        normalized_kind = EMBEDDING_KIND_ALIASES[document_kind]
    except KeyError as error:
        choices = ", ".join(EMBEDDING_KIND_ALIASES)
        raise ValueError(
            f"Unknown embedding document kind {document_kind!r}. "
            f"Expected one of: {choices}"
        ) from error
    return EMBEDDING_TABLES[normalized_kind]


def _embedding_columns_sql() -> sql.Composed:
    return sql.SQL(", ").join(
        sql.Identifier(column) for column in EMBEDDING_DUMP_COLUMNS
    )


def _select_xml_rows(
    cursor: Any, *, sample: int | None = None, seed: int = 0
) -> tuple[dict[str, Any], ...]:
    if sample is None:
        cursor.execute(
            f"""
SELECT transcription_id, source_path, tm_id, xml_content::text, type, language
FROM {TRANSCRIPTIONS_TABLE}
ORDER BY transcription_id
"""
        )
    else:
        cursor.execute(
            f"""
WITH sampled_records AS (
    SELECT tm_id
    FROM {TRANSCRIPTIONS_TABLE}
    GROUP BY tm_id
    HAVING bool_or(type = 'transcription')
       AND bool_or(type = 'translation')
    ORDER BY md5(tm_id::text || ':' || (%s)::text), tm_id
    LIMIT %s
)
SELECT transcription_id, source_path, tm_id, xml_content::text, type, language
FROM {TRANSCRIPTIONS_TABLE}
JOIN sampled_records USING (tm_id)
ORDER BY transcription_id
""",
            (seed, sample),
        )
    keys = (
        "transcription_id",
        "source_path",
        "tm_id",
        "xml_content",
        "type",
        "language",
    )
    return tuple(
        row if isinstance(row, dict) else dict(zip(keys, row, strict=True))
        for row in cursor.fetchall()
    )


def _ensure_embedding_schema(cursor: Any) -> None:
    try:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except (psycopg.errors.FeatureNotSupported, psycopg.errors.UndefinedFile) as error:
        if _is_missing_vector_extension_error(error):
            raise PgvectorUnavailableError(PGVECTOR_UNAVAILABLE_MESSAGE) from error
        raise
    for table in EMBEDDING_TABLES.values():
        cursor.execute(
            f"""
CREATE TABLE IF NOT EXISTS {table} (
    xml_id bigint NOT NULL,
    model_name text NOT NULL,
    chunk_index integer NOT NULL DEFAULT 0,
    source_path text NOT NULL,
    tm_id text NOT NULL,
    language text,
    document_text text NOT NULL,
    input_hash text NOT NULL,
    embedding vector NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (xml_id, model_name, chunk_index)
)
"""
        )
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
            "chunk_index integer NOT NULL DEFAULT 0"
        )
        cursor.execute(
            f"""
DO $$
DECLARE current_primary_key text;
BEGIN
    SELECT constraint_name INTO current_primary_key
    FROM information_schema.table_constraints
    WHERE table_schema = current_schema()
      AND table_name = '{table}'
      AND constraint_type = 'PRIMARY KEY';

    IF current_primary_key IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM information_schema.key_column_usage
        WHERE table_schema = current_schema()
          AND table_name = '{table}'
          AND constraint_name = current_primary_key
          AND column_name = 'chunk_index'
    ) THEN
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I',
                       '{table}', current_primary_key);
        ALTER TABLE {table}
            ADD PRIMARY KEY (xml_id, model_name, chunk_index);
    END IF;
END $$
"""
        )


def _is_missing_vector_extension_error(error: psycopg.Error) -> bool:
    message = str(error)
    return (
        'extension "vector" is not available' in message or "vector.control" in message
    )


def _select_stored_source(
    cursor: Any, table: str, xml_id: int, modelname: str, chunk_index: int
) -> tuple[str, str, str, str | None] | None:
    cursor.execute(
        sql.SQL(
            "SELECT input_hash, source_path, tm_id, language FROM {} "
            "WHERE xml_id = %s AND model_name = %s AND chunk_index = %s"
        ).format(sql.Identifier(table)),
        (xml_id, modelname, chunk_index),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return (
        str(_row_value(row, "input_hash", 0)),
        str(_row_value(row, "source_path", 1)),
        str(_row_value(row, "tm_id", 2)),
        _row_value(row, "language", 3),
    )


def _upsert_embedding(cursor: Any, table: str, row: dict[str, Any]) -> None:
    cursor.execute(
        sql.SQL(
            """
INSERT INTO {} (
    xml_id, model_name, chunk_index, source_path, tm_id, language,
    document_text, input_hash, embedding
) VALUES (
    %(xml_id)s, %(model_name)s, %(chunk_index)s, %(source_path)s, %(tm_id)s, %(language)s,
    %(document_text)s, %(input_hash)s, %(embedding)s::vector
)
ON CONFLICT (xml_id, model_name, chunk_index) DO UPDATE SET
    source_path = EXCLUDED.source_path,
    tm_id = EXCLUDED.tm_id,
    language = EXCLUDED.language,
    document_text = EXCLUDED.document_text,
    input_hash = EXCLUDED.input_hash,
    embedding = EXCLUDED.embedding,
    updated_at = now()
"""
        ).format(sql.Identifier(table)),
        row,
    )


def _delete_missing_source_rows(
    cursor: Any, table: str, modelname: str, seen_ids: set[int]
) -> None:
    cursor.execute(
        sql.SQL(
            "DELETE FROM {} WHERE model_name = %s AND NOT (xml_id = ANY(%s))"
        ).format(sql.Identifier(table)),
        (modelname, list(sorted(seen_ids))),
    )


def _delete_extra_chunks(
    cursor: Any, table: str, xml_id: int, modelname: str, chunk_count: int
) -> None:
    cursor.execute(
        sql.SQL(
            "DELETE FROM {} WHERE xml_id = %s AND model_name = %s AND chunk_index >= %s"
        ).format(sql.Identifier(table)),
        (xml_id, modelname, chunk_count),
    )


def _embedding_index_name(table: str, modelname: str) -> str:
    digest = hashlib.sha256(modelname.encode("utf-8")).hexdigest()[:12]
    return f"{table}_{digest}_hnsw_idx"


def _drop_embedding_index(cursor: Any, table: str, modelname: str) -> None:
    cursor.execute(
        sql.SQL("DROP INDEX IF EXISTS {}").format(
            sql.Identifier(_embedding_index_name(table, modelname))
        )
    )


def _recreate_embedding_index(
    cursor: Any, table: str, modelname: str, dimensions: int
) -> None:
    _drop_embedding_index(cursor, table, modelname)
    if dimensions <= HNSW_VECTOR_MAX_DIMENSIONS:
        index_type = "vector"
        operator_class = "vector_cosine_ops"
    elif dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS:
        index_type = "halfvec"
        operator_class = "halfvec_cosine_ops"
    else:
        return
    cursor.execute(
        sql.SQL(
            "CREATE INDEX {} ON {} USING hnsw "
            "((embedding::{}({})) {}) WHERE model_name = {}"
        ).format(
            sql.Identifier(_embedding_index_name(table, modelname)),
            sql.Identifier(table),
            sql.SQL(index_type),
            sql.Literal(dimensions),
            sql.SQL(operator_class),
            sql.Literal(modelname),
        )
    )


def _imported_model_names(cursor: Any, temporary_table: str) -> list[str]:
    cursor.execute(
        sql.SQL(
            "SELECT model_name FROM {} GROUP BY model_name ORDER BY model_name"
        ).format(sql.Identifier(temporary_table))
    )
    return [str(_first_column(row)) for row in cursor.fetchall()]


def _imported_embedding_stats(
    cursor: Any, temporary_table: str
) -> tuple[int, int | None]:
    cursor.execute(
        sql.SQL(
            "SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding)) "
            "FROM {}"
        ).format(sql.Identifier(temporary_table))
    )
    row = cursor.fetchone()
    row_count = int(_row_value(row, "count", 0))
    minimum_dimensions = _row_value(row, "min", 1)
    maximum_dimensions = _row_value(row, "max", 2)
    if row_count == 0:
        return 0, None
    if minimum_dimensions != maximum_dimensions:
        raise ValueError(
            "Imported embeddings contain vectors with inconsistent dimensions"
        )
    return row_count, int(minimum_dimensions)


def _embed_documents(
    jobs: Sequence[_EmbeddingJob], *, progressbar: bool, progressbar_title: str
) -> list[_EmbeddedDocument]:
    progress = (
        tqdm(total=len(jobs), unit="request", desc=progressbar_title)
        if progressbar
        else None
    )
    completed: list[_EmbeddedDocument] = []
    skipped: list[_SkippedEmbeddingDocument] = []
    try:
        for job in jobs:
            result = _embed_document(job, progress)
            (
                skipped if isinstance(result, _SkippedEmbeddingDocument) else completed
            ).append(result)
    finally:
        if progress is not None:
            progress.close()
    for item in skipped:
        print(item.message, flush=True)
    return completed


def _embed_document(
    job: _EmbeddingJob, progress: Any | None
) -> _EmbeddedDocument | _SkippedEmbeddingDocument:
    try:
        embedding = job.store._embed(job.row["document_text"])
    except Exception as error:
        if not _is_skippable_embedding_error(error):
            raise
        result: _EmbeddedDocument | _SkippedEmbeddingDocument = (
            _SkippedEmbeddingDocument(job, _skipped_embedding_message(job, error))
        )
    else:
        result = _EmbeddedDocument(job, embedding)
    finally:
        if progress is not None:
            progress.update(1)
    return result


def _is_skippable_embedding_error(error: BaseException) -> bool:
    message = _embedding_error_message(error).lower()
    return (
        "maximum context length" in message
        and ("input_tokens" in message or "input token" in message)
        and ("prompt contains" in message or "requested" in message)
    )


def _skipped_embedding_message(job: _EmbeddingJob, error: BaseException) -> str:
    return (
        "Skipping embedding XML row after context-length validation error: "
        f"xml_id={job.row['xml_id']} source_path={job.row['source_path']} "
        f"model={job.store.modelname}: {_embedding_error_message(error)}"
    )


def _embedding_error_message(error: BaseException) -> str:
    message = str(error)
    if isinstance(error, requests.HTTPError) and error.response is not None:
        response_message = _response_error_message(error.response)
        if response_message:
            return (
                f"{message}: {response_message}"
                if message and response_message not in message
                else response_message
            )
    return message


def _response_error_message(response: Any) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error_payload = payload.get("error", payload)
        if isinstance(error_payload, dict):
            parts = [
                str(error_payload[key])
                for key in ("message", "type", "param", "code")
                if error_payload.get(key) is not None
            ]
            return " ".join(parts) or None
        return str(error_payload)
    text = getattr(response, "text", None)
    return text.strip() if isinstance(text, str) and text.strip() else None


def _input_hash(document_text: str) -> str:
    return hashlib.sha256(document_text.encode("utf-8")).hexdigest()


def _document_path(path: str | Path) -> str:
    return Path(path).as_posix()


def _vector_literal(embedding: tuple[float, ...]) -> str:
    return "[" + ",".join(format(value, ".17g") for value in embedding) + "]"


def _parse_vector(value: Any) -> tuple[float, ...]:
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("[") or not text.endswith("]"):
            raise ValueError(f"Could not parse vector value: {value!r}")
        return tuple(float(item) for item in text[1:-1].split(",") if item)
    if isinstance(value, (list, tuple)):
        return tuple(float(item) for item in value)
    raise TypeError(f"Unsupported vector value: {value!r}")


def _first_column(row: Any) -> Any:
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


def _row_value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, dict) else row[index]
