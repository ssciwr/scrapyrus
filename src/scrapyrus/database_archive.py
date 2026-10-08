"""Wrap ``pg_dump`` and ``pg_restore`` for complete database archives."""

from pathlib import Path
import subprocess
import tempfile

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo


def _recreate_database(conninfo: str) -> None:
    """Drop and recreate the database selected by ``conninfo``."""

    with psycopg.connect(conninfo) as connection:
        database_name, owner = connection.execute(
            """
            SELECT current_database(), pg_catalog.pg_get_userbyid(datdba)
            FROM pg_catalog.pg_database
            WHERE datname = current_database()
            """
        ).fetchone()

    maintenance_database = "template1" if database_name == "postgres" else "postgres"
    maintenance_conninfo = make_conninfo(
        conninfo,
        dbname=maintenance_database,
    )
    with psycopg.connect(maintenance_conninfo, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                sql.Identifier(database_name)
            )
        )
        connection.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database_name),
                sql.Identifier(owner),
            )
        )


def dump_database(target: str | Path, conninfo: str = "") -> None:
    """Run ``pg_dump`` with its built-in custom format, writing to ``target``."""

    target = Path(target)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {target}")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"output directory does not exist: {target.parent}")

    with tempfile.NamedTemporaryFile(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        subprocess.run(
            [
                "pg_dump",
                f"--dbname={conninfo}",
                "--format=custom",
                f"--file={temporary_path}",
                "--verbose",
            ],
            check=True,
        )
        temporary_path.replace(target)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def import_database(
    source: str | Path,
    conninfo: str = "",
    *,
    no_owner: bool = False,
) -> None:
    """Recreate a database and restore a complete archive into it."""

    source = Path(source)
    subprocess.run(
        ["pg_restore", "--list", str(source)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    _recreate_database(conninfo)

    command = [
        "pg_restore",
        f"--dbname={conninfo}",
        "--exit-on-error",
        "--single-transaction",
        "--verbose",
    ]
    if no_owner:
        command.extend(("--no-owner", "--no-privileges"))
    command.append(str(source))
    subprocess.run(command, check=True)
