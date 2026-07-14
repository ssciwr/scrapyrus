from importlib import metadata as importlib_metadata

from scrapyrus.metadata.base import catalog, table_summary
from scrapyrus.transcriptions.core import (
    epidoc_xml_to_text,
    translation_epidoc_xml_to_text,
)
from scrapyrus.transcriptions.search import BM25SearchHit, MetadataFilter, bm25_search

__version__ = importlib_metadata.version(__package__)

__all__ = [
    "__version__",
    "BM25SearchHit",
    "MetadataFilter",
    "bm25_search",
    "catalog",
    "epidoc_xml_to_text",
    "table_summary",
    "translation_epidoc_xml_to_text",
]
