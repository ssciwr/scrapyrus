"""Typed semantic catalog models, rendering, validation, and publication."""

from __future__ import annotations

from importlib import metadata as importlib_metadata
from typing import Any, Literal, get_args

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CATALOG_SCHEMA_VERSION = 1
CATALOG_TABLE = "scrapyrus_semantic_catalog"

RelationshipCardinality = Literal[
    "one-to-one",
    "one-to-many",
    "many-to-one",
    "many-to-many",
]
CatalogComponent = Literal["metadata", "transcriptions", "embeddings"]


def _validate_nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


def _validate_string_sequence(values: tuple[str, ...]) -> tuple[str, ...]:
    if any(not value.strip() for value in values):
        raise ValueError("values must not contain blanks")
    if len(values) != len(set(values)):
        raise ValueError("values must not contain duplicates")
    return values


class ColumnSemantics(BaseModel):
    """Domain meaning of one data-table column."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    value_meanings: dict[str, str] = Field(default_factory=dict)
    null_means: str | None = None
    examples: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()

    _description_nonblank = field_validator("description")(_validate_nonblank)
    _aliases_valid = field_validator("aliases")(_validate_string_sequence)
    _examples_valid = field_validator("examples")(_validate_string_sequence)
    _caveats_valid = field_validator("caveats")(_validate_string_sequence)

    @field_validator("null_means")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        """Reject a present but blank null meaning."""

        return None if value is None else _validate_nonblank(value)

    @field_validator("value_meanings")
    @classmethod
    def validate_value_meanings(cls, values: dict[str, str]) -> dict[str, str]:
        """Reject blank controlled values or meanings."""

        if any(
            not key.strip() or not meaning.strip() for key, meaning in values.items()
        ):
            raise ValueError("value meanings must not contain blanks")
        return values


class RelationshipSemantics(BaseModel):
    """Meaning of a logical or database-enforced relationship."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_schema: str = "public"
    target_table: str
    source_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    cardinality: RelationshipCardinality
    description: str = Field(min_length=1)
    enforced_by_database: bool = False

    _description_nonblank = field_validator("description")(_validate_nonblank)

    @field_validator("target_schema", "target_table")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Reject blank database object names."""

        return _validate_nonblank(value)

    @field_validator("source_columns", "target_columns")
    @classmethod
    def validate_columns(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank or duplicated relationship columns."""

        return _validate_string_sequence(values)

    @model_validator(mode="after")
    def validate_column_pairs(self) -> "RelationshipSemantics":
        """Require a nonempty, pairwise relationship column mapping."""

        if not self.source_columns:
            raise ValueError("a relationship must have at least one column")
        if len(self.source_columns) != len(self.target_columns):
            raise ValueError("source_columns and target_columns must have equal length")
        return self


class TableSemantics(BaseModel):
    """Structured domain semantics for one Scrapyrus-owned data table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_name: str = "public"
    table_name: str
    description: str = Field(min_length=1)
    row_grain: str = Field(min_length=1)
    useful_for: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    columns: dict[str, ColumnSemantics]
    relationships: tuple[RelationshipSemantics, ...] = ()
    caveats: tuple[str, ...] = ()

    _description_nonblank = field_validator("description")(_validate_nonblank)
    _row_grain_nonblank = field_validator("row_grain")(_validate_nonblank)
    _useful_for_valid = field_validator("useful_for")(_validate_string_sequence)
    _aliases_valid = field_validator("aliases")(_validate_string_sequence)
    _caveats_valid = field_validator("caveats")(_validate_string_sequence)

    @field_validator("schema_name", "table_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Reject blank database object names."""

        return _validate_nonblank(value)

    @field_validator("columns")
    @classmethod
    def validate_columns(
        cls, columns: dict[str, ColumnSemantics]
    ) -> dict[str, ColumnSemantics]:
        """Require at least one named semantic column."""

        if not columns:
            raise ValueError("a table must define at least one semantic column")
        if any(not name.strip() for name in columns):
            raise ValueError("column names must not be blank")
        return columns

    @model_validator(mode="after")
    def validate_relationship_sources(self) -> "TableSemantics":
        """Require relationship source columns to exist in this table."""

        missing = sorted(
            {
                column
                for relationship in self.relationships
                for column in relationship.source_columns
                if column not in self.columns
            }
        )
        if missing:
            raise ValueError(
                f"relationship source columns are not defined: {', '.join(missing)}"
            )
        return self


def validate_semantic_columns(
    semantics: TableSemantics,
    expected_columns: tuple[str, ...],
) -> None:
    """Require exact agreement between data columns and semantic column keys."""

    expected = set(expected_columns)
    actual = set(semantics.columns)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise ValueError(
            f"Semantic columns for {semantics.schema_name}.{semantics.table_name} "
            f"do not match the data columns ({'; '.join(details)})"
        )


def validate_catalog_entries(
    entries: tuple[TableSemantics, ...],
    *,
    require_relationship_targets: bool = True,
) -> None:
    """Validate entry uniqueness and optionally all relationship targets."""

    keys = [(entry.schema_name, entry.table_name) for entry in entries]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        names = ", ".join(f"{schema}.{table}" for schema, table in duplicates)
        raise ValueError(f"Duplicate semantic catalog entries: {names}")

    if not require_relationship_targets:
        return

    by_key = {(entry.schema_name, entry.table_name): entry for entry in entries}
    errors = []
    for entry in entries:
        for relationship in entry.relationships:
            target_key = (relationship.target_schema, relationship.target_table)
            target = by_key.get(target_key)
            if target is None:
                errors.append(
                    f"{entry.schema_name}.{entry.table_name} targets missing table "
                    f"{relationship.target_schema}.{relationship.target_table}"
                )
                continue
            missing_columns = [
                column
                for column in relationship.target_columns
                if column not in target.columns
            ]
            if missing_columns:
                errors.append(
                    f"{entry.schema_name}.{entry.table_name} targets missing columns "
                    f"on {relationship.target_schema}.{relationship.target_table}: "
                    f"{', '.join(missing_columns)}"
                )
    if errors:
        raise ValueError("Invalid semantic relationships: " + "; ".join(errors))


def render_table_summary(entries: tuple[TableSemantics, ...]) -> str:
    """Render deterministic human-readable descriptions for several tables."""

    return "\n\n".join(entry.description for entry in entries)


def render_catalog_entry(entry: TableSemantics) -> str:
    """Render one structured semantic entry as deterministic prose."""

    lines = [
        f"Table: {entry.table_name}",
        entry.description,
        f"Row grain: {entry.row_grain}",
    ]
    if entry.useful_for:
        lines.append(f"Useful for: {'; '.join(entry.useful_for)}")
    if entry.aliases:
        lines.append(f"Aliases: {', '.join(entry.aliases)}")
    for name, column in entry.columns.items():
        detail = column.description
        if column.aliases:
            detail += f" Aliases: {', '.join(column.aliases)}."
        if column.value_meanings:
            meanings = "; ".join(
                f"{value} = {meaning}"
                for value, meaning in column.value_meanings.items()
            )
            detail += f" Values: {meanings}."
        if column.null_means is not None:
            detail += f" Null means: {column.null_means}."
        if column.examples:
            detail += f" Examples: {', '.join(column.examples)}."
        if column.caveats:
            detail += f" Caveats: {'; '.join(column.caveats)}."
        lines.append(f"{name}: {detail}")
    for relationship in entry.relationships:
        source = ", ".join(relationship.source_columns)
        target = ", ".join(relationship.target_columns)
        enforcement = (
            "database-enforced"
            if relationship.enforced_by_database
            else "not database-enforced"
        )
        lines.append(
            f"Relationship: ({source}) -> {relationship.target_schema}."
            f"{relationship.target_table} ({target}); {relationship.cardinality}; "
            f"{enforcement}. {relationship.description}"
        )
    if entry.caveats:
        lines.extend(f"Caveat: {caveat}" for caveat in entry.caveats)
    return "\n".join(lines)


def producer_version() -> str:
    """Return the installed Scrapyrus distribution version."""

    return importlib_metadata.version("scrapyrus")


def publish_semantics(
    cursor: Any,
    entries: tuple[TableSemantics, ...],
    *,
    component: CatalogComponent,
) -> None:
    """Create, upsert, and prune one component's catalog rows without committing."""

    if component not in get_args(CatalogComponent):
        raise ValueError(f"Unknown semantic catalog component: {component!r}")
    validate_catalog_entries(entries, require_relationship_targets=False)
    cursor.execute(
        f"""
CREATE TABLE IF NOT EXISTS {CATALOG_TABLE} (
    schema_name text NOT NULL,
    table_name text NOT NULL,
    component text NOT NULL,
    catalog_schema_version integer NOT NULL,
    producer_version text NOT NULL,
    semantics jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (schema_name, table_name),
    CHECK (jsonb_typeof(semantics) = 'object')
)
"""
    )
    version = producer_version()
    for entry in entries:
        cursor.execute(
            f"""
INSERT INTO {CATALOG_TABLE} (
    schema_name, table_name, component, catalog_schema_version,
    producer_version, semantics
) VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (schema_name, table_name) DO UPDATE SET
    component = EXCLUDED.component,
    catalog_schema_version = EXCLUDED.catalog_schema_version,
    producer_version = EXCLUDED.producer_version,
    semantics = EXCLUDED.semantics,
    updated_at = now()
WHERE {CATALOG_TABLE}.component IS DISTINCT FROM EXCLUDED.component
   OR {CATALOG_TABLE}.catalog_schema_version IS DISTINCT FROM EXCLUDED.catalog_schema_version
   OR {CATALOG_TABLE}.producer_version IS DISTINCT FROM EXCLUDED.producer_version
   OR {CATALOG_TABLE}.semantics IS DISTINCT FROM EXCLUDED.semantics
""",
            (
                entry.schema_name,
                entry.table_name,
                component,
                CATALOG_SCHEMA_VERSION,
                version,
                Jsonb(entry.model_dump(mode="json")),
            ),
        )

    if entries:
        placeholders = ", ".join("(%s, %s)" for _ in entries)
        parameters: list[Any] = [component]
        for entry in entries:
            parameters.extend((entry.schema_name, entry.table_name))
        cursor.execute(
            f"DELETE FROM {CATALOG_TABLE} WHERE component = %s "
            f"AND (schema_name, table_name) NOT IN ({placeholders})",
            tuple(parameters),
        )
    else:
        cursor.execute(
            f"DELETE FROM {CATALOG_TABLE} WHERE component = %s",
            (component,),
        )
