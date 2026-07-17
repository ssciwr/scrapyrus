import logging
from pathlib import Path

from click.testing import CliRunner

from scrapyrus.__main__ import DATABASE_URL_ENVVAR, DEFAULT_DATABASE_URL, main
from scrapyrus.images import DEFAULT_BROKEN_IMAGE_FILE
from scrapyrus.transcriptions.embeddings import (
    PgvectorUnavailableError,
    TranscriptionsUnavailableError,
)


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


def test_database_commands_use_shared_database_url_default_and_envvar():
    command_paths = (
        ("metadata", "ingest"),
        ("metadata", "dump"),
        ("transcriptions", "ingest"),
        ("transcriptions", "dump"),
        ("transcriptions", "lemmatize"),
        ("embeddings", "ingest"),
        ("embeddings", "delete"),
        ("embeddings", "dump"),
        ("embeddings", "import"),
        ("embeddings", "update"),
        ("embeddings", "evaluate"),
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


def test_transcriptions_lemmatize_subcommand_triggers_lemmatization(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.lemmatize_transcriptions",
        lambda database_url, *, progressbar: calls.append((database_url, progressbar)),
    )

    result = CliRunner().invoke(
        main,
        (
            "transcriptions",
            "lemmatize",
            "--database-url",
            "postgresql://database.example/scrapyrus",
            "--no-progress",
        ),
    )

    assert result.exit_code == 0
    assert calls == [("postgresql://database.example/scrapyrus", False)]


def test_embeddings_ingest_reads_database_without_text_variant_options(monkeypatch):
    calls = []

    class Store:
        def __init__(self, url, model, key):
            calls.append(("init", url, model, key))

        def setup_store(self, database_url, progress, **kwargs):
            calls.append(("setup", database_url, progress, kwargs))

    monkeypatch.setattr("scrapyrus.__main__.EmbeddingStore", Store)
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "ingest",
            "--database-url",
            "postgresql://db",
            "--inference-server-url",
            "https://inference.example/v1",
            "--model-name",
            "model",
            "--api-key",
            "secret",
            "--no-progress",
        ),
    )
    assert result.exit_code == 0
    assert calls == [
        ("init", "https://inference.example/v1", "model", "secret"),
        (
            "setup",
            "postgresql://db",
            False,
            {"sample": None, "seed": 0, "chunk_size": 500},
        ),
    ]


def test_embeddings_ingest_uses_envvars(monkeypatch):
    calls = []

    class Store:
        def __init__(self, url, model, key):
            calls.append((url, model, key))

        def setup_store(self, database_url, progress, **kwargs):
            calls.append((database_url, progress, kwargs))

    monkeypatch.setattr("scrapyrus.__main__.EmbeddingStore", Store)
    result = CliRunner().invoke(
        main,
        ("embeddings", "ingest"),
        env={
            "SCRAPYRUS_DATABASE_URL": "postgresql://db",
            "SCRAPYRUS_EMBEDDINGS_URL": "https://inference.example",
            "SCRAPYRUS_EMBEDDINGS_MODEL": "model",
            "SCRAPYRUS_EMBEDDINGS_API_KEY": "secret",
        },
    )
    assert result.exit_code == 0
    assert calls == [
        ("https://inference.example", "model", "secret"),
        (
            "postgresql://db",
            True,
            {"sample": None, "seed": 0, "chunk_size": 500},
        ),
    ]


def test_embeddings_ingest_passes_sample_size(monkeypatch):
    calls = []

    class Store:
        def __init__(self, *args):
            pass

        def setup_store(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr("scrapyrus.__main__.EmbeddingStore", Store)
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "ingest",
            "--database-url",
            "postgresql://db",
            "--inference-server-url",
            "https://example",
            "--model-name",
            "model",
            "--api-key",
            "secret",
            "--sample",
            "12",
            "--seed",
            "8675309",
            "--chunk-size",
            "750",
            "--no-progress",
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            ("postgresql://db", False),
            {"sample": 12, "seed": 8675309, "chunk_size": 750},
        )
    ]


def test_embeddings_ingest_reports_missing_pgvector(monkeypatch):
    class Store:
        def __init__(self, *args):
            pass

        def setup_store(self, *args, **kwargs):
            raise PgvectorUnavailableError(
                "PostgreSQL extension 'vector' is not available."
            )

    monkeypatch.setattr("scrapyrus.__main__.EmbeddingStore", Store)
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "ingest",
            "--database-url",
            "postgresql://db",
            "--inference-server-url",
            "https://example",
            "--model-name",
            "model",
            "--api-key",
            "secret",
        ),
    )
    assert result.exit_code == 1
    assert "extension 'vector' is not available" in result.output


def test_embeddings_ingest_reports_missing_transcriptions(monkeypatch):
    class Store:
        def __init__(self, *args):
            pass

        def setup_store(self, *args, **kwargs):
            raise TranscriptionsUnavailableError(
                "Run 'scrapyrus transcriptions ingest' first."
            )

    monkeypatch.setattr("scrapyrus.__main__.EmbeddingStore", Store)
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "ingest",
            "--database-url",
            "postgresql://db",
            "--inference-server-url",
            "https://example",
            "--model-name",
            "model",
            "--api-key",
            "secret",
        ),
    )

    assert result.exit_code == 1
    assert result.output == ("Error: Run 'scrapyrus transcriptions ingest' first.\n")


def test_embeddings_delete_removes_model_from_both_tables(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.delete_embeddings",
        lambda database_url, **kwargs: calls.append((database_url, kwargs)),
    )
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "delete",
            "--database-url",
            "postgresql://db",
            "--model-name",
            "model",
        ),
    )
    assert result.exit_code == 0
    assert calls == [("postgresql://db", {"modelname": "model"})]


def test_embeddings_dump_writes_selected_table(tmp_path, monkeypatch):
    calls = []
    output = tmp_path / "embeddings.dump"
    monkeypatch.setattr(
        "scrapyrus.__main__.dump_embeddings",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "dump",
            "--database-url",
            "postgresql://db",
            "--model-name",
            "model",
            "--kind",
            "translations",
            str(output),
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            (output, "postgresql://db"),
            {"modelname": "model", "document_kind": "translations"},
        )
    ]


def test_embeddings_dump_uses_parameterized_default_filename(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.dump_embeddings",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "dump",
            "--database-url",
            "postgresql://db",
            "--model-name",
            "provider/model name",
            "--kind",
            "translations",
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            (
                Path("translation-embeddings-provider-model-name.dump"),
                "postgresql://db",
            ),
            {"modelname": "provider/model name", "document_kind": "translations"},
        )
    ]


def test_embeddings_import_reads_selected_table(tmp_path, monkeypatch):
    calls = []
    source = tmp_path / "embeddings.dump"
    source.write_bytes(b"dump")
    monkeypatch.setattr(
        "scrapyrus.__main__.import_embeddings",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "import",
            "--database-url",
            "postgresql://db",
            "--model-name",
            "model",
            "--kind",
            "transcription",
            str(source),
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            (source, "postgresql://db"),
            {"modelname": "model", "document_kind": "transcription"},
        )
    ]


def test_embeddings_update_requires_model_and_uses_database(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.update_embeddings",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "update",
            "--database-url",
            "postgresql://db",
            "--inference-server-url",
            "https://example",
            "--model-name",
            "model",
            "--api-key",
            "secret",
            "--no-progress",
        ),
    )
    assert result.exit_code == 0
    assert calls == [
        (
            ("postgresql://db", False),
            {
                "inference_server_url": "https://example",
                "modelname": "model",
                "api_key": "secret",
                "chunk_size": 500,
            },
        )
    ]


def test_embeddings_evaluate_has_no_idpdata_or_variant_arguments(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.evaluate_embeddings",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    output = tmp_path / "evaluation.md"
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "evaluate",
            "--database-url",
            "postgresql://db",
            "--output",
            str(output),
        ),
    )
    assert result.exit_code == 0
    assert calls == [
        (
            ("postgresql://db",),
            {
                "output_file": output,
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
    output = tmp_path / "evaluation.md"

    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "evaluate",
            "--database-url",
            "postgresql://db",
            "--sample",
            "12",
            "--seed",
            "8675309",
            "--output",
            str(output),
            "--no-progress",
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            ("postgresql://db",),
            {
                "output_file": output,
                "progressbar": False,
                "sample": 12,
                "seed": 8675309,
            },
        )
    ]
