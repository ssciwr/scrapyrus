import psycopg
import pytest

from scrapyrus.transcriptions.search import (
    BM25SearchHit,
    MetadataFilter,
    bm25_search,
)


class RecordingCursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.executions.append((query.as_string(), params))

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor


@pytest.mark.parametrize(
    ("use_lemmas", "expected_vector"),
    [(False, '"text_vector"'), (True, '"lemma_vector"')],
)
def test_bm25_search_uses_selected_tsvector(monkeypatch, use_lemmas, expected_vector):
    cursor = RecordingCursor(
        [(7, "DDB/p.test.xml", 46, "transcription", None, "Stored text", 2.5)]
    )
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )

    hits = bm25_search(
        "postgresql://db",
        use_lemmas=use_lemmas,
        query_text="search terms",
        limit=4,
    )

    assert hits == (
        BM25SearchHit(
            transcription_id=7,
            source_path="DDB/p.test.xml",
            tm_id=46,
            type="transcription",
            language=None,
            text="Stored text",
            score=2.5,
        ),
    )
    query, params = cursor.executions[0]
    assert f"transcription.{expected_vector} AS document_vector" in query
    assert f"WHERE transcription.{expected_vector} IS NOT NULL" in query
    assert "unnest(to_tsvector('simple', %(query_text)s))" in query
    assert "cardinality(term.positions)" in query
    assert "document_frequency" in query
    assert "ORDER BY scores.score DESC, transcription.transcription_id" in query
    assert params == {
        "query_text": "search terms",
        "limit": 4,
        "k1": 1.2,
        "b": 0.75,
    }


def test_bm25_search_filters_metadata_before_collection_statistics(monkeypatch):
    cursor = RecordingCursor()
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )

    bm25_search(
        "postgresql://db",
        use_lemmas=True,
        query_text="tax receipt",
        limit=20,
        metadata_filter=MetadataFilter(
            material="papyrus",
            not_before_year=-100,
            not_after_year=100,
            keywords=("taxation", "account"),
            tm_place_ids=(1234, 5678),
        ),
    )

    query, params = cursor.executions[0]
    documents = query.index("documents AS MATERIALIZED")
    statistics = query.index("collection_statistics AS")
    assert documents < query.index("FROM papyri AS papyrus") < statistics
    assert documents < query.index("FROM orig_dates AS original_date") < statistics
    assert documents < query.index("FROM keywords AS keyword") < statistics
    assert documents < query.index("FROM orig_places AS original_place") < statistics
    assert "original_date.alternative = false" in query
    assert "original_date.not_after_year >= %(metadata_not_before_year)s" in query
    assert "original_date.not_before_year <= %(metadata_not_after_year)s" in query
    assert "keyword.keyword = ANY(%(metadata_keywords)s)" in query
    assert "original_place.tm_place_id = ANY(%(metadata_tm_place_ids)s)" in query
    assert params == {
        "query_text": "tax receipt",
        "limit": 20,
        "k1": 1.2,
        "b": 0.75,
        "metadata_material": "papyrus",
        "metadata_not_before_year": -100,
        "metadata_not_after_year": 100,
        "metadata_keywords": ["taxation", "account"],
        "metadata_tm_place_ids": [1234, 5678],
    }


def test_metadata_filter_validates_ranges_and_values():
    with pytest.raises(ValueError, match="not_before_year"):
        MetadataFilter(not_before_year=100, not_after_year=-100)
    with pytest.raises(ValueError, match="empty strings"):
        MetadataFilter(keywords=("",))
    with pytest.raises(ValueError, match="positive integers"):
        MetadataFilter(tm_place_ids=(0,))


def test_bm25_search_accepts_mapping_rows(monkeypatch):
    cursor = RecordingCursor(
        [
            {
                "transcription_id": 8,
                "source_path": "DCLP/8.xml",
                "tm_id": 8,
                "type": "transcription",
                "language": "grc",
                "text": "Text",
                "score": 1.25,
            }
        ]
    )
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )

    hit = bm25_search("postgresql://db", use_lemmas=True, query_text="lemma", limit=1)[
        0
    ]

    assert hit.language == "grc"
    assert hit.score == 1.25


def test_bm25_search_rejects_negative_limit_before_connecting(monkeypatch):
    monkeypatch.setattr(
        psycopg,
        "connect",
        lambda conninfo: pytest.fail("negative limit should not connect"),
    )

    with pytest.raises(ValueError, match="limit must be non-negative"):
        bm25_search("postgresql://db", use_lemmas=False, query_text="term", limit=-1)
