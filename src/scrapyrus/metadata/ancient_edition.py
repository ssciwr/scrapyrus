import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.xmlutils import (
    create_xpath_expr,
    drop_known_id_placeholders,
    publication_idno_string,
)


ANCIENT_EDITION_BIBL_NODES_XPATH = (
    ".//tei:div[@type='bibliography'][@subtype='ancientEdition']/tei:listBibl/tei:bibl"
)
TM_AUTHORWORK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?trismegistos\.org/authorwork/(?P<id>\d+)\b"
)
PERSEUS_URN_RE = re.compile(r"urn:cts:[^\s]+")


def _optional_string(result):
    if result is None:
        return None

    value = result.string_value.strip()
    if value == "":
        return None

    return value


def _first_tm_authorwork_id(ref: str | None) -> int | None:
    if ref is None:
        return None

    for title_ref in ref.split():
        match = TM_AUTHORWORK_RE.match(title_ref)
        if match is not None:
            return int(match.group("id"))

    return None


def _perseus_author_urn(ref: str | None) -> str | None:
    if ref is None:
        return None

    match = PERSEUS_URN_RE.search(ref)
    if match is None:
        return None

    return match.group(0)


class AncientEditionModel(BaseModel):
    ancient_edition_id: int = Field(gt=0)
    tm_id: int = Field(gt=0)
    title: Optional[str]
    tm_title_id: Optional[int] = Field(gt=0, default=None)
    author: Optional[str] = None
    perseus_author_urn: Optional[str] = None


ANCIENT_EDITIONS_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS ancient_editions (
    ancient_edition_id integer NOT NULL PRIMARY KEY,
    tm_id integer NOT NULL,
    title text,
    tm_title_id integer,
    author text,
    perseus_author_urn text
);"""


class AncientEditionModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()
        self._next_ancient_edition_id = 1

        self.tm_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("TM"),
            value_processor=drop_known_id_placeholders,
        )
        self.bibl_nodes_proc = proc.new_xpath_processor()
        self.bibl_nodes_proc.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")
        self.bibl_value_proc = proc.new_xpath_processor()
        self.bibl_value_proc.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")

    def parse(self, filename):
        data = self.doc_builder.parse_xml(xml_file_name=filename)
        tm_id = self.tm_id_proc(data)

        self.bibl_nodes_proc.set_context(xdm_item=data)
        bibl_nodes = self.bibl_nodes_proc.evaluate(ANCIENT_EDITION_BIBL_NODES_XPATH)
        if bibl_nodes is None:
            return []

        return [self._parse_bibl(tm_id, bibl_node) for bibl_node in bibl_nodes]

    def _parse_bibl(self, tm_id, bibl_node):
        self.bibl_value_proc.set_context(xdm_item=bibl_node)

        title = self._node_string(
            "normalize-space((tei:title[@type='main'], "
            "tei:title[@type='abbreviated'], tei:title)[1])"
        )
        title_ref = self._node_string(
            "string(((tei:title[@type='main'], "
            "tei:title[@type='abbreviated'], tei:title)[1]/@ref)[1])"
        )

        return AncientEditionModel(
            ancient_edition_id=self.next_ancient_edition_id(),
            tm_id=tm_id,
            title=title,
            tm_title_id=_first_tm_authorwork_id(title_ref),
            author=self._author(),
            perseus_author_urn=_perseus_author_urn(
                self._node_string("string((tei:author[1]/@ref)[1])")
            ),
        )

    def _author(self):
        forename = self._node_string("normalize-space((tei:author/tei:forename)[1])")
        surname = self._node_string("normalize-space((tei:author/tei:surname)[1])")
        if forename is not None or surname is not None:
            return " ".join(part for part in (forename, surname) if part is not None)

        return self._node_string("normalize-space((tei:author)[1])")

    def _node_string(self, expression):
        return _optional_string(self.bibl_value_proc.evaluate_single(expression))

    def next_ancient_edition_id(self):
        ancient_edition_id = self._next_ancient_edition_id
        self._next_ancient_edition_id += 1
        return ancient_edition_id


class AncientEditionMetadataTable(MetadataTable):
    name = "ancient_editions"
    order_by = ("ancient_edition_id",)
    schema_sql = ANCIENT_EDITIONS_SCHEMA_SQL

    @property
    def model_class(self) -> type[AncientEditionModel]:
        return AncientEditionModel

    def create_factory(self, proc):
        return AncientEditionModelFactory(proc)

    def build_rows(
        self, factory: AncientEditionModelFactory, idp_data: Path, metadata: Path
    ) -> list[dict[str, Any]]:
        return [model.model_dump() for model in factory.parse(str(metadata))]
