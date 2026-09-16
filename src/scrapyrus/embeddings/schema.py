"""Shared pgvector schema, serialization, and validation utilities."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg import sql

from scrapyrus.embeddings.semantics import EMBEDDING_TABLE_METADATA_SEMANTICS
from scrapyrus.semantics import publish_semantics

if TYPE_CHECKING:
    from scrapyrus.embeddings.corpora import EmbeddingCorpus

HNSW_VECTOR_MAX_DIMENSIONS = 2_000
HNSW_HALFVEC_MAX_DIMENSIONS = 4_000


class PgvectorUnavailableError(RuntimeError):
    """Raised when the PostgreSQL server does not provide pgvector."""


class SourceUnavailableError(RuntimeError):
    """Raised when a corpus's source metadata has not been ingested."""


class EmbeddingsUnavailableError(RuntimeError):
    """Raised when a corpus's embedding table has not been created."""


def ensure_schema(cursor: Any, corpora: Iterable[EmbeddingCorpus]) -> None:
    """Create the registered corpus tables and publish their semantics."""

    try:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except (psycopg.errors.FeatureNotSupported, psycopg.errors.UndefinedFile) as error:
        if is_missing_vector_extension_error(error):
            raise PgvectorUnavailableError(
                "PostgreSQL extension 'vector' is not available. Install pgvector "
                "on the database server or use a pgvector-enabled PostgreSQL image."
            ) from error
        raise
    corpora = tuple(corpora)
    cursor.execute("""
CREATE TABLE IF NOT EXISTS embedding_table_metadata (
    table_name text PRIMARY KEY,
    model_name text NOT NULL,
    embedding_size integer CHECK (embedding_size > 0)
)
""")
    for corpus in corpora:
        corpus.create_schema(cursor)
    publish_semantics(
        cursor,
        (EMBEDDING_TABLE_METADATA_SEMANTICS, *(c.semantics for c in corpora)),
        component="embeddings",
    )


def embedding_stats(cursor: Any, corpus: EmbeddingCorpus) -> tuple[int, int | None]:
    """Return row count and validate the stored vectors' common dimension."""

    try:
        cursor.execute(
            sql.SQL(
                "SELECT count(*), min(vector_dims(embedding)), "
                "max(vector_dims(embedding)) FROM {}"
            ).format(sql.Identifier(corpus.table_name)),
        )
    except psycopg.errors.UndefinedTable as error:
        raise EmbeddingsUnavailableError(
            f"PostgreSQL table {corpus.table_name!r} does not exist. Run "
            f"'scrapyrus embeddings ingest {corpus.name}' against this database first."
        ) from error
    row = cursor.fetchone()
    count = int(row_value(row, "count", 0))
    if count == 0:
        return 0, None
    minimum = int(row_value(row, "min", 1))
    maximum = int(row_value(row, "max", 2))
    if minimum != maximum:
        raise ValueError(
            f"Stored {corpus.name} embeddings have inconsistent dimensions"
        )
    return count, minimum


def cosine_distance(dimensions: int) -> sql.Composed:
    """Match the cast used by the corpus's HNSW index, if supported."""

    vector_type = (
        "vector"
        if dimensions <= HNSW_VECTOR_MAX_DIMENSIONS
        else "halfvec"
        if dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS
        else None
    )
    if vector_type is None:
        stored = sql.Identifier("embedding")
        query = sql.SQL("{}::vector").format(sql.Placeholder("embedding"))
    else:
        cast = sql.SQL("{}({})").format(sql.SQL(vector_type), sql.Literal(dimensions))
        stored = sql.SQL("{}::{}").format(sql.Identifier("embedding"), cast)
        query = sql.SQL("{}::{}").format(sql.Placeholder("embedding"), cast)
    return sql.SQL("{} <=> {}").format(stored, query)


def vector_literal(embedding: tuple[float, ...]) -> str:
    return "[" + ",".join(format(value, ".17g") for value in embedding) + "]"


def parse_vector(value: Any) -> tuple[float, ...]:
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("[") or not text.endswith("]"):
            raise ValueError(f"Could not parse vector value: {value!r}")
        return tuple(float(item) for item in text[1:-1].split(",") if item)
    if isinstance(value, (list, tuple)):
        return tuple(float(item) for item in value)
    raise TypeError(f"Unsupported vector value: {value!r}")


def row_value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, dict) else row[index]


def imported_embedding_stats(
    cursor: Any, temporary_table: str
) -> tuple[int, int | None]:
    cursor.execute(
        sql.SQL(
            "SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding)) "
            "FROM {}"
        ).format(sql.Identifier(temporary_table))
    )
    row = cursor.fetchone()
    row_count = int(row_value(row, "count", 0))
    minimum_dimensions = row_value(row, "min", 1)
    maximum_dimensions = row_value(row, "max", 2)
    if row_count == 0:
        return 0, None
    if minimum_dimensions != maximum_dimensions:
        raise ValueError(
            "Imported embeddings contain vectors with inconsistent dimensions"
        )
    return row_count, int(minimum_dimensions)


def embedding_index_name(table: str) -> str:
    return f"{table}_hnsw_idx"


def drop_embedding_index(cursor: Any, table: str) -> None:
    cursor.execute(
        sql.SQL("DROP INDEX IF EXISTS {}").format(
            sql.Identifier(embedding_index_name(table))
        )
    )


def recreate_embedding_index(cursor: Any, table: str, dimensions: int) -> None:
    drop_embedding_index(cursor, table)
    if dimensions <= HNSW_VECTOR_MAX_DIMENSIONS:
        index_type = "vector"
        operator_class = "vector_cosine_ops"
    elif dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS:
        index_type = "halfvec"
        operator_class = "halfvec_cosine_ops"
    else:
        return
    cursor.execute(
        sql.SQL("CREATE INDEX {} ON {} USING hnsw ((embedding::{}({})) {})").format(
            sql.Identifier(embedding_index_name(table)),
            sql.Identifier(table),
            sql.SQL(index_type),
            sql.Literal(dimensions),
            sql.SQL(operator_class),
        )
    )


def is_missing_vector_extension_error(error: psycopg.Error) -> bool:
    message = str(error)
    return (
        'extension "vector" is not available' in message or "vector.control" in message
    )


@dataclass(frozen=True)
class EmbeddingTableMetadata:
    """The model and vector dimension associated with one corpus table."""

    table_name: str
    model_name: str
    embedding_size: int | None


class EmbeddingModelMismatchError(ValueError):
    """Raised when an operation requests a model different from the table's."""


def embedding_table_metadata(
    cursor: Any, corpus: EmbeddingCorpus, *, lock: bool = False
) -> EmbeddingTableMetadata | None:
    """Read corpus configuration, optionally locking it for a write operation."""
    try:
        cursor.execute(
            "SELECT table_name, model_name, embedding_size FROM embedding_table_metadata "
            "WHERE table_name = %s" + (" FOR UPDATE" if lock else " FOR SHARE"),
            (corpus.table_name,),
        )
    except psycopg.errors.UndefinedTable as error:
        raise EmbeddingsUnavailableError(
            f"No embedding metadata exists. Run 'scrapyrus embeddings ingest {corpus.name}' first."
        ) from error
    row = cursor.fetchone()
    if row is None:
        return None
    size = row_value(row, "embedding_size", 2)
    return EmbeddingTableMetadata(
        str(row_value(row, "table_name", 0)),
        str(row_value(row, "model_name", 1)),
        None if size is None else int(size),
    )


def require_embedding_model(
    cursor: Any, corpus: EmbeddingCorpus, model_name: str, *, lock: bool = False
) -> EmbeddingTableMetadata:
    """Require the requested model to match the corpus configuration."""
    metadata = embedding_table_metadata(cursor, corpus, lock=lock)
    if metadata is None:
        raise ValueError(f"No embedding model is configured for {corpus.table_name!r}")
    if metadata.model_name != model_name:
        raise EmbeddingModelMismatchError(
            f"{corpus.table_name!r} uses embedding model {metadata.model_name!r}, "
            f"not {model_name!r}"
        )
    return metadata


def associate_embedding_model(
    cursor: Any, corpus: EmbeddingCorpus, model_name: str, *, force: bool
) -> EmbeddingTableMetadata:
    """Configure a corpus, discarding its vectors only for a forced model change."""
    cursor.execute(
        "INSERT INTO embedding_table_metadata (table_name, model_name) VALUES (%s, %s) "
        "ON CONFLICT (table_name) DO NOTHING",
        (corpus.table_name, model_name),
    )
    metadata = embedding_table_metadata(cursor, corpus, lock=True)
    if metadata is None:
        raise RuntimeError(f"Could not configure {corpus.table_name!r}")
    if metadata.model_name == model_name:
        return metadata
    if not force:
        raise EmbeddingModelMismatchError(
            f"{corpus.table_name!r} uses embedding model {metadata.model_name!r}, not {model_name!r}. "
            "Pass --force to discard its embeddings and use the new model."
        )
    drop_embedding_index(cursor, corpus.table_name)
    cursor.execute(sql.SQL("TRUNCATE {}").format(sql.Identifier(corpus.table_name)))
    cursor.execute(
        "UPDATE embedding_table_metadata SET model_name = %s, "
        "embedding_size = NULL WHERE table_name = %s",
        (model_name, corpus.table_name),
    )
    return EmbeddingTableMetadata(corpus.table_name, model_name, None)


def set_embedding_size(
    cursor: Any, corpus: EmbeddingCorpus, dimensions: int | None
) -> None:
    """Persist the dimension after a validated corpus write."""
    cursor.execute(
        "UPDATE embedding_table_metadata SET embedding_size = %s WHERE table_name = %s",
        (dimensions, corpus.table_name),
    )
