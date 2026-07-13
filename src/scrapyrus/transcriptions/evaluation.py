from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

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
    embedding: str


@dataclass(frozen=True)
class LanguageEmbeddingEvaluation:
    language: str
    evaluated_count: int
    recall_hits: dict[int, int]

    @property
    def recall_at(self) -> dict[int, float]:
        return {
            rank: hits / self.evaluated_count if self.evaluated_count else 0.0
            for rank, hits in sorted(self.recall_hits.items())
        }


@dataclass(frozen=True)
class EmbeddingEvaluation:
    modelname: str
    transcription_count: int
    translation_count: int
    embedding_dimensions: int
    evaluated_count: int
    recall_hits: dict[int, int]
    language_results: dict[str, LanguageEmbeddingEvaluation]

    @property
    def recall_at(self) -> dict[int, float]:
        return {
            rank: hits / self.evaluated_count if self.evaluated_count else 0.0
            for rank, hits in sorted(self.recall_hits.items())
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Embedding Evaluation: {_markdown_code(self.modelname)}",
            "",
            "## Scope",
            "",
            f"- Model: {_markdown_code(self.modelname)}",
            f"- Transcription documents: {self.transcription_count}",
            f"- Translation documents: {self.translation_count}",
            f"- Paired documents evaluated: {self.evaluated_count}",
            "- Ranking: transcription embedding against translation embeddings by cosine distance.",
            "",
            "## Metrics",
            "",
            "| Metric | Hits | Queries | Score |",
            "| --- | ---: | ---: | ---: |",
        ]
        for rank, hits in sorted(self.recall_hits.items()):
            lines.append(
                f"| recall@{rank} | {hits} | {self.evaluated_count} | {self.recall_at[rank]:.2%} |"
            )
        if self.language_results:
            lines.extend(
                [
                    "",
                    "## Metrics by Language",
                    "",
                    "| Language | Metric | Hits | Queries | Score |",
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
        return "\n".join(lines) + "\n"


def evaluate_embeddings_model(
    conninfo: str = "", /, *, modelname: str, output_file: str | Path | None = None
) -> EmbeddingEvaluation:
    """Evaluate transcription-to-translation retrieval for one stored model."""

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            transcription_count, transcription_dimensions = _collection_stats(
                cursor, TRANSCRIPTION_EMBEDDINGS_TABLE, modelname
            )
            translation_count, translation_dimensions = _collection_stats(
                cursor, TRANSLATION_EMBEDDINGS_TABLE, modelname
            )
            if not transcription_count:
                raise ValueError(
                    f"No transcription embeddings found for model {modelname!r}"
                )
            if not translation_count:
                raise ValueError(
                    f"No translation embeddings found for model {modelname!r}"
                )
            if transcription_dimensions != translation_dimensions:
                raise ValueError(
                    f"Transcription embeddings have {transcription_dimensions} dimensions, "
                    f"but translation embeddings have {translation_dimensions}"
                )
            queries = _select_translation_retrieval_queries(cursor, modelname)
            if not queries:
                raise ValueError(
                    "No documents have both transcription and translation embeddings for the selected model"
                )
            hits = {rank: 0 for rank in RECALL_RANKS}
            language_counts: dict[str, int] = {}
            language_hits: dict[str, dict[int, int]] = {}
            for query in queries:
                language = _language_label(query.language)
                language_counts[language] = language_counts.get(language, 0) + 1
                query_hits = language_hits.setdefault(
                    language, {rank: 0 for rank in RECALL_RANKS}
                )
                candidates = _select_nearest_translations(
                    cursor, modelname, query.embedding, max(RECALL_RANKS)
                )
                for rank in RECALL_RANKS:
                    if any(
                        candidate.tm_id == query.tm_id
                        for candidate in candidates[:rank]
                    ):
                        hits[rank] += 1
                        query_hits[rank] += 1

    evaluation = EmbeddingEvaluation(
        modelname,
        transcription_count,
        translation_count,
        int(transcription_dimensions),
        len(queries),
        hits,
        {
            language: LanguageEmbeddingEvaluation(
                language, language_counts[language], language_hits[language]
            )
            for language in sorted(language_counts)
        },
    )
    if output_file is not None:
        Path(output_file).write_text(evaluation.to_markdown(), encoding="utf-8")
    return evaluation


def _collection_stats(
    cursor: Any, table: str, modelname: str
) -> tuple[int, int | None]:
    cursor.execute(
        f"SELECT count(*) AS count, min(vector_dims(embedding)) AS dimensions "
        f"FROM {table} WHERE model_name = %s",
        (modelname,),
    )
    row = cursor.fetchone()
    return int(_row_value(row, "count", 0)), _row_value(row, "dimensions", 1)


def _select_translation_retrieval_queries(
    cursor: Any, modelname: str
) -> tuple[TranslationRetrievalQuery, ...]:
    cursor.execute(
        f"""
SELECT transcriptions.tm_id,
       transcriptions.source_path AS transcription_path,
       transcriptions.language AS language,
       transcriptions.embedding::text AS embedding
FROM {TRANSCRIPTION_EMBEDDINGS_TABLE} AS transcriptions
WHERE transcriptions.model_name = %s
  AND EXISTS (
      SELECT 1 FROM {TRANSLATION_EMBEDDINGS_TABLE} AS translations
      WHERE translations.model_name = transcriptions.model_name
        AND translations.tm_id = transcriptions.tm_id
  )
ORDER BY transcriptions.tm_id, transcriptions.xml_id
""",
        (modelname,),
    )
    return tuple(
        TranslationRetrievalQuery(
            str(_row_value(row, "tm_id", 0)),
            _document_path(_row_value(row, "transcription_path", 1)),
            _row_value(row, "language", 2),
            str(_row_value(row, "embedding", 3)),
        )
        for row in cursor.fetchall()
    )


@dataclass(frozen=True)
class _TranslationCandidate:
    tm_id: str
    document_path: str


def _select_nearest_translations(
    cursor: Any, modelname: str, embedding: str, limit: int
) -> tuple[_TranslationCandidate, ...]:
    cursor.execute(
        f"""
SELECT tm_id, source_path FROM {TRANSLATION_EMBEDDINGS_TABLE}
WHERE model_name = %(model_name)s
ORDER BY embedding <=> %(embedding)s::vector, tm_id, source_path
LIMIT %(limit)s
""",
        {"model_name": modelname, "embedding": embedding, "limit": limit},
    )
    return tuple(
        _TranslationCandidate(
            str(_row_value(row, "tm_id", 0)),
            _document_path(_row_value(row, "source_path", 1)),
        )
        for row in cursor.fetchall()
    )


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
