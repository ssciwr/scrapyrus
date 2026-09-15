"""Binary transfer contract validation before vectors are published."""

import json

import pytest

from scrapyrus.embeddings import EMBEDDING_CORPORA, EmbeddingStore
from scrapyrus.embeddings.manifest import load_manifest, manifest_path, write_manifest
from scrapyrus.embeddings.specification import EmbeddingTableMetadata
from tests.embeddings.helpers import configuration, specification


@pytest.fixture
def dump(tmp_path):
    path = tmp_path / "embeddings.dump"
    path.write_bytes(b"binary")
    return path


def prepare_manifest(path, corpus="keywords", count=2, size=2, **options):
    adapter = EMBEDDING_CORPORA[corpus]
    metadata = EmbeddingTableMetadata(
        table_name=adapter.table_name,
        **specification(size=size, **options).model_dump(),
    )
    write_manifest(path, adapter, count, metadata)
    return metadata


@pytest.mark.parametrize("corpus", tuple(EMBEDDING_CORPORA))
def test_manifests_roundtrip_the_complete_non_secret_specification(dump, corpus):
    expected = prepare_manifest(dump, corpus)
    value, metadata = load_manifest(dump, EMBEDDING_CORPORA[corpus])
    assert metadata == expected
    assert value["columns"] == list(EMBEDDING_CORPORA[corpus].export_columns)
    assert value["row_count"] == 2
    assert "search_embedding" not in value["columns"]
    assert set(value["embedding_specification"]) == {
        "table_name",
        "model_name",
        "provider",
        "provider_options",
        "embedding_size",
        "endpoint_profile",
        "contract_version",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"format": "unknown"},
        {"document_kind": "translations"},
        {"columns": ["embedding"]},
        {"row_count": True},
        {"row_count": -1},
        {"embedding_specification": []},
    ],
)
def test_invalid_manifests_fail_before_opening_a_database(dump, change, monkeypatch):
    prepare_manifest(dump)
    value = json.loads(manifest_path(dump).read_text())
    value.update(change)
    manifest_path(dump).write_text(json.dumps(value))
    monkeypatch.setattr(
        "psycopg.connect",
        lambda *args: pytest.fail("Invalid manifest connected to database"),
    )
    with pytest.raises(ValueError):
        EmbeddingStore(corpus="keywords", specification=specification()).import_dump(
            dump
        )


@pytest.mark.parametrize(
    "change",
    [
        {"table_name": "translation_embeddings"},
        {"embedding_size": None},
        {"embedding_size": True},
        {"contract_version": 2},
        {"provider_options": {}},
        {"api_key": "secret"},
        {"provider_options": {"base_url": "https://private"}},
    ],
)
def test_invalid_specifications_are_never_published(dump, change):
    prepare_manifest(dump)
    value = json.loads(manifest_path(dump).read_text())
    value["embedding_specification"].update(change)
    manifest_path(dump).write_text(json.dumps(value))
    with pytest.raises(ValueError):
        load_manifest(dump, EMBEDDING_CORPORA["keywords"])


@pytest.mark.parametrize("text", ["[]", "null", "{broken"])
def test_malformed_json_is_reported_as_a_manifest_error(dump, text):
    manifest_path(dump).write_text(text)
    with pytest.raises(ValueError):
        load_manifest(dump, EMBEDDING_CORPORA["keywords"])


def test_binary_dumps_require_a_manifest(dump):
    with pytest.raises(ValueError, match="manifest is missing"):
        load_manifest(dump, EMBEDDING_CORPORA["keywords"])


@pytest.mark.parametrize(
    "stats,unmatched,message",
    [
        ((1, 2, 2), None, "row count"),
        ((2, 3, 3), None, "dimensions"),
        ((2, 2, 2), 1, "matching keyword source"),
    ],
)
def test_invalid_imports_roll_back_before_replacing_vectors(
    dump, database, stats, unmatched, message
):
    prepare_manifest(dump)
    cursor, connection = database
    cursor.metadata["keyword_embeddings"] = configuration()
    cursor.one_results = [stats] + ([(unmatched,)] if unmatched is not None else [])
    with pytest.raises(ValueError, match=message):
        EmbeddingStore(corpus="keywords", specification=specification()).import_dump(
            dump
        )
    assert connection.outcomes == ["rollback"]
    assert cursor.metadata["keyword_embeddings"] == configuration()
    assert not any(
        query.startswith(("TRUNCATE", 'DELETE FROM "keyword_embeddings"'))
        for query, _ in cursor.executions
    )


@pytest.mark.parametrize("corpus", tuple(EMBEDDING_CORPORA))
def test_empty_import_preserves_the_manifest_dimension(dump, database, corpus):
    prepare_manifest(dump, corpus, count=0, size=3000)
    cursor, connection = database
    cursor.one_results = [(0, None, None), (0,)]
    store = EmbeddingStore.from_dump(corpus=corpus, model_name="model", source=dump)
    assert store.import_dump(dump) == 0
    assert cursor.metadata[EMBEDDING_CORPORA[corpus].table_name] == configuration(
        size=3000
    )
    assert any(
        "GENERATED ALWAYS AS (embedding::halfvec(3000)) STORED" in query
        for query, _ in cursor.executions
    )
    assert connection.outcomes == ["commit"]
