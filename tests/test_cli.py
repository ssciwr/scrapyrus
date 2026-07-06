import logging
from pathlib import Path

from scrapyrus.images import DEFAULT_BROKEN_IMAGE_FILE
from scrapyrus.__main__ import main

from click.testing import CliRunner


def test_images_subcommand_triggers_image_scrape(tmp_path, monkeypatch):
    calls = []
    log = tmp_path / "images.log"

    def fake_scrape_images(
        target,
        todo_filename,
        error_filename,
        unavailable_filename,
        *,
        broken_filename,
        idp_data,
    ):
        logging.getLogger("scrapyrus.images.scrapers.test").debug(
            "scraper debug details"
        )
        calls.append(
            (
                target,
                todo_filename,
                broken_filename,
                error_filename,
                unavailable_filename,
                idp_data,
            )
        )

    monkeypatch.setattr("scrapyrus.__main__.scrape_images", fake_scrape_images)
    idp_data = tmp_path / "idp.data"
    target = tmp_path / "images"
    runner = CliRunner()

    result = runner.invoke(
        main,
        (
            "--idp-data",
            str(idp_data),
            "images",
            "--log-file",
            str(log),
            "--log-level",
            "DEBUG",
            "--todo-file",
            "todo.txt",
            "--broken-file",
            "broken.txt",
            "--error-file",
            "error.txt",
            "--unavailable-file",
            "unavailable.txt",
            str(target),
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            target,
            Path("todo.txt"),
            Path("broken.txt"),
            Path("error.txt"),
            Path("unavailable.txt"),
            idp_data,
        )
    ]
    assert "DEBUG scrapyrus.images.scrapers.test: scraper debug details" in (
        log.read_text(encoding="utf-8")
    )
    assert result.output == ""


def test_images_subcommand_uses_defaults(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.scrape_images",
        lambda target,
        todo_filename,
        error_filename,
        unavailable_filename,
        *,
        broken_filename,
        idp_data: calls.append(
            (
                target,
                todo_filename,
                broken_filename,
                error_filename,
                unavailable_filename,
                idp_data,
            )
        ),
    )
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(main, ("images",))
        assert Path("images.log").exists()

    assert result.exit_code == 0
    assert calls == [
        (
            Path("images"),
            Path("images_todo.txt"),
            DEFAULT_BROKEN_IMAGE_FILE,
            Path("images_error.txt"),
            Path("images_unavailable.txt"),
            Path("idp.data"),
        )
    ]


def test_metadata_ingest_subcommand_triggers_metadata_ingest(tmp_path, monkeypatch):
    calls = []

    def fake_ingest_metadata(idp_data, database_url, *, progressbar):
        calls.append((idp_data, database_url, progressbar))

    monkeypatch.setattr("scrapyrus.__main__.ingest_metadata", fake_ingest_metadata)
    idp_data = tmp_path / "idp.data"
    runner = CliRunner()

    result = runner.invoke(
        main,
        (
            "--idp-data",
            str(idp_data),
            "metadata",
            "ingest",
            "--database-url",
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            "--no-progress",
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            idp_data,
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            False,
        )
    ]
    assert result.output == ""


def test_metadata_ingest_subcommand_uses_database_url_envvar(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.ingest_metadata",
        lambda idp_data, database_url, *, progressbar: calls.append(
            (idp_data, database_url, progressbar)
        ),
    )
    runner = CliRunner()

    result = runner.invoke(
        main,
        ("metadata", "ingest"),
        env={
            "SCRAPYRUS_DATABASE_URL": (
                "postgresql://scrapyrus:secret@postgres:5432/scrapyrus"
            )
        },
    )

    assert result.exit_code == 0
    assert calls == [
        (
            Path("idp.data"),
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            True,
        )
    ]


def test_metadata_dump_subcommand_triggers_csv_dump(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.dump_metadata_tables",
        lambda output_dir, database_url: calls.append((output_dir, database_url)),
    )
    output_dir = tmp_path / "metadata-csv"
    runner = CliRunner()

    result = runner.invoke(
        main,
        (
            "metadata",
            "dump",
            "--database-url",
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            "--output-dir",
            str(output_dir),
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            output_dir,
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
        )
    ]
    assert result.output == ""


def test_metadata_dump_subcommand_uses_database_url_envvar(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.dump_metadata_tables",
        lambda output_dir, database_url: calls.append((output_dir, database_url)),
    )
    runner = CliRunner()

    result = runner.invoke(
        main,
        ("metadata", "dump"),
        env={
            "SCRAPYRUS_DATABASE_URL": (
                "postgresql://scrapyrus:secret@postgres:5432/scrapyrus"
            )
        },
    )

    assert result.exit_code == 0
    assert calls == [
        (
            Path("metadata-csv"),
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
        )
    ]
