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


def publish_catalog(
    conninfo: str = "",
    **connect_kwargs: Any,
) -> None:
    """Publish every semantic component in one PostgreSQL transaction."""

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        with connection.cursor() as cursor:
            for component, entries in _CATALOG_COMPONENTS.items():
                publish_semantics(cursor, entries, component=component)
