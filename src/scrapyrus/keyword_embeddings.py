"""Create and query model-specific embeddings for metadata keywords."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from langchain_core.embeddings import Embeddings
import psycopg
from psycopg import sql
from tqdm import tqdm

from scrapyrus.transcriptions.embeddings import (
    EmbeddingTableMetadata,
    HNSW_HALFVEC_MAX_DIMENSIONS,
    HNSW_VECTOR_MAX_DIMENSIONS,
    KEYWORD_EMBEDDINGS_TABLE,
    _associate_embedding_specification,
    _ensure_embedding_schema,
    initialize_llm_provider,
    _recreate_embedding_index,
    _require_embedding_model,
    _require_compatible_specification,
    _set_embedding_size,
    _set_publication_state,
    _vector_literal,
)
from scrapyrus.transcriptions.embedding_clients import (
    build_embedding_client,
    effective_provider_options,
    infer_embedding_provider,
)


KEYWORDS_TABLE = "keywords"
KEYWORDS_UNAVAILABLE_MESSAGE = (
    f"PostgreSQL table '{KEYWORDS_TABLE}' does not exist. Run "
    "'scrapyrus metadata ingest' against this database before creating keyword "
    "embeddings."
)
KEYWORD_EMBEDDINGS_UNAVAILABLE_MESSAGE = (
    f"PostgreSQL table '{KEYWORD_EMBEDDINGS_TABLE}' does not exist. Run "
    "'scrapyrus embeddings ingest keywords' against this database first."
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
    """Store one embedding per distinct keyword/qualifier text and model."""

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

    def _metadata(self) -> EmbeddingTableMetadata:
        return EmbeddingTableMetadata(
            KEYWORD_EMBEDDINGS_TABLE,
            self.modelname,
            None,
            self.provider_name,
            self.provider_options,
            self.endpoint_profile,
        )

    def setup_store(
        self,
        conninfo: str = "",
        progressbar: bool = True,
        /,
        *,
        stale_only: bool = False,
        force: bool = False,
    ) -> int:
        """Embed keyword and optional qualifier strings for this model.

        Qualifiers are appended as ``keyword, qualifier``. Duplicate assignments
        in ``keywords`` share one embedding. Stored terms which no longer occur
        in the source table are removed for this model. When ``stale_only`` is
        true, existing terms are not sent to the model. Return the number of
        embedded terms.
        """

        with psycopg.connect(conninfo) as connection:
            with connection.cursor() as cursor:
                _ensure_keyword_embedding_schema(cursor)
                metadata = _associate_embedding_specification(
                    cursor, self._metadata(), force=force
                )
                keywords = _select_keywords(cursor)
                stored_dimensions = _select_stored_keyword_dimensions(cursor)
                dimensions = set(stored_dimensions.values())
                if len(dimensions) > 1:
                    raise ValueError(
                        f"Stored keyword embeddings for model {self.modelname!r} "
                        "have inconsistent dimensions"
                    )

                pending = (
                    [
                        keyword
                        for keyword in keywords
                        if keyword not in stored_dimensions
                    ]
                    if stale_only
                    else list(keywords)
                )
                terms = (
                    tqdm(pending, unit="keyword", desc="Embedding keywords")
                    if progressbar
                    else pending
                )
                expected_dimensions = metadata.embedding_size
                if dimensions and dimensions != {expected_dimensions}:
                    raise ValueError(
                        "Stored keyword vectors do not match the configured "
                        f"embedding size {expected_dimensions}"
                    )
                for keyword in terms:
                    embedding = tuple(self.provider.embed_documents([keyword])[0])
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
                        embedding=embedding,
                    )

                _delete_stale_keyword_embeddings(cursor)
                if expected_dimensions is None:
                    expected_dimensions = len(
                        self.provider.embed_query(
                            "Scrapyrus empty-corpus dimension readiness probe"
                        )
                    )
                _set_embedding_size(
                    cursor,
                    KEYWORD_EMBEDDINGS_TABLE,
                    self.modelname,
                    expected_dimensions,
                )
                _recreate_embedding_index(
                    cursor,
                    KEYWORD_EMBEDDINGS_TABLE,
                    expected_dimensions,
                )
                _set_publication_state(cursor, KEYWORD_EMBEDDINGS_TABLE, "ready")

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

    query_store = KeywordEmbeddingStore(inference_server_url, modelname, api_key)
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            metadata = _require_embedding_model(
                cursor, KEYWORD_EMBEDDINGS_TABLE, modelname
            )
            _require_compatible_specification(
                cursor, KEYWORD_EMBEDDINGS_TABLE, query_store._metadata()
            )
            count, minimum_dimensions, maximum_dimensions = (
                _stored_keyword_embedding_stats(cursor)
            )
            if count == 0:
                raise ValueError(
                    f"No keyword embeddings found for model {modelname!r}. Run "
                    "'scrapyrus embeddings ingest keywords' with the same model first."
                )
            if minimum_dimensions != maximum_dimensions:
                raise ValueError(
                    f"Stored keyword embeddings for model {modelname!r} have "
                    "inconsistent dimensions"
                )
            if metadata.embedding_size != minimum_dimensions:
                raise ValueError(
                    "Stored keyword vectors do not match the configured embedding "
                    f"size {metadata.embedding_size}"
                )

            embedding = tuple(query_store.provider.embed_query(query))
            if len(embedding) != minimum_dimensions:
                raise ValueError(
                    f"Query embedding has {len(embedding)} dimensions, but stored "
                    f"embeddings for model {modelname!r} have {minimum_dimensions}"
                )
            cursor.execute(
                _nearest_keywords_query(minimum_dimensions),
                {
                    "embedding": _vector_literal(embedding),
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
    _ensure_embedding_schema(cursor)


def _select_keywords(cursor: Any) -> tuple[str, ...]:
    try:
        cursor.execute(
            f"SELECT DISTINCT {_embedding_keyword_sql()} AS embedding_keyword "
            f"FROM {KEYWORDS_TABLE} WHERE keyword IS NOT NULL "
            "ORDER BY embedding_keyword"
        )
    except psycopg.errors.UndefinedTable as error:
        raise KeywordsUnavailableError(KEYWORDS_UNAVAILABLE_MESSAGE) from error
    return tuple(
        str(_row_value(row, "embedding_keyword", 0)) for row in cursor.fetchall()
    )


def _embedding_keyword_sql(table_alias: str | None = None) -> str:
    prefix = f"{table_alias}." if table_alias is not None else ""
    return (
        f"CASE WHEN {prefix}qualifier IS NULL THEN {prefix}keyword "
        f"ELSE {prefix}keyword || ', ' || {prefix}qualifier END"
    )


def _select_stored_keyword_dimensions(cursor: Any) -> dict[str, int]:
    cursor.execute(
        f"SELECT keyword, vector_dims(embedding) FROM {KEYWORD_EMBEDDINGS_TABLE} "
        "ORDER BY keyword"
    )
    return {
        str(_row_value(row, "keyword", 0)): int(_row_value(row, "vector_dims", 1))
        for row in cursor.fetchall()
    }


def _upsert_keyword_embedding(
    cursor: Any,
    *,
    keyword: str,
    embedding: tuple[float, ...],
) -> None:
    cursor.execute(
        f"""
INSERT INTO {KEYWORD_EMBEDDINGS_TABLE} (keyword, embedding)
VALUES (%(keyword)s, %(embedding)s::vector)
ON CONFLICT (keyword) DO UPDATE SET
    embedding = EXCLUDED.embedding,
    updated_at = now()
""",
        {
            "keyword": keyword,
            "embedding": _vector_literal(embedding),
        },
    )


def _delete_stale_keyword_embeddings(cursor: Any) -> None:
    cursor.execute(
        f"""
DELETE FROM {KEYWORD_EMBEDDINGS_TABLE} AS embedding
WHERE NOT EXISTS (
      SELECT 1 FROM {KEYWORDS_TABLE} AS source
      WHERE {_embedding_keyword_sql("source")} = embedding.keyword
  )
""",
    )


def _stored_keyword_embedding_stats(cursor: Any) -> tuple[int, int, int]:
    try:
        cursor.execute(
            f"""
SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding))
FROM {KEYWORD_EMBEDDINGS_TABLE}
"""
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
        "SELECT keyword, 1 - ({distance}) AS similarity "
        "FROM {table} "
        "ORDER BY {distance}, keyword LIMIT {top_k}"
    ).format(
        distance=distance,
        table=sql.Identifier(KEYWORD_EMBEDDINGS_TABLE),
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
