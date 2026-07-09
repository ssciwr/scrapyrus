import re
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.xmlutils import (
    create_xpath_expr,
    drop_known_id_placeholders,
    publication_idno_string,
)


ORIG_PLACE_XPATH = ".//tei:msDesc/tei:history/tei:origin/tei:origPlace"
ORIG_PLACE_NAME_NODES_XPATH = (
    ".//tei:msDesc/tei:history/tei:provenance/tei:p/tei:placeName[@type='ancient']"
)
TRISMEGISTOS_PLACE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?trismegistos\.org/place/(?P<id>\d+)\b"
)
PLEIADES_PLACE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?pleiades\.stoa\.org/places/(?P<id>\d+)\b"
)
PLACE_TYPES = {"located", "found", "composed", "sent", "acquired", "received"}
GRANULARITIES = {"settlement", "nome", "region"}


def _optional_string(result):
    if result is None:
        return None

    value = result.string_value.strip()
    if value == "":
        return None

    return value


def _first_place_id(pattern: re.Pattern[str], value: str | None) -> int | None:
    if value is None:
        return None

    match = pattern.search(value)
    if match is None:
        return None

    return int(match.group("id"))


def _place_ids(pattern: re.Pattern[str], value: str | None) -> tuple[int, ...]:
    if value is None:
        return ()

    return tuple(int(match.group("id")) for match in pattern.finditer(value))


class OrigPlaceModel(BaseModel):
    place_id: int = Field(gt=0)
    tm_id: int = Field(gt=0)
    full_place_name: str
    place_name: str
    tm_place_id: Optional[int] = Field(gt=0, default=None)
    pleiades_place_id: Optional[int] = Field(gt=0, default=None)
    place_type: Optional[
        Literal["located", "found", "composed", "sent", "acquired", "received"]
    ] = None
    granularity: Literal["settlement", "nome", "region"] = "settlement"


ORIG_PLACES_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS orig_places (
    place_id integer NOT NULL PRIMARY KEY,
    tm_id integer NOT NULL,
    full_place_name text NOT NULL,
    place_name text NOT NULL,
    tm_place_id integer,
    pleiades_place_id integer,
    place_type text,
    granularity text NOT NULL
);"""

ORIG_PLACES_DESCRIPTION = """The orig_places table contains one row for each extracted ancient place
associated with a papyrus record's origin or provenance. It stores the full
source place expression, normalized place name, Trismegistos and Pleiades place
identifiers, relationship type, and geographic granularity."""

ORIG_PLACES_SEMANTIC_CATALOG = """Table: orig_places
Use this table for ancient geography, provenance, findspot, composition place, and origin-place queries. Join to papyri on tm_id.
place_id: Synthetic row identifier for an extracted place statement; not an external place ID.
tm_id: Trismegistos document ID for the papyrus record associated with this place.
full_place_name: Complete source origin-place expression, useful when the query asks for the full recorded provenance wording.
place_name: Normalized ancient place name extracted from the provenance text.
tm_place_id: Trismegistos place ID for the ancient place, when available.
pleiades_place_id: Pleiades place ID for the ancient place, when available.
place_type: Relationship between the record and place, such as located, found, composed, sent, acquired, or received.
granularity: Geographic specificity of place_name: settlement is most specific, while nome and region are broader areas."""


class OrigPlaceModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()
        self._next_place_id = 1

        self.tm_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("TM"),
            value_processor=drop_known_id_placeholders,
        )
        self.full_place_name_proc = create_xpath_expr(
            proc,
            f"normalize-space(({ORIG_PLACE_XPATH})[1])",
        )
        self.place_nodes_proc = proc.new_xpath_processor()
        self.place_nodes_proc.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")
        self.place_value_proc = proc.new_xpath_processor()
        self.place_value_proc.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")

    def parse(self, filename):
        data = self.doc_builder.parse_xml(xml_file_name=filename)
        tm_id = self.tm_id_proc(data)
        full_place_name = self.full_place_name_proc(data) or ""

        self.place_nodes_proc.set_context(xdm_item=data)
        place_nodes = self.place_nodes_proc.evaluate(ORIG_PLACE_NAME_NODES_XPATH)
        if place_nodes is None:
            return []

        models = []
        for place_node in place_nodes:
            models.extend(self._parse_place(tm_id, full_place_name, place_node))

        return models

    def _parse_place(self, tm_id, full_place_name, place_node):
        self.place_value_proc.set_context(xdm_item=place_node)

        place_name = self._node_string("normalize-space(.)")
        if place_name is None:
            return []

        place_type = self._node_string("string((ancestor::tei:provenance[1]/@type)[1])")
        if place_type is not None and place_type not in PLACE_TYPES:
            return []

        granularity = self._node_string("string((@subtype)[1])") or "settlement"
        if granularity not in GRANULARITIES:
            return []

        ref = self._node_string("string((@ref)[1])")
        tm_place_ids = _place_ids(TRISMEGISTOS_PLACE_RE, ref) or (None,)
        pleiades_place_id = _first_place_id(PLEIADES_PLACE_RE, ref)

        return [
            OrigPlaceModel(
                place_id=self.next_place_id(),
                tm_id=tm_id,
                full_place_name=full_place_name,
                place_name=place_name,
                tm_place_id=tm_place_id,
                pleiades_place_id=pleiades_place_id,
                place_type=place_type,
                granularity=granularity,
            )
            for tm_place_id in tm_place_ids
        ]

    def _node_string(self, expression):
        return _optional_string(self.place_value_proc.evaluate_single(expression))

    def next_place_id(self):
        place_id = self._next_place_id
        self._next_place_id += 1
        return place_id


class OrigPlaceMetadataTable(MetadataTable):
    name = "orig_places"
    order_by = ("place_id",)
    schema_sql = ORIG_PLACES_SCHEMA_SQL

    def description(self) -> str:
        return ORIG_PLACES_DESCRIPTION

    def semantic_catalog(self) -> str:
        return ORIG_PLACES_SEMANTIC_CATALOG

    @property
    def model_class(self) -> type[OrigPlaceModel]:
        return OrigPlaceModel

    def create_factory(self, proc):
        return OrigPlaceModelFactory(proc)

    def build_rows(
        self, factory: OrigPlaceModelFactory, idp_data: Path, metadata: Path
    ) -> list[dict[str, Any]]:
        return [model.model_dump() for model in factory.parse(str(metadata))]
