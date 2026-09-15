"""Required manifests for binary corpus embedding transfers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scrapyrus.embeddings.specification import EmbeddingTableMetadata

if TYPE_CHECKING:
    from scrapyrus.embeddings.corpora import EmbeddingCorpus

DUMP_FORMAT = "scrapyrus-embedding-dump-v1"


def manifest_path(path: Path) -> Path:
    return path.with_name(path.name + ".manifest.json")


def write_manifest(
    path: Path, corpus: EmbeddingCorpus, count: int, metadata: EmbeddingTableMetadata
) -> None:
    if metadata.embedding_size is None:
        raise ValueError("Embedding dimensions must be known before exporting")
    manifest_path(path).write_text(
        json.dumps(
            {
                "format": DUMP_FORMAT,
                "document_kind": corpus.name,
                "columns": list(corpus.export_columns),
                "row_count": count,
                "embedding_specification": metadata.model_dump(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def load_manifest(
    path: Path, corpus: EmbeddingCorpus
) -> tuple[dict[str, Any], EmbeddingTableMetadata]:
    sidecar = manifest_path(path)
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Embedding dump manifest is missing: {sidecar}") from error
    except (OSError, ValueError) as error:
        raise ValueError(f"Invalid embedding dump manifest: {sidecar}") from error
    if not isinstance(value, dict) or set(value) != {
        "format",
        "document_kind",
        "columns",
        "row_count",
        "embedding_specification",
    }:
        raise ValueError("Invalid embedding dump manifest fields")
    if value["format"] != DUMP_FORMAT:
        raise ValueError("Unsupported embedding dump manifest format")
    if value["document_kind"] != corpus.name:
        raise ValueError("Embedding dump names the wrong corpus")
    if value["columns"] != list(corpus.export_columns):
        raise ValueError("Embedding dump columns do not match the table contract")
    if type(value["row_count"]) is not int or value["row_count"] < 0:
        raise ValueError("Embedding dump manifest has an invalid row count")
    fields = value["embedding_specification"]
    if not isinstance(fields, dict) or set(fields) != set(
        EmbeddingTableMetadata.model_fields
    ):
        raise ValueError("Embedding dump specification fields are incomplete")
    metadata = EmbeddingTableMetadata.model_validate(fields)
    if metadata.embedding_size is None:
        raise ValueError("Embedding dump must declare positive embedding dimensions")
    if metadata.table_name != corpus.table_name:
        raise ValueError("Embedding dump specification names the wrong table")
    if metadata.provider_options != fields["provider_options"]:
        raise ValueError(
            "Embedding dump must record all effective provider option values"
        )
    return value, metadata
