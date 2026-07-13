import hashlib

import psycopg

from scrapyrus.transcriptions.embeddings import (
    MAXIMUM_TRANSCRIPTION_OPTIONS,
    EmbeddingStore,
    _ensure_embedding_schema,
    _xml_to_embedding_text,
    delete_embeddings,
    retrieve_embedding,
    update_embeddings,
)


def _sql_text(query):
    return query if isinstance(query, str) else query.as_string()


class RecordingCursor:
    def __init__(self, *, rows=(), results=(), rowcount=0):
        self.rows = list(rows)
        self.results = list(results)
        self.executions = []
        self.rowcount = rowcount

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.executions.append((_sql_text(query), params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.results.pop(0) if self.results else None


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


def test_maximum_transcription_variant_is_fixed(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.epidoc_xml_to_text",
        lambda xml, **options: calls.append((xml, options)) or "maximum",
    )

    assert _xml_to_embedding_text("<div/>", "transcription") == "maximum"
    assert calls == [("<div/>", MAXIMUM_TRANSCRIPTION_OPTIONS)]
    assert MAXIMUM_TRANSCRIPTION_OPTIONS == {
        "abbrev": True,
        "break_on_gap": False,
        "lost": True,
        "unclear": True,
        "regularize": True,
    }


def test_schema_creates_separate_kind_tables_without_migration():
    cursor = RecordingCursor()
    _ensure_embedding_schema(cursor)
    sql = "\n".join(query for query, _ in cursor.executions)

    assert "CREATE TABLE IF NOT EXISTS transcription_embeddings" in sql
    assert "CREATE TABLE IF NOT EXISTS translation_embeddings" in sql
    assert "DROP TABLE" not in sql
    assert "embedding_configurations" not in sql
    assert "document_embeddings" not in sql
    assert "config_id" not in sql


def test_setup_store_reads_all_xml_rows_and_splits_output_tables(monkeypatch):
    rows = [
        (1, "DDB/a.xml", 46, '<div type="edition">A</div>', "transcription", None),
        (2, "HGV/46.xml", 46, '<div type="translation">B</div>', "translation", "en"),
    ]
    cursor = RecordingCursor(rows=rows)
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.epidoc_xml_to_text",
        lambda xml, **options: "Alpha",
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.translation_epidoc_xml_to_text",
        lambda xml: "Beta",
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.transcription_language",
        lambda xml: "grc",
    )
    provider = FakeProvider([[0.1, 0.2], [0.3, 0.4]])
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.initialize_llm_provider",
        lambda *args: provider,
    )

    count = EmbeddingStore("https://example/v1", "model", "key").setup_store(
        "postgresql://db", False
    )

    assert count == 2
    selects = [
        query for query, _ in cursor.executions if "FROM transcriptions" in query
    ]
    assert len(selects) == 1
    inserts = [
        (query, params) for query, params in cursor.executions if "INSERT INTO" in query
    ]
    assert "transcription_embeddings" in inserts[0][0]
    assert inserts[0][1]["language"] == "grc"
    assert inserts[0][1]["document_text"] == "Alpha"
    assert inserts[0][1]["input_hash"] == hashlib.sha256(b"Alpha").hexdigest()
    assert "translation_embeddings" in inserts[1][0]
    assert inserts[1][1]["language"] == "en"
    assert inserts[1][1]["document_text"] == "Beta"
    assert provider.inputs == ["Alpha", "Beta"]


def test_update_embeddings_only_embeds_stale_rows(monkeypatch):
    rows = [(1, "a.xml", 1, "<div/>", "transcription", None)]
    current_hash = hashlib.sha256(b"Alpha").hexdigest()
    cursor = RecordingCursor(rows=rows, results=[(current_hash, "a.xml", "1", None)])
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.epidoc_xml_to_text",
        lambda xml, **options: "Alpha",
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.transcription_language", lambda xml: None
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.initialize_llm_provider",
        lambda *args: FakeProvider([]),
    )

    assert (
        update_embeddings(
            "postgresql://db",
            False,
            inference_server_url="https://example",
            modelname="model",
            api_key="key",
        )
        == 0
    )


def test_retrieve_embedding_uses_separate_kind_table(monkeypatch):
    cursor = RecordingCursor(results=[("[0.25,0.5]",)])
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )

    result = retrieve_embedding(
        "postgresql://db",
        modelname="model",
        document_path="HGV/46.xml",
        translation=True,
    )

    assert result == (0.25, 0.5)
    assert 'FROM "translation_embeddings"' in cursor.executions[0][0]


def test_delete_embeddings_deletes_model_from_both_tables(monkeypatch):
    cursor = RecordingCursor(rowcount=3)
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )

    assert delete_embeddings("postgresql://db", modelname="model") == 6
    deletes = [
        query for query, _ in cursor.executions if query.startswith("DELETE FROM")
    ]
    assert len(deletes) == 2
    assert any("transcription_embeddings" in query for query in deletes)
    assert any("translation_embeddings" in query for query in deletes)


def test_embedding_store_initializes_provider(monkeypatch):
    calls = []
    provider = FakeProvider([])
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.initialize_llm_provider",
        lambda *args: calls.append(args) or provider,
    )
    store = EmbeddingStore("https://example", "model", "test-key")

    assert store.provider is provider
    assert calls == [("https://example", "model", "test-key")]
