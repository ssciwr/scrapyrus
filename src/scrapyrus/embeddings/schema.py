"""Shared pgvector schema, serialization, and validation utilities."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg import sql

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
    for corpus in corpora:
        corpus.create_schema(cursor)
    publish_semantics(
        cursor, tuple(c.semantics for c in corpora), component="embeddings"
    )


def embedding_stats(
    cursor: Any, corpus: EmbeddingCorpus, model_name: str
) -> tuple[int, int | None]:
    """Return row count and validate the stored vectors' common dimension."""

    try:
        cursor.execute(
            sql.SQL(
                "SELECT count(*), min(vector_dims(embedding)), "
                "max(vector_dims(embedding)) FROM {} WHERE model_name = %s"
            ).format(sql.Identifier(corpus.table_name)),
            (model_name,),
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


def imported_model_names(cursor: Any, temporary_table: str) -> list[str]:
    cursor.execute(
        sql.SQL(
            "SELECT model_name FROM {} GROUP BY model_name ORDER BY model_name"
        ).format(sql.Identifier(temporary_table))
    )
    return [str(row_value(row, "model_name", 0)) for row in cursor.fetchall()]


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


def embedding_index_name(table: str, model_name: str) -> str:
    digest = hashlib.sha256(model_name.encode("utf-8")).hexdigest()[:12]
    return f"{table}_{digest}_hnsw_idx"


def drop_embedding_index(cursor: Any, table: str, model_name: str) -> None:
    cursor.execute(
        sql.SQL("DROP INDEX IF EXISTS {}").format(
            sql.Identifier(embedding_index_name(table, model_name))
        )
    )


def recreate_embedding_index(
    cursor: Any, table: str, model_name: str, dimensions: int
) -> None:
    drop_embedding_index(cursor, table, model_name)
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
            sql.Identifier(embedding_index_name(table, model_name)),
            sql.Identifier(table),
            sql.SQL(index_type),
            sql.Literal(dimensions),
            sql.SQL(operator_class),
            sql.Literal(model_name),
        )
    )


def is_missing_vector_extension_error(error: psycopg.Error) -> bool:
    message = str(error)
    return (
        'extension "vector" is not available' in message or "vector.control" in message
    )
