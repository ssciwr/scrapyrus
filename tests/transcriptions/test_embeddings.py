from inspect import signature
import hashlib

import psycopg

from scrapyrus.transcriptions.core import epidoc_xml_to_text
from scrapyrus.transcriptions.embeddings import (
    EmbeddingConfiguration,
    EmbeddingStore,
    delete_embeddings,
    retrieve_embedding,
    update_embeddings,
)


class RecordingCursor:
    def __init__(self, results=(), all_results=()):
        self.executions = []
        self._results = list(results)
        self._all_results = list(all_results)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def fetchone(self):
        if not self._results:
            return None
        return self._results.pop(0)

    def fetchall(self):
        if not self._all_results:
            return []
        return self._all_results.pop(0)


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor


class FakeEmbeddingResponse:
    def __init__(self, embedding):
        self._embedding = embedding

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [{"embedding": self._embedding}]}


class FakeEmbeddingClient:
    def __init__(self, embeddings):
        self.headers = {}
        self.embeddings = list(embeddings)
        self.posts = []

    def post(self, url, *, json, timeout):
        self.posts.append((url, json, timeout))
        return FakeEmbeddingResponse(self.embeddings.pop(0))


def _normalize_sql(sql):
    return " ".join(sql.split())


def _execution_matching(cursor, fragment):
    for execution in cursor.executions:
        query, _ = execution
        if fragment in _normalize_sql(query):
            return execution
    raise AssertionError(f"No SQL execution contained {fragment!r}")


def test_embedding_configuration_is_parameter_specific():
    default = EmbeddingConfiguration("vendor/Text Embedding 3")
    same = EmbeddingConfiguration("vendor/Text Embedding 3")
    translation = EmbeddingConfiguration("vendor/Text Embedding 3", translation=True)
    expanded = EmbeddingConfiguration("vendor/Text Embedding 3", abbrev=True)

    assert same == default
    assert translation != default
    assert expanded != default
    assert default.document_kind == "transcription"
    assert translation.document_kind == "translation"


def test_setup_store_keyword_only_arguments_match_text_conversion_flags():
    text_flag_names = [
        name
        for name, parameter in signature(epidoc_xml_to_text).parameters.items()
        if parameter.kind is parameter.KEYWORD_ONLY
    ]
    store_keyword_names = [
        name
        for name, parameter in signature(EmbeddingStore.setup_store).parameters.items()
        if parameter.kind is parameter.KEYWORD_ONLY
    ]

    assert store_keyword_names == [*text_flag_names, "translation"]


def test_embedding_store_ingests_transcription_embeddings(tmp_path, monkeypatch):
    idp_data = tmp_path / "idp.data"
    metadata = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "46.xml"
    transcription = idp_data / "DDB_EpiDoc_XML" / "p.test" / "p.test.46.xml"
    metadata.parent.mkdir(parents=True)
    transcription.parent.mkdir(parents=True)
    metadata.write_text("<TEI />", encoding="utf-8")
    transcription.write_text("<TEI />", encoding="utf-8")
    cursor = RecordingCursor(results=[(42,)])
    connection = RecordingConnection(cursor)
    text_calls = []

    def connect(conninfo):
        assert conninfo == "postgresql://metadata.example/scrapyrus"
        return connection

    def iterate(idp_data_arg, *, progressbar):
        assert idp_data_arg == idp_data
        assert progressbar is False
        yield "46", metadata, transcription, None
        yield "47", metadata, None, None

    def text_converter(path, **kwargs):
        text_calls.append((path, kwargs))
        return "Alpha beta."

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.iterate_idpdata_triples",
        iterate,
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.epidoc_xml_to_text",
        text_converter,
    )
    fake_client = FakeEmbeddingClient([[0.25, 0.5, 0.75]])
    store = EmbeddingStore("https://inference.example/v1", "embed/model", "secret")
    store.client = fake_client

    config_id = store.setup_store(
        idp_data,
        "postgresql://metadata.example/scrapyrus",
        False,
        abbrev=True,
        lost=True,
    )

    assert config_id == 42
    assert text_calls == [
        (
            transcription,
            {
                "abbrev": True,
                "break_on_gap": False,
                "lost": True,
                "unclear": False,
                "regularize": False,
            },
        )
    ]
    assert fake_client.posts == [
        (
            "https://inference.example/v1/embeddings",
            {"model": "embed/model", "input": "Alpha beta."},
            60,
        )
    ]
    assert (
        _normalize_sql(cursor.executions[0][0])
        == "CREATE EXTENSION IF NOT EXISTS vector"
    )
    assert "CREATE TABLE IF NOT EXISTS embedding_configurations" in _normalize_sql(
        cursor.executions[1][0]
    )
    assert "CREATE TABLE IF NOT EXISTS document_embeddings" in _normalize_sql(
        cursor.executions[2][0]
    )
    assert "input_hash text NOT NULL" in _normalize_sql(cursor.executions[2][0])

    _, config_params = _execution_matching(
        cursor,
        "INSERT INTO embedding_configurations",
    )
    assert config_params == {
        "model_name": "embed/model",
        "document_kind": "transcription",
        "abbrev": True,
        "break_on_gap": False,
        "lost": True,
        "unclear": False,
        "regularize": False,
        "embedding_dimensions": 3,
    }

    assert all(
        "DELETE FROM document_embeddings" not in _normalize_sql(query)
        for query, _ in cursor.executions
    )

    insert_sql, insert_params = _execution_matching(
        cursor, "INSERT INTO document_embeddings"
    )
    normalized_insert_sql = _normalize_sql(insert_sql)
    assert "ON CONFLICT (config_id, document_path)" in normalized_insert_sql
    assert "input_hash = EXCLUDED.input_hash" in normalized_insert_sql
    assert insert_params == {
        "config_id": 42,
        "tm_id": "46",
        "metadata_path": "HGV_meta_EpiDoc/HGV1/46.xml",
        "document_path": "DDB_EpiDoc_XML/p.test/p.test.46.xml",
        "document_text": "Alpha beta.",
        "input_hash": hashlib.sha256(b"Alpha beta.").hexdigest(),
        "embedding": "[0.25,0.5,0.75]",
    }

    drop_index_sql, _ = _execution_matching(
        cursor,
        "DROP INDEX IF EXISTS doc_embed_cfg_42_hnsw_idx",
    )
    assert _normalize_sql(drop_index_sql).endswith(
        "DROP INDEX IF EXISTS doc_embed_cfg_42_hnsw_idx"
    )
    create_index_sql, _ = _execution_matching(
        cursor,
        "CREATE INDEX doc_embed_cfg_42_hnsw_idx",
    )
    normalized_index_sql = _normalize_sql(create_index_sql)
    assert "ON document_embeddings" in normalized_index_sql
    assert (
        "USING hnsw ((embedding::vector(3)) vector_cosine_ops)" in normalized_index_sql
    )
    assert "WHERE config_id = 42" in normalized_index_sql

    update_sql, update_params = _execution_matching(
        cursor, "UPDATE embedding_configurations"
    )
    assert update_params == {"config_id": 42}
    assert "SELECT count(*)::integer" in _normalize_sql(update_sql)


def test_embedding_store_ingests_translation_embeddings(tmp_path, monkeypatch):
    idp_data = tmp_path / "idp.data"
    metadata = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "53.xml"
    transcription = idp_data / "DDB_EpiDoc_XML" / "p.test" / "p.test.53.xml"
    translation = idp_data / "HGV_trans_EpiDoc" / "53.xml"
    for path in (metadata, transcription, translation):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<TEI />", encoding="utf-8")
    cursor = RecordingCursor(results=[(7,)])
    connection = RecordingConnection(cursor)
    translation_calls = []

    monkeypatch.setattr(psycopg, "connect", lambda conninfo: connection)
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.iterate_idpdata_triples",
        lambda idp_data_arg, *, progressbar: iter(
            [("53", metadata, transcription, translation)]
        ),
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.epidoc_xml_to_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("transcription converter should not be used")
        ),
    )

    def translation_converter(path):
        translation_calls.append(path)
        return "Translated text."

    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.translation_epidoc_xml_to_text",
        translation_converter,
    )
    fake_client = FakeEmbeddingClient([[1, 2]])
    store = EmbeddingStore("https://inference.example", "embed-model", "secret")
    store.client = fake_client

    config_id = store.setup_store(idp_data, "", False, translation=True)

    assert config_id == 7
    assert translation_calls == [translation]
    _, config_params = _execution_matching(
        cursor,
        "INSERT INTO embedding_configurations",
    )
    assert config_params["document_kind"] == "translation"
    _, insert_params = _execution_matching(cursor, "INSERT INTO document_embeddings")
    assert insert_params["document_path"] == "HGV_trans_EpiDoc/53.xml"
    assert fake_client.posts[0][0] == "https://inference.example/v1/embeddings"


def test_update_embeddings_computes_only_stale_or_missing_embeddings(
    tmp_path,
    monkeypatch,
):
    idp_data = tmp_path / "idp.data"
    metadata = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "46.xml"
    transcription = idp_data / "DDB_EpiDoc_XML" / "p.test" / "p.test.46.xml"
    translation = idp_data / "HGV_trans_EpiDoc" / "46.xml"
    for path in (metadata, transcription, translation):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<TEI />", encoding="utf-8")

    translated_hash = hashlib.sha256(b"Translated text.").hexdigest()
    cursor = RecordingCursor(
        results=[("old-transcription-hash",), (translated_hash,)],
        all_results=[
            [
                (
                    42,
                    "embed/model",
                    "transcription",
                    True,
                    False,
                    True,
                    False,
                    False,
                    3,
                ),
                (7, "embed/model", "translation", False, False, False, False, False, 2),
            ]
        ],
    )
    connection = RecordingConnection(cursor)

    def connect(conninfo):
        assert conninfo == "postgresql://metadata.example/scrapyrus"
        return connection

    def iterate(idp_data_arg, *, progressbar):
        assert idp_data_arg == idp_data
        assert progressbar is False
        yield "46", metadata, transcription, translation

    transcription_calls = []
    translation_calls = []

    def transcription_converter(path, **kwargs):
        transcription_calls.append((path, kwargs))
        return "Alpha beta."

    def translation_converter(path):
        translation_calls.append(path)
        return "Translated text."

    fake_client = FakeEmbeddingClient([[0.25, 0.5, 0.75]])
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.iterate_idpdata_triples",
        iterate,
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.epidoc_xml_to_text",
        transcription_converter,
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.translation_epidoc_xml_to_text",
        translation_converter,
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.requests.Session",
        lambda: fake_client,
    )

    updated_count = update_embeddings(
        idp_data,
        "postgresql://metadata.example/scrapyrus",
        False,
        inference_server_url="https://inference.example/v1",
        api_key="secret",
    )

    assert updated_count == 1
    assert transcription_calls == [
        (
            transcription,
            {
                "abbrev": True,
                "break_on_gap": False,
                "lost": True,
                "unclear": False,
                "regularize": False,
            },
        )
    ]
    assert translation_calls == [translation]
    assert fake_client.posts == [
        (
            "https://inference.example/v1/embeddings",
            {"model": "embed/model", "input": "Alpha beta."},
            60,
        )
    ]

    hash_selects = [
        params
        for query, params in cursor.executions
        if "SELECT input_hash" in _normalize_sql(query)
    ]
    assert hash_selects == [
        {
            "config_id": 42,
            "document_path": "DDB_EpiDoc_XML/p.test/p.test.46.xml",
        },
        {"config_id": 7, "document_path": "HGV_trans_EpiDoc/46.xml"},
    ]

    insert_sql, insert_params = _execution_matching(
        cursor, "INSERT INTO document_embeddings"
    )
    assert insert_params == {
        "config_id": 42,
        "tm_id": "46",
        "metadata_path": "HGV_meta_EpiDoc/HGV1/46.xml",
        "document_path": "DDB_EpiDoc_XML/p.test/p.test.46.xml",
        "document_text": "Alpha beta.",
        "input_hash": hashlib.sha256(b"Alpha beta.").hexdigest(),
        "embedding": "[0.25,0.5,0.75]",
    }
    assert "input_hash = EXCLUDED.input_hash" in _normalize_sql(insert_sql)

    create_index_sql, _ = _execution_matching(
        cursor, "CREATE INDEX IF NOT EXISTS doc_embed_cfg_42_hnsw_idx"
    )
    assert "WHERE config_id = 42" in _normalize_sql(create_index_sql)
    _, update_params = _execution_matching(cursor, "UPDATE embedding_configurations")
    assert update_params == {"config_id": 42}
    assert all(
        "DELETE FROM" not in _normalize_sql(query) for query, _ in cursor.executions
    )


def test_retrieve_embedding_selects_configuration_and_document(monkeypatch):
    cursor = RecordingCursor(results=[("[0.25,0.5,0.75]",)])
    connection = RecordingConnection(cursor)

    def connect(conninfo):
        assert conninfo == "postgresql://metadata.example/scrapyrus"
        return connection

    monkeypatch.setattr(psycopg, "connect", connect)

    embedding = retrieve_embedding(
        "postgresql://metadata.example/scrapyrus",
        modelname="embed/model",
        document_path="DDB_EpiDoc_XML/p.test/p.test.46.xml",
        abbrev=True,
        lost=True,
    )

    assert embedding == (0.25, 0.5, 0.75)
    query, params = cursor.executions[0]
    normalized_query = _normalize_sql(query)
    assert "FROM embedding_configurations" in normalized_query
    assert "JOIN document_embeddings" in normalized_query
    assert params == {
        "model_name": "embed/model",
        "document_kind": "transcription",
        "abbrev": True,
        "break_on_gap": False,
        "lost": True,
        "unclear": False,
        "regularize": False,
        "document_path": "DDB_EpiDoc_XML/p.test/p.test.46.xml",
    }


def test_retrieve_embedding_returns_none_for_missing_document(monkeypatch):
    cursor = RecordingCursor(results=[None])
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(psycopg, "connect", lambda conninfo: connection)

    assert (
        retrieve_embedding(
            modelname="embed/model",
            document_path="DDB_EpiDoc_XML/p.test/missing.xml",
        )
        is None
    )


def test_delete_embeddings_removes_selected_configuration(monkeypatch):
    cursor = RecordingCursor(results=[(42,)])
    connection = RecordingConnection(cursor)

    def connect(conninfo):
        assert conninfo == "postgresql://metadata.example/scrapyrus"
        return connection

    monkeypatch.setattr(psycopg, "connect", connect)

    deleted_config_id = delete_embeddings(
        "postgresql://metadata.example/scrapyrus",
        modelname="embed/model",
        abbrev=True,
        lost=True,
    )

    assert deleted_config_id == 42
    select_sql, select_params = cursor.executions[0]
    assert "FROM embedding_configurations" in _normalize_sql(select_sql)
    assert select_params == {
        "model_name": "embed/model",
        "document_kind": "transcription",
        "abbrev": True,
        "break_on_gap": False,
        "lost": True,
        "unclear": False,
        "regularize": False,
    }
    drop_sql, _ = _execution_matching(
        cursor, "DROP INDEX IF EXISTS doc_embed_cfg_42_hnsw_idx"
    )
    assert _normalize_sql(drop_sql).endswith(
        "DROP INDEX IF EXISTS doc_embed_cfg_42_hnsw_idx"
    )
    _, delete_params = _execution_matching(
        cursor, "DELETE FROM embedding_configurations"
    )
    assert delete_params == {"config_id": 42}


def test_delete_embeddings_returns_none_for_missing_configuration(monkeypatch):
    cursor = RecordingCursor(results=[None])
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(psycopg, "connect", lambda conninfo: connection)

    assert delete_embeddings(modelname="embed/model") is None
    assert all(
        "DELETE FROM" not in _normalize_sql(query) for query, _ in cursor.executions
    )


def test_embedding_store_initializes_client_headers(monkeypatch):
    fake_client = FakeEmbeddingClient([])
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.requests.Session",
        lambda: fake_client,
    )

    store = EmbeddingStore("https://inference.example", "model", "test-key")

    assert store.client is fake_client
    assert fake_client.headers == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
