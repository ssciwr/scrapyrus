from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


def _create_xpath_expr(
    proc: Any, xpath: str, value_processor: Callable[[str], str | None] | None = None
):
    xpath_proc = proc.new_xpath_processor()
    xpath_proc.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")

    def eval(root):
        xpath_proc.set_context(xdm_item=root)
        result = xpath_proc.evaluate_single(xpath)
        if result is None:
            return None
        result = result.string_value
        if result == "":
            return None
        if value_processor is not None:
            result = value_processor(result)
        if result is None or result == "":
            return None

        return result

    return eval


def _drop_known_id_placeholders(val):
    if val in ("hgvTEMP",):
        return None
    return val


def _first_string(path):
    return f"string(({path})[1])"


def _publication_idno_string(identifier_type):
    return _first_string(f".//tei:publicationStmt/tei:idno[@type='{identifier_type}']")


def _drop_unknown(val):
    if val in ("unbekannt", "keiner"):
        return None
    return val


class PapyrusModel(BaseModel):
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


PAPYRUS_MODEL_COLUMNS = tuple(PapyrusModel.model_fields)
PAPYRUS_TABLE_COLUMNS = (
    "source_path",
    *PAPYRUS_MODEL_COLUMNS,
)
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
);

CREATE INDEX IF NOT EXISTS papyri_tm_id_idx ON papyri (tm_id);"""


class PapyrusModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()

        material_path = (
            ".//tei:physDesc/tei:objectDesc/tei:supportDesc/tei:support/tei:material"
        )
        self.tm_id_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("TM"),
            value_processor=_drop_known_id_placeholders,
        )
        self.dclp_id_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("dclp"),
            value_processor=_drop_known_id_placeholders,
        )
        self.dclp_hybrid_id_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("dclp-hybrid"),
            value_processor=_drop_known_id_placeholders,
        )
        self.ddb_perseus_style_id_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("ddb-perseus-style"),
            value_processor=_drop_known_id_placeholders,
        )
        self.ddb_filename_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("ddb-filename"),
            value_processor=_drop_known_id_placeholders,
        )
        self.ddb_hybrid_id_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("ddb-hybrid"),
            value_processor=_drop_known_id_placeholders,
        )
        self.hgv_id_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("HGV"),
            value_processor=_drop_known_id_placeholders,
        )
        self.ldab_id_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("LDAB"),
            value_processor=_drop_known_id_placeholders,
        )
        self.mp3_id_proc = _create_xpath_expr(
            proc,
            _publication_idno_string("MP3"),
            value_processor=_drop_known_id_placeholders,
        )
        self.title_proc = _create_xpath_expr(
            proc,
            _first_string(".//tei:titleStmt/tei:title"),
            value_processor=_drop_unknown,
        )
        self.material_proc = _create_xpath_expr(
            proc,
            f"lower-case({_first_string(material_path)})",
        )
        self.current_location_proc = _create_xpath_expr(
            proc,
            _first_string(
                ".//tei:msDesc/tei:msIdentifier/tei:idno"
                "|.//tei:msDesc/tei:msIdentifier/tei:placeName/tei:settlement"
                "|.//tei:msDesc/tei:msIdentifier/tei:collection"
                "|.//tei:msDesc/tei:msIdentifier/tei:institution"
            ),
            value_processor=_drop_unknown,
        )

    def parse(self, filename):
        data = self.doc_builder.parse_xml(xml_file_name=filename)

        return PapyrusModel(
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


class PapyrusMetadataTable:
    name = "papyri"
    columns = PAPYRUS_TABLE_COLUMNS
    order_by = ("source_path",)
    schema_sql = PAPYRI_SCHEMA_SQL

    def create_factory(self, proc):
        return PapyrusModelFactory(proc)

    def build_row(
        self, factory: PapyrusModelFactory, idp_data: Path, metadata: Path
    ) -> dict[str, Any]:
        model = factory.parse(str(metadata))
        return {
            "source_path": _metadata_source_path(idp_data, metadata),
            **model.model_dump(),
        }

    def build_rows(
        self, factory: PapyrusModelFactory, idp_data: Path, metadata: Path
    ) -> tuple[dict[str, Any]]:
        return (self.build_row(factory, idp_data, metadata),)


PAPYRI_METADATA_TABLE = PapyrusMetadataTable()
PAPYRUS_TABLE_DUMP = (
    PAPYRI_METADATA_TABLE.name,
    PAPYRI_METADATA_TABLE.columns,
    PAPYRI_METADATA_TABLE.order_by,
)
