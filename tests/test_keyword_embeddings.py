import psycopg
import pytest

from scrapyrus.keyword_embeddings import (
    KEYWORD_EMBEDDINGS_TABLE,
    KeywordEmbeddingStore,
    _ensure_keyword_embedding_schema,
    find_similar_keywords,
)


def _sql_text(query):
    return query if isinstance(query, str) else query.as_string()


class RecordingCursor:
    def __init__(self, *, keyword_rows=(), stored_rows=(), stats=None, matches=()):
        self.keyword_rows = list(keyword_rows)
        self.stored_rows = list(stored_rows)
        self.stats = stats
        self.matches = list(matches)
        self.executions = []
        self._result = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        query = _sql_text(query)
        self.executions.append((query, params))
        if query.startswith("SELECT DISTINCT keyword"):
            self._result = self.keyword_rows
        elif query.startswith("SELECT keyword, vector_dims"):
            self._result = self.stored_rows
        elif query.lstrip().startswith("SELECT count(*)"):
            self._result = [self.stats]
        elif "AS similarity" in query:
            self._result = self.matches
        else:
            self._result = []

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0]


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor


class FakeProvider:
    def __init__(self, embeddings):
        self.embeddings = list(embeddings)
        self.inputs = []

    def embed(self, text):
        self.inputs.append(text)
        return tuple(self.embeddings.pop(0))


def test_keyword_schema_uses_exact_keyword_and_model_as_identity(monkeypatch):
    cursor = RecordingCursor()

    _ensure_keyword_embedding_schema(cursor)

    schema = "\n".join(query for query, _ in cursor.executions)
    assert "CREATE EXTENSION IF NOT EXISTS vector" in schema
    assert f"CREATE TABLE IF NOT EXISTS {KEYWORD_EMBEDDINGS_TABLE}" in schema
    assert "PRIMARY KEY (keyword, model_name)" in schema


def test_update_store_embeds_only_missing_distinct_keywords(monkeypatch):
    cursor = RecordingCursor(
        keyword_rows=[("alpha",), ("beta",)], stored_rows=[("alpha", 2)]
    )
    provider = FakeProvider([[0.25, 0.75]])
    indexes = []
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )
    monkeypatch.setattr(
        "scrapyrus.keyword_embeddings.initialize_llm_provider",
        lambda *args: provider,
    )
    monkeypatch.setattr(
        "scrapyrus.keyword_embeddings._recreate_embedding_index",
        lambda *args: indexes.append(args),
    )

    count = KeywordEmbeddingStore("https://example", "model", "key").setup_store(
        "postgresql://db", False, stale_only=True
    )

    assert count == 1
    assert provider.inputs == ["beta"]
    inserts = [
        params
        for query, params in cursor.executions
        if query.lstrip().startswith("INSERT INTO keyword_embeddings")
    ]
    assert inserts == [
        {
            "keyword": "beta",
            "model_name": "model",
            "embedding": "[0.25,0.75]",
        }
    ]
    assert any(
        query.lstrip().startswith("DELETE FROM keyword_embeddings")
        for query, _ in cursor.executions
    )
    assert indexes == [(cursor, "keyword_embeddings", "model", 2)]


def test_ingest_store_reembeds_existing_keywords(monkeypatch):
    cursor = RecordingCursor(keyword_rows=[("alpha",)], stored_rows=[("alpha", 2)])
    provider = FakeProvider([[0.4, 0.6]])
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )
    monkeypatch.setattr(
        "scrapyrus.keyword_embeddings.initialize_llm_provider",
        lambda *args: provider,
    )
    monkeypatch.setattr(
        "scrapyrus.keyword_embeddings._recreate_embedding_index",
        lambda *args: None,
    )

    count = KeywordEmbeddingStore("https://example", "model", "key").setup_store(
        "postgresql://db", False, stale_only=False
    )

    assert count == 1
    assert provider.inputs == ["alpha"]


def test_setup_store_rejects_changed_embedding_dimensions(monkeypatch):
    cursor = RecordingCursor(
        keyword_rows=[("alpha",), ("beta",)], stored_rows=[("alpha", 2)]
    )
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )
    monkeypatch.setattr(
        "scrapyrus.keyword_embeddings.initialize_llm_provider",
        lambda *args: FakeProvider([[0.1, 0.2, 0.3]]),
    )

    store = KeywordEmbeddingStore("https://example", "model", "key")
    with pytest.raises(ValueError, match="inconsistent dimensions"):
        store.setup_store("postgresql://db", False)


def test_find_similar_keywords_embeds_query_and_returns_ranked_matches(monkeypatch):
    cursor = RecordingCursor(
        stats=(2, 2, 2), matches=[("contract", 0.9), ("receipt", 0.75)]
    )
    provider = FakeProvider([[0.4, 0.6]])
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )
    monkeypatch.setattr(
        "scrapyrus.keyword_embeddings.initialize_llm_provider",
        lambda *args: provider,
    )

    matches = find_similar_keywords(
        "sale of a house",
        "postgresql://db",
        inference_server_url="https://example",
        modelname="model",
        api_key="key",
        top_k=2,
    )

    assert provider.inputs == ["sale of a house"]
    assert [(match.keyword, match.similarity) for match in matches] == [
        ("contract", 0.9),
        ("receipt", 0.75),
    ]
    query, params = next(
        (query, params)
        for query, params in cursor.executions
        if "AS similarity" in query
    )
    assert '"embedding"::vector(2) <=> %(embedding)s::vector(2)' in query
    assert "ORDER BY" in query
    assert params == {
        "embedding": "[0.40000000000000002,0.59999999999999998]",
        "modelname": "model",
        "top_k": 2,
    }


@pytest.mark.parametrize("query, top_k", [("", 1), ("text", 0)])
def test_find_similar_keywords_validates_inputs(query, top_k):
    with pytest.raises(ValueError):
        find_similar_keywords(
            query,
            inference_server_url="https://example",
            modelname="model",
            api_key="key",
            top_k=top_k,
        )
