import re
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.xmlutils import (
    create_xpath_expr,
    drop_known_id_placeholders,
    optional_string,
    publication_idno_string,
)
from scrapyrus.semantics import ColumnSemantics, RelationshipSemantics, TableSemantics


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

ORIG_PLACES_INDEX_SQL = """CREATE INDEX IF NOT EXISTS orig_places_tm_id_idx ON orig_places (tm_id);
CREATE INDEX IF NOT EXISTS orig_places_pleiades_place_id_idx ON orig_places (pleiades_place_id);
CREATE INDEX IF NOT EXISTS orig_places_place_name_idx ON orig_places (place_name);"""

ORIG_PLACES_SEMANTICS = TableSemantics(
    table_name="orig_places",
    description=(
        "The orig_places table contains extracted ancient-place associations, "
        "source wording, normalized names, external IDs, relation type, and granularity."
    ),
    row_grain="One extracted ancient-place association.",
    useful_for=("ancient geography, provenance, findspots, and places of composition",),
    columns={
        "place_id": ColumnSemantics(
            description="Synthetic extracted-place row identifier, not an external place ID."
        ),
        "tm_id": ColumnSemantics(
            description="Trismegistos document ID of the record associated with the place."
        ),
        "full_place_name": ColumnSemantics(
            description="Complete source origin-place expression preserving its recorded wording."
        ),
        "place_name": ColumnSemantics(
            description="Normalized individual ancient place name extracted from the provenance text."
        ),
        "tm_place_id": ColumnSemantics(
            description="Trismegistos Place identifier for the ancient place."
        ),
        "pleiades_place_id": ColumnSemantics(
            description="Pleiades gazetteer identifier for the ancient place."
        ),
        "place_type": ColumnSemantics(
            description="Semantic relationship between the record and the place.",
            value_meanings={
                "located": "place where the object was located",
                "found": "findspot",
                "composed": "place of textual composition",
                "sent": "place from which it was sent",
                "acquired": "place of acquisition",
                "received": "place where it was received",
            },
            examples=("located", "found", "composed", "sent", "acquired", "received"),
        ),
        "granularity": ColumnSemantics(
            description="Geographic specificity of place_name.",
            value_meanings={
                "settlement": "a specific settlement",
                "nome": "a broader administrative nome",
                "region": "a broader geographic region",
            },
        ),
    },
    relationships=(
        RelationshipSemantics(
            target_table="papyri",
            source_columns=("tm_id",),
            target_columns=("tm_id",),
            cardinality="many-to-many",
            description="Logical, unenforced Trismegistos document-key join.",
        ),
    ),
)


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
        return optional_string(self.place_value_proc.evaluate_single(expression))

    def next_place_id(self):
        place_id = self._next_place_id
        self._next_place_id += 1
        return place_id


class OrigPlaceMetadataTable(MetadataTable):
    name = "orig_places"
    order_by = ("place_id",)
    schema_sql = ORIG_PLACES_SCHEMA_SQL
    semantics = ORIG_PLACES_SEMANTICS

    def index_sql(self) -> str:
        return ORIG_PLACES_INDEX_SQL

    @property
    def model_class(self) -> type[OrigPlaceModel]:
        return OrigPlaceModel

    def create_factory(self, proc):
        return OrigPlaceModelFactory(proc)

    def build_rows(
        self, factory: OrigPlaceModelFactory, idp_data: Path, metadata: Path
    ) -> list[dict[str, Any]]:
        return [model.model_dump() for model in factory.parse(str(metadata))]
