from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import psycopg
import requests

from scrapyrus.idpdata import iterate_idpdata_triples
from scrapyrus.transcriptions.core import (
    epidoc_xml_to_text,
    translation_epidoc_xml_to_text,
)


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
        self.client = requests.Session()
        self.client.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )
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
        document_count = 0
        embedding_dimensions = None

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

                    embedding = self._embed(document_text)
                    if config_id is None:
                        embedding_dimensions = len(embedding)
                        config_id = _upsert_embedding_configuration(
                            cursor,
                            configuration,
                            embedding_dimensions,
                        )
                        _delete_configuration_embeddings(cursor, config_id)

                    _insert_document(
                        cursor,
                        config_id,
                        {
                            "tm_id": tm_id,
                            "metadata_path": _relative_path(idp_data, metadata),
                            "document_path": _relative_path(idp_data, document),
                            "document_text": document_text,
                            "embedding": _vector_literal(embedding),
                        },
                    )
                    document_count += 1

                if config_id is not None:
                    if embedding_dimensions is None:
                        raise RuntimeError("Embedding dimensions were not recorded")
                    _recreate_embedding_index(cursor, config_id, embedding_dimensions)
                    _update_configuration_document_count(
                        cursor,
                        config_id,
                        document_count,
                    )

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

    def _embed(self, text: str) -> tuple[float, ...]:
        response = self.client.post(
            self._embeddings_url,
            json={"model": self.modelname, "input": text},
            timeout=60,
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
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _create_embedding_configurations_table(cursor)
    _create_document_embeddings_table(cursor)


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
    embedding_dimensions,
    refreshed_at,
    document_count
)
VALUES (
    %(model_name)s,
    %(document_kind)s,
    %(abbrev)s,
    %(break_on_gap)s,
    %(lost)s,
    %(unclear)s,
    %(regularize)s,
    %(embedding_dimensions)s,
    now(),
    0
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
    embedding_dimensions = EXCLUDED.embedding_dimensions,
    refreshed_at = now(),
    document_count = 0
RETURNING id
""",
        {
            **_configuration_params(configuration),
            "embedding_dimensions": embedding_dimensions,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Embedding configuration upsert did not return an id")
    return int(_first_column(row))


def _delete_configuration_embeddings(cursor: Any, config_id: int) -> None:
    cursor.execute(
        """
DELETE FROM document_embeddings
WHERE config_id = %(config_id)s
""",
        {"config_id": config_id},
    )


def _insert_document(cursor: Any, config_id: int, row: dict[str, str]) -> None:
    cursor.execute(
        """
INSERT INTO document_embeddings (
    config_id,
    document_path,
    tm_id,
    metadata_path,
    document_text,
    embedding
)
VALUES (
    %(config_id)s,
    %(document_path)s,
    %(tm_id)s,
    %(metadata_path)s,
    %(document_text)s,
    %(embedding)s::vector
)
""",
        {"config_id": config_id, **row},
    )


def _recreate_embedding_index(
    cursor: Any,
    config_id: int,
    embedding_dimensions: int,
) -> None:
    index_name = _embedding_index_name(config_id)
    cursor.execute(
        f"""
DROP INDEX IF EXISTS {index_name}
"""
    )
    cursor.execute(
        f"""
CREATE INDEX {index_name}
ON document_embeddings
USING hnsw ((embedding::vector({embedding_dimensions})) vector_cosine_ops)
WHERE config_id = {config_id}
"""
    )


def _update_configuration_document_count(
    cursor: Any,
    config_id: int,
    document_count: int,
) -> None:
    cursor.execute(
        """
UPDATE embedding_configurations
SET document_count = %(document_count)s
WHERE id = %(config_id)s
""",
        {"config_id": config_id, "document_count": document_count},
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
