from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from tqdm import tqdm

from scrapyrus.transcriptions.core import TRANSCRIPTIONS_TABLE
from scrapyrus.transcriptions.embeddings import (
    EMBEDDING_TABLES,
    TRANSCRIPTION_EMBEDDINGS_TABLE,
    TRANSLATION_EMBEDDINGS_TABLE,
    _document_path,
    _row_value,
    embedding_table_metadata,
)


RECALL_RANKS = (1, 2, 3, 4, 5)
UNKNOWN_LANGUAGE = "unknown"
LANGUAGE_LABELS = {
    "ar": "arabic",
    "ara": "arabic",
    "cop": "coptic",
    "coptic": "coptic",
    "dem": "demotic",
    "demotic": "demotic",
    "egy": "egyptian",
    "egyptian": "egyptian",
    "el": "greek",
    "grc": "greek",
    "greek": "greek",
    "he": "hebrew",
    "heb": "hebrew",
    "hebrew": "hebrew",
    "la": "latin",
    "lat": "latin",
    "latin": "latin",
    "syr": "syriac",
    "syc": "syriac",
    "syriac": "syriac",
}


@dataclass(frozen=True)
class RetrievalQuery:
    tm_id: str
    source_path: str
    language: str | None
    embeddings: tuple[str, ...]

    @property
    def chunk_count(self) -> int:
        return len(self.embeddings)


@dataclass(frozen=True)
class LanguageEmbeddingEvaluation:
    language: str
    evaluated_count: int
    recall_hits: dict[int, int]
    reciprocal_rank_sum: float

    @property
    def recall_at(self) -> dict[int, float]:
        return {
            rank: hits / self.evaluated_count if self.evaluated_count else 0.0
            for rank, hits in sorted(self.recall_hits.items())
        }

    @property
    def mrr(self) -> float:
        return (
            self.reciprocal_rank_sum / self.evaluated_count
            if self.evaluated_count
            else 0.0
        )


@dataclass(frozen=True)
class ChunkEmbeddingEvaluation:
    chunk_group: str
    evaluated_count: int
    recall_hits: dict[int, int]
    reciprocal_rank_sum: float

    @property
    def recall_at(self) -> dict[int, float]:
        return {
            rank: hits / self.evaluated_count if self.evaluated_count else 0.0
            for rank, hits in sorted(self.recall_hits.items())
        }

    @property
    def mrr(self) -> float:
        return (
            self.reciprocal_rank_sum / self.evaluated_count
            if self.evaluated_count
            else 0.0
        )


@dataclass(frozen=True)
class EmbeddingEvaluation:
    modelname: str
    transcription_count: int
    translation_count: int
    embedding_dimensions: int
    evaluated_count: int
    recall_hits: dict[int, int]
    reciprocal_rank_sum: float
    language_results: dict[str, LanguageEmbeddingEvaluation]
    query_kind: str
    transcription_chunk_count: int = 0
    translation_chunk_count: int = 0
    chunked_transcription_count: int = 0
    chunked_translation_count: int = 0
    chunk_results: dict[str, ChunkEmbeddingEvaluation] | None = None

    @property
    def recall_at(self) -> dict[int, float]:
        return {
            rank: hits / self.evaluated_count if self.evaluated_count else 0.0
            for rank, hits in sorted(self.recall_hits.items())
        }

    @property
    def mrr(self) -> float:
        return (
            self.reciprocal_rank_sum / self.evaluated_count
            if self.evaluated_count
            else 0.0
        )

    def to_markdown(self, *, heading_level: int = 1) -> str:
        heading = "#" * heading_level
        subheading = "#" * (heading_level + 1)
        lines = [
            f"{heading} Embedding Evaluation: {_markdown_code(self.modelname)}",
            "",
            f"{subheading} Scope",
            "",
            f"- Model: {_markdown_code(self.modelname)}",
            f"- Query collection: {self.query_kind.title()}",
            f"- Transcription documents: {self.transcription_count}",
            f"- Translation documents: {self.translation_count}",
            f"- Transcription chunks: {self.transcription_chunk_count}",
            f"- Translation chunks: {self.translation_chunk_count}",
            f"- Multi-chunk transcriptions: {self.chunked_transcription_count}",
            f"- Multi-chunk translations: {self.chunked_translation_count}",
            f"- Paired documents evaluated: {self.evaluated_count}",
            "- Ranking: document-level MaxSim (best cosine similarity across all query/candidate chunk pairs).",
            "",
            f"{subheading} Metrics",
            "",
            "| Metric | Total | Queries | Score |",
            "| --- | ---: | ---: | ---: |",
        ]
        for rank, hits in sorted(self.recall_hits.items()):
            lines.append(
                f"| recall@{rank} | {hits} | {self.evaluated_count} | {self.recall_at[rank]:.2%} |"
            )
        lines.append(
            f"| MRR | {self.reciprocal_rank_sum:.4f} | {self.evaluated_count} | {self.mrr:.2%} |"
        )
        if self.language_results:
            lines.extend(
                [
                    "",
                    f"{subheading} Metrics by Language",
                    "",
                    "| Language | Metric | Total | Queries | Score |",
                    "| --- | --- | ---: | ---: | ---: |",
                ]
            )
            for result in sorted(
                self.language_results.values(), key=lambda item: item.language
            ):
                for rank, hits in sorted(result.recall_hits.items()):
                    lines.append(
                        f"| {result.language} | recall@{rank} | {hits} | "
                        f"{result.evaluated_count} | {result.recall_at[rank]:.2%} |"
                    )
                lines.append(
                    f"| {result.language} | MRR | {result.reciprocal_rank_sum:.4f} | "
                    f"{result.evaluated_count} | {result.mrr:.2%} |"
                )
        if self.chunk_results:
            lines.extend(
                [
                    "",
                    f"{subheading} Metrics by {self.query_kind[:-1].title()} Chunk Count",
                    "",
                    "| Chunk group | Metric | Total | Queries | Score |",
                    "| --- | --- | ---: | ---: | ---: |",
                ]
            )
            for result in self.chunk_results.values():
                for rank, hits in sorted(result.recall_hits.items()):
                    lines.append(
                        f"| {result.chunk_group} | recall@{rank} | {hits} | "
                        f"{result.evaluated_count} | {result.recall_at[rank]:.2%} |"
                    )
                lines.append(
                    f"| {result.chunk_group} | MRR | {result.reciprocal_rank_sum:.4f} | "
                    f"{result.evaluated_count} | {result.mrr:.2%} |"
                )
        return "\n".join(lines) + "\n"


def evaluate_embeddings(
    conninfo: str = "",
    /,
    *,
    query_kind: str,
    progressbar: bool = True,
    sample: int | None = None,
    seed: int = 0,
) -> EmbeddingEvaluation:
    """Evaluate cross-collection retrieval for the tables' unique model.

    When ``sample`` is set, use the same deterministic paired-record selection
    as embedding ingestion and restrict queries and candidates to that scope.
    The Markdown result is written to standard output.
    """

    _evaluation_tables(query_kind)
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            tm_ids = _select_sample_tm_ids(cursor, sample=sample, seed=seed)
            transcription_metadata = embedding_table_metadata(
                cursor, TRANSCRIPTION_EMBEDDINGS_TABLE
            )
            translation_metadata = embedding_table_metadata(
                cursor, TRANSLATION_EMBEDDINGS_TABLE
            )
            if transcription_metadata is None or translation_metadata is None:
                raise ValueError(
                    "Both transcription and translation embeddings must be configured"
                )
            if transcription_metadata.model_name != translation_metadata.model_name:
                raise ValueError(
                    "Transcription and translation embeddings use different models: "
                    f"{transcription_metadata.model_name!r} and "
                    f"{translation_metadata.model_name!r}"
                )
            if transcription_metadata.embedding_size is None:
                raise ValueError("Transcription embeddings do not have a stored size")
            if translation_metadata.embedding_size is None:
                raise ValueError("Translation embeddings do not have a stored size")
            if (
                transcription_metadata.embedding_size
                != translation_metadata.embedding_size
            ):
                raise ValueError(
                    "Transcription and translation embeddings have different sizes: "
                    f"{transcription_metadata.embedding_size} and "
                    f"{translation_metadata.embedding_size}"
                )
            evaluation = _evaluate_embeddings_model(
                cursor,
                transcription_metadata.model_name,
                query_kind=query_kind,
                progressbar=progressbar,
                tm_ids=tm_ids,
            )
    print(evaluation.to_markdown(), end="")
    return evaluation


def evaluate_embeddings_model(
    conninfo: str = "",
    /,
    *,
    query_kind: str,
    modelname: str,
    output_file: str | Path | None = None,
    progressbar: bool = True,
    sample: int | None = None,
    seed: int = 0,
) -> EmbeddingEvaluation:
    """Evaluate cross-collection retrieval for one stored model."""

    _evaluation_tables(query_kind)
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            tm_ids = _select_sample_tm_ids(cursor, sample=sample, seed=seed)
            evaluation = _evaluate_embeddings_model(
                cursor,
                modelname,
                query_kind=query_kind,
                progressbar=progressbar,
                tm_ids=tm_ids,
            )

    if output_file is not None:
        Path(output_file).write_text(evaluation.to_markdown(), encoding="utf-8")
    return evaluation


def _evaluate_embeddings_model(
    cursor: Any,
    modelname: str,
    *,
    query_kind: str,
    progressbar: bool,
    tm_ids: tuple[str, ...] | None = None,
) -> EmbeddingEvaluation:
    query_table, candidate_table = _evaluation_tables(query_kind)
    transcription_stats = _collection_stats(
        cursor, TRANSCRIPTION_EMBEDDINGS_TABLE, tm_ids=tm_ids
    )
    translation_stats = _collection_stats(
        cursor, TRANSLATION_EMBEDDINGS_TABLE, tm_ids=tm_ids
    )
    if not transcription_stats.document_count:
        raise ValueError(f"No transcription embeddings found for model {modelname!r}")
    if not translation_stats.document_count:
        raise ValueError(f"No translation embeddings found for model {modelname!r}")
    if transcription_stats.dimensions != translation_stats.dimensions:
        raise ValueError(
            f"Transcription embeddings have {transcription_stats.dimensions} dimensions, "
            f"but translation embeddings have {translation_stats.dimensions}"
        )
    queries = _select_retrieval_queries(
        cursor,
        query_table=query_table,
        candidate_table=candidate_table,
        tm_ids=tm_ids,
    )
    if not queries:
        raise ValueError(
            "No documents have both transcription and translation embeddings for the selected model"
        )
    hits = {rank: 0 for rank in RECALL_RANKS}
    reciprocal_rank_sum = 0.0
    language_counts: dict[str, int] = {}
    language_hits: dict[str, dict[int, int]] = {}
    language_reciprocal_rank_sums: dict[str, float] = {}
    chunk_counts: dict[str, int] = {}
    chunk_hits: dict[str, dict[int, int]] = {}
    chunk_reciprocal_rank_sums: dict[str, float] = {}
    query_iterator = (
        tqdm(
            queries,
            total=len(queries),
            unit="document",
            desc=f"Evaluating {modelname}",
        )
        if progressbar
        else queries
    )
    for query in query_iterator:
        language = _language_label(query.language)
        chunk_group = _chunk_group(query.chunk_count)
        language_counts[language] = language_counts.get(language, 0) + 1
        chunk_counts[chunk_group] = chunk_counts.get(chunk_group, 0) + 1
        query_hits = language_hits.setdefault(
            language, {rank: 0 for rank in RECALL_RANKS}
        )
        query_chunk_hits = chunk_hits.setdefault(
            chunk_group, {rank: 0 for rank in RECALL_RANKS}
        )
        language_reciprocal_rank_sums.setdefault(language, 0.0)
        chunk_reciprocal_rank_sums.setdefault(chunk_group, 0.0)
        candidates = _select_nearest_candidates(
            cursor,
            query.embeddings,
            max(RECALL_RANKS),
            candidate_table=candidate_table,
            tm_ids=tm_ids,
        )
        reciprocal_rank = _candidate_reciprocal_rank(candidates, query.tm_id)
        if reciprocal_rank == 0.0:
            reciprocal_rank = _select_reciprocal_rank(
                cursor,
                query.embeddings,
                query.tm_id,
                candidate_table=candidate_table,
                tm_ids=tm_ids,
            )
        reciprocal_rank_sum += reciprocal_rank
        language_reciprocal_rank_sums[language] += reciprocal_rank
        chunk_reciprocal_rank_sums[chunk_group] += reciprocal_rank
        for rank in RECALL_RANKS:
            if any(candidate.tm_id == query.tm_id for candidate in candidates[:rank]):
                hits[rank] += 1
                query_hits[rank] += 1
                query_chunk_hits[rank] += 1

    return EmbeddingEvaluation(
        modelname,
        transcription_stats.document_count,
        translation_stats.document_count,
        int(transcription_stats.dimensions),
        len(queries),
        hits,
        reciprocal_rank_sum,
        {
            language: LanguageEmbeddingEvaluation(
                language,
                language_counts[language],
                language_hits[language],
                language_reciprocal_rank_sums[language],
            )
            for language in sorted(language_counts)
        },
        query_kind,
        transcription_stats.chunk_count,
        translation_stats.chunk_count,
        transcription_stats.chunked_document_count,
        translation_stats.chunked_document_count,
        {
            chunk_group: ChunkEmbeddingEvaluation(
                chunk_group,
                chunk_counts[chunk_group],
                chunk_hits[chunk_group],
                chunk_reciprocal_rank_sums[chunk_group],
            )
            for chunk_group in ("1 chunk", "2-3 chunks", "4+ chunks")
            if chunk_group in chunk_counts
        },
    )


def _evaluation_tables(query_kind: str) -> tuple[str, str]:
    if query_kind not in EMBEDDING_TABLES:
        raise ValueError(f"Unknown embedding query kind {query_kind!r}")
    candidate_kind = (
        "translations" if query_kind == "transcriptions" else "transcriptions"
    )
    return EMBEDDING_TABLES[query_kind], EMBEDDING_TABLES[candidate_kind]


def _select_sample_tm_ids(
    cursor: Any, *, sample: int | None, seed: int
) -> tuple[str, ...] | None:
    if sample is None:
        return None
    cursor.execute(
        f"""
SELECT tm_id
FROM {TRANSCRIPTIONS_TABLE}
GROUP BY tm_id
HAVING bool_or(type = 'transcription')
   AND bool_or(type = 'translation')
ORDER BY md5(tm_id::text || ':' || (%s)::text), tm_id
LIMIT %s
""",
        (seed, sample),
    )
    return tuple(str(_row_value(row, "tm_id", 0)) for row in cursor.fetchall())


@dataclass(frozen=True)
class _CollectionStats:
    document_count: int
    chunk_count: int
    chunked_document_count: int
    dimensions: int | None


def _collection_stats(
    cursor: Any,
    table: str,
    *,
    tm_ids: tuple[str, ...] | None = None,
) -> _CollectionStats:
    scope_sql = " AND tm_id = ANY(%s)" if tm_ids is not None else ""
    cursor.execute(
        f"""
SELECT count(*) AS document_count,
       COALESCE(sum(document.chunk_count), 0) AS chunk_count,
       count(*) FILTER (WHERE document.chunk_count > 1) AS chunked_document_count,
       min(document.minimum_dimensions) AS minimum_dimensions,
       max(document.maximum_dimensions) AS maximum_dimensions
FROM (
    SELECT tm_id,
           count(*) AS chunk_count,
           min(vector_dims(embedding)) AS minimum_dimensions,
           max(vector_dims(embedding)) AS maximum_dimensions
    FROM {table}
    WHERE true
    {scope_sql}
    GROUP BY tm_id
) AS document
""",
        (list(tm_ids),) if tm_ids is not None else None,
    )
    row = cursor.fetchone()
    minimum_dimensions = _row_value(row, "minimum_dimensions", 3)
    maximum_dimensions = _row_value(row, "maximum_dimensions", 4)
    if minimum_dimensions != maximum_dimensions:
        raise ValueError(f"{table} contains vectors with inconsistent dimensions")
    return _CollectionStats(
        int(_row_value(row, "document_count", 0)),
        int(_row_value(row, "chunk_count", 1)),
        int(_row_value(row, "chunked_document_count", 2)),
        minimum_dimensions,
    )


def _select_retrieval_queries(
    cursor: Any,
    *,
    query_table: str,
    candidate_table: str,
    tm_ids: tuple[str, ...] | None = None,
) -> tuple[RetrievalQuery, ...]:
    scope_sql = "  AND queries.tm_id = ANY(%s)" if tm_ids is not None else ""
    cursor.execute(
        f"""
SELECT queries.tm_id,
       min(queries.source_path) AS source_path,
       min(queries.language) AS language,
       array_agg(
           queries.embedding::text
           ORDER BY queries.xml_id, queries.chunk_index
       ) AS embeddings
FROM {query_table} AS queries
WHERE true
{scope_sql}
  AND EXISTS (
      SELECT 1 FROM {candidate_table} AS candidates
      WHERE candidates.tm_id = queries.tm_id
  )
GROUP BY queries.tm_id
ORDER BY queries.tm_id
""",
        (list(tm_ids),) if tm_ids is not None else None,
    )
    return tuple(
        RetrievalQuery(
            str(_row_value(row, "tm_id", 0)),
            _document_path(_row_value(row, "source_path", 1)),
            _row_value(row, "language", 2),
            _embedding_values(_row_value(row, "embeddings", 3)),
        )
        for row in cursor.fetchall()
    )


@dataclass(frozen=True)
class _Candidate:
    tm_id: str
    document_path: str


def _select_nearest_candidates(
    cursor: Any,
    embeddings: tuple[str, ...],
    limit: int,
    *,
    candidate_table: str,
    tm_ids: tuple[str, ...] | None = None,
) -> tuple[_Candidate, ...]:
    scope_sql = (
        "      AND candidates.tm_id = ANY(%(tm_ids)s)" if tm_ids is not None else ""
    )
    cursor.execute(
        f"""
WITH query_chunks AS (
    SELECT value::vector AS embedding
    FROM unnest(%(embeddings)s::text[]) AS value
), candidate_documents AS (
    SELECT candidates.tm_id,
           min(candidates.source_path) AS source_path,
           min(candidates.embedding <=> query_chunks.embedding) AS distance
    FROM {candidate_table} AS candidates
    CROSS JOIN query_chunks
    WHERE true
{scope_sql}
    GROUP BY candidates.tm_id
)
SELECT tm_id, source_path
FROM candidate_documents
ORDER BY distance, tm_id, source_path
LIMIT %(limit)s
""",
        {
            "embeddings": list(embeddings),
            "limit": limit,
            **({"tm_ids": list(tm_ids)} if tm_ids is not None else {}),
        },
    )
    return tuple(
        _Candidate(
            str(_row_value(row, "tm_id", 0)),
            _document_path(_row_value(row, "source_path", 1)),
        )
        for row in cursor.fetchall()
    )


def _candidate_reciprocal_rank(candidates: tuple[_Candidate, ...], tm_id: str) -> float:
    for rank, candidate in enumerate(candidates, start=1):
        if candidate.tm_id == tm_id:
            return 1.0 / rank
    return 0.0


def _select_reciprocal_rank(
    cursor: Any,
    embeddings: tuple[str, ...],
    tm_id: str,
    *,
    candidate_table: str,
    tm_ids: tuple[str, ...] | None = None,
) -> float:
    scope_sql = (
        "          AND candidates.tm_id = ANY(%(tm_ids)s)" if tm_ids is not None else ""
    )
    cursor.execute(
        f"""
SELECT ranked.rank
FROM (
    SELECT candidate_documents.tm_id,
           row_number() OVER (
               ORDER BY candidate_documents.distance,
                        candidate_documents.tm_id,
                        candidate_documents.source_path
           ) AS rank
    FROM (
        SELECT candidates.tm_id,
               min(candidates.source_path) AS source_path,
               min(candidates.embedding <=> query_chunks.embedding) AS distance
        FROM {candidate_table} AS candidates
        CROSS JOIN (
            SELECT value::vector AS embedding
            FROM unnest(%(embeddings)s::text[]) AS value
        ) AS query_chunks
        WHERE true
{scope_sql}
        GROUP BY candidates.tm_id
    ) AS candidate_documents
) AS ranked
WHERE ranked.tm_id = %(tm_id)s
""",
        {
            "embeddings": list(embeddings),
            "tm_id": tm_id,
            **({"tm_ids": list(tm_ids)} if tm_ids is not None else {}),
        },
    )
    row = cursor.fetchone()
    if row is None:
        return 0.0
    rank = int(_row_value(row, "rank", 0))
    return 1.0 / rank if rank else 0.0


def _embedding_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(str(embedding) for embedding in value)


def _chunk_group(chunk_count: int) -> str:
    if chunk_count == 1:
        return "1 chunk"
    if chunk_count <= 3:
        return "2-3 chunks"
    return "4+ chunks"


def _language_label(language: str | None) -> str:
    if language is None:
        return UNKNOWN_LANGUAGE
    normalized = "-".join(language.strip().lower().replace("_", "-").split())
    return (
        LANGUAGE_LABELS.get(normalized.split("-", 1)[0], normalized)
        if normalized
        else UNKNOWN_LANGUAGE
    )


def _markdown_code(value: str) -> str:
    return f"`{value}`" if "`" not in value else f"`` {value} ``"
