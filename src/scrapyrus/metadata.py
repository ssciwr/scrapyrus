from collections.abc import Callable
import csv
from importlib import resources
from pathlib import Path
import sys
from typing import Any, Optional

from pydantic import BaseModel, Field
from saxonche import PySaxonProcessor

from scrapyrus.idpdata import iterate_idpdata_triples

import psycopg
from psycopg import sql


def _create_xpath_expr(
    proc, xpath, value_processor: Callable[[str], str | None] | None = None
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
METADATA_TABLE_DUMPS = (("papyri", PAPYRUS_TABLE_COLUMNS, ("source_path",)),)


class PapyrusModelFactory:
    def __init__(self, proc):
        self.proc = proc
        self.doc_builder = proc.new_document_builder()

        # Build XPath processors for all fields
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


def _metadata_schema_sql() -> str:
    return (
        resources.files("scrapyrus")
        .joinpath("metadata.sql")
        .read_text(encoding="utf-8")
    )


def _metadata_source_path(idp_data: Path, metadata: Path) -> str:
    return metadata.relative_to(idp_data).as_posix()


def ingest_metadata(
    idp_data: str | Path,
    conninfo: str = "",
    *,
    progressbar: bool = True,
    **connect_kwargs: Any,
):
    """Ingest idp.data papyrus metadata into a PostgreSQL database.

    The function rebuilds the generated metadata table before parsing records.
    ``conninfo`` and ``connect_kwargs`` are passed to ``psycopg.connect``.
    """

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS papyri")
            cursor.execute(_metadata_schema_sql())
            with PySaxonProcessor(license=False) as proc:
                factory = PapyrusModelFactory(proc)
                idp_data = Path(idp_data)
                for _, metadata, _, _ in iterate_idpdata_triples(
                    idp_data, progressbar=progressbar
                ):
                    try:
                        model = factory.parse(str(metadata))
                    except Exception:
                        print(
                            f"Failed while processing metadata file: {metadata}",
                            file=sys.stderr,
                        )
                        raise
                    row = {
                        "source_path": _metadata_source_path(idp_data, metadata),
                        **model.model_dump(),
                    }
                    cursor.execute(
                        f"""
INSERT INTO papyri ({", ".join(PAPYRUS_TABLE_COLUMNS)})
VALUES ({", ".join(f"%({column})s" for column in PAPYRUS_TABLE_COLUMNS)})
""",
                        row,
                    )


def dump_metadata_tables(
    target: str | Path,
    conninfo: str = "",
    **connect_kwargs: Any,
) -> None:
    """Dump generated metadata database tables as CSV files.

    ``conninfo`` and ``connect_kwargs`` are passed to ``psycopg.connect``. The
    target directory receives one ``.csv`` file per table owned by this module.
    """

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        for table_name, columns, order_by in METADATA_TABLE_DUMPS:
            output = target / f"{table_name}.csv"
            with output.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(columns)

                select_columns = sql.SQL(", ").join(
                    sql.Identifier(column) for column in columns
                )
                ordering = sql.SQL(", ").join(
                    sql.Identifier(column) for column in order_by
                )
                query = sql.SQL(
                    "SELECT {columns} FROM {table} ORDER BY {ordering}"
                ).format(
                    columns=select_columns,
                    table=sql.Identifier(table_name),
                    ordering=ordering,
                )

                with connection.cursor() as cursor:
                    cursor.execute(query)
                    writer.writerows(cursor)
