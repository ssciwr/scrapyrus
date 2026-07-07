import csv
from pathlib import Path
import sys
from typing import Any, Protocol

from saxonche import PySaxonProcessor

from scrapyrus.idpdata import iterate_idpdata_triples
from scrapyrus.metadata.keywords import KEYWORDS_METADATA_TABLE
from scrapyrus.metadata.papyri import PAPYRI_METADATA_TABLE

import psycopg
from psycopg import sql


class MetadataTable(Protocol):
    name: str
    columns: tuple[str, ...]
    order_by: tuple[str, ...]
    schema_sql: str

    def create_factory(self, proc: Any) -> Any: ...

    def build_rows(
        self, factory: Any, idp_data: Path, metadata: Path
    ) -> tuple[dict[str, Any], ...] | list[dict[str, Any]]: ...


METADATA_TABLES: tuple[MetadataTable, ...] = (
    PAPYRI_METADATA_TABLE,
    KEYWORDS_METADATA_TABLE,
)


def _metadata_schema_sql() -> str:
    schemas = []
    for table in METADATA_TABLES:
        if table.schema_sql not in schemas:
            schemas.append(table.schema_sql)

    return "\n".join(schemas)


def _insert_metadata_row(
    cursor: Any, table: MetadataTable, row: dict[str, Any]
) -> None:
    cursor.execute(
        f"""
INSERT INTO {table.name} ({", ".join(table.columns)})
VALUES ({", ".join(f"%({column})s" for column in table.columns)})
""",
        row,
    )


def ingest_metadata(
    idp_data: str | Path,
    conninfo: str = "",
    *,
    progressbar: bool = True,
    **connect_kwargs: Any,
):
    """Ingest idp.data metadata into a PostgreSQL database.

    The function rebuilds the generated metadata tables before parsing records.
    ``conninfo`` and ``connect_kwargs`` are passed to ``psycopg.connect``.
    """

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        with connection.cursor() as cursor:
            for table in METADATA_TABLES:
                cursor.execute(f"DROP TABLE IF EXISTS {table.name}")
            cursor.execute(_metadata_schema_sql())
            with PySaxonProcessor(license=False) as proc:
                factories = {
                    table.name: table.create_factory(proc) for table in METADATA_TABLES
                }
                idp_data = Path(idp_data)
                for _, metadata, _, _ in iterate_idpdata_triples(
                    idp_data, progressbar=progressbar
                ):
                    for table in METADATA_TABLES:
                        try:
                            rows = table.build_rows(
                                factories[table.name], idp_data, metadata
                            )
                        except Exception:
                            print(
                                f"Failed while processing metadata file: {metadata}",
                                file=sys.stderr,
                            )
                            raise
                        for row in rows:
                            _insert_metadata_row(cursor, table, row)


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
        for table in METADATA_TABLES:
            output = target / f"{table.name}.csv"
            with output.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(table.columns)

                select_columns = sql.SQL(", ").join(
                    sql.Identifier(column) for column in table.columns
                )
                ordering = sql.SQL(", ").join(
                    sql.Identifier(column) for column in table.order_by
                )
                query = sql.SQL(
                    "SELECT {columns} FROM {table} ORDER BY {ordering}"
                ).format(
                    columns=select_columns,
                    table=sql.Identifier(table.name),
                    ordering=ordering,
                )

                with connection.cursor() as cursor:
                    cursor.execute(query)
                    writer.writerows(cursor)
