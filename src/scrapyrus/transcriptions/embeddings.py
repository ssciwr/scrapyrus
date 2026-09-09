from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from langchain_core.embeddings import Embeddings
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
from scrapyrus.semantics import publish_semantics
from scrapyrus.transcriptions.embedding_clients import (
    SUPPORTED_EMBEDDING_PROVIDERS,
    build_embedding_client,
    effective_provider_options,
    infer_embedding_provider,
)
from scrapyrus.transcriptions.semantics import (
    EMBEDDING_TABLE_METADATA_SEMANTICS,
    KEYWORD_EMBEDDINGS_SEMANTICS,
    TRANSCRIPTION_EMBEDDINGS_SEMANTICS,
    TRANSLATION_EMBEDDINGS_SEMANTICS,
)


TRANSCRIPTION_EMBEDDINGS_TABLE = "transcription_embeddings"
TRANSLATION_EMBEDDINGS_TABLE = "translation_embeddings"
KEYWORD_EMBEDDINGS_TABLE = "keyword_embeddings"
KEYWORDS_TABLE_NAME = "keywords"
EMBEDDING_TABLE_METADATA_TABLE = "embedding_table_metadata"
EMBEDDING_TABLES = {
    "transcriptions": TRANSCRIPTION_EMBEDDINGS_TABLE,
    "translations": TRANSLATION_EMBEDDINGS_TABLE,
}
EMBEDDING_SOURCE_TYPES = {
    "transcriptions": "transcription",
    "translations": "translation",
}
EMBEDDING_DUMP_COLUMNS = (
    "chunk_id",
    "xml_id",
    "chunk_index",
    "source_path",
    "tm_id",
    "language",
    "document_text",
    "input_hash",
    "embedding",
    "updated_at",
)
KEYWORD_EMBEDDING_DUMP_COLUMNS = (
    "keyword",
    "embedding",
    "updated_at",
)
EXPORT_EMBEDDING_TABLES = {
    **EMBEDDING_TABLES,
    "keywords": KEYWORD_EMBEDDINGS_TABLE,
}
EMBEDDING_DUMP_COLUMNS_BY_KIND = {
    "transcriptions": EMBEDDING_DUMP_COLUMNS,
    "translations": EMBEDDING_DUMP_COLUMNS,
    "keywords": KEYWORD_EMBEDDING_DUMP_COLUMNS,
}
EMBEDDING_DUMP_ORDER_BY = {
    "transcriptions": ("xml_id", "chunk_index"),
    "translations": ("xml_id", "chunk_index"),
    "keywords": ("keyword",),
}

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
EMBEDDING_CONTRACT_VERSION = 1


def initialize_llm_provider(
    inference_server_url: str, modelname: str, api_key: str
) -> Embeddings:
    """Return the standard embedding client for legacy direct callers."""

    provider = infer_embedding_provider(inference_server_url)
    return build_embedding_client(
        provider=provider,
        model_name=modelname,
        api_key=api_key,
        inference_server_url=inference_server_url,
        provider_options=effective_provider_options(provider),
    )


class PgvectorUnavailableError(RuntimeError):
    """Raised when the PostgreSQL server does not provide pgvector."""


class TranscriptionsUnavailableError(RuntimeError):
    """Raised when transcription XML has not been ingested into PostgreSQL."""


class DocumentEmbeddingsUnavailableError(RuntimeError):
    """Raised when a requested document embedding table does not exist."""


class EmbeddingModelMismatchError(ValueError):
    """Raised when an operation requests a table's non-configured model."""


@dataclass(frozen=True)
class EmbeddingTableMetadata:
    """The unique embedding configuration associated with one data table."""

    table_name: str
    model_name: str
    embedding_size: int | None
    provider: str | None = None
    provider_options: dict[str, Any] | None = None
    endpoint_profile: str | None = None
    contract_version: int = EMBEDDING_CONTRACT_VERSION

    def specification_dict(self) -> dict[str, Any]:
        """Return the complete, non-secret specification for a dump manifest."""

        return {
            "table_name": self.table_name,
            "model_name": self.model_name,
            "embedding_size": self.embedding_size,
            "provider": self.provider,
            "provider_options": self.provider_options or {},
            "endpoint_profile": self.endpoint_profile,
            "contract_version": self.contract_version,
        }


@dataclass(frozen=True)
class DocumentMatch:
    """One source document nearest to an embedded free-text query."""

    source_path: str
    tm_id: str
    language: str | None
    document_text: str
    similarity: float


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

    def __init__(
        self,
        inference_server_url: str,
        modelname: str,
        api_key: str,
        *,
        provider: str | None = None,
        provider_options: dict[str, Any] | None = None,
        endpoint_profile: str | None = None,
    ) -> None:
        self.inference_server_url = inference_server_url
        self.modelname = modelname
        self.provider_name = provider or infer_embedding_provider(inference_server_url)
        self.provider_options = effective_provider_options(
            self.provider_name, provider_options
        )
        self.endpoint_profile = endpoint_profile
        if self.provider_name == "vllm" and self.endpoint_profile is None:
            self.endpoint_profile = os.getenv(
                "SCRAPYRUS_EMBEDDING_ENDPOINT_PROFILE", "vllm"
            )
        self.provider: Embeddings = (
            initialize_llm_provider(inference_server_url, modelname, api_key)
            if provider is None and provider_options is None
            else build_embedding_client(
                provider=self.provider_name,
                model_name=modelname,
                api_key=api_key,
                inference_server_url=inference_server_url,
                provider_options=self.provider_options,
            )
        )

    def _metadata(self, table: str) -> EmbeddingTableMetadata:
        return EmbeddingTableMetadata(
            table_name=table,
            model_name=self.modelname,
            embedding_size=None,
            provider=self.provider_name,
            provider_options=self.provider_options,
            endpoint_profile=self.endpoint_profile,
        )

    def setup_store(
        self,
        conninfo: str = "",
        progressbar: bool = True,
        /,
        *,
        document_kind: str,
        stale_only: bool = False,
        sample: int | None = None,
        seed: int = 0,
        chunk_size: int = 500,
        force: bool = False,
    ) -> int:
        """Embed one kind of transcription XML row in PostgreSQL.

        Transcriptions always use the maximum text variant. Translations use
        their complete plain-text rendering. Rows are stored in separate tables.
        When ``stale_only`` is true, unchanged rows are not sent to the model.
        When ``sample`` is set, deterministically select that many ``tm_id``
        records using ``seed`` from those which have both a transcription and
        a translation, and embed all XML rows belonging to those records.
        Text size and overlap are measured in whitespace-delimited words.
        """

        if document_kind not in EMBEDDING_TABLES:
            raise ValueError(f"Unknown embedding document kind {document_kind!r}")
        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")

        jobs: list[_EmbeddingJob] = []
        seen_ids: set[int] = set()
        table = EMBEDDING_TABLES[document_kind]
        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                _ensure_embedding_schema(cursor)
                metadata = _associate_embedding_specification(
                    cursor, self._metadata(table), force=force
                )
                try:
                    sources = _select_xml_rows(
                        cursor,
                        document_kind=document_kind,
                        sample=sample,
                        seed=seed,
                    )
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
                    xml_id = int(source["transcription_id"])
                    document_text = _xml_to_embedding_text(
                        str(source["xml_content"]), document_kind
                    )
                    if not document_text.strip():
                        continue
                    seen_ids.add(xml_id)
                    chunks = chunk_embedding_text(document_text, chunk_size)
                    _delete_extra_chunks(cursor, table, xml_id, len(chunks))
                    language = (
                        transcription_language(str(source["xml_content"]))
                        if document_kind == "transcriptions"
                        else source["language"]
                    )
                    for chunk_index, chunk in enumerate(chunks):
                        row = {
                            "chunk_id": f"{document_kind}:{xml_id}:{chunk_index}",
                            "xml_id": xml_id,
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
                dimensions = metadata.embedding_size
                for document in embedded:
                    dimension = len(document.embedding)
                    if dimensions is None:
                        dimensions = dimension
                    elif dimensions != dimension:
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

                _delete_missing_source_rows(cursor, table, seen_ids)
                if dimensions is None:
                    dimensions = len(
                        self.provider.embed_query(
                            "Scrapyrus empty-corpus dimension readiness probe"
                        )
                    )
                _set_embedding_size(cursor, table, self.modelname, dimensions)
                _recreate_embedding_index(cursor, table, dimensions)

        return len(embedded)

    def _embed(self, text: str) -> tuple[float, ...]:
        result = self.provider.embed_documents([text])[0]
        return tuple(float(value) for value in result)


def update_embeddings(
    conninfo: str = "",
    progressbar: bool = True,
    /,
    *,
    document_kind: str,
    inference_server_url: str,
    modelname: str,
    api_key: str,
    chunk_size: int = 500,
    force: bool = False,
) -> int:
    """Compute missing or stale embeddings for one model from database XML."""

    return EmbeddingStore(inference_server_url, modelname, api_key).setup_store(
        conninfo,
        progressbar,
        document_kind=document_kind,
        stale_only=True,
        chunk_size=chunk_size,
        force=force,
    )


def delete_embeddings(
    conninfo: str = "", /, *, modelname: str, document_kind: str
) -> int:
    """Delete one model's embeddings for one document kind."""

    table = _embedding_table(document_kind)
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            _ensure_embedding_schema(cursor)
            _require_embedding_model(cursor, table, modelname)
            _drop_embedding_index(cursor, table)
            cursor.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(table)))
            deleted = max(cursor.rowcount, 0)
            return deleted


def dump_embeddings(
    target: str | Path,
    conninfo: str = "",
    /,
    *,
    modelname: str,
    document_kind: str,
) -> int:
    """Dump one model's embedding rows in PostgreSQL binary COPY format."""

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    table = _embedding_table(document_kind)
    columns = _embedding_columns_sql(document_kind)
    ordering = _embedding_ordering_sql(document_kind)

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            _ensure_embedding_schema(cursor)
            metadata = _require_embedding_model(cursor, table, modelname)
            cursor.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            )
            row_count = int(_first_column(cursor.fetchone()))
            with target.open("wb") as output:
                with cursor.copy(
                    sql.SQL(
                        "COPY (SELECT {columns} FROM {table} ORDER BY {ordering}) "
                        "TO STDOUT WITH (FORMAT binary)"
                    ).format(
                        columns=columns,
                        table=sql.Identifier(table),
                        ordering=ordering,
                    )
                ) as copy:
                    for chunk in copy:
                        output.write(chunk)
    manifest = {
        "format": "scrapyrus-embedding-dump-v1",
        "document_kind": document_kind,
        "columns": list(EMBEDDING_DUMP_COLUMNS_BY_KIND[document_kind]),
        "row_count": row_count,
        "embedding_specification": metadata.specification_dict(),
    }
    _dump_manifest_path(target).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return row_count


def import_embeddings(
    source: str | Path,
    conninfo: str = "",
    /,
    *,
    modelname: str,
    document_kind: str,
    force: bool = False,
) -> int:
    """Import one model's embedding rows from PostgreSQL binary COPY format."""

    source = Path(source)
    table = _embedding_table(document_kind)
    manifest = _load_dump_manifest(source, document_kind, modelname)
    specification = _metadata_from_manifest(manifest["embedding_specification"])
    temporary_table = f"{table}_import"
    columns = _embedding_columns_sql(document_kind)
    ordering = _embedding_ordering_sql(document_kind)

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            _ensure_embedding_schema(cursor)
            metadata = _associate_embedding_specification(
                cursor, specification, force=force
            )
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

            row_count, dimensions = _imported_embedding_stats(cursor, temporary_table)
            if row_count != manifest["row_count"]:
                raise ValueError(
                    f"Embedding dump manifest declares {manifest['row_count']} rows, "
                    f"but the binary data contains {row_count}"
                )
            if (
                dimensions is not None
                and metadata.embedding_size is not None
                and dimensions != metadata.embedding_size
            ):
                raise ValueError(
                    f"Imported embeddings have {dimensions} dimensions, but "
                    f"{table!r} is configured for {metadata.embedding_size}"
                )
            if dimensions is not None and dimensions != specification.embedding_size:
                raise ValueError(
                    f"Embedding dump declares {specification.embedding_size} dimensions, "
                    f"but its vectors have {dimensions}"
                )
            _validate_imported_sources(
                cursor, temporary_table, document_kind=document_kind
            )
            _drop_embedding_index(cursor, table)
            cursor.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(table)))
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {table} ({columns}) "
                    "SELECT {columns} FROM {temporary_table} "
                    "ORDER BY {ordering}"
                ).format(
                    table=sql.Identifier(table),
                    columns=columns,
                    temporary_table=sql.Identifier(temporary_table),
                    ordering=ordering,
                )
            )
            published_dimensions = dimensions or specification.embedding_size
            _set_embedding_size(cursor, table, modelname, published_dimensions)
            _recreate_embedding_index(cursor, table, published_dimensions)
    return row_count


def _dump_manifest_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.manifest.json")


def _load_dump_manifest(
    source: Path, document_kind: str, modelname: str
) -> dict[str, Any]:
    path = _dump_manifest_path(source)
    if not path.is_file():
        raise ValueError(f"Embedding dump manifest is missing: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid embedding dump manifest: {path}") from error
    if manifest.get("format") != "scrapyrus-embedding-dump-v1":
        raise ValueError("Unsupported embedding dump manifest format")
    if manifest.get("document_kind") != document_kind:
        raise ValueError(
            f"Embedding dump contains {manifest.get('document_kind')!r}, not "
            f"{document_kind!r}"
        )
    expected_columns = list(EMBEDDING_DUMP_COLUMNS_BY_KIND[document_kind])
    if manifest.get("columns") != expected_columns:
        raise ValueError("Embedding dump columns do not match the table contract")
    specification = manifest.get("embedding_specification")
    if not isinstance(specification, dict):
        raise ValueError("Embedding dump has no embedding specification")
    if specification.get("model_name") != modelname:
        raise EmbeddingModelMismatchError(
            f"Embedding dump uses model {specification.get('model_name')!r}, not "
            f"{modelname!r}"
        )
    if specification.get("table_name") != _embedding_table(document_kind):
        raise ValueError("Embedding dump specification names the wrong table")
    if not isinstance(manifest.get("row_count"), int) or manifest["row_count"] < 0:
        raise ValueError("Embedding dump manifest has an invalid row count")
    return manifest


def _metadata_from_manifest(value: dict[str, Any]) -> EmbeddingTableMetadata:
    required = {
        "table_name",
        "model_name",
        "embedding_size",
        "provider",
        "provider_options",
        "endpoint_profile",
        "contract_version",
    }
    if set(value) != required:
        raise ValueError("Embedding dump specification fields are incomplete")
    size = value["embedding_size"]
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError("Embedding dump has an invalid embedding size")
    options = value["provider_options"]
    if not isinstance(options, dict):
        raise ValueError("Embedding dump has invalid provider options")
    provider = str(value["provider"])
    if effective_provider_options(provider, options) != options:
        raise ValueError(
            "Embedding dump must record all effective provider option values"
        )
    version = value["contract_version"]
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version != EMBEDDING_CONTRACT_VERSION
    ):
        raise ValueError(
            f"Embedding dump uses contract version {version!r}; expected "
            f"{EMBEDDING_CONTRACT_VERSION}"
        )
    return EmbeddingTableMetadata(
        table_name=str(value["table_name"]),
        model_name=str(value["model_name"]),
        embedding_size=size,
        provider=provider,
        provider_options=options,
        endpoint_profile=(
            None
            if value["endpoint_profile"] is None
            else str(value["endpoint_profile"])
        ),
        contract_version=version,
    )


def _validate_imported_sources(
    cursor: Any, temporary_table: str, *, document_kind: str
) -> None:
    if document_kind == "keywords":
        cursor.execute(
            sql.SQL(
                "SELECT count(*) FROM {} AS imported WHERE NOT EXISTS ("
                f"SELECT 1 FROM {KEYWORDS_TABLE_NAME} AS source WHERE "
                "CASE WHEN source.qualifier IS NULL THEN source.keyword ELSE "
                "source.keyword || ', ' || source.qualifier END = imported.keyword)"
            ).format(sql.Identifier(temporary_table))
        )
    else:
        cursor.execute(
            sql.SQL(
                "SELECT count(*) FROM {} AS imported WHERE NOT EXISTS ("
                f"SELECT 1 FROM {TRANSCRIPTIONS_TABLE} AS source "
                "WHERE source.transcription_id = imported.xml_id AND source.type = %s)"
            ).format(sql.Identifier(temporary_table)),
            (EMBEDDING_SOURCE_TYPES[document_kind],),
        )
    unmatched = int(_first_column(cursor.fetchone()))
    if unmatched:
        raise ValueError(
            f"Embedding dump contains {unmatched} rows without matching "
            f"{document_kind} source data"
        )


def find_similar_documents(
    query: str,
    conninfo: str = "",
    /,
    *,
    document_kind: str,
    inference_server_url: str,
    modelname: str,
    api_key: str,
    top_k: int = 10,
) -> tuple[DocumentMatch, ...]:
    """Embed *query* and return the nearest stored source documents.

    Chunked documents occur only once in the result, using their closest chunk
    as the displayed text and as the document's similarity score.
    """

    if not query.strip():
        raise ValueError("query must not be blank")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    if document_kind not in EMBEDDING_TABLES:
        choices = ", ".join(EMBEDDING_TABLES)
        raise ValueError(
            f"Cannot query embedding document kind {document_kind!r}. "
            f"Expected one of: {choices}"
        )
    table = EMBEDDING_TABLES[document_kind]

    query_store = EmbeddingStore(inference_server_url, modelname, api_key)
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            metadata = _require_embedding_model(cursor, table, modelname)
            count, minimum_dimensions, maximum_dimensions = (
                _stored_document_embedding_stats(cursor, table)
            )
            if count == 0:
                raise ValueError(
                    f"No {document_kind} embeddings found for model {modelname!r}. "
                    f"Run 'scrapyrus embeddings ingest {document_kind}' with the "
                    "same model first."
                )
            if minimum_dimensions != maximum_dimensions:
                raise ValueError(
                    f"Stored {document_kind} embeddings for model {modelname!r} "
                    "have inconsistent dimensions"
                )
            if metadata.embedding_size != minimum_dimensions:
                raise ValueError(
                    f"Stored metadata says {document_kind} embeddings have "
                    f"{metadata.embedding_size} dimensions, but the vectors have "
                    f"{minimum_dimensions}"
                )

            _require_compatible_specification(
                cursor, table, query_store._metadata(table)
            )
            embedding = tuple(query_store.provider.embed_query(query))
            if len(embedding) != minimum_dimensions:
                raise ValueError(
                    f"Query embedding has {len(embedding)} dimensions, but stored "
                    f"{document_kind} embeddings for model {modelname!r} have "
                    f"{minimum_dimensions}"
                )
            cursor.execute(
                _nearest_documents_query(table, minimum_dimensions),
                {
                    "embedding": _vector_literal(embedding),
                    "top_k": top_k,
                },
            )
            return tuple(
                DocumentMatch(
                    source_path=str(_row_value(row, "source_path", 0)),
                    tm_id=str(_row_value(row, "tm_id", 1)),
                    language=(
                        None
                        if _row_value(row, "language", 2) is None
                        else str(_row_value(row, "language", 2))
                    ),
                    document_text=str(_row_value(row, "document_text", 3)),
                    similarity=float(_row_value(row, "similarity", 4)),
                )
                for row in cursor.fetchall()
            )


def _xml_to_embedding_text(xml: str, document_kind: str) -> str:
    if document_kind == "translations":
        return translation_epidoc_xml_to_text(xml)
    return epidoc_xml_to_text(xml, **MAXIMUM_TRANSCRIPTION_OPTIONS)


def chunk_embedding_text(document_text: str, chunk_size: int = 500) -> tuple[str, ...]:
    """Split text into deterministic word chunks with a ten-percent overlap.

    Documents no longer than ``chunk_size`` remain untouched. Chunked text has
    whitespace normalized between words; unchunked text is returned exactly as
    supplied.
    """

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    words = document_text.split()
    if len(words) <= chunk_size:
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
    normalized_kind = _embedding_kind(document_kind)
    return EXPORT_EMBEDDING_TABLES[normalized_kind]


def _embedding_kind(document_kind: str) -> str:
    if document_kind not in EXPORT_EMBEDDING_TABLES:
        choices = ", ".join(EXPORT_EMBEDDING_TABLES)
        raise ValueError(
            f"Unknown embedding document kind {document_kind!r}. "
            f"Expected one of: {choices}"
        )
    return document_kind


def _embedding_columns_sql(document_kind: str) -> sql.Composed:
    columns = EMBEDDING_DUMP_COLUMNS_BY_KIND[_embedding_kind(document_kind)]
    return sql.SQL(", ").join(sql.Identifier(column) for column in columns)


def _embedding_ordering_sql(document_kind: str) -> sql.Composed:
    ordering = EMBEDDING_DUMP_ORDER_BY[_embedding_kind(document_kind)]
    return sql.SQL(", ").join(sql.Identifier(column) for column in ordering)


def _stored_document_embedding_stats(cursor: Any, table: str) -> tuple[int, int, int]:
    try:
        cursor.execute(
            sql.SQL(
                "SELECT count(*), min(vector_dims(embedding)), "
                "max(vector_dims(embedding)) FROM {}"
            ).format(sql.Identifier(table)),
        )
    except psycopg.errors.UndefinedTable as error:
        document_kind = (
            "transcriptions"
            if table == TRANSCRIPTION_EMBEDDINGS_TABLE
            else "translations"
        )
        raise DocumentEmbeddingsUnavailableError(
            f"PostgreSQL table {table!r} does not exist. Run "
            f"'scrapyrus embeddings ingest {document_kind}' against this "
            "database first."
        ) from error
    row = cursor.fetchone()
    count = int(_row_value(row, "count", 0))
    if count == 0:
        return 0, 0, 0
    return (
        count,
        int(_row_value(row, "min", 1)),
        int(_row_value(row, "max", 2)),
    )


def _nearest_documents_query(table: str, dimensions: int) -> sql.Composed:
    if dimensions <= HNSW_VECTOR_MAX_DIMENSIONS:
        stored = sql.Identifier("embedding")
        query_type = "vector"
    elif dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS:
        stored = sql.Identifier("search_embedding")
        query_type = "halfvec"
    else:
        stored = sql.Identifier("embedding")
        query_type = "vector"

    cast = sql.SQL("{}({})").format(sql.SQL(query_type), sql.Literal(dimensions))
    query = sql.SQL("{}::{}").format(sql.Placeholder("embedding"), cast)
    distance = sql.SQL("{} <=> {}").format(stored, query)
    return sql.SQL(
        "WITH ranked_chunks AS ("
        "SELECT xml_id, source_path, tm_id, language, document_text, chunk_index, "
        "1 - ({distance}) AS similarity, "
        "row_number() OVER (PARTITION BY xml_id ORDER BY {distance}, chunk_index) "
        "AS chunk_rank FROM {table}"
        ") SELECT source_path, tm_id, language, document_text, similarity "
        "FROM ranked_chunks WHERE chunk_rank = 1 "
        "ORDER BY similarity DESC, source_path, tm_id, xml_id LIMIT {top_k}"
    ).format(
        distance=distance,
        table=sql.Identifier(table),
        top_k=sql.Placeholder("top_k"),
    )


def _select_xml_rows(
    cursor: Any,
    *,
    document_kind: str,
    sample: int | None = None,
    seed: int = 0,
) -> tuple[dict[str, Any], ...]:
    if sample is None:
        cursor.execute(
            f"""
SELECT transcription_id, source_path, tm_id, xml_content::text, type, language
FROM {TRANSCRIPTIONS_TABLE}
WHERE type = %s
ORDER BY transcription_id
""",
            (EMBEDDING_SOURCE_TYPES[document_kind],),
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
WHERE type = %s
ORDER BY transcription_id
""",
            (seed, sample, EMBEDDING_SOURCE_TYPES[document_kind]),
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
    embedding_table_names = ", ".join(
        repr(table) for table in EXPORT_EMBEDDING_TABLES.values()
    )
    embedding_providers = ", ".join(
        repr(provider) for provider in sorted(SUPPORTED_EMBEDDING_PROVIDERS)
    )
    cursor.execute(
        f"""
CREATE TABLE IF NOT EXISTS {EMBEDDING_TABLE_METADATA_TABLE} (
    table_name text PRIMARY KEY,
    model_name text NOT NULL,
    embedding_size integer,
    provider text,
    provider_options jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    endpoint_profile text,
    contract_version integer NOT NULL DEFAULT {EMBEDDING_CONTRACT_VERSION},
    CHECK (table_name IN ({embedding_table_names})),
    CHECK (embedding_size IS NULL OR embedding_size > 0),
    CHECK (provider IS NULL OR provider IN ({embedding_providers}))
)
"""
    )
    cursor.execute(
        f"ALTER TABLE {EMBEDDING_TABLE_METADATA_TABLE} "
        "ADD COLUMN IF NOT EXISTS provider text, "
        "ADD COLUMN IF NOT EXISTS provider_options jsonb NOT NULL DEFAULT '{}'::jsonb, "
        "ADD COLUMN IF NOT EXISTS endpoint_profile text, "
        f"ADD COLUMN IF NOT EXISTS contract_version integer NOT NULL DEFAULT {EMBEDDING_CONTRACT_VERSION}"
    )
    for table in EMBEDDING_TABLES.values():
        corpus = (
            "transcriptions"
            if table == TRANSCRIPTION_EMBEDDINGS_TABLE
            else "translations"
        )
        cursor.execute(
            f"""
CREATE TABLE IF NOT EXISTS {table} (
    chunk_id text NOT NULL,
    xml_id bigint NOT NULL,
    chunk_index integer NOT NULL DEFAULT 0,
    source_path text NOT NULL,
    tm_id text NOT NULL,
    language text,
    document_text text NOT NULL,
    input_hash text NOT NULL,
    embedding vector NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (xml_id, chunk_index),
    UNIQUE (chunk_id)
)
"""
        )
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS chunk_id text")
        cursor.execute(
            f"UPDATE {table} SET chunk_id = %s || ':' || xml_id || ':' || chunk_index "
            "WHERE chunk_id IS NULL",
            (corpus,),
        )
        cursor.execute(f"ALTER TABLE {table} ALTER COLUMN chunk_id SET NOT NULL")
        cursor.execute(
            sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON {} (chunk_id)").format(
                sql.Identifier(f"{table}_chunk_id_key"), sql.Identifier(table)
            )
        )
    cursor.execute(
        f"""
CREATE TABLE IF NOT EXISTS {KEYWORD_EMBEDDINGS_TABLE} (
    keyword text NOT NULL,
    embedding vector NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (keyword)
)
"""
    )
    publish_semantics(
        cursor,
        (
            EMBEDDING_TABLE_METADATA_SEMANTICS,
            TRANSCRIPTION_EMBEDDINGS_SEMANTICS,
            TRANSLATION_EMBEDDINGS_SEMANTICS,
            KEYWORD_EMBEDDINGS_SEMANTICS,
        ),
        component="embeddings",
    )


def embedding_table_metadata(cursor: Any, table: str) -> EmbeddingTableMetadata | None:
    """Return the model configuration associated with an embeddings table."""

    if table not in EXPORT_EMBEDDING_TABLES.values():
        raise ValueError(f"Unknown embeddings table {table!r}")
    cursor.execute(
        f"SELECT table_name, model_name, embedding_size, provider, "
        "provider_options, endpoint_profile, contract_version "
        f"FROM {EMBEDDING_TABLE_METADATA_TABLE} WHERE table_name = %s",
        (table,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return _metadata_from_row(row)


def _metadata_from_row(row: Any) -> EmbeddingTableMetadata:
    size = _row_value(row, "embedding_size", 2)
    if not isinstance(row, dict) and len(row) == 3:
        return EmbeddingTableMetadata(
            str(row[0]),
            str(row[1]),
            None if size is None else int(size),
            "vllm",
            {"check_embedding_ctx_length": False},
            "vllm",
        )
    options = _row_value(row, "provider_options", 4)
    if isinstance(options, str):
        options = json.loads(options)
    return EmbeddingTableMetadata(
        table_name=str(_row_value(row, "table_name", 0)),
        model_name=str(_row_value(row, "model_name", 1)),
        embedding_size=None if size is None else int(size),
        provider=(
            None
            if _row_value(row, "provider", 3) is None
            else str(_row_value(row, "provider", 3))
        ),
        provider_options=dict(options or {}),
        endpoint_profile=(
            None
            if _row_value(row, "endpoint_profile", 5) is None
            else str(_row_value(row, "endpoint_profile", 5))
        ),
        contract_version=int(_row_value(row, "contract_version", 6)),
    )


def _same_embedding_specification(
    left: EmbeddingTableMetadata, right: EmbeddingTableMetadata
) -> bool:
    return (
        left.table_name,
        left.model_name,
        left.provider,
        left.provider_options or {},
        left.endpoint_profile,
        left.contract_version,
    ) == (
        right.table_name,
        right.model_name,
        right.provider,
        right.provider_options or {},
        right.endpoint_profile,
        right.contract_version,
    )


def _associate_embedding_specification(
    cursor: Any, specification: EmbeddingTableMetadata, *, force: bool
) -> EmbeddingTableMetadata:
    table = specification.table_name
    cursor.execute(
        f"INSERT INTO {EMBEDDING_TABLE_METADATA_TABLE} "
        "(table_name, model_name, provider, provider_options, endpoint_profile, "
        "contract_version) "
        "VALUES (%s, %s, %s, %s::jsonb, %s, %s) "
        "ON CONFLICT (table_name) DO NOTHING",
        (
            table,
            specification.model_name,
            specification.provider,
            json.dumps(specification.provider_options or {}, sort_keys=True),
            specification.endpoint_profile,
            specification.contract_version,
        ),
    )
    cursor.execute(
        f"SELECT table_name, model_name, embedding_size, provider, "
        "provider_options, endpoint_profile, contract_version "
        f"FROM {EMBEDDING_TABLE_METADATA_TABLE} "
        "WHERE table_name = %s FOR UPDATE",
        (table,),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Could not configure embeddings table {table!r}")
    metadata = _metadata_from_row(row)
    if _same_embedding_specification(metadata, specification):
        return metadata
    if not force:
        raise EmbeddingModelMismatchError(
            f"{table!r} uses a different embedding specification. Pass --force "
            "to discard its embeddings and publish the requested provider, model, "
            "and compatibility options."
        )
    _drop_embedding_index(cursor, table)
    cursor.execute(sql.SQL("TRUNCATE {}").format(sql.Identifier(table)))
    cursor.execute(
        sql.SQL("ALTER TABLE {} DROP COLUMN IF EXISTS search_embedding").format(
            sql.Identifier(table)
        )
    )
    cursor.execute(
        sql.SQL(
            "ALTER TABLE {} ALTER COLUMN embedding TYPE vector USING embedding::vector"
        ).format(sql.Identifier(table))
    )
    cursor.execute(
        f"UPDATE {EMBEDDING_TABLE_METADATA_TABLE} "
        "SET model_name = %s, embedding_size = NULL, provider = %s, "
        "provider_options = %s::jsonb, endpoint_profile = %s, "
        "contract_version = %s "
        "WHERE table_name = %s",
        (
            specification.model_name,
            specification.provider,
            json.dumps(specification.provider_options or {}, sort_keys=True),
            specification.endpoint_profile,
            specification.contract_version,
            table,
        ),
    )
    return specification


def _require_compatible_specification(
    cursor: Any, table: str, requested: EmbeddingTableMetadata
) -> EmbeddingTableMetadata:
    metadata = embedding_table_metadata(cursor, table)
    if metadata is None:
        raise ValueError(f"No embedding specification is configured for {table!r}")
    comparable = EmbeddingTableMetadata(
        **{**requested.__dict__, "embedding_size": metadata.embedding_size}
    )
    if not _same_embedding_specification(metadata, comparable):
        raise EmbeddingModelMismatchError(
            f"{table!r} uses a different embedding specification"
        )
    return metadata


def _require_embedding_model(
    cursor: Any, table: str, modelname: str
) -> EmbeddingTableMetadata:
    metadata = embedding_table_metadata(cursor, table)
    if metadata is None:
        raise ValueError(f"No embedding model is configured for {table!r}")
    if metadata.model_name != modelname:
        raise EmbeddingModelMismatchError(
            f"{table!r} uses embedding model {metadata.model_name!r}, not {modelname!r}"
        )
    return metadata


def _set_embedding_size(
    cursor: Any, table: str, modelname: str, embedding_size: int
) -> None:
    metadata = _require_embedding_model(cursor, table, modelname)
    if (
        metadata.embedding_size is not None
        and metadata.embedding_size != embedding_size
    ):
        raise ValueError(
            f"Embedding model {modelname!r} returned {embedding_size}-dimensional "
            f"vectors, but {table!r} is configured for {metadata.embedding_size}"
        )
    cursor.execute(
        f"UPDATE {EMBEDDING_TABLE_METADATA_TABLE} SET embedding_size = %s "
        "WHERE table_name = %s AND model_name = %s",
        (embedding_size, table, modelname),
    )
    _dimension_embedding_columns(cursor, table, embedding_size)


def _dimension_embedding_columns(cursor: Any, table: str, dimensions: int) -> None:
    """Enforce dimensions and provision the column used by ordinary searches."""

    _drop_embedding_index(cursor, table)
    cursor.execute(
        sql.SQL("ALTER TABLE {} DROP COLUMN IF EXISTS search_embedding").format(
            sql.Identifier(table)
        )
    )
    vector_type = sql.SQL("vector({})").format(sql.Literal(dimensions))
    cursor.execute(
        sql.SQL(
            "ALTER TABLE {} ALTER COLUMN embedding TYPE {} USING embedding::{}"
        ).format(sql.Identifier(table), vector_type, vector_type)
    )
    if HNSW_VECTOR_MAX_DIMENSIONS < dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS:
        halfvec_type = sql.SQL("halfvec({})").format(sql.Literal(dimensions))
        cursor.execute(
            sql.SQL(
                "ALTER TABLE {} ADD COLUMN search_embedding {} "
                "GENERATED ALWAYS AS (embedding::{}) STORED"
            ).format(sql.Identifier(table), halfvec_type, halfvec_type)
        )


def _is_missing_vector_extension_error(error: psycopg.Error) -> bool:
    message = str(error)
    return (
        'extension "vector" is not available' in message or "vector.control" in message
    )


def _select_stored_source(
    cursor: Any, table: str, xml_id: int, chunk_index: int
) -> tuple[str, str, str, str | None] | None:
    cursor.execute(
        sql.SQL(
            "SELECT input_hash, source_path, tm_id, language FROM {} "
            "WHERE xml_id = %s AND chunk_index = %s"
        ).format(sql.Identifier(table)),
        (xml_id, chunk_index),
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
    chunk_id, xml_id, chunk_index, source_path, tm_id, language,
    document_text, input_hash, embedding
) VALUES (
    %(chunk_id)s, %(xml_id)s, %(chunk_index)s, %(source_path)s, %(tm_id)s, %(language)s,
    %(document_text)s, %(input_hash)s, %(embedding)s::vector
)
ON CONFLICT (xml_id, chunk_index) DO UPDATE SET
    chunk_id = EXCLUDED.chunk_id,
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


def _delete_missing_source_rows(cursor: Any, table: str, seen_ids: set[int]) -> None:
    cursor.execute(
        sql.SQL("DELETE FROM {} WHERE NOT (xml_id = ANY(%s))").format(
            sql.Identifier(table)
        ),
        (list(sorted(seen_ids)),),
    )


def _delete_extra_chunks(
    cursor: Any, table: str, xml_id: int, chunk_count: int
) -> None:
    cursor.execute(
        sql.SQL("DELETE FROM {} WHERE xml_id = %s AND chunk_index >= %s").format(
            sql.Identifier(table)
        ),
        (xml_id, chunk_count),
    )


def _embedding_index_name(table: str) -> str:
    return f"{table}_hnsw_idx"


def _drop_embedding_index(cursor: Any, table: str) -> None:
    cursor.execute(
        sql.SQL("DROP INDEX IF EXISTS {}").format(
            sql.Identifier(_embedding_index_name(table))
        )
    )


def _recreate_embedding_index(cursor: Any, table: str, dimensions: int) -> None:
    _drop_embedding_index(cursor, table)
    if dimensions <= HNSW_VECTOR_MAX_DIMENSIONS:
        column = "embedding"
        operator_class = "vector_cosine_ops"
    elif dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS:
        column = "search_embedding"
        operator_class = "halfvec_cosine_ops"
    else:
        return
    cursor.execute(
        sql.SQL("CREATE INDEX {} ON {} USING hnsw ({} {})").format(
            sql.Identifier(_embedding_index_name(table)),
            sql.Identifier(table),
            sql.Identifier(column),
            sql.SQL(operator_class),
        )
    )


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


def _first_column(row: Any) -> Any:
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


def _row_value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, dict) else row[index]
