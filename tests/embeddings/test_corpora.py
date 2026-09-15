import hashlib

import pytest

from scrapyrus.embeddings import EMBEDDING_CORPORA
from scrapyrus.embeddings.corpora import CorpusInputs, EmbeddingInput, chunk_text


@pytest.mark.parametrize("corpus_name", ["transcriptions", "translations"])
def test_xml_adapters_prepare_chunks_and_language_from_the_configured_source(
    corpus_name, database
):
    cursor, _ = database
    corpus = EMBEDDING_CORPORA[corpus_name]
    division = "edition" if corpus_name == "transcriptions" else "translation"
    cursor.all_results = [
        [
            {
                "transcription_id": 7,
                "source_path": "source.xml",
                "tm_id": "42",
                "xml_content": f'<div type="{division}" xml:lang="grc"><ab>one two three four five six</ab></div>',
                "type": corpus.source_type,
                "language": "en",
            }
        ]
    ]
    inputs = corpus.read_inputs(cursor, chunk_size=4, sample=None, seed=0)
    assert [r.text for r in inputs.records] == ["one two three four", "five six"]
    assert [r.values["chunk_index"] for r in inputs.records] == [0, 1]
    assert all(
        r.values["language"] == ("grc" if corpus_name == "transcriptions" else "en")
        for r in inputs.records
    )
    assert (
        inputs.records[0].values["input_hash"]
        == hashlib.sha256(b"one two three four").hexdigest()
    )
    assert cursor.executions[0][1] == (corpus.source_type,)


def test_transcription_adapter_uses_the_maximum_editorial_rendering(database):
    cursor, _ = database
    cursor.all_results = [
        [
            {
                "transcription_id": 1,
                "source_path": "source.xml",
                "tm_id": "42",
                "xml_content": '<div type="edition"><ab>word <supplied reason="lost">lost</supplied> <unclear>unclear</unclear></ab></div>',
                "type": "transcription",
                "language": None,
            }
        ]
    ]
    inputs = EMBEDDING_CORPORA["transcriptions"].read_inputs(
        cursor, chunk_size=500, sample=None, seed=0
    )
    assert "lost" in inputs.records[0].text
    assert "unclear" in inputs.records[0].text


def test_keyword_adapter_keeps_qualified_terms_whole(database):
    cursor, _ = database
    cursor.all_results = [[("lease",), ("lease, land",)]]
    inputs = EMBEDDING_CORPORA["keywords"].read_inputs(
        cursor, chunk_size=1, sample=None, seed=0
    )
    assert [r.text for r in inputs.records] == ["lease", "lease, land"]
    assert [r.values for r in inputs.records] == [
        {"keyword": "lease"},
        {"keyword": "lease, land"},
    ]
    query = cursor.executions[0][0]
    assert "SELECT DISTINCT" in query
    assert "qualifier IS NULL" in query
    assert "keyword || ', ' || qualifier" in query


@pytest.mark.parametrize("corpus_name", ["transcriptions", "translations"])
def test_xml_cleanup_removes_missing_rows_and_surplus_chunks(corpus_name, database):
    cursor, _ = database
    inputs = CorpusInputs(
        (
            EmbeddingInput("first", {"xml_id": 7, "chunk_index": 0}),
            EmbeddingInput("second", {"xml_id": 7, "chunk_index": 1}),
        )
    )
    EMBEDDING_CORPORA[corpus_name].remove_stale(cursor, "model", inputs)
    assert cursor.executions[0][1] == ("model", [7])
    assert cursor.executions[1][1] == (7, "model", 2)
    assert "chunk_index >= %s" in cursor.executions[1][0]


def test_sampled_cleanup_does_not_delete_xml_rows_outside_the_sample(database):
    cursor, _ = database
    inputs = CorpusInputs(
        (EmbeddingInput("text", {"xml_id": 7, "chunk_index": 0}),), scope_ids=(7, 8)
    )
    EMBEDDING_CORPORA["transcriptions"].remove_stale(cursor, "model", inputs)
    query, params = cursor.executions[0]
    assert "AND xml_id = ANY(%s)" in query
    assert params == ("model", [7], [7, 8])


def test_xml_sampling_is_deterministic_and_selects_the_configured_source(database):
    cursor, _ = database
    cursor.all_results = [[]]
    assert (
        EMBEDDING_CORPORA["translations"].read_sources(cursor, sample=3, seed=17) == ()
    )
    query, params = cursor.executions[0]
    assert (
        "HAVING bool_or(type = 'transcription') AND bool_or(type = 'translation')"
        in query
    )
    assert "ORDER BY md5(tm_id::text || ':' || (%s)::text), tm_id LIMIT %s" in query
    assert params == (17, 3, "translation")


def test_keyword_adapter_rejects_xml_sampling(database):
    cursor, _ = database
    with pytest.raises(ValueError, match="do not support XML record sampling"):
        EMBEDDING_CORPORA["keywords"].read_inputs(
            cursor, chunk_size=500, sample=1, seed=0
        )
    assert cursor.executions == []


def test_word_chunking_preserves_short_text_and_overlaps_long_text():
    assert chunk_text(" exact  whitespace ", 10) == (" exact  whitespace ",)
    text = " ".join(str(n) for n in range(21))
    assert chunk_text(text, 10) == (
        "0 1 2 3 4 5 6 7 8 9",
        "9 10 11 12 13 14 15 16 17 18",
        "18 19 20",
    )
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("text", 0)


def test_retrieval_rejects_keys_missing_corpus_identity_fields(database):
    cursor, _ = database
    with pytest.raises(ValueError, match="xml_id, chunk_index"):
        EMBEDDING_CORPORA["transcriptions"].retrieve(cursor, "model", {"xml_id": 7})
    assert cursor.executions == []


def test_blank_xml_is_omitted_from_embedding_inputs(database):
    cursor, _ = database
    cursor.all_results = [
        [
            {
                "transcription_id": 7,
                "source_path": "source.xml",
                "tm_id": "42",
                "xml_content": '<div type="edition"><ab/></div>',
                "type": "transcription",
                "language": None,
            }
        ]
    ]
    inputs = EMBEDDING_CORPORA["transcriptions"].read_inputs(
        cursor, chunk_size=500, sample=None, seed=0
    )
    assert inputs.records == ()
