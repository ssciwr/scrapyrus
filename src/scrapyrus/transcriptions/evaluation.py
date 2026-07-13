from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from scrapyrus.transcriptions.embeddings import (
    EmbeddingConfiguration,
    _configuration_params,
    _document_path,
    _row_value,
)
from scrapyrus.transcriptions.core import transcription_language


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
class EvaluationEmbeddingConfiguration:
    """A stored embedding configuration used for evaluation."""

    id: int
    configuration: EmbeddingConfiguration
    embedding_dimensions: int
    document_count: int


@dataclass(frozen=True)
class TranslationRetrievalQuery:
    """One transcription embedding query with an expected translation target."""

    tm_id: str
    transcription_path: str
    translation_path: str
    embedding: str


@dataclass(frozen=True)
class LanguageEmbeddingEvaluation:
    """Summary statistics for one transcription language."""

    language: str
    evaluated_count: int
    recall_hits: dict[int, int]

    @property
    def recall_at(self) -> dict[int, float]:
        if self.evaluated_count == 0:
            return {rank: 0.0 for rank in sorted(self.recall_hits)}
        return {
            rank: hits / self.evaluated_count
            for rank, hits in sorted(self.recall_hits.items())
        }


@dataclass(frozen=True)
class EmbeddingEvaluation:
    """Summary statistics for transcription-to-translation retrieval."""

    modelname: str
    transcription_configuration: EvaluationEmbeddingConfiguration
    translation_configuration: EvaluationEmbeddingConfiguration
    evaluated_count: int
    recall_hits: dict[int, int]
    language_results: dict[str, LanguageEmbeddingEvaluation]

    @property
    def recall_at(self) -> dict[int, float]:
        if self.evaluated_count == 0:
            return {rank: 0.0 for rank in sorted(self.recall_hits)}
        return {
            rank: hits / self.evaluated_count
            for rank, hits in sorted(self.recall_hits.items())
        }

    def to_markdown(self) -> str:
        """Render the evaluation as a Markdown report."""

        lines = [
            f"# Embedding Evaluation: {_markdown_code(self.modelname)}",
            "",
            "## Scope",
            "",
            f"- Model: {_markdown_code(self.modelname)}",
            (f"- Transcription configuration: `{self.transcription_configuration.id}`"),
            (f"- Translation configuration: `{self.translation_configuration.id}`"),
            f"- Transcription documents: {self.transcription_configuration.document_count}",
            f"- Translation documents: {self.translation_configuration.document_count}",
            f"- Paired documents evaluated: {self.evaluated_count}",
            "- Ranking: transcription embedding against translation embeddings by cosine distance.",
            "",
            "## Metrics",
            "",
            "| Metric | Hits | Queries | Score |",
            "| --- | ---: | ---: | ---: |",
        ]

        for rank, hits in sorted(self.recall_hits.items()):
            score = self.recall_at[rank]
            lines.append(
                f"| recall@{rank} | {hits} | {self.evaluated_count} | {score:.2%} |"
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
                self.language_results.values(), key=lambda result: result.language
            ):
                for rank, hits in sorted(result.recall_hits.items()):
                    score = result.recall_at[rank]
                    lines.append(
                        f"| {result.language} | recall@{rank} | {hits} | "
                        f"{result.evaluated_count} | {score:.2%} |"
                    )

        return "\n".join(lines) + "\n"


def evaluate_embeddings_model(
    conninfo: str = "",
    /,
    *,
    modelname: str,
    idp_data: str | Path = Path("idp.data"),
    output_file: str | Path | None = None,
    abbrev: bool = False,
    break_on_gap: bool = False,
    lost: bool = False,
    unclear: bool = False,
    regularize: bool = False,
) -> EmbeddingEvaluation:
    """Evaluate how well a model aligns transcriptions with translations.

    The evaluation treats each stored transcription embedding as a query and
    considers it successful at rank ``k`` when the translation embedding with
    the same ``tm_id`` appears in the top ``k`` nearest translation embeddings.
    """

    transcription_configuration = EmbeddingConfiguration(
        modelname,
        abbrev=abbrev,
        break_on_gap=break_on_gap,
        lost=lost,
        unclear=unclear,
        regularize=regularize,
    )
    translation_configuration = EmbeddingConfiguration(
        modelname,
        translation=True,
    )

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            transcription = _select_evaluation_configuration(
                cursor,
                transcription_configuration,
            )
            if transcription is None:
                raise ValueError(
                    "No transcription embedding configuration found for "
                    f"model {modelname!r}"
                )

            translation = _select_evaluation_configuration(
                cursor,
                translation_configuration,
            )
            if translation is None:
                raise ValueError(
                    "No default translation embedding configuration found for "
                    f"model {modelname!r}"
                )

            if transcription.embedding_dimensions != translation.embedding_dimensions:
                raise ValueError(
                    f"Transcription configuration {transcription.id} has "
                    f"{transcription.embedding_dimensions} dimensions, but "
                    f"translation configuration {translation.id} has "
                    f"{translation.embedding_dimensions}"
                )

            queries = _select_translation_retrieval_queries(
                cursor,
                transcription.id,
                translation.id,
            )
            if not queries:
                raise ValueError(
                    "No documents have both transcription and translation "
                    "embeddings for the selected model"
                )

            source_root = Path(idp_data)
            hits = {rank: 0 for rank in RECALL_RANKS}
            language_counts: dict[str, int] = {}
            language_hits: dict[str, dict[int, int]] = {}
            language_cache: dict[str, str] = {}
            for query in queries:
                language = _query_language(source_root, query, language_cache)
                language_counts[language] = language_counts.get(language, 0) + 1
                query_language_hits = language_hits.setdefault(
                    language,
                    {rank: 0 for rank in RECALL_RANKS},
                )
                candidates = _select_nearest_translations(
                    cursor,
                    translation.id,
                    query.embedding,
                    max(RECALL_RANKS),
                )
                for rank in RECALL_RANKS:
                    if any(
                        candidate.tm_id == query.tm_id
                        for candidate in candidates[:rank]
                    ):
                        hits[rank] += 1
                        query_language_hits[rank] += 1

    evaluation = EmbeddingEvaluation(
        modelname=modelname,
        transcription_configuration=transcription,
        translation_configuration=translation,
        evaluated_count=len(queries),
        recall_hits=hits,
        language_results={
            language: LanguageEmbeddingEvaluation(
                language=language,
                evaluated_count=language_counts[language],
                recall_hits=language_hits[language],
            )
            for language in sorted(language_counts)
        },
    )

    if output_file is not None:
        Path(output_file).write_text(evaluation.to_markdown(), encoding="utf-8")

    return evaluation


def _query_language(
    idp_data: Path,
    query: TranslationRetrievalQuery,
    cache: dict[str, str],
) -> str:
    transcription_path = idp_data / query.transcription_path
    cache_key = transcription_path.as_posix()
    if cache_key not in cache:
        cache[cache_key] = _language_label(
            _source_transcription_language(transcription_path)
        )
    return cache[cache_key]


def _source_transcription_language(transcription_path: Path) -> str | None:
    try:
        if not transcription_path.is_file():
            return None
    except OSError:
        return None

    return transcription_language(transcription_path)


def _language_label(language: str | None) -> str:
    if language is None:
        return UNKNOWN_LANGUAGE

    normalized = "-".join(language.strip().lower().replace("_", "-").split())
    if not normalized:
        return UNKNOWN_LANGUAGE

    return LANGUAGE_LABELS.get(normalized.split("-", 1)[0], normalized)


def _select_evaluation_configuration(
    cursor: Any,
    configuration: EmbeddingConfiguration,
) -> EvaluationEmbeddingConfiguration | None:
    cursor.execute(
        """
SELECT
    id,
    embedding_dimensions,
    document_count
FROM embedding_configurations
WHERE model_name = %(model_name)s
    AND document_kind = %(document_kind)s
    AND abbrev = %(abbrev)s
    AND break_on_gap = %(break_on_gap)s
    AND lost = %(lost)s
    AND unclear = %(unclear)s
    AND regularize = %(regularize)s
""",
        _configuration_params(configuration),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return EvaluationEmbeddingConfiguration(
        id=int(_row_value(row, "id", 0)),
        configuration=configuration,
        embedding_dimensions=int(_row_value(row, "embedding_dimensions", 1)),
        document_count=int(_row_value(row, "document_count", 2)),
    )


def _select_translation_retrieval_queries(
    cursor: Any,
    transcription_config_id: int,
    translation_config_id: int,
) -> tuple[TranslationRetrievalQuery, ...]:
    cursor.execute(
        """
SELECT
    transcriptions.tm_id,
    transcriptions.document_path AS transcription_path,
    translations.document_path AS translation_path,
    transcriptions.embedding::text
FROM document_embeddings AS transcriptions
JOIN document_embeddings AS translations
    ON translations.config_id = %(translation_config_id)s
    AND translations.tm_id = transcriptions.tm_id
WHERE transcriptions.config_id = %(transcription_config_id)s
ORDER BY transcriptions.tm_id, transcriptions.document_path
""",
        {
            "transcription_config_id": transcription_config_id,
            "translation_config_id": translation_config_id,
        },
    )
    return tuple(_translation_retrieval_query(row) for row in cursor.fetchall())


def _translation_retrieval_query(row: Any) -> TranslationRetrievalQuery:
    return TranslationRetrievalQuery(
        tm_id=str(_row_value(row, "tm_id", 0)),
        transcription_path=_document_path(_row_value(row, "transcription_path", 1)),
        translation_path=_document_path(_row_value(row, "translation_path", 2)),
        embedding=str(_row_value(row, "embedding", 3)),
    )


@dataclass(frozen=True)
class _TranslationCandidate:
    tm_id: str
    document_path: str


def _select_nearest_translations(
    cursor: Any,
    translation_config_id: int,
    embedding: str,
    limit: int,
) -> tuple[_TranslationCandidate, ...]:
    cursor.execute(
        """
SELECT
    tm_id,
    document_path
FROM document_embeddings
WHERE config_id = %(translation_config_id)s
ORDER BY embedding <=> %(embedding)s::vector, tm_id, document_path
LIMIT %(limit)s
""",
        {
            "translation_config_id": translation_config_id,
            "embedding": embedding,
            "limit": limit,
        },
    )
    return tuple(
        _TranslationCandidate(
            tm_id=str(_row_value(row, "tm_id", 0)),
            document_path=_document_path(_row_value(row, "document_path", 1)),
        )
        for row in cursor.fetchall()
    )


def _markdown_code(value: str) -> str:
    if "`" not in value:
        return f"`{value}`"
    return f"`` {value} ``"
