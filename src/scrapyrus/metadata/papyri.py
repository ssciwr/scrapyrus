from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from scrapyrus.metadata.base import MetadataTable
from scrapyrus.metadata.xmlutils import (
    create_xpath_expr,
    drop_known_id_placeholders,
    drop_unknown,
    first_string,
    publication_idno_string,
)
from scrapyrus.semantics import (
    ColumnSemantics,
    RelationshipSemantics,
    TableSemantics,
)


class PapyrusModel(BaseModel):
    source_path: str
    tm_id: int = Field(gt=0)
    dclp_id: Optional[int] = Field(gt=0, default=None)
    dclp_hybrid_id: Optional[str] = None
    ddb_perseus_style_id: Optional[str] = None
    ddb_filename: Optional[str] = None
    ddb_hybrid_id: Optional[str] = None
    hgv_id: Optional[str] = Field(pattern=r"[0-9]*[a-z]*", default=None)
    # This is numeric with exceptions that might be corrected (see ./insights/ldab.md)
    ldab_id: Optional[str] = None
    mp3_id: Optional[str] = None
    title: Optional[str] = None
    material: Optional[str] = None
    current_location: Optional[str] = None


PAPYRI_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS papyri (
    source_path text NOT NULL PRIMARY KEY,
    tm_id integer NOT NULL,
    dclp_id integer,
    dclp_hybrid_id text,
    ddb_perseus_style_id text,
    ddb_filename text,
    ddb_hybrid_id text,
    hgv_id text,
    ldab_id text,
    mp3_id text,
    title text,
    material text,
    current_location text
);"""

PAPYRI_INDEX_SQL = """CREATE INDEX IF NOT EXISTS papyri_tm_id_idx ON papyri (tm_id);
CREATE INDEX IF NOT EXISTS papyri_material_idx ON papyri (material);
CREATE INDEX IF NOT EXISTS papyri_dclp_id_idx ON papyri (dclp_id);
CREATE INDEX IF NOT EXISTS papyri_hgv_id_idx ON papyri (hgv_id);
CREATE INDEX IF NOT EXISTS papyri_ldab_id_idx ON papyri (ldab_id);
CREATE INDEX IF NOT EXISTS papyri_mp3_id_idx ON papyri (mp3_id);
CREATE INDEX IF NOT EXISTS papyri_current_location_idx ON papyri (current_location);"""

PAPYRI_SEMANTICS = TableSemantics(
    table_name="papyri",
    description=(
        "The papyri table contains metadata and provenance from idp.data XML "
        "records, including external identifiers, title, material, and location."
    ),
    row_grain="One row per idp.data metadata XML record, identified by source_path.",
    useful_for=(
        "central metadata and provenance queries",
        "linking records through Trismegistos document IDs",
    ),
    columns={
        "source_path": ColumnSemantics(
            description="Relative path to the idp.data metadata XML file and primary-key provenance for the source record."
        ),
        "tm_id": ColumnSemantics(
            description="Trismegistos document ID used as the logical document key across Scrapyrus tables.",
            caveats=(
                "It is not the papyri primary key and is not unique in this table.",
            ),
        ),
        "dclp_id": ColumnSemantics(
            description="Numeric Digital Corpus of Literary Papyri identifier.",
            null_means="The source record has no DCLP identifier.",
        ),
        "dclp_hybrid_id": ColumnSemantics(
            description="DCLP hybrid identifier string from the source metadata.",
            null_means="The source record has no DCLP hybrid identifier.",
        ),
        "ddb_perseus_style_id": ColumnSemantics(
            description="DDbDP identifier in Perseus-style form from the source metadata.",
            aliases=("DDbDP Perseus-style ID",),
        ),
        "ddb_filename": ColumnSemantics(
            description="DDbDP filename for the associated documentary transcription when present."
        ),
        "ddb_hybrid_id": ColumnSemantics(
            description="DDbDP hybrid identifier string from the source metadata."
        ),
        "hgv_id": ColumnSemantics(description="HGV metadata identifier."),
        "ldab_id": ColumnSemantics(
            description="Leuven Database of Ancient Books identifier when linked."
        ),
        "mp3_id": ColumnSemantics(
            description="MP3 identifier supplied by the source metadata."
        ),
        "title": ColumnSemantics(
            description="Human-readable record or publication title from the metadata."
        ),
        "material": ColumnSemantics(
            description="Lowercase physical support material.",
            examples=("papyrus", "ostracon", "parchment"),
        ),
        "current_location": ColumnSemantics(
            description="Current holding location, inventory context, collection, or institution text from the manuscript identifier."
        ),
    },
    relationships=tuple(
        RelationshipSemantics(
            target_table=target,
            source_columns=("tm_id",),
            target_columns=("tm_id",),
            cardinality="many-to-many",
            description=(
                "Logical Trismegistos document-key join; rows can multiply because "
                "neither side is guaranteed unique on tm_id."
            ),
        )
        for target in (
            "principal_editions",
            "keywords",
            "orig_dates",
            "orig_places",
            "ancient_editions",
            "transcriptions",
        )
    ),
    caveats=(
        "Multiple source_path rows may share a tm_id; document counts may mean distinct tm_id values or metadata source records.",
        "This is the central metadata table, but not necessarily one row per logical TM document.",
    ),
)


class PapyrusModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()

        material_path = (
            ".//tei:physDesc/tei:objectDesc/tei:supportDesc/tei:support/tei:material"
        )
        self.tm_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("TM"),
            value_processor=drop_known_id_placeholders,
        )
        self.dclp_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("dclp"),
            value_processor=drop_known_id_placeholders,
        )
        self.dclp_hybrid_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("dclp-hybrid"),
            value_processor=drop_known_id_placeholders,
        )
        self.ddb_perseus_style_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("ddb-perseus-style"),
            value_processor=drop_known_id_placeholders,
        )
        self.ddb_filename_proc = create_xpath_expr(
            proc,
            publication_idno_string("ddb-filename"),
            value_processor=drop_known_id_placeholders,
        )
        self.ddb_hybrid_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("ddb-hybrid"),
            value_processor=drop_known_id_placeholders,
        )
        self.hgv_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("HGV"),
            value_processor=drop_known_id_placeholders,
        )
        self.ldab_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("LDAB"),
            value_processor=drop_known_id_placeholders,
        )
        self.mp3_id_proc = create_xpath_expr(
            proc,
            publication_idno_string("MP3"),
            value_processor=drop_known_id_placeholders,
        )
        self.title_proc = create_xpath_expr(
            proc,
            first_string(".//tei:titleStmt/tei:title"),
            value_processor=drop_unknown,
        )
        self.material_proc = create_xpath_expr(
            proc,
            f"lower-case({first_string(material_path)})",
        )
        self.current_location_proc = create_xpath_expr(
            proc,
            first_string(
                ".//tei:msDesc/tei:msIdentifier/tei:idno"
                "|.//tei:msDesc/tei:msIdentifier/tei:placeName/tei:settlement"
                "|.//tei:msDesc/tei:msIdentifier/tei:collection"
                "|.//tei:msDesc/tei:msIdentifier/tei:institution"
            ),
            value_processor=drop_unknown,
        )

    def parse(self, filename, source_path):
        data = self.doc_builder.parse_xml(xml_file_name=filename)

        return PapyrusModel(
            source_path=source_path,
            tm_id=self.tm_id_proc(data),
            dclp_id=self.dclp_id_proc(data),
            dclp_hybrid_id=self.dclp_hybrid_id_proc(data),
            ddb_perseus_style_id=self.ddb_perseus_style_id_proc(data),
            ddb_filename=self.ddb_filename_proc(data),
            ddb_hybrid_id=self.ddb_hybrid_id_proc(data),
            hgv_id=self.hgv_id_proc(data),
            ldab_id=self.ldab_id_proc(data),
            mp3_id=self.mp3_id_proc(data),
            title=self.title_proc(data),
            material=self.material_proc(data),
            current_location=self.current_location_proc(data),
        )


def _metadata_source_path(idp_data: Path, metadata: Path) -> str:
    return metadata.relative_to(idp_data).as_posix()


class PapyrusMetadataTable(MetadataTable):
    name = "papyri"
    order_by = ("source_path",)
    schema_sql = PAPYRI_SCHEMA_SQL
    semantics = PAPYRI_SEMANTICS

    def index_sql(self) -> str:
        return PAPYRI_INDEX_SQL

    @property
    def model_class(self) -> type[PapyrusModel]:
        return PapyrusModel

    def create_factory(self, proc):
        return PapyrusModelFactory(proc)

    def build_row(
        self, factory: PapyrusModelFactory, idp_data: Path, metadata: Path
    ) -> dict[str, Any]:
        source_path = _metadata_source_path(idp_data, metadata)
        model = factory.parse(str(metadata), source_path)
        return model.model_dump()

    def build_rows(
        self, factory: PapyrusModelFactory, idp_data: Path, metadata: Path
    ) -> tuple[dict[str, Any]]:
        return (self.build_row(factory, idp_data, metadata),)
