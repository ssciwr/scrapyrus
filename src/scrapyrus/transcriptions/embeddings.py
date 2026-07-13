from __future__ import annotations

import asyncio
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Any

import psycopg
import requests
from tqdm import tqdm

from scrapyrus.idpdata import iterate_idpdata_triples
from scrapyrus.transcriptions.core import (
    epidoc_xml_to_text,
    translation_epidoc_xml_to_text,
)


MAX_CONCURRENT_EMBEDDING_REQUESTS = 100
EMBEDDING_REQUEST_TIMEOUT = 60

PGVECTOR_UNAVAILABLE_MESSAGE = (
    "PostgreSQL extension 'vector' is not available. Install pgvector on the "
    "database server before using embeddings, or use a pgvector-enabled "
    "PostgreSQL image such as pgvector/pgvector:pg16."
)


class PgvectorUnavailableError(RuntimeError):
    """Raised when the PostgreSQL server does not provide pgvector."""


@dataclass(frozen=True)
class EmbeddingConfiguration:
    """Settings that define a reusable embedding collection."""

    modelname: str
    abbrev: bool = False
    break_on_gap: bool = False
    lost: bool = False
    unclear: bool = False
    regularize: bool = False
    translation: bool = False

    @property
    def document_kind(self) -> str:
        if self.translation:
            return "translation"
        return "transcription"


@dataclass(frozen=True)
class StoredEmbeddingConfiguration:
    """A persisted embedding configuration selected from PostgreSQL."""

    id: int
    configuration: EmbeddingConfiguration
    embedding_dimensions: int


@dataclass(frozen=True)
class _EmbeddingJob:
    ordinal: int
    store: "EmbeddingStore"
    row: dict[str, str]
    config_id: int | None = None
    expected_dimensions: int | None = None
    configuration: EmbeddingConfiguration | None = None


@dataclass(frozen=True)
class _EmbeddedDocument:
    job: _EmbeddingJob
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class _SkippedEmbeddingDocument:
    job: _EmbeddingJob
    message: str


class _EmbeddingRequestSentinel:
    """Limit embedding requests running against the inference server."""

    def __init__(self, limit: int = MAX_CONCURRENT_EMBEDDING_REQUESTS) -> None:
        if limit < 1:
            raise ValueError("Embedding request concurrency limit must be positive")
        self._semaphore = asyncio.Semaphore(limit)

    async def embed(
        self,
        store: "EmbeddingStore",
        executor: ThreadPoolExecutor,
        text: str,
    ) -> tuple[float, ...]:
        async with self._semaphore:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, store._embed_sync, text)


class EmbeddingStore:
    """Build a pgvector store for EpiDoc transcription or translation text."""

    def __init__(
        self,
        inference_server_url: str,
        modelname: str,
        api_key: str,
    ) -> None:
        self.inference_server_url = inference_server_url
        self.modelname = modelname
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._embeddings_url = _embeddings_url(inference_server_url)

    def setup_store(
        self,
        idp_data: str | Path,
        conninfo: str = "",
        progressbar: bool = True,
        /,
        *,
        abbrev: bool = False,
        break_on_gap: bool = False,
        lost: bool = False,
        unclear: bool = False,
        regularize: bool = False,
        translation: bool = False,
    ) -> int | None:
        """Create and populate the pgvector store for these embedding settings."""

        idp_data = Path(idp_data)
        configuration = EmbeddingConfiguration(
            self.modelname,
            abbrev=abbrev,
            break_on_gap=break_on_gap,
            lost=lost,
            unclear=unclear,
            regularize=regularize,
            translation=translation,
        )
        config_id = None
        embedding_dimensions = None
        jobs: list[_EmbeddingJob] = []

        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                _ensure_embedding_schema(cursor)

                for (
                    tm_id,
                    metadata,
                    transcription,
                    translation_path,
                ) in iterate_idpdata_triples(idp_data, progressbar=progressbar):
                    document = translation_path if translation else transcription
                    if document is None:
                        continue

                    document_text = self._document_text(
                        document,
                        abbrev=abbrev,
                        break_on_gap=break_on_gap,
                        lost=lost,
                        unclear=unclear,
                        regularize=regularize,
                        translation=translation,
                    )
                    if document_text.strip() == "":
                        continue

                    jobs.append(
                        _EmbeddingJob(
                            ordinal=len(jobs),
                            store=self,
                            row={
                                "tm_id": tm_id,
                                "metadata_path": _relative_path(idp_data, metadata),
                                "document_path": _relative_path(idp_data, document),
                                "document_text": document_text,
                                "input_hash": _input_hash(document_text),
                            },
                            configuration=configuration,
                        )
                    )

                embedded_documents = _embed_documents(
                    jobs,
                    progressbar=progressbar,
                    progressbar_title="Embedding documents",
                )
                for embedded_document in embedded_documents:
                    embedding = embedded_document.embedding
                    if config_id is None:
                        embedding_dimensions = len(embedding)
                        config_id = _upsert_embedding_configuration(
                            cursor,
                            configuration,
                            embedding_dimensions,
                        )

                    _upsert_document(
                        cursor,
                        config_id,
                        {
                            **embedded_document.job.row,
                            "embedding": _vector_literal(embedding),
                        },
                    )

                if config_id is not None:
                    if embedding_dimensions is None:
                        raise RuntimeError("Embedding dimensions were not recorded")
                    _recreate_embedding_index(cursor, config_id, embedding_dimensions)
                    _refresh_configuration_document_count(cursor, config_id)

        return config_id

    def _document_text(
        self,
        document: Path,
        *,
        abbrev: bool,
        break_on_gap: bool,
        lost: bool,
        unclear: bool,
        regularize: bool,
        translation: bool,
    ) -> str:
        if translation:
            return translation_epidoc_xml_to_text(document)

        return epidoc_xml_to_text(
            document,
            abbrev=abbrev,
            break_on_gap=break_on_gap,
            lost=lost,
            unclear=unclear,
            regularize=regularize,
        )

    def _session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self.headers)
        return session

    def _embed_sync(self, text: str) -> tuple[float, ...]:
        with self._session() as client:
            response = client.post(
                self._embeddings_url,
                json={"model": self.modelname, "input": text},
                timeout=EMBEDDING_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        try:
            embedding = payload["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError(
                "Embedding response did not contain data[0].embedding"
            ) from error

        if not isinstance(embedding, list) or not embedding:
            raise ValueError("Embedding response did not contain a non-empty vector")

        vector = tuple(float(value) for value in embedding)
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("Embedding response contained non-finite vector values")
        return vector


def _embed_documents(
    jobs: Sequence[_EmbeddingJob],
    *,
    progressbar: bool,
    progressbar_title: str,
) -> list[_EmbeddedDocument]:
    if not jobs:
        return []
    embedded_documents, skipped_messages = asyncio.run(
        _embed_documents_async(
            jobs,
            progressbar=progressbar,
            progressbar_title=progressbar_title,
        )
    )
    for message in skipped_messages:
        print(message, flush=True)
    return embedded_documents


async def _embed_documents_async(
    jobs: Sequence[_EmbeddingJob],
    *,
    progressbar: bool,
    progressbar_title: str,
) -> tuple[list[_EmbeddedDocument], list[str]]:
    sentinel = _EmbeddingRequestSentinel()
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_EMBEDDING_REQUESTS) as executor:
        progress = None
        if progressbar:
            progress = tqdm(
                total=len(jobs),
                unit="request",
                desc=progressbar_title,
            )
        tasks = [
            asyncio.create_task(_embed_document(job, sentinel, executor, progress))
            for job in jobs
        ]
        completed: list[_EmbeddedDocument] = []
        skipped: list[_SkippedEmbeddingDocument] = []

        try:
            for result in await asyncio.gather(*tasks):
                if isinstance(result, _SkippedEmbeddingDocument):
                    skipped.append(result)
                else:
                    completed.append(result)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        finally:
            if progress is not None and hasattr(progress, "close"):
                progress.close()

    completed.sort(key=lambda document: document.job.ordinal)
    skipped_messages = [
        skipped_document.message
        for skipped_document in sorted(
            skipped, key=lambda document: document.job.ordinal
        )
    ]
    return completed, skipped_messages


async def _embed_document(
    job: _EmbeddingJob,
    sentinel: _EmbeddingRequestSentinel,
    executor: ThreadPoolExecutor,
    progress: Any | None,
) -> _EmbeddedDocument | _SkippedEmbeddingDocument:
    try:
        embedding = await sentinel.embed(job.store, executor, job.row["document_text"])
    except Exception as error:
        if _is_skippable_embedding_error(error):
            result: _EmbeddedDocument | _SkippedEmbeddingDocument = (
                _SkippedEmbeddingDocument(
                    job,
                    _skipped_embedding_message(job, error),
                )
            )
        else:
            raise
    else:
        result = _EmbeddedDocument(
            job,
            embedding,
        )
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
    document_kind = (
        job.configuration.document_kind if job.configuration is not None else "unknown"
    )
    return (
        "Skipping embedding document after context-length validation error: "
        f"tm_id={job.row['tm_id']} "
        f"metadata_path={job.row['metadata_path']} "
        f"document_path={job.row['document_path']} "
        f"model={job.store.modelname} "
        f"document_kind={document_kind}: "
        f"{_embedding_error_message(error)}"
    )


def _embedding_error_message(error: BaseException) -> str:
    message = str(error)
    if isinstance(error, requests.HTTPError) and error.response is not None:
        response_message = _response_error_message(error.response)
        if response_message:
            if message and response_message not in message:
                return f"{message}: {response_message}"
            return response_message
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
            if parts:
                return " ".join(parts)
        elif isinstance(error_payload, str):
            return error_payload
        return str(payload)

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    return None


def update_embeddings(
    idp_data: str | Path,
    conninfo: str = "",
    progressbar: bool = True,
    /,
    *,
    inference_server_url: str,
    api_key: str,
) -> int:
    """Compute missing or stale embeddings for every stored configuration."""

    idp_data = Path(idp_data)
    stores: dict[str, EmbeddingStore] = {}
    updated_config_ids: set[int] = set()
    updated_count = 0
    jobs: list[_EmbeddingJob] = []

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            _ensure_embedding_schema(cursor)
            stored_configurations = _list_embedding_configurations(cursor)
            if not stored_configurations:
                return 0

            for (
                tm_id,
                metadata,
                transcription,
                translation_path,
            ) in iterate_idpdata_triples(idp_data, progressbar=progressbar):
                for stored in stored_configurations:
                    configuration = stored.configuration
                    document = (
                        translation_path if configuration.translation else transcription
                    )
                    if document is None:
                        continue

                    document_text = _configuration_document_text(
                        document,
                        configuration,
                    )
                    if document_text.strip() == "":
                        continue

                    input_hash = _input_hash(document_text)
                    document_path = _relative_path(idp_data, document)
                    stored_hash = _select_document_input_hash(
                        cursor,
                        stored.id,
                        document_path,
                    )
                    if stored_hash == input_hash:
                        continue

                    store = stores.get(configuration.modelname)
                    if store is None:
                        store = EmbeddingStore(
                            inference_server_url,
                            configuration.modelname,
                            api_key,
                        )
                        stores[configuration.modelname] = store

                    jobs.append(
                        _EmbeddingJob(
                            ordinal=len(jobs),
                            store=store,
                            row={
                                "tm_id": tm_id,
                                "metadata_path": _relative_path(idp_data, metadata),
                                "document_path": document_path,
                                "document_text": document_text,
                                "input_hash": input_hash,
                            },
                            config_id=stored.id,
                            expected_dimensions=stored.embedding_dimensions,
                            configuration=configuration,
                        )
                    )

            embedded_documents = _embed_documents(
                jobs,
                progressbar=progressbar,
                progressbar_title="Updating embeddings",
            )
            for embedded_document in embedded_documents:
                job = embedded_document.job
                embedding = embedded_document.embedding
                if job.config_id is None:
                    raise RuntimeError(
                        "Updated embedding job did not include config id"
                    )
                if job.expected_dimensions is None:
                    raise RuntimeError(
                        "Updated embedding job did not include expected dimensions"
                    )
                if job.configuration is None:
                    raise RuntimeError(
                        "Updated embedding job did not include configuration"
                    )

                if len(embedding) != job.expected_dimensions:
                    raise ValueError(
                        f"Embedding model {job.configuration.modelname!r} returned "
                        f"{len(embedding)} dimensions for configuration "
                        f"{job.config_id}; expected {job.expected_dimensions}"
                    )

                _upsert_document(
                    cursor,
                    job.config_id,
                    {**job.row, "embedding": _vector_literal(embedding)},
                )
                updated_config_ids.add(job.config_id)
                updated_count += 1

            for stored in stored_configurations:
                if stored.id in updated_config_ids:
                    _create_embedding_index(
                        cursor,
                        stored.id,
                        stored.embedding_dimensions,
                        if_not_exists=True,
                    )
                    _refresh_configuration_document_count(cursor, stored.id)

    return updated_count


def delete_embeddings(
    conninfo: str = "",
    /,
    *,
    modelname: str,
    abbrev: bool = False,
    break_on_gap: bool = False,
    lost: bool = False,
    unclear: bool = False,
    regularize: bool = False,
    translation: bool = False,
) -> int | None:
    """Delete stored embeddings for one embedding configuration."""

    configuration = EmbeddingConfiguration(
        modelname,
        abbrev=abbrev,
        break_on_gap=break_on_gap,
        lost=lost,
        unclear=unclear,
        regularize=regularize,
        translation=translation,
    )

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            config_id = _select_embedding_configuration_id(cursor, configuration)
            if config_id is None:
                return None
            _drop_embedding_index(cursor, config_id)
            _delete_embedding_configuration(cursor, config_id)

    return config_id


def retrieve_embedding(
    conninfo: str = "",
    /,
    *,
    modelname: str,
    document_path: str | Path,
    abbrev: bool = False,
    break_on_gap: bool = False,
    lost: bool = False,
    unclear: bool = False,
    regularize: bool = False,
    translation: bool = False,
) -> tuple[float, ...] | None:
    """Return a stored embedding for a document and embedding configuration."""

    configuration = EmbeddingConfiguration(
        modelname,
        abbrev=abbrev,
        break_on_gap=break_on_gap,
        lost=lost,
        unclear=unclear,
        regularize=regularize,
        translation=translation,
    )
    params = {
        **_configuration_params(configuration),
        "document_path": _document_path(document_path),
    }

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
SELECT document_embeddings.embedding::text
FROM embedding_configurations
JOIN document_embeddings
    ON document_embeddings.config_id = embedding_configurations.id
WHERE embedding_configurations.model_name = %(model_name)s
    AND embedding_configurations.document_kind = %(document_kind)s
    AND embedding_configurations.abbrev = %(abbrev)s
    AND embedding_configurations.break_on_gap = %(break_on_gap)s
    AND embedding_configurations.lost = %(lost)s
    AND embedding_configurations.unclear = %(unclear)s
    AND embedding_configurations.regularize = %(regularize)s
    AND document_embeddings.document_path = %(document_path)s
""",
                params,
            )
            row = cursor.fetchone()

    if row is None:
        return None
    return _parse_vector(_first_column(row))


def _embeddings_url(inference_server_url: str) -> str:
    base_url = inference_server_url.rstrip("/")
    if base_url.endswith("/v1"):
        return f"{base_url}/embeddings"
    return f"{base_url}/v1/embeddings"


def _ensure_embedding_schema(cursor: Any) -> None:
    try:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except (
        psycopg.errors.FeatureNotSupported,
        psycopg.errors.UndefinedFile,
    ) as error:
        if _is_missing_vector_extension_error(error):
            raise PgvectorUnavailableError(PGVECTOR_UNAVAILABLE_MESSAGE) from error
        raise
    _create_embedding_configurations_table(cursor)
    _create_document_embeddings_table(cursor)


def _is_missing_vector_extension_error(error: psycopg.Error) -> bool:
    message = str(error)
    return (
        'extension "vector" is not available' in message or "vector.control" in message
    )


def _create_embedding_configurations_table(cursor: Any) -> None:
    cursor.execute(
        """
CREATE TABLE IF NOT EXISTS embedding_configurations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_name text NOT NULL,
    document_kind text NOT NULL CHECK (
        document_kind IN ('transcription', 'translation')
    ),
    abbrev boolean NOT NULL,
    break_on_gap boolean NOT NULL,
    lost boolean NOT NULL,
    unclear boolean NOT NULL,
    regularize boolean NOT NULL,
    embedding_dimensions integer NOT NULL CHECK (embedding_dimensions > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    refreshed_at timestamptz NOT NULL DEFAULT now(),
    document_count integer NOT NULL DEFAULT 0 CHECK (document_count >= 0),
    UNIQUE (
        model_name,
        document_kind,
        abbrev,
        break_on_gap,
        lost,
        unclear,
        regularize
    )
)
"""
    )


def _create_document_embeddings_table(cursor: Any) -> None:
    cursor.execute(
        """
CREATE TABLE IF NOT EXISTS document_embeddings (
    config_id bigint NOT NULL REFERENCES embedding_configurations(id) ON DELETE CASCADE,
    document_path text NOT NULL,
    tm_id text NOT NULL,
    metadata_path text NOT NULL,
    document_text text NOT NULL,
    input_hash text NOT NULL,
    embedding vector NOT NULL,
    PRIMARY KEY (config_id, document_path)
)
"""
    )


def _upsert_embedding_configuration(
    cursor: Any,
    configuration: EmbeddingConfiguration,
    embedding_dimensions: int,
) -> int:
    cursor.execute(
        """
INSERT INTO embedding_configurations (
    model_name,
    document_kind,
    abbrev,
    break_on_gap,
    lost,
    unclear,
    regularize,
    embedding_dimensions
)
VALUES (
    %(model_name)s,
    %(document_kind)s,
    %(abbrev)s,
    %(break_on_gap)s,
    %(lost)s,
    %(unclear)s,
    %(regularize)s,
    %(embedding_dimensions)s
)
ON CONFLICT (
    model_name,
    document_kind,
    abbrev,
    break_on_gap,
    lost,
    unclear,
    regularize
)
DO UPDATE SET
    embedding_dimensions = EXCLUDED.embedding_dimensions
WHERE embedding_configurations.embedding_dimensions = EXCLUDED.embedding_dimensions
RETURNING id
""",
        {
            **_configuration_params(configuration),
            "embedding_dimensions": embedding_dimensions,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError(
            "Embedding configuration already exists with different dimensions; "
            "delete it with `scrapyrus embeddings delete` before ingesting this "
            "configuration again."
        )
    return int(_first_column(row))


def _select_embedding_configuration_id(
    cursor: Any,
    configuration: EmbeddingConfiguration,
) -> int | None:
    cursor.execute(
        """
SELECT id
FROM embedding_configurations
WHERE model_name = %(model_name)s
    AND document_kind = %(document_kind)s
    AND abbrev = %(abbrev)s
    AND break_on_gap = %(break_on_gap)s
    AND lost = %(lost)s
    AND unclear = %(unclear)s
    AND regularize = %(regularize)s
""",
        _configuration_params(configuration),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return int(_first_column(row))


def _list_embedding_configurations(
    cursor: Any,
) -> tuple[StoredEmbeddingConfiguration, ...]:
    cursor.execute(
        """
SELECT
    id,
    model_name,
    document_kind,
    abbrev,
    break_on_gap,
    lost,
    unclear,
    regularize,
    embedding_dimensions
FROM embedding_configurations
ORDER BY id
"""
    )
    return tuple(_stored_embedding_configuration(row) for row in cursor.fetchall())


def _stored_embedding_configuration(row: Any) -> StoredEmbeddingConfiguration:
    document_kind = _row_value(row, "document_kind", 2)
    if document_kind not in {"transcription", "translation"}:
        raise ValueError(f"Unknown embedding document kind: {document_kind!r}")

    configuration = EmbeddingConfiguration(
        _row_value(row, "model_name", 1),
        abbrev=bool(_row_value(row, "abbrev", 3)),
        break_on_gap=bool(_row_value(row, "break_on_gap", 4)),
        lost=bool(_row_value(row, "lost", 5)),
        unclear=bool(_row_value(row, "unclear", 6)),
        regularize=bool(_row_value(row, "regularize", 7)),
        translation=document_kind == "translation",
    )
    return StoredEmbeddingConfiguration(
        int(_row_value(row, "id", 0)),
        configuration,
        int(_row_value(row, "embedding_dimensions", 8)),
    )


def _delete_embedding_configuration(cursor: Any, config_id: int) -> None:
    cursor.execute(
        """
DELETE FROM embedding_configurations
WHERE id = %(config_id)s
""",
        {"config_id": config_id},
    )


def _upsert_document(cursor: Any, config_id: int, row: dict[str, str]) -> None:
    cursor.execute(
        """
INSERT INTO document_embeddings (
    config_id,
    document_path,
    tm_id,
    metadata_path,
    document_text,
    input_hash,
    embedding
)
VALUES (
    %(config_id)s,
    %(document_path)s,
    %(tm_id)s,
    %(metadata_path)s,
    %(document_text)s,
    %(input_hash)s,
    %(embedding)s::vector
)
ON CONFLICT (config_id, document_path)
DO UPDATE SET
    tm_id = EXCLUDED.tm_id,
    metadata_path = EXCLUDED.metadata_path,
    document_text = EXCLUDED.document_text,
    input_hash = EXCLUDED.input_hash,
    embedding = EXCLUDED.embedding
""",
        {"config_id": config_id, **row},
    )


def _select_document_input_hash(
    cursor: Any,
    config_id: int,
    document_path: str,
) -> str | None:
    cursor.execute(
        """
SELECT input_hash
FROM document_embeddings
WHERE config_id = %(config_id)s
    AND document_path = %(document_path)s
""",
        {"config_id": config_id, "document_path": document_path},
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return _first_column(row)


def _drop_embedding_index(cursor: Any, config_id: int) -> None:
    index_name = _embedding_index_name(config_id)
    cursor.execute(
        f"""
DROP INDEX IF EXISTS {index_name}
"""
    )


def _create_embedding_index(
    cursor: Any,
    config_id: int,
    embedding_dimensions: int,
    *,
    if_not_exists: bool = False,
) -> None:
    index_name = _embedding_index_name(config_id)
    existence_clause = "IF NOT EXISTS " if if_not_exists else ""
    cursor.execute(
        f"""
CREATE INDEX {existence_clause}{index_name}
ON document_embeddings
USING hnsw ((embedding::vector({embedding_dimensions})) vector_cosine_ops)
WHERE config_id = {config_id}
"""
    )


def _recreate_embedding_index(
    cursor: Any,
    config_id: int,
    embedding_dimensions: int,
) -> None:
    _drop_embedding_index(cursor, config_id)
    _create_embedding_index(cursor, config_id, embedding_dimensions)


def _refresh_configuration_document_count(cursor: Any, config_id: int) -> None:
    cursor.execute(
        """
UPDATE embedding_configurations
SET
    refreshed_at = now(),
    document_count = (
        SELECT count(*)::integer
        FROM document_embeddings
        WHERE config_id = %(config_id)s
    )
WHERE id = %(config_id)s
""",
        {"config_id": config_id},
    )


def _embedding_index_name(config_id: int) -> str:
    if config_id < 1:
        raise ValueError(f"Invalid embedding configuration id: {config_id!r}")
    return f"doc_embed_cfg_{config_id}_hnsw_idx"


def _configuration_params(configuration: EmbeddingConfiguration) -> dict[str, Any]:
    return {
        "model_name": configuration.modelname,
        "document_kind": configuration.document_kind,
        "abbrev": configuration.abbrev,
        "break_on_gap": configuration.break_on_gap,
        "lost": configuration.lost,
        "unclear": configuration.unclear,
        "regularize": configuration.regularize,
    }


def _configuration_document_text(
    document: Path,
    configuration: EmbeddingConfiguration,
) -> str:
    if configuration.translation:
        return translation_epidoc_xml_to_text(document)

    return epidoc_xml_to_text(
        document,
        abbrev=configuration.abbrev,
        break_on_gap=configuration.break_on_gap,
        lost=configuration.lost,
        unclear=configuration.unclear,
        regularize=configuration.regularize,
    )


def _input_hash(document_text: str) -> str:
    return hashlib.sha256(document_text.encode("utf-8")).hexdigest()


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _document_path(path: str | Path) -> str:
    return Path(path).as_posix()


def _vector_literal(embedding: tuple[float, ...]) -> str:
    return "[" + ",".join(format(value, ".17g") for value in embedding) + "]"


def _parse_vector(value: Any) -> tuple[float, ...]:
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("[") or not text.endswith("]"):
            raise ValueError(f"Could not parse vector value: {value!r}")
        values = text[1:-1].strip()
        if values == "":
            return ()
        return tuple(float(item) for item in values.split(","))

    if isinstance(value, (list, tuple)):
        return tuple(float(item) for item in value)

    raise TypeError(f"Unsupported vector value: {value!r}")


def _first_column(row: Any) -> Any:
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[index]
