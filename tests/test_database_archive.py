from pathlib import Path
import subprocess

import pytest
from psycopg import sql

from scrapyrus.database_archive import (
    _recreate_database,
    dump_database,
    import_database,
)


def test_dump_database_wraps_pg_dump_and_writes_atomically(tmp_path, monkeypatch):
    calls = []

    def run(command, *, check):
        calls.append((command, check))
        temporary_path = Path(command[3].removeprefix("--file="))
        temporary_path.write_bytes(b"postgres archive")

    monkeypatch.setattr(subprocess, "run", run)
    target = tmp_path / "scrapyrus.dump"

    dump_database(target, "postgresql://database.example/scrapyrus")

    assert target.read_bytes() == b"postgres archive"
    assert len(calls) == 1
    command, check = calls[0]
    assert command[:3] == [
        "pg_dump",
        "--dbname=postgresql://database.example/scrapyrus",
        "--format=custom",
    ]
    assert command[3].startswith(f"--file={tmp_path}/.scrapyrus.dump.")
    assert command[3].endswith(".tmp")
    assert command[4:] == ["--verbose"]
    assert check is True


def test_dump_database_refuses_to_overwrite_existing_file(tmp_path, monkeypatch):
    target = tmp_path / "scrapyrus.dump"
    target.write_bytes(b"keep this")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("pg_dump must not be called"),
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        dump_database(target)

    assert target.read_bytes() == b"keep this"


def test_dump_database_removes_temporary_file_on_failure(tmp_path, monkeypatch):
    def run(command, *, check):
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(subprocess.CalledProcessError):
        dump_database(tmp_path / "scrapyrus.dump")

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("database_name", "maintenance_database"),
    [
        ("scrapyrus", "postgres"),
        ("postgres", "template1"),
    ],
)
def test_recreate_database_preserves_owner_and_uses_maintenance_database(
    monkeypatch, database_name, maintenance_database
):
    connections = []
    statements = []

    class Result:
        def fetchone(self):
            return database_name, "database-owner"

    class Connection:
        def __init__(self, is_target):
            self.is_target = is_target

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, statement):
            if isinstance(statement, sql.Composable):
                statements.append(statement.as_string())
            else:
                statements.append(" ".join(statement.split()))
            return Result() if self.is_target else None

    def connect(conninfo, **options):
        connections.append((conninfo, options))
        return Connection(is_target=len(connections) == 1)

    monkeypatch.setattr("scrapyrus.database_archive.psycopg.connect", connect)

    _recreate_database("postgresql://scrapyrus:secret@database.example:5432/scrapyrus")

    assert connections == [
        (
            "postgresql://scrapyrus:secret@database.example:5432/scrapyrus",
            {},
        ),
        (
            "user=scrapyrus password=secret "
            f"dbname={maintenance_database} host=database.example port=5432",
            {"autocommit": True},
        ),
    ]
    assert statements == [
        (
            "SELECT current_database(), pg_catalog.pg_get_userbyid(datdba) "
            "FROM pg_catalog.pg_database WHERE datname = current_database()"
        ),
        f'DROP DATABASE "{database_name}" WITH (FORCE)',
        f'CREATE DATABASE "{database_name}" OWNER "database-owner"',
    ]


@pytest.mark.parametrize(
    ("no_owner", "ownership_options"),
    [
        (False, []),
        (True, ["--no-owner", "--no-privileges"]),
    ],
)
def test_import_database_validates_then_restores_complete_archive(
    tmp_path, monkeypatch, no_owner, ownership_options
):
    events = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **options: events.append((command, options)),
    )
    monkeypatch.setattr(
        "scrapyrus.database_archive._recreate_database",
        lambda conninfo: events.append(("recreate", conninfo)),
    )
    source = tmp_path / "scrapyrus.dump"
    source.write_bytes(b"postgres archive")

    import_database(
        source,
        "postgresql://database.example/scrapyrus",
        no_owner=no_owner,
    )

    assert events == [
        (
            ["pg_restore", "--list", str(source)],
            {"check": True, "stdout": subprocess.DEVNULL},
        ),
        ("recreate", "postgresql://database.example/scrapyrus"),
        (
            [
                "pg_restore",
                "--dbname=postgresql://database.example/scrapyrus",
                "--exit-on-error",
                "--single-transaction",
                "--verbose",
                *ownership_options,
                str(source),
            ],
            {"check": True},
        ),
    ]


def test_import_database_does_not_restore_invalid_archive(tmp_path, monkeypatch):
    calls = []

    def run(command, **options):
        calls.append((command, options))
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        "scrapyrus.database_archive._recreate_database",
        lambda conninfo: pytest.fail("the database must not be recreated"),
    )
    source = tmp_path / "invalid.dump"

    with pytest.raises(subprocess.CalledProcessError):
        import_database(source)

    assert calls == [
        (
            ["pg_restore", "--list", str(source)],
            {"check": True, "stdout": subprocess.DEVNULL},
        )
    ]
