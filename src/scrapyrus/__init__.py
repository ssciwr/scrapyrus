from importlib import metadata

from scrapyrus.metadata.base import catalog, table_summary
from scrapyrus.transcriptions.core import (
    epidoc_xml_to_text,
    translation_epidoc_xml_to_text,
)

__version__ = metadata.version(__package__)

__all__ = [
    "__version__",
    "catalog",
    "epidoc_xml_to_text",
    "table_summary",
    "translation_epidoc_xml_to_text",
]
