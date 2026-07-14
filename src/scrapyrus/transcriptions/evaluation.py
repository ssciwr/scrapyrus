from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from tqdm import tqdm

from scrapyrus.transcriptions.embeddings import (
    TRANSCRIPTION_EMBEDDINGS_TABLE,
    TRANSLATION_EMBEDDINGS_TABLE,
    _document_path,
    _row_value,
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
class TranslationRetrievalQuery:
    tm_id: str
    transcription_path: str
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
                    f"{subheading} Metrics by Transcription Chunk Count",
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


@dataclass(frozen=True)
class EmbeddingsEvaluation:
    results: tuple[EmbeddingEvaluation, ...]

    def to_markdown(self) -> str:
        lines = [
            "# Embedding Evaluations",
            "",
            "## Summary",
            "",
            "| Model | Transcriptions | Translations | Paired | Dimensions | "
            + " | ".join(f"recall@{rank}" for rank in RECALL_RANKS)
            + " |",
            "| --- | ---: | ---: | ---: | ---: | "
            + " | ".join("---:" for _ in RECALL_RANKS)
            + " |",
        ]
        for result in self.results:
            lines.append(
                f"| {_markdown_code(result.modelname)} | {result.transcription_count} | "
                f"{result.translation_count} | {result.evaluated_count} | "
                f"{result.embedding_dimensions} | "
                + " | ".join(f"{result.recall_at[rank]:.2%}" for rank in RECALL_RANKS)
                + " |"
            )
        for result in self.results:
            lines.extend(["", result.to_markdown(heading_level=2).rstrip()])
        return "\n".join(lines) + "\n"


def evaluate_embeddings(
    conninfo: str = "",
    /,
    *,
    output_file: str | Path | None = None,
    progressbar: bool = True,
) -> EmbeddingsEvaluation:
    """Evaluate transcription-to-translation retrieval for every stored model."""

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            modelnames = _select_embedding_modelnames(cursor)
            if not modelnames:
                raise ValueError(
                    "No models have both transcription and translation embeddings"
                )
            results = tuple(
                _evaluate_embeddings_model(cursor, modelname, progressbar=progressbar)
                for modelname in modelnames
            )

    evaluation = EmbeddingsEvaluation(results)
    if output_file is not None:
        Path(output_file).write_text(evaluation.to_markdown(), encoding="utf-8")
    return evaluation


def evaluate_embeddings_model(
    conninfo: str = "",
    /,
    *,
    modelname: str,
    output_file: str | Path | None = None,
    progressbar: bool = True,
) -> EmbeddingEvaluation:
    """Evaluate transcription-to-translation retrieval for one stored model."""

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            evaluation = _evaluate_embeddings_model(
                cursor, modelname, progressbar=progressbar
            )

    if output_file is not None:
        Path(output_file).write_text(evaluation.to_markdown(), encoding="utf-8")
    return evaluation


def _evaluate_embeddings_model(
    cursor: Any, modelname: str, *, progressbar: bool
) -> EmbeddingEvaluation:
    transcription_stats = _collection_stats(
        cursor, TRANSCRIPTION_EMBEDDINGS_TABLE, modelname
    )
    translation_stats = _collection_stats(
        cursor, TRANSLATION_EMBEDDINGS_TABLE, modelname
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
    queries = _select_translation_retrieval_queries(cursor, modelname)
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
        candidates = _select_nearest_translations(
            cursor, modelname, query.embeddings, max(RECALL_RANKS)
        )
        reciprocal_rank = _candidate_reciprocal_rank(candidates, query.tm_id)
        if reciprocal_rank == 0.0:
            reciprocal_rank = _select_translation_reciprocal_rank(
                cursor, modelname, query.embeddings, query.tm_id
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


def _select_embedding_modelnames(cursor: Any) -> tuple[str, ...]:
    cursor.execute(
        f"""
SELECT transcriptions.model_name
FROM {TRANSCRIPTION_EMBEDDINGS_TABLE} AS transcriptions
WHERE EXISTS (
    SELECT 1 FROM {TRANSLATION_EMBEDDINGS_TABLE} AS translations
    WHERE translations.model_name = transcriptions.model_name
)
GROUP BY transcriptions.model_name
ORDER BY transcriptions.model_name
"""
    )
    return tuple(str(_row_value(row, "model_name", 0)) for row in cursor.fetchall())


@dataclass(frozen=True)
class _CollectionStats:
    document_count: int
    chunk_count: int
    chunked_document_count: int
    dimensions: int | None


def _collection_stats(cursor: Any, table: str, modelname: str) -> _CollectionStats:
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
    WHERE model_name = %s
    GROUP BY tm_id
) AS document
""",
        (modelname,),
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


def _select_translation_retrieval_queries(
    cursor: Any, modelname: str
) -> tuple[TranslationRetrievalQuery, ...]:
    cursor.execute(
        f"""
SELECT transcriptions.tm_id,
       min(transcriptions.source_path) AS transcription_path,
       min(transcriptions.language) AS language,
       array_agg(
           transcriptions.embedding::text
           ORDER BY transcriptions.xml_id, transcriptions.chunk_index
       ) AS embeddings
FROM {TRANSCRIPTION_EMBEDDINGS_TABLE} AS transcriptions
WHERE transcriptions.model_name = %s
  AND EXISTS (
      SELECT 1 FROM {TRANSLATION_EMBEDDINGS_TABLE} AS translations
      WHERE translations.model_name = transcriptions.model_name
        AND translations.tm_id = transcriptions.tm_id
  )
GROUP BY transcriptions.tm_id
ORDER BY transcriptions.tm_id
""",
        (modelname,),
    )
    return tuple(
        TranslationRetrievalQuery(
            str(_row_value(row, "tm_id", 0)),
            _document_path(_row_value(row, "transcription_path", 1)),
            _row_value(row, "language", 2),
            _embedding_values(_row_value(row, "embeddings", 3)),
        )
        for row in cursor.fetchall()
    )


@dataclass(frozen=True)
class _TranslationCandidate:
    tm_id: str
    document_path: str


def _select_nearest_translations(
    cursor: Any, modelname: str, embeddings: tuple[str, ...], limit: int
) -> tuple[_TranslationCandidate, ...]:
    cursor.execute(
        f"""
WITH query_chunks AS (
    SELECT value::vector AS embedding
    FROM unnest(%(embeddings)s::text[]) AS value
), candidate_documents AS (
    SELECT candidates.tm_id,
           min(candidates.source_path) AS source_path,
           min(candidates.embedding <=> query_chunks.embedding) AS distance
    FROM {TRANSLATION_EMBEDDINGS_TABLE} AS candidates
    CROSS JOIN query_chunks
    WHERE candidates.model_name = %(model_name)s
    GROUP BY candidates.tm_id
)
SELECT tm_id, source_path
FROM candidate_documents
ORDER BY distance, tm_id, source_path
LIMIT %(limit)s
""",
        {"model_name": modelname, "embeddings": list(embeddings), "limit": limit},
    )
    return tuple(
        _TranslationCandidate(
            str(_row_value(row, "tm_id", 0)),
            _document_path(_row_value(row, "source_path", 1)),
        )
        for row in cursor.fetchall()
    )


def _candidate_reciprocal_rank(
    candidates: tuple[_TranslationCandidate, ...], tm_id: str
) -> float:
    for rank, candidate in enumerate(candidates, start=1):
        if candidate.tm_id == tm_id:
            return 1.0 / rank
    return 0.0


def _select_translation_reciprocal_rank(
    cursor: Any, modelname: str, embeddings: tuple[str, ...], tm_id: str
) -> float:
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
        FROM {TRANSLATION_EMBEDDINGS_TABLE} AS candidates
        CROSS JOIN (
            SELECT value::vector AS embedding
            FROM unnest(%(embeddings)s::text[]) AS value
        ) AS query_chunks
        WHERE candidates.model_name = %(model_name)s
        GROUP BY candidates.tm_id
    ) AS candidate_documents
) AS ranked
WHERE ranked.tm_id = %(tm_id)s
""",
        {"model_name": modelname, "embeddings": list(embeddings), "tm_id": tm_id},
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
