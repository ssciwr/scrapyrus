import logging
from pathlib import Path

from click.testing import CliRunner

from scrapyrus.__main__ import DATABASE_URL_ENVVAR, DEFAULT_DATABASE_URL, main
from scrapyrus.embeddings import (
    EMBEDDING_CORPORA,
)
from scrapyrus.images import DEFAULT_BROKEN_IMAGE_FILE


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
    result = CliRunner().invoke(
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
    assert "scraper debug details" in log.read_text(encoding="utf-8")


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
        idp_data: (
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


def test_database_commands_use_shared_database_url_default_and_envvar():
    command_paths = (
        ("catalog",),
        ("dump",),
        ("import",),
        ("metadata", "ingest"),
        ("metadata", "dump"),
        ("transcriptions", "ingest"),
        ("transcriptions", "dump"),
        ("transcriptions", "import"),
        ("transcriptions", "lemmatize"),
        ("embeddings", "ingest", "transcriptions"),
        ("embeddings", "ingest", "translations"),
        ("embeddings", "ingest", "keywords"),
        ("embeddings", "dump", "transcriptions"),
        ("embeddings", "dump", "translations"),
        ("embeddings", "dump", "keywords"),
        ("embeddings", "import", "transcriptions"),
        ("embeddings", "import", "translations"),
        ("embeddings", "import", "keywords"),
        ("embeddings", "evaluate", "transcriptions"),
        ("embeddings", "evaluate", "translations"),
        ("embeddings", "query", "transcriptions"),
        ("embeddings", "query", "translations"),
        ("embeddings", "query", "keywords"),
        ("embeddings", "update", "transcriptions"),
        ("embeddings", "update", "translations"),
        ("embeddings", "update", "keywords"),
        ("embeddings", "delete", "transcriptions"),
        ("embeddings", "delete", "translations"),
        ("embeddings", "delete", "keywords"),
    )

    for command_path in command_paths:
        command = main
        for command_name in command_path:
            command = command.commands[command_name]

        database_options = [
            parameter
            for parameter in command.params
            if parameter.name == "database_url"
        ]
        assert len(database_options) == 1, " ".join(command_path)
        assert database_options[0].envvar == DATABASE_URL_ENVVAR
        assert database_options[0].default == DEFAULT_DATABASE_URL
        assert not database_options[0].required


def test_embedding_operation_commands_cover_the_corpus_registry():
    assert set(main.commands["embeddings"].commands) == {
        "ingest",
        "dump",
        "import",
        "evaluate",
        "query",
        "update",
        "delete",
    }
    complete_operations = ("ingest", "dump", "import", "query", "update", "delete")
    for operation_name in complete_operations:
        operation = main.commands["embeddings"].commands[operation_name]
        assert set(operation.commands) == set(EMBEDDING_CORPORA)
    assert set(main.commands["embeddings"].commands["evaluate"].commands) == {
        "transcriptions",
        "translations",
    }


def test_catalog_subcommand_publishes_all_semantics(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.publish_catalog",
        lambda database_url: calls.append(database_url),
    )

    result = CliRunner().invoke(
        main,
        (
            "catalog",
            "--database-url",
            "postgresql://database.example/scrapyrus",
        ),
    )

    assert result.exit_code == 0
    assert calls == ["postgresql://database.example/scrapyrus"]


def test_database_dump_subcommand_creates_full_archive(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.dump_database",
        lambda output_file, database_url: calls.append((output_file, database_url)),
    )
    output = tmp_path / "database.dump"

    result = CliRunner().invoke(
        main,
        (
            "dump",
            "--database-url",
            "postgresql://database.example/scrapyrus",
            str(output),
        ),
    )

    assert result.exit_code == 0
    assert calls == [(output, "postgresql://database.example/scrapyrus")]
    assert result.output == f"Database dump written to {output}\n"


def test_database_import_subcommand_restores_full_archive(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.import_database",
        lambda input_file, database_url, *, no_owner: calls.append(
            (input_file, database_url, no_owner)
        ),
    )
    source = tmp_path / "database.dump"
    source.write_bytes(b"postgres archive")

    result = CliRunner().invoke(
        main,
        (
            "import",
            "--database-url",
            "postgresql://database.example/scrapyrus",
            "--no-owner",
            str(source),
        ),
    )

    assert result.exit_code == 0
    assert calls == [(source, "postgresql://database.example/scrapyrus", True)]
    assert result.output == f"Database restored from {source}\n"


def test_database_archive_subcommands_use_default_filename_and_connection(
    monkeypatch,
):
    dump_calls = []
    import_calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.dump_database",
        lambda output_file, database_url: dump_calls.append(
            (output_file, database_url)
        ),
    )
    monkeypatch.setattr(
        "scrapyrus.__main__.import_database",
        lambda input_file, database_url, *, no_owner: import_calls.append(
            (input_file, database_url, no_owner)
        ),
    )

    runner = CliRunner()
    with runner.isolated_filesystem():
        dump_result = runner.invoke(main, ("dump",))
        Path("scrapyrus.dump").touch()
        import_result = runner.invoke(main, ("import",))

    assert dump_result.exit_code == 0
    assert import_result.exit_code == 0
    assert dump_calls == [(Path("scrapyrus.dump"), DEFAULT_DATABASE_URL)]
    assert import_calls == [(Path("scrapyrus.dump"), DEFAULT_DATABASE_URL, False)]


def test_database_dump_reports_missing_pg_dump(monkeypatch):
    def missing_pg_dump(output_file, database_url):
        raise FileNotFoundError(2, "No such file or directory", "pg_dump")

    monkeypatch.setattr(
        "scrapyrus.__main__.dump_database",
        missing_pg_dump,
    )

    result = CliRunner().invoke(main, ("dump",))

    assert result.exit_code == 1
    assert result.output == "Error: pg_dump is not installed or not on PATH\n"


def test_metadata_ingest_subcommand_uses_postgresql_connection_defaults(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.ingest_metadata",
        lambda idp_data, database_url, *, progressbar: calls.append(
            (idp_data, database_url, progressbar)
        ),
    )

    result = CliRunner().invoke(main, ("metadata", "ingest"))

    assert result.exit_code == 0
    assert calls == [(Path("idp.data"), DEFAULT_DATABASE_URL, True)]


def test_transcriptions_ingest_subcommand_uses_postgresql_connection_defaults(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.ingest_transcriptions",
        lambda idp_data, database_url, *, progressbar: calls.append(
            (idp_data, database_url, progressbar)
        ),
    )

    result = CliRunner().invoke(main, ("transcriptions", "ingest"))

    assert result.exit_code == 0
    assert calls == [(Path("idp.data"), DEFAULT_DATABASE_URL, True)]


def test_metadata_ingest_subcommand_triggers_metadata_ingest(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.ingest_metadata",
        lambda idp_data, database_url, *, progressbar: calls.append(
            (idp_data, database_url, progressbar)
        ),
    )
    idp_data = tmp_path / "idp.data"
    result = CliRunner().invoke(
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
        (idp_data, "postgresql://scrapyrus:secret@postgres:5432/scrapyrus", False)
    ]


def test_metadata_ingest_subcommand_uses_database_url_envvar(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.ingest_metadata",
        lambda idp_data, database_url, *, progressbar: calls.append(
            (idp_data, database_url, progressbar)
        ),
    )
    result = CliRunner().invoke(
        main,
        ("metadata", "ingest"),
        env={
            "SCRAPYRUS_DATABASE_URL": "postgresql://scrapyrus:secret@postgres:5432/scrapyrus"
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
    result = CliRunner().invoke(
        main,
        (
            "metadata",
            "dump",
            "--database-url",
            "postgresql://database.example/scrapyrus",
            "--output-dir",
            str(output_dir),
        ),
    )
    assert result.exit_code == 0
    assert calls == [(output_dir, "postgresql://database.example/scrapyrus")]


def test_metadata_dump_subcommand_uses_database_url_envvar(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.dump_metadata_tables",
        lambda output_dir, database_url: calls.append((output_dir, database_url)),
    )
    result = CliRunner().invoke(
        main,
        ("metadata", "dump"),
        env={"SCRAPYRUS_DATABASE_URL": "postgresql://database.example/scrapyrus"},
    )
    assert result.exit_code == 0
    assert calls == [(Path("metadata-csv"), "postgresql://database.example/scrapyrus")]


def test_transcriptions_ingest_subcommand_triggers_ingestion(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.ingest_transcriptions",
        lambda idp_data, database_url, *, progressbar: calls.append(
            (idp_data, database_url, progressbar)
        ),
    )
    idp_data = tmp_path / "idp.data"
    result = CliRunner().invoke(
        main,
        (
            "--idp-data",
            str(idp_data),
            "transcriptions",
            "ingest",
            "--database-url",
            "postgresql://database.example/scrapyrus",
            "--no-progress",
        ),
    )
    assert result.exit_code == 0
    assert calls == [(idp_data, "postgresql://database.example/scrapyrus", False)]


def test_transcriptions_dump_subcommand_triggers_csv_dump(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.dump_transcriptions",
        lambda output_dir, database_url: calls.append((output_dir, database_url)),
    )
    output_dir = tmp_path / "transcriptions-csv"
    result = CliRunner().invoke(
        main,
        (
            "transcriptions",
            "dump",
            "--database-url",
            "postgresql://database.example/scrapyrus",
            "--output-dir",
            str(output_dir),
        ),
    )
    assert result.exit_code == 0
    assert calls == [(output_dir, "postgresql://database.example/scrapyrus")]


def test_transcriptions_import_subcommand_triggers_csv_import(tmp_path, monkeypatch):
    calls = []
    source = tmp_path / "transcriptions.csv"
    source.write_text("dump", encoding="utf-8")
    monkeypatch.setattr(
        "scrapyrus.__main__.import_transcriptions",
        lambda input_file, database_url: calls.append((input_file, database_url)),
    )

    result = CliRunner().invoke(
        main,
        (
            "transcriptions",
            "import",
            "--database-url",
            "postgresql://database.example/scrapyrus",
            str(source),
        ),
    )

    assert result.exit_code == 0
    assert calls == [(source, "postgresql://database.example/scrapyrus")]


def test_transcriptions_lemmatize_subcommand_triggers_lemmatization(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.lemmatize_transcriptions",
        lambda database_url, *, progressbar, max_words: calls.append(
            (database_url, progressbar, max_words)
        ),
    )

    result = CliRunner().invoke(
        main,
        (
            "transcriptions",
            "lemmatize",
            "--database-url",
            "postgresql://database.example/scrapyrus",
            "--no-progress",
            "--max-words",
            "25",
        ),
    )

    assert result.exit_code == 0
    assert calls == [("postgresql://database.example/scrapyrus", False, 25)]


def test_embeddings_evaluate_has_no_idpdata_or_variant_arguments(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.evaluate_embeddings",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "evaluate",
            "transcriptions",
            "--database-url",
            "postgresql://db",
        ),
    )
    assert result.exit_code == 0
    assert calls == [
        (
            ("postgresql://db",),
            {
                "query_kind": "transcriptions",
                "progressbar": True,
                "sample": None,
                "seed": 0,
            },
        )
    ]


def test_embeddings_evaluate_passes_sample_size_and_seed(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.evaluate_embeddings",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "evaluate",
            "translations",
            "--database-url",
            "postgresql://db",
            "--sample",
            "12",
            "--seed",
            "8675309",
            "--no-progress",
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            ("postgresql://db",),
            {
                "query_kind": "translations",
                "progressbar": False,
                "sample": 12,
                "seed": 8675309,
            },
        )
    ]
