import hashlib

import psycopg
import pytest

from scrapyrus.transcriptions.embeddings import (
    MAXIMUM_TRANSCRIPTION_OPTIONS,
    EmbeddingStore,
    TranscriptionsUnavailableError,
    chunk_embedding_text,
    dump_embeddings,
    _recreate_embedding_index,
    _ensure_embedding_schema,
    _select_xml_rows,
    _xml_to_embedding_text,
    delete_embeddings,
    import_embeddings,
    retrieve_embedding,
    update_embeddings,
)


def _sql_text(query):
    return query if isinstance(query, str) else query.as_string()


class RecordingCopy:
    def __init__(self, chunks, writes):
        self.chunks = list(chunks)
        self.writes = writes

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self.chunks)

    def write(self, chunk):
        self.writes.append(chunk)


class RecordingCursor:
    def __init__(
        self,
        *,
        rows=(),
        fetchall_results=None,
        results=(),
        rowcount=0,
        copy_chunks=(),
    ):
        self.rows = list(rows)
        self.fetchall_results = (
            [list(result) for result in fetchall_results]
            if fetchall_results is not None
            else []
        )
        self.results = list(results)
        self.executions = []
        self.rowcount = rowcount
        self.copy_chunks = list(copy_chunks)
        self.copy_writes = []
        self.copies = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.executions.append((_sql_text(query), params))

    def copy(self, query):
        self.copies.append(_sql_text(query))
        return RecordingCopy(self.copy_chunks, self.copy_writes)

    def fetchall(self):
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
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
    assert "chunk_index integer NOT NULL DEFAULT 0" in sql
    assert "PRIMARY KEY (xml_id, model_name, chunk_index)" in sql


def test_chunking_keeps_documents_within_fifty_percent_of_target_unchanged():
    document = "  " + " ".join(f"word-{index}" for index in range(15)) + "\n"

    assert chunk_embedding_text(document, 10) == (document,)


def test_chunking_is_deterministic_and_overlaps_by_ten_percent():
    document = " ".join(f"word-{index}" for index in range(16))

    expected = (
        " ".join(f"word-{index}" for index in range(10)),
        " ".join(f"word-{index}" for index in range(9, 16)),
    )
    assert chunk_embedding_text(document, 10) == expected
    assert chunk_embedding_text(document, 10) == expected


def test_chunking_does_not_add_a_chunk_containing_only_overlap():
    document = " ".join(f"word-{index}" for index in range(19))

    chunks = chunk_embedding_text(document, 10)

    assert len(chunks) == 2
    assert chunks[-1].split() == [f"word-{index}" for index in range(9, 19)]


def test_chunking_rejects_non_positive_chunk_size():
    with pytest.raises(ValueError, match="at least 1"):
        chunk_embedding_text("text", 0)


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
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.tqdm",
        lambda *args, **kwargs: pytest.fail("progress bar should be disabled"),
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


def test_setup_store_reports_xml_preparation_progress(monkeypatch):
    rows = [
        (1, "DDB/a.xml", 46, "<div/>", "transcription", None),
        (2, "HGV/46.xml", 46, "<div/>", "translation", "en"),
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
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.initialize_llm_provider",
        lambda *args: FakeProvider([[0.1], [0.2]]),
    )
    progress_calls = []

    class FakeProgress:
        def __init__(self, iterable):
            self.iterable = iterable

        def __iter__(self):
            return iter(self.iterable)

        def update(self, amount):
            pass

        def close(self):
            pass

    def fake_tqdm(iterable=(), *, total, unit, desc):
        progress_calls.append((iterable, total, unit, desc))
        return FakeProgress(iterable)

    monkeypatch.setattr("scrapyrus.transcriptions.embeddings.tqdm", fake_tqdm)

    EmbeddingStore("https://example/v1", "model", "key").setup_store(
        "postgresql://db", True
    )

    prepared_rows, total, unit, description = progress_calls[0]
    assert len(prepared_rows) == 2
    assert (total, unit, description) == (2, "row", "Preparing XML rows")
    assert progress_calls[1][1:] == (2, "request", "Embedding XML rows")


def test_setup_store_embeds_chunks_with_indices(monkeypatch):
    rows = [(1, "DDB/a.xml", 46, "<div/>", "transcription", None)]
    cursor = RecordingCursor(rows=rows)
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )
    document = " ".join(f"word-{index}" for index in range(16))
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.epidoc_xml_to_text",
        lambda xml, **options: document,
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
        "postgresql://db", False, chunk_size=10
    )

    inserts = [params for query, params in cursor.executions if "INSERT INTO" in query]
    assert count == 2
    assert [params["chunk_index"] for params in inserts] == [0, 1]
    assert provider.inputs == list(chunk_embedding_text(document, 10))
    assert any(
        "chunk_index >= %s" in query and params == (1, "model", 2)
        for query, params in cursor.executions
    )


def test_setup_store_reports_missing_transcriptions_table(monkeypatch):
    class MissingTranscriptionsCursor(RecordingCursor):
        def execute(self, query, params=None):
            super().execute(query, params)
            if "FROM transcriptions" in _sql_text(query):
                raise psycopg.errors.UndefinedTable(
                    'relation "transcriptions" does not exist'
                )

    cursor = MissingTranscriptionsCursor()
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )
    monkeypatch.setattr(
        "scrapyrus.transcriptions.embeddings.initialize_llm_provider",
        lambda *args: FakeProvider([]),
    )

    store = EmbeddingStore("https://example/v1", "model", "key")
    with pytest.raises(TranscriptionsUnavailableError, match="transcriptions ingest"):
        store.setup_store("postgresql://db", False)


def test_select_xml_rows_samples_deterministically_with_seed():
    cursor = RecordingCursor()

    _select_xml_rows(cursor, sample=10, seed=42)

    query, params = cursor.executions[0]
    assert "GROUP BY tm_id" in query
    assert "bool_or(type = 'transcription')" in query
    assert "bool_or(type = 'translation')" in query
    assert "ORDER BY md5(tm_id::text || ':' || (%s)::text), tm_id" in query
    assert "random()" not in query
    assert params == (42, 10)


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


def test_dump_embeddings_writes_filtered_binary_copy(tmp_path, monkeypatch):
    output = tmp_path / "nested" / "translation-embeddings.dump"
    cursor = RecordingCursor(
        results=[(2,)],
        copy_chunks=[b"PGCOPY\n", b"binary-data"],
    )
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )

    count = dump_embeddings(
        output,
        "postgresql://db",
        modelname="model",
        document_kind="translations",
    )

    assert count == 2
    assert output.read_bytes() == b"PGCOPY\nbinary-data"
    assert len(cursor.copies) == 1
    assert 'FROM "translation_embeddings"' in cursor.copies[0]
    assert "WHERE model_name = 'model'" in cursor.copies[0]
    assert '"chunk_index"' in cursor.copies[0]
    assert "TO STDOUT WITH (FORMAT binary)" in cursor.copies[0]


def test_import_embeddings_replaces_model_rows_and_rebuilds_index(
    tmp_path, monkeypatch
):
    source = tmp_path / "transcription-embeddings.dump"
    source.write_bytes(b"PGCOPY\nbinary-data")
    cursor = RecordingCursor(
        fetchall_results=[[("model",)]],
        results=[(2, 3, 3)],
    )
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )

    count = import_embeddings(
        source,
        "postgresql://db",
        modelname="model",
        document_kind="transcription",
    )

    assert count == 2
    assert cursor.copy_writes == [b"PGCOPY\nbinary-data"]
    assert any(
        'CREATE TEMP TABLE "transcription_embeddings_import"' in query
        and 'LIKE "transcription_embeddings"' in query
        for query, _ in cursor.executions
    )
    deletes = [
        (query, params)
        for query, params in cursor.executions
        if query.startswith("DELETE FROM")
    ]
    assert deletes == [
        ('DELETE FROM "transcription_embeddings" WHERE model_name = %s', ("model",))
    ]
    assert any(
        query.startswith('INSERT INTO "transcription_embeddings"')
        for query, _ in cursor.executions
    )
    assert any(
        "USING hnsw" in query and "vector(3)" in query for query, _ in cursor.executions
    )


def test_high_dimensional_embeddings_use_halfvec_hnsw_index():
    cursor = RecordingCursor()

    _recreate_embedding_index(cursor, "transcription_embeddings", "model", 2560)

    assert len(cursor.executions) == 2
    query, params = cursor.executions[-1]
    assert params is None
    assert "USING hnsw" in query
    assert "embedding::halfvec(2560)" in query
    assert "halfvec_cosine_ops" in query


def test_embeddings_above_hnsw_dimension_limits_are_stored_without_index():
    cursor = RecordingCursor()

    _recreate_embedding_index(cursor, "transcription_embeddings", "model", 4001)

    assert len(cursor.executions) == 1
    assert cursor.executions[0][0].startswith("DROP INDEX IF EXISTS")


def test_import_embeddings_rejects_unexpected_model_names(tmp_path, monkeypatch):
    source = tmp_path / "translation-embeddings.dump"
    source.write_bytes(b"PGCOPY\nbinary-data")
    cursor = RecordingCursor(fetchall_results=[[("other-model",)]])
    monkeypatch.setattr(
        psycopg, "connect", lambda conninfo: RecordingConnection(cursor)
    )

    try:
        import_embeddings(
            source,
            "postgresql://db",
            modelname="model",
            document_kind="translation",
        )
    except ValueError as error:
        assert "other than 'model'" in str(error)
    else:
        raise AssertionError("Expected import_embeddings to reject mismatched models")

    assert not any(query.startswith("DELETE FROM") for query, _ in cursor.executions)


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
