"""Create and query model-specific embeddings for metadata keywords."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from tqdm import tqdm

from scrapyrus.semantics import publish_semantics
from scrapyrus.transcriptions.embeddings import (
    PGVECTOR_UNAVAILABLE_MESSAGE,
    HNSW_HALFVEC_MAX_DIMENSIONS,
    HNSW_VECTOR_MAX_DIMENSIONS,
    PgvectorUnavailableError,
    _is_missing_vector_extension_error,
    _recreate_embedding_index,
    _vector_literal,
)
from scrapyrus.transcriptions.llms import LLMProviderBase, initialize_llm_provider
from scrapyrus.transcriptions.semantics import (
    KEYWORD_EMBEDDINGS_SEMANTICS,
    TRANSCRIPTION_EMBEDDINGS_SEMANTICS,
    TRANSLATION_EMBEDDINGS_SEMANTICS,
)


KEYWORDS_TABLE = "keywords"
KEYWORD_EMBEDDINGS_TABLE = "keyword_embeddings"
KEYWORDS_UNAVAILABLE_MESSAGE = (
    f"PostgreSQL table '{KEYWORDS_TABLE}' does not exist. Run "
    "'scrapyrus metadata ingest' against this database before creating keyword "
    "embeddings."
)
KEYWORD_EMBEDDINGS_UNAVAILABLE_MESSAGE = (
    f"PostgreSQL table '{KEYWORD_EMBEDDINGS_TABLE}' does not exist. Run "
    "'scrapyrus embeddings keywords' against this database first."
)


class KeywordsUnavailableError(RuntimeError):
    """Raised when keyword metadata has not been ingested into PostgreSQL."""


class KeywordEmbeddingsUnavailableError(RuntimeError):
    """Raised when the keyword embedding store has not been created."""


@dataclass(frozen=True)
class KeywordMatch:
    """One keyword nearest to an embedded query by cosine similarity."""

    keyword: str
    similarity: float


class KeywordEmbeddingStore:
    """Store one embedding per distinct, non-null keyword and model."""

    def __init__(self, inference_server_url: str, modelname: str, api_key: str) -> None:
        self.modelname = modelname
        self.provider: LLMProviderBase = initialize_llm_provider(
            inference_server_url, modelname, api_key
        )

    def setup_store(self, conninfo: str = "", progressbar: bool = True, /) -> int:
        """Embed keyword strings not yet stored for this model.

        Duplicate assignments in ``keywords`` share one embedding. Stored terms
        which no longer occur in the source table are removed for this model.
        Return the number of newly embedded terms.
        """

        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                _ensure_keyword_embedding_schema(cursor)
                keywords = _select_keywords(cursor)
                stored_dimensions = _select_stored_keyword_dimensions(
                    cursor, self.modelname
                )
                dimensions = set(stored_dimensions.values())
                if len(dimensions) > 1:
                    raise ValueError(
                        f"Stored keyword embeddings for model {self.modelname!r} "
                        "have inconsistent dimensions"
                    )

                pending = [
                    keyword for keyword in keywords if keyword not in stored_dimensions
                ]
                terms = (
                    tqdm(pending, unit="keyword", desc="Embedding keywords")
                    if progressbar
                    else pending
                )
                expected_dimensions = next(iter(dimensions), None)
                for keyword in terms:
                    embedding = self.provider.embed(keyword)
                    if expected_dimensions is None:
                        expected_dimensions = len(embedding)
                    elif len(embedding) != expected_dimensions:
                        raise ValueError(
                            f"Embedding model {self.modelname!r} returned vectors "
                            "with inconsistent dimensions"
                        )
                    _upsert_keyword_embedding(
                        cursor,
                        keyword=keyword,
                        modelname=self.modelname,
                        embedding=embedding,
                    )

                _delete_stale_keyword_embeddings(cursor, self.modelname)
                if expected_dimensions is not None:
                    _recreate_embedding_index(
                        cursor,
                        KEYWORD_EMBEDDINGS_TABLE,
                        self.modelname,
                        expected_dimensions,
                    )

        return len(pending)


def find_similar_keywords(
    query: str,
    conninfo: str = "",
    /,
    *,
    inference_server_url: str,
    modelname: str,
    api_key: str,
    top_k: int = 10,
) -> tuple[KeywordMatch, ...]:
    """Embed *query* and return its top-k stored keywords by cosine similarity."""

    if not query.strip():
        raise ValueError("query must not be blank")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    provider = initialize_llm_provider(inference_server_url, modelname, api_key)
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            count, minimum_dimensions, maximum_dimensions = (
                _stored_keyword_embedding_stats(cursor, modelname)
            )
            if count == 0:
                raise ValueError(
                    f"No keyword embeddings found for model {modelname!r}. Run "
                    "'scrapyrus embeddings keywords' with the same model first."
                )
            if minimum_dimensions != maximum_dimensions:
                raise ValueError(
                    f"Stored keyword embeddings for model {modelname!r} have "
                    "inconsistent dimensions"
                )

            embedding = provider.embed(query)
            if len(embedding) != minimum_dimensions:
                raise ValueError(
                    f"Query embedding has {len(embedding)} dimensions, but stored "
                    f"embeddings for model {modelname!r} have {minimum_dimensions}"
                )
            cursor.execute(
                _nearest_keywords_query(minimum_dimensions),
                {
                    "embedding": _vector_literal(embedding),
                    "modelname": modelname,
                    "top_k": top_k,
                },
            )
            return tuple(
                KeywordMatch(
                    keyword=str(_row_value(row, "keyword", 0)),
                    similarity=float(_row_value(row, "similarity", 1)),
                )
                for row in cursor.fetchall()
            )


def _ensure_keyword_embedding_schema(cursor: Any) -> None:
    try:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except (psycopg.errors.FeatureNotSupported, psycopg.errors.UndefinedFile) as error:
        if _is_missing_vector_extension_error(error):
            raise PgvectorUnavailableError(PGVECTOR_UNAVAILABLE_MESSAGE) from error
        raise
    cursor.execute(
        f"""
CREATE TABLE IF NOT EXISTS {KEYWORD_EMBEDDINGS_TABLE} (
    keyword text NOT NULL,
    model_name text NOT NULL,
    embedding vector NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (keyword, model_name)
)
"""
    )
    publish_semantics(
        cursor,
        (
            TRANSCRIPTION_EMBEDDINGS_SEMANTICS,
            TRANSLATION_EMBEDDINGS_SEMANTICS,
            KEYWORD_EMBEDDINGS_SEMANTICS,
        ),
        component="embeddings",
    )


def _select_keywords(cursor: Any) -> tuple[str, ...]:
    try:
        cursor.execute(
            f"SELECT DISTINCT keyword FROM {KEYWORDS_TABLE} "
            "WHERE keyword IS NOT NULL ORDER BY keyword"
        )
    except psycopg.errors.UndefinedTable as error:
        raise KeywordsUnavailableError(KEYWORDS_UNAVAILABLE_MESSAGE) from error
    return tuple(str(_row_value(row, "keyword", 0)) for row in cursor.fetchall())


def _select_stored_keyword_dimensions(cursor: Any, modelname: str) -> dict[str, int]:
    cursor.execute(
        f"SELECT keyword, vector_dims(embedding) FROM {KEYWORD_EMBEDDINGS_TABLE} "
        "WHERE model_name = %s",
        (modelname,),
    )
    return {
        str(_row_value(row, "keyword", 0)): int(_row_value(row, "vector_dims", 1))
        for row in cursor.fetchall()
    }


def _upsert_keyword_embedding(
    cursor: Any,
    *,
    keyword: str,
    modelname: str,
    embedding: tuple[float, ...],
) -> None:
    cursor.execute(
        f"""
INSERT INTO {KEYWORD_EMBEDDINGS_TABLE} (keyword, model_name, embedding)
VALUES (%(keyword)s, %(model_name)s, %(embedding)s::vector)
ON CONFLICT (keyword, model_name) DO UPDATE SET
    embedding = EXCLUDED.embedding,
    updated_at = now()
""",
        {
            "keyword": keyword,
            "model_name": modelname,
            "embedding": _vector_literal(embedding),
        },
    )


def _delete_stale_keyword_embeddings(cursor: Any, modelname: str) -> None:
    cursor.execute(
        f"""
DELETE FROM {KEYWORD_EMBEDDINGS_TABLE} AS embedding
WHERE embedding.model_name = %s
  AND NOT EXISTS (
      SELECT 1 FROM {KEYWORDS_TABLE} AS source
      WHERE source.keyword = embedding.keyword
  )
""",
        (modelname,),
    )


def _stored_keyword_embedding_stats(
    cursor: Any, modelname: str
) -> tuple[int, int, int]:
    try:
        cursor.execute(
            f"""
SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding))
FROM {KEYWORD_EMBEDDINGS_TABLE}
WHERE model_name = %s
""",
            (modelname,),
        )
    except psycopg.errors.UndefinedTable as error:
        raise KeywordEmbeddingsUnavailableError(
            KEYWORD_EMBEDDINGS_UNAVAILABLE_MESSAGE
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


def _nearest_keywords_query(dimensions: int) -> sql.Composed:
    if dimensions <= HNSW_VECTOR_MAX_DIMENSIONS:
        vector_type = "vector"
    elif dimensions <= HNSW_HALFVEC_MAX_DIMENSIONS:
        vector_type = "halfvec"
    else:
        vector_type = None

    if vector_type is None:
        stored = sql.Identifier("embedding")
        query = sql.SQL("{}::vector").format(sql.Placeholder("embedding"))
    else:
        cast = sql.SQL("{}({})").format(sql.SQL(vector_type), sql.Literal(dimensions))
        stored = sql.SQL("{}::{}").format(sql.Identifier("embedding"), cast)
        query = sql.SQL("{}::{}").format(sql.Placeholder("embedding"), cast)
    distance = sql.SQL("{} <=> {}").format(stored, query)
    return sql.SQL(
        "SELECT keyword, 1 - ({distance}) AS similarity "
        "FROM {table} WHERE model_name = {modelname} "
        "ORDER BY {distance}, keyword LIMIT {top_k}"
    ).format(
        distance=distance,
        table=sql.Identifier(KEYWORD_EMBEDDINGS_TABLE),
        modelname=sql.Placeholder("modelname"),
        top_k=sql.Placeholder("top_k"),
    )


def _row_value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, dict) else row[index]


__all__ = [
    "KEYWORD_EMBEDDINGS_TABLE",
    "KeywordEmbeddingStore",
    "KeywordEmbeddingsUnavailableError",
    "KeywordMatch",
    "KeywordsUnavailableError",
    "find_similar_keywords",
]
