from pathlib import Path
import subprocess

import pytest

from scrapyrus.database_archive import dump_database, import_database


def test_dump_database_creates_custom_format_archive_atomically(tmp_path, monkeypatch):
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
    ("no_owner", "ownership_options"),
    [
        (False, []),
        (True, ["--no-owner", "--no-privileges"]),
    ],
)
def test_import_database_validates_then_restores_complete_archive(
    tmp_path, monkeypatch, no_owner, ownership_options
):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **options: calls.append((command, options)),
    )
    source = tmp_path / "scrapyrus.dump"
    source.write_bytes(b"postgres archive")

    import_database(
        source,
        "postgresql://database.example/scrapyrus",
        no_owner=no_owner,
    )

    assert calls == [
        (
            ["pg_restore", "--list", str(source)],
            {"check": True, "stdout": subprocess.DEVNULL},
        ),
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
    source = tmp_path / "invalid.dump"

    with pytest.raises(subprocess.CalledProcessError):
        import_database(source)

    assert calls == [
        (
            ["pg_restore", "--list", str(source)],
            {"check": True, "stdout": subprocess.DEVNULL},
        )
    ]
