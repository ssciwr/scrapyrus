import hashlib
from dataclasses import replace

import psycopg
import pytest

from scrapyrus.embeddings import (
    EMBEDDING_CORPORA,
    DocumentMatch,
    EmbeddingSpecification,
    EmbeddingStore,
    EmbeddingsUnavailableError,
    KeywordMatch,
    PgvectorUnavailableError,
    SourceUnavailableError,
)
from scrapyrus.embeddings.schema import cosine_distance, recreate_embedding_index

CORPORA = tuple(EMBEDDING_CORPORA)


def source_rows(corpus_name, text="land lease", *, xml_id=7):
    if corpus_name == "keywords":
        return [(text,)]
    division = "edition" if corpus_name == "transcriptions" else "translation"
    return [
        {
            "transcription_id": xml_id,
            "source_path": "source.xml",
            "tm_id": "42",
            "xml_content": f'<div type="{division}" xml:lang="en"><ab>{text}</ab></div>',
            "type": EMBEDDING_CORPORA[corpus_name].source_type,
            "language": "en",
        }
    ]


def make_store(corpus_name, client=None):
    return EmbeddingStore(
        corpus=corpus_name, client=client, specification=EmbeddingSpecification("model")
    )


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_ingestion_and_repeated_queries_share_the_bound_client(
    corpus_name, database, client
):
    cursor, connection = database
    cursor.all_results = [source_rows(corpus_name)]
    cursor.one_results = [(0, None, None)]
    store = make_store(corpus_name, client)

    assert store.ingest("postgresql://db", progressbar=False) == 1
    assert client.documents == ["land lease"]
    inserts = [
        (q, p)
        for q, p in cursor.executions
        if q.startswith("INSERT INTO")
        and p
        and isinstance(p, dict)
        and "embedding" in p
    ]
    assert len(inserts) == 1
    assert inserts[0][1]["model_name"] == "model"
    assert EMBEDDING_CORPORA[corpus_name].table_name in inserts[0][0]

    rows = (
        [("lease, land", 0.9)]
        if corpus_name == "keywords"
        else [
            ("source.xml", "42", "en", "land lease", 0.9),
        ]
    )
    cursor.all_results = [rows, rows]
    cursor.one_results = [(1, 2, 2), (1, 2, 2)]
    expected = (
        (KeywordMatch("lease, land", 0.9),)
        if corpus_name == "keywords"
        else (DocumentMatch("source.xml", "42", "en", "land lease", 0.9),)
    )
    assert store.query("lease", top_k=1) == expected
    assert store.query("contract", top_k=1) == expected
    assert client.queries == ["lease", "contract"]
    assert connection.outcomes == ["commit", "commit", "commit"]
    query, params = cursor.executions[-1]
    assert params == {"model_name": "model", "embedding": "[1,0]", "top_k": 1}
    if corpus_name != "keywords":
        assert "PARTITION BY xml_id" in query
        assert "WHERE chunk_rank = 1" in query


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_incremental_ingestion_skips_current_records_and_embeds_changed_records(
    corpus_name, database, client
):
    cursor, _ = database
    rows = source_rows(corpus_name, "unchanged") + source_rows(
        corpus_name, "changed", xml_id=8
    )
    cursor.all_results = [rows]
    current = (
        (1,)
        if corpus_name == "keywords"
        else (
            hashlib.sha256(b"unchanged").hexdigest(),
            "source.xml",
            "42",
            "en",
        )
    )
    cursor.one_results = [(1, 2, 2), current, None]

    assert (
        make_store(corpus_name, client).ingest(stale_only=True, progressbar=False) == 1
    )
    assert client.documents == ["changed"]


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_incremental_ingestion_rejects_dimensions_different_from_existing_vectors(
    corpus_name, database, client
):
    cursor, connection = database
    cursor.all_results = [source_rows(corpus_name)]
    cursor.one_results = [(1, 3, 3), None]
    with pytest.raises(ValueError, match="expected 3"):
        make_store(corpus_name, client).ingest(stale_only=True, progressbar=False)
    assert connection.outcomes == ["rollback"]
    assert not any(
        q.startswith("DELETE FROM") and EMBEDDING_CORPORA[corpus_name].table_name in q
        for q, _ in cursor.executions
    )


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_ingestion_rejects_inconsistent_new_vectors_before_writing(
    corpus_name, database, client
):
    cursor, connection = database
    cursor.all_results = [
        source_rows(corpus_name, "first") + source_rows(corpus_name, "second", xml_id=8)
    ]
    cursor.one_results = [(0, None, None)]
    client.vectors = [(1, 0), (1, 0, 0)]
    with pytest.raises(ValueError, match="expected 2"):
        make_store(corpus_name, client).ingest(progressbar=False)
    assert connection.outcomes == ["rollback"]
    assert not any(
        isinstance(p, dict) and "embedding" in p for _, p in cursor.executions
    )


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_empty_sources_remove_stale_records_without_calling_the_client(
    corpus_name, database, client
):
    cursor, _ = database
    cursor.all_results = [[]]
    cursor.one_results = [(0, None, None)]
    assert make_store(corpus_name, client).ingest(progressbar=False) == 0
    assert client.documents == []
    query, params = cursor.executions[-1]
    assert query.startswith("DELETE FROM")
    assert params == ("model", [])


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_context_length_errors_skip_only_the_affected_input(
    corpus_name, database, client, capsys
):
    cursor, connection = database
    cursor.all_results = [
        source_rows(corpus_name, "too long")
        + source_rows(corpus_name, "short", xml_id=8)
    ]
    cursor.one_results = [(0, None, None)]
    client.vectors = [
        ValueError("maximum context length: requested 99999 input tokens"),
        (1, 0),
    ]
    assert make_store(corpus_name, client).ingest(progressbar=False) == 1
    assert "context-length validation error" in capsys.readouterr().out
    assert connection.outcomes == ["commit"]


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_other_client_errors_roll_back(corpus_name, database, client):
    cursor, connection = database
    cursor.all_results = [source_rows(corpus_name)]
    cursor.one_results = [(0, None, None)]
    client.vectors = [RuntimeError("server failed")]
    with pytest.raises(RuntimeError, match="server failed"):
        make_store(corpus_name, client).ingest(progressbar=False)
    assert connection.outcomes == ["rollback"]


@pytest.mark.parametrize("corpus_name", CORPORA)
@pytest.mark.parametrize("stats", [(0, None, None), (2, 2, 3)])
def test_query_rejects_empty_or_inconsistent_stores_before_embedding(
    corpus_name, stats, database, client
):
    cursor, connection = database
    cursor.one_results = [stats]
    with pytest.raises(ValueError):
        make_store(corpus_name, client).query("lease")
    assert client.queries == []
    assert connection.outcomes == ["rollback"]


@pytest.mark.parametrize(
    "vector", [(), (float("nan"), 0), (float("inf"), 0), (1, 0, 0)]
)
def test_query_validates_client_vectors(vector, database, client):
    cursor, _ = database
    cursor.one_results = [(1, 2, 2)]
    client.vectors = [vector]
    with pytest.raises(ValueError):
        make_store("keywords", client).query("lease")
    assert len(cursor.executions) == 1


@pytest.mark.parametrize("text,top_k", [(" ", 1), ("lease", 0)])
def test_invalid_queries_fail_before_connecting(text, top_k, monkeypatch, client):
    def unexpected(*args):
        pytest.fail("Invalid query opened a database connection")

    monkeypatch.setattr(psycopg, "connect", unexpected)
    with pytest.raises(ValueError):
        make_store("keywords", client).query(text, top_k=top_k)


def test_store_requires_a_known_corpus_and_nonblank_model():
    with pytest.raises(ValueError, match="Unknown embedding corpus"):
        make_store("unknown")
    with pytest.raises(ValueError, match="model_name must not be blank"):
        EmbeddingSpecification(" ")
    with pytest.raises(ValueError, match="client is required"):
        make_store("keywords").query("lease")


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_delete_uses_the_bound_corpus_and_model_without_a_client(corpus_name, database):
    cursor, _ = database
    cursor.rowcount = 5
    assert make_store(corpus_name).delete() == 5
    query, params = cursor.executions[-1]
    assert EMBEDDING_CORPORA[corpus_name].table_name in query
    assert params == ("model",)


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_dump_and_import_use_the_same_corpus_column_order(
    corpus_name, database, tmp_path
):
    cursor, connection = database
    cursor.one_results = [(2, 2, 2)]
    cursor.copy_chunks = [b"binary", b" corpus"]
    target = tmp_path / "nested" / "corpus.dump"
    store = make_store(corpus_name)
    assert store.dump(target) == 2
    assert target.read_bytes() == b"binary corpus"
    export_sql = cursor.copies[-1]
    corpus = EMBEDDING_CORPORA[corpus_name]
    columns = ", ".join(f'"{c}"' for c in corpus.export_columns)
    assert columns in export_sql
    assert corpus.table_name in export_sql
    assert "WHERE model_name = 'model'" in export_sql
    cursor.all_results = [[("model",)]]
    cursor.one_results = [(2, 2, 2)]
    assert store.import_dump(target) == 2
    assert cursor.copy_writes == [b"binary corpus"]
    assert columns in cursor.copies[-1]
    assert connection.outcomes == ["commit", "commit"]


@pytest.mark.parametrize(
    "models,stats", [([("other",)], (2, 2, 2)), ([("model",)], (2, 2, 3))]
)
def test_invalid_imports_do_not_delete_existing_vectors(
    models, stats, database, tmp_path
):
    cursor, connection = database
    cursor.all_results = [models]
    cursor.one_results = [stats]
    source = tmp_path / "corpus.dump"
    source.write_bytes(b"binary")
    with pytest.raises(ValueError):
        make_store("keywords").import_dump(source)
    assert not any(
        q.startswith("DELETE FROM") and "keyword_embeddings" in q
        for q, _ in cursor.executions
    )
    assert connection.outcomes == ["rollback"]


@pytest.mark.parametrize(
    "corpus_name,key",
    [
        ("keywords", {"keyword": "lease, land"}),
        ("transcriptions", {"xml_id": 7, "chunk_index": 1}),
        ("translations", {"xml_id": 9, "chunk_index": 2}),
    ],
)
def test_retrieve_uses_exact_corpus_record_keys(corpus_name, key, database):
    cursor, _ = database
    cursor.one_results = [("[1,0]",)]
    assert make_store(corpus_name).retrieve(key) == (1.0, 0.0)
    query, params = cursor.executions[-1]
    assert params == {**key, "model_name": "model"}
    assert all(f'"{column}" = %({column})s' in query for column in key)


@pytest.mark.parametrize("corpus_name", CORPORA)
def test_missing_embedding_tables_report_the_bound_corpus(
    corpus_name, database, client
):
    cursor, _ = database

    def fail(text):
        raise psycopg.errors.UndefinedTable()

    cursor.fail_on = fail
    with pytest.raises(EmbeddingsUnavailableError, match=f"ingest {corpus_name}"):
        make_store(corpus_name, client).query("lease")


@pytest.mark.parametrize(
    "corpus_name,command",
    [("keywords", "metadata ingest"), ("translations", "transcriptions ingest")],
)
def test_missing_source_tables_report_the_source_ingestion_command(
    corpus_name, command, database, client
):
    cursor, _ = database

    def fail(text):
        if text.lstrip().startswith("SELECT"):
            raise psycopg.errors.UndefinedTable()

    cursor.fail_on = fail
    with pytest.raises(SourceUnavailableError, match=command):
        make_store(corpus_name, client).ingest(progressbar=False)


def test_missing_pgvector_is_reported_before_source_reads(database, client):
    cursor, _ = database

    def fail(text):
        raise psycopg.errors.UndefinedFile('extension "vector" is not available')

    cursor.fail_on = fail
    with pytest.raises(PgvectorUnavailableError):
        make_store("keywords", client).ingest(progressbar=False)


@pytest.mark.parametrize(
    "dimensions,operator",
    [(2, "vector_cosine_ops"), (3000, "halfvec_cosine_ops"), (5000, None)],
)
def test_search_casts_match_index_casts(dimensions, operator, database):
    cursor, _ = database
    recreate_embedding_index(cursor, "keyword_embeddings", "model", dimensions)
    distance = cosine_distance(dimensions).as_string()
    query = cursor.executions[-1][0]
    if operator is None:
        assert query.startswith("DROP INDEX")
        assert '"embedding" <=>' in distance
    else:
        assert operator in query
        cast = f"{'halfvec' if dimensions == 3000 else 'vector'}({dimensions})"
        assert cast in query and cast in distance


def test_registry_extension_drives_schema_creation_and_store_operations(
    monkeypatch, database
):
    cursor, _ = database
    extra = replace(
        EMBEDDING_CORPORA["keywords"],
        name="terms",
        table_name="term_embeddings",
        semantics=EMBEDDING_CORPORA["keywords"].semantics.model_copy(
            update={"table_name": "term_embeddings"}
        ),
    )
    monkeypatch.setattr(
        "scrapyrus.embeddings.store.EMBEDDING_CORPORA", {"terms": extra}
    )
    cursor.rowcount = 1
    assert make_store("terms").delete() == 1
    assert any(
        'CREATE TABLE IF NOT EXISTS "term_embeddings"' in q
        for q, _ in cursor.executions
    )
    assert not any(
        'CREATE TABLE IF NOT EXISTS "keyword_embeddings"' in q
        for q, _ in cursor.executions
    )


@pytest.mark.parametrize("options", [{"chunk_size": 0}, {"sample": 0}])
def test_invalid_ingestion_options_fail_before_connecting(options, monkeypatch, client):
    def unexpected(*args):
        pytest.fail("Invalid ingestion opened a database connection")

    monkeypatch.setattr(psycopg, "connect", unexpected)
    with pytest.raises(ValueError):
        make_store("transcriptions", client).ingest(**options)


def test_malformed_client_batch_is_rejected_before_writing(database, client):
    cursor, connection = database
    cursor.all_results = [source_rows("keywords")]
    cursor.one_results = [(0, None, None)]
    client.embed_documents = lambda texts: []
    with pytest.raises(ValueError, match="one vector per input"):
        make_store("keywords", client).ingest(progressbar=False)
    assert connection.outcomes == ["rollback"]


def test_ingestion_closes_the_progress_bar_when_the_client_fails(
    database, client, monkeypatch
):
    cursor, connection = database
    cursor.all_results = [source_rows("keywords")]
    cursor.one_results = [(0, None, None)]
    client.vectors = [RuntimeError("server failed")]
    closed = []

    class Progress:
        def __init__(self, records, **options):
            self.records = records

        def __iter__(self):
            return iter(self.records)

        def close(self):
            closed.append(True)

    monkeypatch.setattr("scrapyrus.embeddings.store.tqdm", Progress)
    with pytest.raises(RuntimeError):
        make_store("keywords", client).ingest(progressbar=True)
    assert closed == [True]
    assert connection.outcomes == ["rollback"]
