import pytest
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from scrapyrus.metadata.base import MetadataTable
from scrapyrus.semantic_catalog import _CATALOG_COMPONENTS, publish_catalog
from scrapyrus.semantics import (
    CATALOG_SCHEMA_VERSION,
    ColumnSemantics,
    RelationshipSemantics,
    TableSemantics,
    publish_semantics,
    validate_catalog_entries,
)
from scrapyrus.transcriptions.core import TRANSCRIPTION_COLUMNS
from scrapyrus.transcriptions.embeddings import (
    EMBEDDING_DUMP_COLUMNS,
    KEYWORD_EMBEDDING_DUMP_COLUMNS,
)


class RecordingCursor:
    def __init__(self):
        self.executions = []

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor


def _entry(table_name="example", **overrides):
    values = {
        "table_name": table_name,
        "description": "Example table.",
        "row_grain": "One example row.",
        "columns": {"id": ColumnSemantics(description="Row identity.")},
    }
    values.update(overrides)
    return TableSemantics(**values)


def test_semantic_models_are_frozen_and_forbid_extra_fields():
    entry = _entry()

    with pytest.raises(ValidationError):
        ColumnSemantics(description="Identity.", typo=True)
    with pytest.raises(ValidationError):
        entry.description = "Changed"


@pytest.mark.parametrize("value", ["", "   "])
def test_semantic_models_reject_blank_descriptions(value):
    with pytest.raises(ValidationError):
        ColumnSemantics(description=value)
    with pytest.raises(ValidationError):
        _entry(description=value)


def test_relationships_require_matching_nonempty_column_pairs():
    with pytest.raises(ValidationError, match="at least one column"):
        RelationshipSemantics(
            target_table="target",
            source_columns=(),
            target_columns=(),
            cardinality="many-to-one",
            description="Example relationship.",
        )
    with pytest.raises(ValidationError, match="equal length"):
        RelationshipSemantics(
            target_table="target",
            source_columns=("first", "second"),
            target_columns=("id",),
            cardinality="many-to-one",
            description="Example relationship.",
        )


def test_catalog_has_all_tables_with_exact_static_column_coverage():
    entries = tuple(
        entry
        for component_entries in _CATALOG_COMPONENTS.values()
        for entry in component_entries
    )
    assert tuple(entry.table_name for entry in entries) == (
        "papyri",
        "principal_editions",
        "keywords",
        "orig_dates",
        "orig_places",
        "ancient_editions",
        "transcriptions",
        "embedding_table_metadata",
        "transcription_embeddings",
        "translation_embeddings",
        "keyword_embeddings",
    )
    metadata_entries = entries[:6]
    for table_type, entry in zip(
        MetadataTable.registered_tables(), metadata_entries, strict=True
    ):
        assert set(entry.columns) == set(table_type().model_class.model_fields)
    assert set(entries[6].columns) == set(TRANSCRIPTION_COLUMNS)
    assert set(entries[7].columns) == {
        "table_name",
        "model_name",
        "embedding_size",
        "provider",
        "provider_options",
        "endpoint_profile",
        "contract_version",
    }
    assert set(entries[8].columns) == set(EMBEDDING_DUMP_COLUMNS)
    assert set(entries[9].columns) == set(EMBEDDING_DUMP_COLUMNS)
    assert set(entries[10].columns) == set(KEYWORD_EMBEDDING_DUMP_COLUMNS)
    validate_catalog_entries(entries)


def test_catalog_schema_version_is_stable():
    assert CATALOG_SCHEMA_VERSION == 1


def test_publish_catalog_publishes_all_components_in_one_connection(monkeypatch):
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)
    connect_calls = []
    publication_calls = []

    def connect(conninfo, **kwargs):
        connect_calls.append((conninfo, kwargs))
        return connection

    monkeypatch.setattr("scrapyrus.semantic_catalog.psycopg.connect", connect)
    monkeypatch.setattr(
        "scrapyrus.semantic_catalog.publish_semantics",
        lambda cursor, entries, *, component: publication_calls.append(
            (cursor, tuple(entry.table_name for entry in entries), component)
        ),
    )

    publish_catalog(
        "postgresql://database.example/scrapyrus",
        application_name="catalog-test",
    )

    assert connect_calls == [
        (
            "postgresql://database.example/scrapyrus",
            {"application_name": "catalog-test"},
        )
    ]
    assert publication_calls == [
        (
            cursor,
            (
                "papyri",
                "principal_editions",
                "keywords",
                "orig_dates",
                "orig_places",
                "ancient_editions",
            ),
            "metadata",
        ),
        (cursor, ("transcriptions",), "transcriptions"),
        (
            cursor,
            (
                "embedding_table_metadata",
                "transcription_embeddings",
                "translation_embeddings",
                "keyword_embeddings",
            ),
            "embeddings",
        ),
    ]


def test_publish_semantics_upserts_parameterized_json_and_prunes_component(
    monkeypatch,
):
    cursor = RecordingCursor()
    entries = (_entry("first"), _entry("second"))
    monkeypatch.setattr("scrapyrus.semantics.producer_version", lambda: "9.8.7")

    publish_semantics(cursor, entries, component="metadata")

    assert (
        "CREATE TABLE IF NOT EXISTS scrapyrus_semantic_catalog"
        in cursor.executions[0][0]
    )
    upserts = cursor.executions[1:3]
    assert all("IS DISTINCT FROM" in query for query, _ in upserts)
    assert [params[:5] for _, params in upserts] == [
        ("public", "first", "metadata", 1, "9.8.7"),
        ("public", "second", "metadata", 1, "9.8.7"),
    ]
    assert all(isinstance(params[5], Jsonb) for _, params in upserts)
    assert upserts[0][1][5].obj == entries[0].model_dump(mode="json")
    delete_query, delete_params = cursor.executions[-1]
    assert "WHERE component = %s" in delete_query
    assert "NOT IN" in delete_query
    assert delete_params == (
        "metadata",
        "public",
        "first",
        "public",
        "second",
    )


def test_publish_semantics_validates_before_executing_sql():
    cursor = RecordingCursor()
    duplicate = _entry()

    with pytest.raises(ValueError, match="Duplicate"):
        publish_semantics(cursor, (duplicate, duplicate), component="metadata")

    assert cursor.executions == []


def test_publish_semantics_rejects_unknown_component_before_sql():
    cursor = RecordingCursor()

    with pytest.raises(ValueError, match="Unknown semantic catalog component"):
        publish_semantics(cursor, (_entry(),), component="typo")

    assert cursor.executions == []
