from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql

from scrapyrus.transcriptions.core import TRANSCRIPTIONS_TABLE


BM25_K1 = 1.2
BM25_B = 0.75


@dataclass(frozen=True)
class BM25SearchHit:
    """A transcription row and its Okapi BM25 relevance score."""

    transcription_id: int
    source_path: str
    tm_id: int
    type: str
    language: str | None
    text: str
    score: float


@dataclass(frozen=True)
class MetadataFilter:
    """Metadata constraints applied before calculating BM25 statistics.

    Date bounds describe an inclusive requested interval and match every
    primary date range which overlaps it. ``keywords`` and ``tm_place_ids``
    use any-match semantics.
    """

    material: str | None = None
    not_before_year: int | None = None
    not_after_year: int | None = None
    keywords: tuple[str, ...] = ()
    tm_place_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "keywords", tuple(self.keywords))
        object.__setattr__(self, "tm_place_ids", tuple(self.tm_place_ids))
        if (
            self.not_before_year is not None
            and self.not_after_year is not None
            and self.not_before_year > self.not_after_year
        ):
            raise ValueError("not_before_year must not be after not_after_year")
        if any(not keyword for keyword in self.keywords):
            raise ValueError("keywords must not contain empty strings")
        if any(place_id <= 0 for place_id in self.tm_place_ids):
            raise ValueError("tm_place_ids must contain positive integers")


def bm25_search(
    conninfo: str = "",
    /,
    *,
    use_lemmas: bool,
    query_text: str,
    limit: int,
    metadata_filter: MetadataFilter | None = None,
) -> tuple[BM25SearchHit, ...]:
    """Return the highest-scoring transcription rows for ``query_text``.

    Ranking is performed entirely by PostgreSQL from the term frequencies and
    positions in the stored ``tsvector`` column. When ``use_lemmas`` is true,
    the query and documents use ``lemma_vector``; otherwise they use
    ``text_vector``. Rows whose selected vector is null are outside the search
    corpus. When supplied, ``metadata_filter`` restricts the corpus before
    collection statistics and relevance scores are calculated.
    """

    if limit < 0:
        raise ValueError("limit must be non-negative")

    vector_column = "lemma_vector" if use_lemmas else "text_vector"
    metadata_predicates, metadata_parameters = _metadata_predicates(
        metadata_filter or MetadataFilter()
    )
    query = _bm25_query(vector_column, metadata_predicates)
    parameters = {
        "query_text": query_text,
        "limit": limit,
        "k1": BM25_K1,
        "b": BM25_B,
        **metadata_parameters,
    }

    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()

    return tuple(_search_hit(row) for row in rows)


def _metadata_predicates(
    metadata_filter: MetadataFilter,
) -> tuple[sql.Composed, dict[str, Any]]:
    predicates: list[sql.SQL | sql.Composed] = []
    parameters: dict[str, Any] = {}

    if metadata_filter.material is not None:
        predicates.append(
            sql.SQL(
                """
AND EXISTS (
    SELECT 1
    FROM papyri AS papyrus
    WHERE papyrus.tm_id = transcription.tm_id
      AND papyrus.material = %(metadata_material)s
)"""
            )
        )
        parameters["metadata_material"] = metadata_filter.material

    date_predicates: list[sql.SQL] = []
    if metadata_filter.not_before_year is not None:
        date_predicates.append(
            sql.SQL(
                "AND (original_date.not_after_year IS NULL "
                "OR original_date.not_after_year >= %(metadata_not_before_year)s)"
            )
        )
        parameters["metadata_not_before_year"] = metadata_filter.not_before_year
    if metadata_filter.not_after_year is not None:
        date_predicates.append(
            sql.SQL(
                "AND (original_date.not_before_year IS NULL "
                "OR original_date.not_before_year <= %(metadata_not_after_year)s)"
            )
        )
        parameters["metadata_not_after_year"] = metadata_filter.not_after_year
    if date_predicates:
        predicates.append(
            sql.SQL(
                """
AND EXISTS (
    SELECT 1
    FROM orig_dates AS original_date
    WHERE original_date.tm_id = transcription.tm_id
      AND original_date.alternative = false
      {date_predicates}
)"""
            ).format(date_predicates=sql.SQL("\n      ").join(date_predicates))
        )

    if metadata_filter.keywords:
        predicates.append(
            sql.SQL(
                """
AND EXISTS (
    SELECT 1
    FROM keywords AS keyword
    WHERE keyword.tm_id = transcription.tm_id
      AND keyword.keyword = ANY(%(metadata_keywords)s)
)"""
            )
        )
        parameters["metadata_keywords"] = list(metadata_filter.keywords)

    if metadata_filter.tm_place_ids:
        predicates.append(
            sql.SQL(
                """
AND EXISTS (
    SELECT 1
    FROM orig_places AS original_place
    WHERE original_place.tm_id = transcription.tm_id
      AND original_place.tm_place_id = ANY(%(metadata_tm_place_ids)s)
)"""
            )
        )
        parameters["metadata_tm_place_ids"] = list(metadata_filter.tm_place_ids)

    return sql.Composed(predicates), parameters


def _bm25_query(vector_column: str, metadata_predicates: sql.Composed) -> sql.Composed:
    return sql.SQL(
        """
WITH query_terms AS MATERIALIZED (
    SELECT lexeme
    FROM unnest(to_tsvector('simple', %(query_text)s))
),
documents AS MATERIALIZED (
    SELECT
        transcription.transcription_id,
        transcription.{vector} AS document_vector
    FROM {table} AS transcription
    WHERE transcription.{vector} IS NOT NULL
    {metadata_predicates}
),
document_lengths AS MATERIALIZED (
    SELECT
        document.transcription_id,
        coalesce(sum(cardinality(term.positions)), 0)::double precision
            AS document_length
    FROM documents AS document
    LEFT JOIN LATERAL unnest(document.document_vector) AS term ON true
    GROUP BY document.transcription_id
),
collection_statistics AS (
    SELECT
        count(*)::double precision AS document_count,
        avg(document_length)::double precision AS average_document_length
    FROM document_lengths
),
matching_terms AS MATERIALIZED (
    SELECT
        document.transcription_id,
        term.lexeme,
        cardinality(term.positions)::double precision AS term_frequency
    FROM documents AS document
    CROSS JOIN LATERAL unnest(document.document_vector) AS term
    JOIN query_terms USING (lexeme)
),
document_frequencies AS (
    SELECT lexeme, count(*)::double precision AS document_frequency
    FROM matching_terms
    GROUP BY lexeme
),
scores AS (
    SELECT
        matching_term.transcription_id,
        sum(
            ln(
                1 + (
                    collection.document_count
                    - frequency.document_frequency
                    + 0.5
                ) / (frequency.document_frequency + 0.5)
            )
            * (
                matching_term.term_frequency * (%(k1)s + 1)
            ) / (
                matching_term.term_frequency
                + %(k1)s * (
                    1 - %(b)s
                    + %(b)s * length.document_length
                        / nullif(collection.average_document_length, 0)
                )
            )
        ) AS score
    FROM matching_terms AS matching_term
    JOIN document_frequencies AS frequency USING (lexeme)
    JOIN document_lengths AS length USING (transcription_id)
    CROSS JOIN collection_statistics AS collection
    GROUP BY matching_term.transcription_id
)
SELECT
    transcription.transcription_id,
    transcription.source_path,
    transcription.tm_id,
    transcription.type,
    transcription.language,
    transcription.text,
    scores.score
FROM scores
JOIN {table} AS transcription USING (transcription_id)
ORDER BY scores.score DESC, transcription.transcription_id
LIMIT %(limit)s
"""
    ).format(
        vector=sql.Identifier(vector_column),
        table=sql.Identifier(TRANSCRIPTIONS_TABLE),
        metadata_predicates=metadata_predicates,
    )


def _search_hit(row: Any) -> BM25SearchHit:
    if isinstance(row, dict):
        return BM25SearchHit(
            transcription_id=int(row["transcription_id"]),
            source_path=str(row["source_path"]),
            tm_id=int(row["tm_id"]),
            type=str(row["type"]),
            language=row["language"],
            text=str(row["text"]),
            score=float(row["score"]),
        )
    return BM25SearchHit(
        transcription_id=int(row[0]),
        source_path=str(row[1]),
        tm_id=int(row[2]),
        type=str(row[3]),
        language=row[4],
        text=str(row[5]),
        score=float(row[6]),
    )
