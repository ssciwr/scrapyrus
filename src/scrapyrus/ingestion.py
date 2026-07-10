import csv
from pathlib import Path
import sys
from typing import Any

from saxonche import PySaxonProcessor

from scrapyrus.idpdata import iterate_idpdata_triples
from scrapyrus.metadata.base import MetadataTable

import psycopg
from psycopg import sql


def _metadata_tables() -> tuple[MetadataTable, ...]:
    return tuple(table_type() for table_type in MetadataTable.registered_tables())


def _metadata_schema_sql(tables: tuple[MetadataTable, ...]) -> str:
    schemas = []
    for table in tables:
        if table.schema_sql not in schemas:
            schemas.append(table.schema_sql)

    return "\n".join(schemas)


def _metadata_index_sql(tables: tuple[MetadataTable, ...]) -> str:
    indexes = []
    for table in tables:
        index_sql = table.index_sql()
        if index_sql and index_sql not in indexes:
            indexes.append(index_sql)

    return "\n".join(indexes)


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

    tables = _metadata_tables()

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table.name}")
            cursor.execute(_metadata_schema_sql(tables))
            with PySaxonProcessor(license=False) as proc:
                factories = {table.name: table.create_factory(proc) for table in tables}
                idp_data = Path(idp_data)
                for _, metadata, _, _ in iterate_idpdata_triples(
                    idp_data, progressbar=progressbar
                ):
                    for table in tables:
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
            index_sql = _metadata_index_sql(tables)
            if index_sql:
                cursor.execute(index_sql)


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
    tables = _metadata_tables()

    with psycopg.connect(conninfo, **connect_kwargs) as connection:
        for table in tables:
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
