"""Lightweight aggregate access to all Scrapyrus semantic definitions."""

from typing import Any

import psycopg

from scrapyrus.metadata.ancient_edition import ANCIENT_EDITIONS_SEMANTICS
from scrapyrus.metadata.keywords import KEYWORDS_SEMANTICS
from scrapyrus.metadata.origdate import ORIG_DATES_SEMANTICS
from scrapyrus.metadata.origplace import ORIG_PLACES_SEMANTICS
from scrapyrus.metadata.papyri import PAPYRI_SEMANTICS
from scrapyrus.metadata.principal_edition import PRINCIPAL_EDITIONS_SEMANTICS
from scrapyrus.semantics import (
    CatalogComponent,
    TableSemantics,
    publish_semantics,
    render_catalog_entry,
    render_table_summary,
)
from scrapyrus.transcriptions.semantics import (
    EMBEDDING_TABLE_METADATA_SEMANTICS,
    KEYWORD_EMBEDDINGS_SEMANTICS,
    TRANSCRIPTIONS_SEMANTICS,
    TRANSCRIPTION_EMBEDDINGS_SEMANTICS,
    TRANSLATION_EMBEDDINGS_SEMANTICS,
)


_CATALOG_COMPONENTS: dict[CatalogComponent, tuple[TableSemantics, ...]] = {
    "metadata": (
        PAPYRI_SEMANTICS,
        PRINCIPAL_EDITIONS_SEMANTICS,
        KEYWORDS_SEMANTICS,
        ORIG_DATES_SEMANTICS,
        ORIG_PLACES_SEMANTICS,
        ANCIENT_EDITIONS_SEMANTICS,
    ),
    "transcriptions": (TRANSCRIPTIONS_SEMANTICS,),
    "embeddings": (
        EMBEDDING_TABLE_METADATA_SEMANTICS,
        TRANSCRIPTION_EMBEDDINGS_SEMANTICS,
        TRANSLATION_EMBEDDINGS_SEMANTICS,
        KEYWORD_EMBEDDINGS_SEMANTICS,
    ),
}
_CATALOG_ENTRIES = tuple(
    entry
    for component_entries in _CATALOG_COMPONENTS.values()
    for entry in component_entries
)


def catalog_entries() -> tuple[TableSemantics, ...]:
    """Return all semantic entries in deterministic producer order."""

    return _CATALOG_ENTRIES


def catalog_entry(table_name: str, schema_name: str = "public") -> TableSemantics:
    """Return one structured semantic entry or raise an informative error."""

    for entry in _CATALOG_ENTRIES:
        if entry.schema_name == schema_name and entry.table_name == table_name:
            return entry
    available = ", ".join(
        f"{entry.schema_name}.{entry.table_name}" for entry in _CATALOG_ENTRIES
    )
    raise ValueError(
        f"Unknown semantic table {schema_name}.{table_name!s}. "
        f"Available tables: {available}"
    )


def table_summary() -> str:
    """Render descriptions of every cataloged data table."""

    return render_table_summary(_CATALOG_ENTRIES)


def catalog(table_name: str, schema_name: str = "public") -> str:
    """Render detailed semantics for one cataloged data table."""

    return render_catalog_entry(catalog_entry(table_name, schema_name))


def publish_catalog(
    conninfo: str = "",
    **connect_kwargs: Any,
) -> None:
    """Publish every semantic component in one PostgreSQL transaction."""

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        with connection.cursor() as cursor:
            for component, entries in _CATALOG_COMPONENTS.items():
                publish_semantics(cursor, entries, component=component)


__all__ = [
    "catalog",
    "catalog_entries",
    "catalog_entry",
    "publish_catalog",
    "table_summary",
]
