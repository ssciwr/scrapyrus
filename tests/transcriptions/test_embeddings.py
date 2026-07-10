from inspect import signature

import psycopg

from scrapyrus.transcriptions.core import epidoc_xml_to_text
from scrapyrus.transcriptions.embeddings import EmbeddingStore, embedding_table_name


class RecordingCursor:
    def __init__(self):
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.executions.append((query, params))


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


def test_embedding_table_name_is_deterministic_safe_and_parameter_specific():
    default_name = embedding_table_name("vendor/Text Embedding 3")
    same_name = embedding_table_name("vendor/Text Embedding 3")
    translation_name = embedding_table_name("vendor/Text Embedding 3", translation=True)
    expanded_name = embedding_table_name("vendor/Text Embedding 3", abbrev=True)

    assert same_name == default_name
    assert translation_name != default_name
    assert expanded_name != default_name
    assert default_name.startswith("documents_vendor_text_embedding")
    assert "_t0_a0_g0_l0_u0_r0_" in default_name
    assert len(default_name) <= 63
    assert default_name.replace("_", "").isalnum()


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
    cursor = RecordingCursor()
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

    table_name = store.setup_store(
        idp_data,
        "postgresql://metadata.example/scrapyrus",
        False,
        abbrev=True,
        lost=True,
    )

    assert table_name == embedding_table_name("embed/model", abbrev=True, lost=True)
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
    assert (
        _normalize_sql(cursor.executions[1][0]) == f"DROP TABLE IF EXISTS {table_name}"
    )
    assert f"CREATE TABLE {table_name}" in _normalize_sql(cursor.executions[2][0])
    assert "embedding vector(3) NOT NULL" in _normalize_sql(cursor.executions[2][0])
    assert f"INSERT INTO {table_name}" in _normalize_sql(cursor.executions[3][0])
    assert cursor.executions[3][1] == {
        "tm_id": "46",
        "metadata_path": "HGV_meta_EpiDoc/HGV1/46.xml",
        "document_path": "DDB_EpiDoc_XML/p.test/p.test.46.xml",
        "document_kind": "transcription",
        "document_text": "Alpha beta.",
        "embedding": "[0.25,0.5,0.75]",
    }
    index_sql = _normalize_sql(cursor.executions[4][0])
    assert index_sql.startswith("CREATE INDEX IF NOT EXISTS")
    assert f"ON {table_name} USING hnsw (embedding vector_cosine_ops)" in index_sql


def test_embedding_store_ingests_translation_embeddings(tmp_path, monkeypatch):
    idp_data = tmp_path / "idp.data"
    metadata = idp_data / "HGV_meta_EpiDoc" / "HGV1" / "53.xml"
    transcription = idp_data / "DDB_EpiDoc_XML" / "p.test" / "p.test.53.xml"
    translation = idp_data / "HGV_trans_EpiDoc" / "53.xml"
    for path in (metadata, transcription, translation):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<TEI />", encoding="utf-8")
    cursor = RecordingCursor()
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

    table_name = store.setup_store(idp_data, "", False, translation=True)

    assert table_name == embedding_table_name("embed-model", translation=True)
    assert translation_calls == [translation]
    assert cursor.executions[3][1]["document_kind"] == "translation"
    assert cursor.executions[3][1]["document_path"] == "HGV_trans_EpiDoc/53.xml"
    assert fake_client.posts[0][0] == "https://inference.example/v1/embeddings"


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
