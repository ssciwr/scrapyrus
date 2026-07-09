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


PRINCIPAL_EDITION_NODES_XPATH = (
    ".//tei:div[@type='bibliography' and @subtype='principalEdition']"
    "/tei:listBibl/tei:bibl"
)
BIBLIO_TARGET_RE = re.compile(r"https?://papyri\.info/biblio/(?P<id>\d+)\b")


def _optional_string(result):
    if result is None:
        return None

    value = result.string_value.strip()
    if value == "":
        return None

    return value


def _biblio_id(target: str | None) -> int | None:
    if target is None:
        return None

    match = BIBLIO_TARGET_RE.search(target)
    if match is None:
        return None

    return int(match.group("id"))


class PrincipalEditionModel(BaseModel):
    principal_edition_id: int = Field(gt=0)
    tm_id: int = Field(gt=0)
    biblio_id: Optional[int] = Field(gt=0)
    title: Optional[str]
    author: Optional[str] = None
    volume: Optional[str]
    number: Optional[str]
    page: Optional[str]


PRINCIPAL_EDITIONS_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS principal_editions (
    principal_edition_id integer NOT NULL PRIMARY KEY,
    tm_id integer NOT NULL,
    biblio_id integer,
    title text,
    author text,
    volume text,
    number text,
    page text
);"""


class PrincipalEditionModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()
        self._next_principal_edition_id = 1

        self.tm_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("TM"),
            value_processor=drop_known_id_placeholders,
        )
        self.principal_edition_nodes_proc = proc.new_xpath_processor()
        self.principal_edition_nodes_proc.declare_namespace(
            "tei", "http://www.tei-c.org/ns/1.0"
        )
        self.principal_edition_value_proc = proc.new_xpath_processor()
        self.principal_edition_value_proc.declare_namespace(
            "tei", "http://www.tei-c.org/ns/1.0"
        )

    def parse(self, filename):
        data = self.doc_builder.parse_xml(xml_file_name=filename)
        tm_id = self.tm_id_proc(data)

        self.principal_edition_nodes_proc.set_context(xdm_item=data)
        principal_edition_nodes = self.principal_edition_nodes_proc.evaluate(
            PRINCIPAL_EDITION_NODES_XPATH
        )
        if principal_edition_nodes is None:
            return []

        return [
            self._parse_principal_edition(tm_id, principal_edition_node)
            for principal_edition_node in principal_edition_nodes
        ]

    def _parse_principal_edition(self, tm_id, principal_edition_node):
        self.principal_edition_value_proc.set_context(xdm_item=principal_edition_node)

        return PrincipalEditionModel(
            principal_edition_id=self.next_principal_edition_id(),
            tm_id=tm_id,
            biblio_id=self._biblio_id(),
            title=self._title(),
            author=self._author(),
            volume=self._scope("volume"),
            number=self._scope("number", "numbers"),
            page=self._scope("page", "pages", "pp"),
        )

    def _node_string(self, expression):
        return _optional_string(
            self.principal_edition_value_proc.evaluate_single(expression)
        )

    def _title(self):
        for title_type in ("main", "abbreviated"):
            title = self._node_string(
                f"normalize-space((tei:title[@type='{title_type}'])[1])"
            )
            if title is not None:
                return title

        return self._node_string(
            "normalize-space((tei:title[not(@type=('main', 'abbreviated'))])[1])"
        )

    def _author(self):
        forename = self._node_string("normalize-space((tei:author[1]/tei:forename)[1])")
        surname = self._node_string("normalize-space((tei:author[1]/tei:surname)[1])")
        if forename is not None or surname is not None:
            return " ".join(part for part in (forename, surname) if part is not None)

        return self._node_string("normalize-space((tei:author)[1])")

    def _biblio_id(self):
        targets = self.principal_edition_value_proc.evaluate("tei:ptr/@target")
        if targets is None:
            return None

        for target in targets:
            biblio_id = _biblio_id(target.string_value)
            if biblio_id is not None:
                return biblio_id

        return None

    def _scope(self, *scope_names):
        predicates = " or ".join(
            f"@unit='{scope_name}' or @type='{scope_name}'"
            for scope_name in scope_names
        )
        return self._node_string(f"normalize-space((tei:biblScope[{predicates}])[1])")

    def next_principal_edition_id(self):
        principal_edition_id = self._next_principal_edition_id
        self._next_principal_edition_id += 1
        return principal_edition_id


class PrincipalEditionMetadataTable(MetadataTable):
    name = "principal_editions"
    order_by = ("principal_edition_id",)
    schema_sql = PRINCIPAL_EDITIONS_SCHEMA_SQL

    @property
    def model_class(self) -> type[PrincipalEditionModel]:
        return PrincipalEditionModel

    def create_factory(self, proc):
        return PrincipalEditionModelFactory(proc)

    def build_rows(
        self, factory: PrincipalEditionModelFactory, idp_data: Path, metadata: Path
    ) -> list[dict[str, Any]]:
        return [model.model_dump() for model in factory.parse(str(metadata))]
