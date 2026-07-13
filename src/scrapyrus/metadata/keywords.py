import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.xmlutils import (
    create_xpath_expr,
    drop_known_id_placeholders,
    optional_string,
    publication_idno_string,
)


KEYWORD_TERMS_XPATH = ".//tei:profileDesc/tei:textClass/tei:keywords/tei:term"
UNCERTAINTY_MARKER_RE = re.compile(r"\(\s*\?\s*\)|\?")


def _keyword_value(value: str) -> tuple[Optional[str], bool]:
    uncertain = "?" in value
    if uncertain:
        value = " ".join(UNCERTAINTY_MARKER_RE.sub("", value).split())
        if value == "":
            return None, uncertain

    return value, uncertain


class KeywordModel(BaseModel):
    keyword_id: int = Field(gt=0)
    tm_id: int = Field(gt=0)
    scheme: Optional[str] = None
    keyword_type: Optional[str] = None
    keyword: Optional[str] = None
    uncertain: bool


KEYWORDS_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS keywords (
    keyword_id integer NOT NULL PRIMARY KEY,
    tm_id integer NOT NULL,
    scheme text,
    keyword_type text,
    keyword text,
    uncertain boolean NOT NULL
);"""

KEYWORDS_DESCRIPTION = """The keywords table contains one row for each normalized keyword term assigned
to a papyrus record. It records the keyword vocabulary scheme, term type,
cleaned keyword text, and whether the assignment was marked uncertain in the
source metadata."""

KEYWORDS_SEMANTIC_CATALOG = """Table: keywords
Use this table for topical, genre, subject, language, and classification queries. Join to papyri on tm_id.
keyword_id: Synthetic row identifier for an extracted keyword; not a stable external term ID.
tm_id: Trismegistos document ID for the papyrus record that has this keyword.
scheme: Source keyword vocabulary or classification scheme from the TEI keywords element.
keyword_type: Category or type of the keyword term from the source metadata.
keyword: Normalized keyword text after removing uncertainty markers; search this field for subjects, genres, and classifications.
uncertain: True when the original keyword was marked with a question mark, meaning the assignment is uncertain."""


class KeywordModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()
        self._next_keyword_id = 1

        self.tm_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("TM"),
            value_processor=drop_known_id_placeholders,
        )
        self.term_nodes_proc = proc.new_xpath_processor()
        self.term_nodes_proc.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")
        self.term_value_proc = proc.new_xpath_processor()

    def parse(self, filename):
        data = self.doc_builder.parse_xml(xml_file_name=filename)
        tm_id = self.tm_id_proc(data)

        self.term_nodes_proc.set_context(xdm_item=data)
        term_nodes = self.term_nodes_proc.evaluate(KEYWORD_TERMS_XPATH)
        if term_nodes is None:
            return []

        return [
            model
            for term_node in term_nodes
            if (model := self._parse_term(tm_id, term_node)) is not None
        ]

    def _parse_term(self, tm_id, term_node):
        self.term_value_proc.set_context(xdm_item=term_node)
        keyword = optional_string(
            self.term_value_proc.evaluate_single("normalize-space(.)")
        )
        if keyword is None:
            return None
        keyword, uncertain = _keyword_value(keyword)
        if keyword is None:
            return None

        return KeywordModel(
            keyword_id=self.next_keyword_id(),
            tm_id=tm_id,
            scheme=optional_string(
                self.term_value_proc.evaluate_single("string((../@scheme)[1])")
            ),
            keyword_type=optional_string(
                self.term_value_proc.evaluate_single("string((@type)[1])")
            ),
            keyword=keyword,
            uncertain=uncertain,
        )

    def next_keyword_id(self):
        keyword_id = self._next_keyword_id
        self._next_keyword_id += 1
        return keyword_id


class KeywordMetadataTable(MetadataTable):
    name = "keywords"
    order_by = ("keyword_id",)
    schema_sql = KEYWORDS_SCHEMA_SQL

    def description(self) -> str:
        return KEYWORDS_DESCRIPTION

    def semantic_catalog(self) -> str:
        return KEYWORDS_SEMANTIC_CATALOG

    @property
    def model_class(self) -> type[KeywordModel]:
        return KeywordModel

    def create_factory(self, proc):
        return KeywordModelFactory(proc)

    def build_rows(
        self, factory: KeywordModelFactory, idp_data: Path, metadata: Path
    ) -> list[dict[str, Any]]:
        return [model.model_dump() for model in factory.parse(str(metadata))]
