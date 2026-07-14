from collections.abc import Callable
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from tqdm import tqdm

from scrapyrus.transcriptions.core import (
    TRANSCRIPTIONS_TABLE,
    transcription_language,
)


LANGUAGE_ALIASES = {
    "cop": "cop",
    "coptic": "cop",
    "el": "grc",
    "grc": "grc",
    "greek": "grc",
    "la": "lat",
    "lat": "lat",
    "latin": "lat",
}


class _Word(Protocol):
    lemma: str | None
    string: str


class _Document(Protocol):
    words: list[_Word]


class _Pipeline(Protocol):
    def analyze(self, text: str) -> _Document: ...


PipelineFactory = Callable[[str], _Pipeline]


def normalize_language(language: str | None) -> str | None:
    """Return a supported CLTK language code, or ``None``."""

    if language is None:
        return None
    base_language = language.strip().lower().replace("_", "-").split("-", 1)[0]
    return LANGUAGE_ALIASES.get(base_language)


def lemmatize_text(text: str, pipeline: _Pipeline) -> str:
    """Return the whitespace-separated lemmata produced by a CLTK pipeline."""

    document = pipeline.analyze(text)
    return " ".join(
        lemma
        for word in document.words
        if (lemma := (word.lemma or word.string).strip())
    )


def lemmatize_transcriptions(
    conninfo: str = "",
    *,
    progressbar: bool = True,
    pipeline_factory: PipelineFactory | None = None,
    **connect_kwargs: Any,
) -> None:
    """Populate missing lemmata for Greek, Latin, and Coptic XML rows."""

    if pipeline_factory is None:
        pipeline_factory = _create_pipeline
    pipelines: dict[str, _Pipeline] = {}

    select_sql = f"""
SELECT transcription_id, xml_content::text, type, language, text
FROM {TRANSCRIPTIONS_TABLE}
WHERE lemma_text IS NULL
ORDER BY transcription_id
"""
    update_sql = f"""
UPDATE {TRANSCRIPTIONS_TABLE}
SET lemma_text = %(lemma_text)s
WHERE transcription_id = %(transcription_id)s
"""

    with psycopg.connect(
        conninfo,
        row_factory=dict_row,
        **connect_kwargs,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(select_sql)
            rows = cursor.fetchall()

        for row in tqdm(
            rows,
            disable=not progressbar,
            desc="Lemmatizing transcriptions",
            unit="row",
        ):
            xml_content = str(row["xml_content"])
            language = _row_language(row, xml_content)
            if language is None:
                continue

            pipeline = pipelines.get(language)
            if pipeline is None:
                pipeline = pipeline_factory(language)
                pipelines[language] = pipeline
            lemma_text = lemmatize_text(str(row["text"]), pipeline)
            with connection.cursor() as cursor:
                cursor.execute(
                    update_sql,
                    {
                        "transcription_id": row["transcription_id"],
                        "lemma_text": lemma_text,
                    },
                )


def _row_language(row: dict[str, Any], xml_content: str) -> str | None:
    language = row["language"]
    if row["type"] == "transcription":
        language = transcription_language(xml_content)
    return normalize_language(language)


def _create_pipeline(language: str) -> _Pipeline:
    # Importing CLTK loads its NLP dependencies, so keep it out of commands that
    # do not perform lemmatization.
    from cltk import NLP

    return NLP(language, backend="stanza", suppress_banner=True)
