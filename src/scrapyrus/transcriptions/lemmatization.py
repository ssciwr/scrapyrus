from collections.abc import Callable
import re
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

MAX_WORDS_PER_CHUNK = 50
_WORD_RE = re.compile(r"\S+")
_SENTENCE_END_RE = re.compile(r"[.!?;\u037e\u0387\u00b7][\"'\u2019\u201d\u00bb)\]}]*$")


def normalize_language(language: str | None) -> str | None:
    """Return a supported CLTK language code, or ``None``."""

    if language is None:
        return None
    base_language = language.strip().lower().replace("_", "-").split("-", 1)[0]
    return LANGUAGE_ALIASES.get(base_language)


def lemmatize_text(
    text: str,
    pipeline: _Pipeline,
    *,
    max_words: int = MAX_WORDS_PER_CHUNK,
) -> str:
    """Return CLTK lemmata while analyzing bounded, sentence-aware chunks."""

    lemmata = []
    for chunk in _text_chunks(text, max_words=max_words):
        document = pipeline.analyze(chunk)
        lemmata.extend(
            lemma
            for word in document.words
            if (lemma := (word.lemma or word.string).strip())
        )
    return " ".join(lemmata)


def _text_chunks(text: str, *, max_words: int) -> list[str]:
    """Split text at sentence boundaries, capping chunks by word count."""

    if max_words < 1:
        raise ValueError("max_words must be at least 1")

    words = list(_WORD_RE.finditer(text))
    chunks = []
    chunk_start = 0
    words_in_chunk = 0

    for index, word in enumerate(words):
        if words_in_chunk == 0:
            chunk_start = word.start()
        words_in_chunk += 1

        next_word = words[index + 1] if index + 1 < len(words) else None
        separator = text[word.end() : next_word.start()] if next_word else ""
        sentence_ends = bool(_SENTENCE_END_RE.search(word.group())) or "\n" in separator
        if words_in_chunk == max_words or sentence_ends:
            chunks.append(text[chunk_start : word.end()].strip())
            words_in_chunk = 0

    if words_in_chunk:
        chunks.append(text[chunk_start : words[-1].end()].strip())

    return chunks


def lemmatize_transcriptions(
    conninfo: str = "",
    *,
    progressbar: bool = True,
    max_words: int = MAX_WORDS_PER_CHUNK,
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
            lemma_text = lemmatize_text(
                str(row["text"]),
                pipeline,
                max_words=max_words,
            )
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
