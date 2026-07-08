from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.papyri import (
    _create_xpath_expr,
    _drop_known_id_placeholders,
    _publication_idno_string,
)


KEYWORD_TERMS_XPATH = ".//tei:profileDesc/tei:textClass/tei:keywords/tei:term"


def _optional_string(result):
    if result is None:
        return None

    value = result.string_value.strip()
    if value == "":
        return None

    return value


class KeywordModel(BaseModel):
    keyword_id: int = Field(gt=0)
    tm_id: int = Field(gt=0)
    scheme: Optional[str] = None
    keyword_type: Optional[str] = None
    keyword: Optional[str] = None


KEYWORDS_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS keywords (
    keyword_id integer NOT NULL PRIMARY KEY,
    tm_id integer NOT NULL,
    scheme text,
    keyword_type text,
    keyword text
);"""


class KeywordModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()
        self._next_keyword_id = 1

        self.tm_id_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("TM"),
            value_processor=_drop_known_id_placeholders,
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
        keyword = _optional_string(
            self.term_value_proc.evaluate_single("normalize-space(.)")
        )
        if keyword is None:
            return None

        return KeywordModel(
            keyword_id=self.next_keyword_id(),
            tm_id=tm_id,
            scheme=_optional_string(
                self.term_value_proc.evaluate_single("string((../@scheme)[1])")
            ),
            keyword_type=_optional_string(
                self.term_value_proc.evaluate_single("string((@type)[1])")
            ),
            keyword=keyword,
        )

    def next_keyword_id(self):
        keyword_id = self._next_keyword_id
        self._next_keyword_id += 1
        return keyword_id


class KeywordMetadataTable(MetadataTable):
    name = "keywords"
    order_by = ("keyword_id",)
    schema_sql = KEYWORDS_SCHEMA_SQL

    @property
    def model_class(self) -> type[KeywordModel]:
        return KeywordModel

    def create_factory(self, proc):
        return KeywordModelFactory(proc)

    def build_rows(
        self, factory: KeywordModelFactory, idp_data: Path, metadata: Path
    ) -> list[dict[str, Any]]:
        return [model.model_dump() for model in factory.parse(str(metadata))]
