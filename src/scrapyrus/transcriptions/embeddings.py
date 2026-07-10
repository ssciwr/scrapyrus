from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import psycopg
import requests

from scrapyrus.idpdata import iterate_idpdata_triples
from scrapyrus.transcriptions.core import (
    epidoc_xml_to_text,
    translation_epidoc_xml_to_text,
)


_MAX_POSTGRES_IDENTIFIER_LENGTH = 63
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def embedding_table_name(
    modelname: str,
    *,
    abbrev: bool = False,
    break_on_gap: bool = False,
    lost: bool = False,
    unclear: bool = False,
    regularize: bool = False,
    translation: bool = False,
) -> str:
    """Return the deterministic pgvector table name for embedding settings."""

    payload = {
        "abbrev": abbrev,
        "break_on_gap": break_on_gap,
        "lost": lost,
        "modelname": modelname,
        "regularize": regularize,
        "translation": translation,
        "unclear": unclear,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    model_slug = _identifier_fragment(modelname) or "model"
    mode = f"t{int(translation)}"
    flag_slug = (
        f"a{int(abbrev)}"
        f"_g{int(break_on_gap)}"
        f"_l{int(lost)}"
        f"_u{int(unclear)}"
        f"_r{int(regularize)}"
    )
    suffix = f"_{mode}_{flag_slug}_{digest}"
    prefix = "documents_"
    max_model_length = _MAX_POSTGRES_IDENTIFIER_LENGTH - len(prefix) - len(suffix)
    model_fragment = model_slug[:max_model_length].rstrip("_") or "model"
    table_name = f"{prefix}{model_fragment}{suffix}"

    if not _IDENTIFIER_RE.fullmatch(table_name):
        raise ValueError(f"Could not mangle embedding table name: {table_name!r}")
    return table_name


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
    ) -> str:
        """Create and populate the pgvector table for these embedding settings."""

        idp_data = Path(idp_data)
        table_name = embedding_table_name(
            self.modelname,
            abbrev=abbrev,
            break_on_gap=break_on_gap,
            lost=lost,
            unclear=unclear,
            regularize=regularize,
            translation=translation,
        )
        document_kind = "translation" if translation else "transcription"
        store_created = False

        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(f"DROP TABLE IF EXISTS {table_name}")

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
                    if not store_created:
                        _create_documents_table(cursor, table_name, len(embedding))
                        store_created = True

                    _insert_document(
                        cursor,
                        table_name,
                        {
                            "tm_id": tm_id,
                            "metadata_path": _relative_path(idp_data, metadata),
                            "document_path": _relative_path(idp_data, document),
                            "document_kind": document_kind,
                            "document_text": document_text,
                            "embedding": _vector_literal(embedding),
                        },
                    )

                if store_created:
                    _create_embedding_index(cursor, table_name)

        return table_name

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


def _identifier_fragment(value: str) -> str:
    fragment = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return re.sub(r"_+", "_", fragment)


def _embeddings_url(inference_server_url: str) -> str:
    base_url = inference_server_url.rstrip("/")
    if base_url.endswith("/v1"):
        return f"{base_url}/embeddings"
    return f"{base_url}/v1/embeddings"


def _create_documents_table(
    cursor: Any,
    table_name: str,
    embedding_dimensions: int,
) -> None:
    cursor.execute(
        f"""
CREATE TABLE {table_name} (
    document_path text NOT NULL PRIMARY KEY,
    tm_id text NOT NULL,
    metadata_path text NOT NULL,
    document_kind text NOT NULL,
    document_text text NOT NULL,
    embedding vector({embedding_dimensions}) NOT NULL
)
"""
    )


def _insert_document(cursor: Any, table_name: str, row: dict[str, str]) -> None:
    cursor.execute(
        f"""
INSERT INTO {table_name} (
    document_path,
    tm_id,
    metadata_path,
    document_kind,
    document_text,
    embedding
)
VALUES (
    %(document_path)s,
    %(tm_id)s,
    %(metadata_path)s,
    %(document_kind)s,
    %(document_text)s,
    %(embedding)s::vector
)
""",
        row,
    )


def _create_embedding_index(cursor: Any, table_name: str) -> None:
    cursor.execute(
        f"""
CREATE INDEX IF NOT EXISTS {_embedding_index_name(table_name)}
ON {table_name}
USING hnsw (embedding vector_cosine_ops)
"""
    )


def _embedding_index_name(table_name: str) -> str:
    suffix = "_embedding_hnsw_idx"
    index_name = f"{table_name}{suffix}"
    if len(index_name) <= _MAX_POSTGRES_IDENTIFIER_LENGTH:
        return index_name

    digest = hashlib.sha256(table_name.encode("utf-8")).hexdigest()[:8]
    max_table_prefix_length = (
        _MAX_POSTGRES_IDENTIFIER_LENGTH - len(suffix) - len(digest) - 1
    )
    return f"{table_name[:max_table_prefix_length]}_{digest}{suffix}"


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _vector_literal(embedding: tuple[float, ...]) -> str:
    return "[" + ",".join(format(value, ".17g") for value in embedding) + "]"
