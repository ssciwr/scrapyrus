"""Shared pgvector schema, serialization, and validation utilities."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from scrapyrus.embeddings.specification import (
    EmbeddingSpecification,
    EmbeddingTableMetadata,
)

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
    embedding_size integer CHECK (embedding_size > 0),
    provider text NOT NULL,
    provider_options jsonb NOT NULL,
    endpoint_profile text,
    contract_version integer NOT NULL CHECK (contract_version = 1)
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

    if HNSW_VECTOR_MAX_DIMENSIONS < dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS:
        column = "search_embedding"
        vector_type = "halfvec"
    else:
        column = "embedding"
        vector_type = "vector"
    cast = sql.SQL("{}({})").format(sql.SQL(vector_type), sql.Literal(dimensions))
    query = sql.SQL("{}::{}").format(sql.Placeholder("embedding"), cast)
    return sql.SQL("{} <=> {}").format(sql.Identifier(column), query)


def vector_literal(embedding: tuple[float, ...]) -> str:
    return "[" + ",".join(format(value, ".17g") for value in embedding) + "]"


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
        column = "embedding"
        operator_class = "vector_cosine_ops"
    elif dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS:
        column = "search_embedding"
        operator_class = "halfvec_cosine_ops"
    else:
        return
    cursor.execute(
        sql.SQL("CREATE INDEX {} ON {} USING hnsw ({} {})").format(
            sql.Identifier(embedding_index_name(table)),
            sql.Identifier(table),
            sql.Identifier(column),
            sql.SQL(operator_class),
        )
    )


def is_missing_vector_extension_error(error: psycopg.Error) -> bool:
    message = str(error)
    return (
        'extension "vector" is not available' in message or "vector.control" in message
    )


class EmbeddingModelMismatchError(ValueError):
    """Raised when an operation requests a model different from the table's."""


def embedding_table_metadata(
    cursor: Any, corpus: EmbeddingCorpus, *, lock: bool = False
) -> EmbeddingTableMetadata | None:
    """Read corpus configuration, optionally locking it for a write operation."""
    try:
        cursor.execute(
            "SELECT table_name, model_name, embedding_size, provider, provider_options, "
            "endpoint_profile, contract_version FROM embedding_table_metadata "
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
    fields = (
        "table_name",
        "model_name",
        "embedding_size",
        "provider",
        "provider_options",
        "endpoint_profile",
        "contract_version",
    )
    return EmbeddingTableMetadata.model_validate(
        {name: row_value(row, name, index) for index, name in enumerate(fields)}
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


def require_embedding_specification(
    cursor: Any,
    corpus: EmbeddingCorpus,
    specification: EmbeddingSpecification,
    *,
    lock: bool = False,
) -> EmbeddingTableMetadata:
    """Reject every incompatible vector space before reading or writing vectors."""
    metadata = require_embedding_model(
        cursor, corpus, specification.model_name, lock=lock
    )
    if not metadata.compatible_with(specification):
        raise EmbeddingModelMismatchError(
            f"{corpus.table_name!r} uses a different embedding specification"
        )
    return metadata


def associate_embedding_specification(
    cursor: Any,
    corpus: EmbeddingCorpus,
    specification: EmbeddingSpecification,
    *,
    force: bool,
) -> EmbeddingTableMetadata:
    """Configure a corpus, discarding vectors for a forced specification change."""
    parameters = (
        corpus.table_name,
        specification.model_name,
        specification.embedding_size,
        specification.provider,
        Jsonb(specification.provider_options),
        specification.endpoint_profile,
        specification.contract_version,
    )
    cursor.execute(
        "INSERT INTO embedding_table_metadata "
        "(table_name, model_name, embedding_size, provider, provider_options, endpoint_profile, contract_version) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (table_name) DO NOTHING",
        parameters,
    )
    metadata = embedding_table_metadata(cursor, corpus, lock=True)
    if metadata is None:
        raise RuntimeError(f"Could not configure {corpus.table_name!r}")
    if metadata.compatible_with(specification):
        return metadata
    if not force:
        raise EmbeddingModelMismatchError(
            f"{corpus.table_name!r} uses a different embedding specification. "
            "Pass --force to discard its embeddings and publish the new specification."
        )
    drop_embedding_index(cursor, corpus.table_name)
    cursor.execute(sql.SQL("TRUNCATE {}").format(sql.Identifier(corpus.table_name)))
    reset_embedding_columns(cursor, corpus.table_name)
    cursor.execute(
        "UPDATE embedding_table_metadata SET model_name = %s, embedding_size = %s, "
        "provider = %s, provider_options = %s, endpoint_profile = %s, contract_version = %s "
        "WHERE table_name = %s",
        (*parameters[1:], parameters[0]),
    )
    return EmbeddingTableMetadata(
        table_name=corpus.table_name, **specification.model_dump()
    )


def reset_embedding_columns(cursor: Any, table: str) -> None:
    """Remove dimension-dependent storage after old vectors have been discarded."""
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


def set_embedding_size(cursor: Any, corpus: EmbeddingCorpus, dimensions: int) -> None:
    """Persist a validated dimension and provision directly indexable columns."""
    drop_embedding_index(cursor, corpus.table_name)
    reset_embedding_columns(cursor, corpus.table_name)
    cast = sql.SQL("vector({})").format(sql.Literal(dimensions))
    cursor.execute(
        sql.SQL(
            "ALTER TABLE {} ALTER COLUMN embedding TYPE {} USING embedding::{}"
        ).format(sql.Identifier(corpus.table_name), cast, cast)
    )
    if HNSW_VECTOR_MAX_DIMENSIONS < dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS:
        halfvec = sql.SQL("halfvec({})").format(sql.Literal(dimensions))
        cursor.execute(
            sql.SQL(
                "ALTER TABLE {} ADD COLUMN search_embedding {} "
                "GENERATED ALWAYS AS (embedding::{}) STORED"
            ).format(sql.Identifier(corpus.table_name), halfvec, halfvec)
        )
    cursor.execute(
        "UPDATE embedding_table_metadata SET embedding_size = %s WHERE table_name = %s",
        (dimensions, corpus.table_name),
    )
