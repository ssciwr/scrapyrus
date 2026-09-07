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
        ("catalog",),
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
        ("embeddings", "evaluate", "keywords"),
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


def test_embeddings_exposes_only_nested_operation_groups():
    assert set(main.commands["embeddings"].commands) == {
        "ingest",
        "dump",
        "import",
        "evaluate",
        "update",
        "delete",
    }
    for operation in main.commands["embeddings"].commands.values():
        assert set(operation.commands) == {
            "transcriptions",
            "translations",
            "keywords",
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
            "transcriptions",
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
            {
                "document_kind": "transcriptions",
                "sample": None,
                "seed": 0,
                "chunk_size": 500,
            },
        ),
    ]


def test_embeddings_ingest_keywords_uses_shared_embedding_options(monkeypatch):
    calls = []

    class Store:
        def __init__(self, url, model, key):
            calls.append(("init", url, model, key))

        def setup_store(self, database_url, progress, **kwargs):
            calls.append(("setup", database_url, progress, kwargs))

    monkeypatch.setattr("scrapyrus.__main__.KeywordEmbeddingStore", Store)
    result = CliRunner().invoke(
        main,
        ("embeddings", "ingest", "keywords", "--no-progress"),
        env={
            "SCRAPYRUS_DATABASE_URL": "postgresql://db",
            "SCRAPYRUS_EMBEDDINGS_URL": "https://inference.example/v1",
            "SCRAPYRUS_EMBEDDINGS_MODEL": "model",
            "SCRAPYRUS_EMBEDDINGS_API_KEY": "secret",
        },
    )

    assert result.exit_code == 0
    assert calls == [
        ("init", "https://inference.example/v1", "model", "secret"),
        ("setup", "postgresql://db", False, {"stale_only": False}),
    ]


def test_embeddings_evaluate_keyword_candidates_prints_ranked_matches(monkeypatch):
    calls = []

    class Match:
        def __init__(self, keyword, similarity):
            self.keyword = keyword
            self.similarity = similarity

    monkeypatch.setattr(
        "scrapyrus.__main__.find_similar_keywords",
        lambda *args, **kwargs: calls.append((args, kwargs))
        or (Match("contract", 0.91234567), Match("receipt", 0.75)),
    )
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "evaluate",
            "keywords",
            "sale of a house",
            "--top-k",
            "2",
        ),
        env={
            "SCRAPYRUS_DATABASE_URL": "postgresql://db",
            "SCRAPYRUS_EMBEDDINGS_URL": "https://inference.example/v1",
            "SCRAPYRUS_EMBEDDINGS_MODEL": "model",
            "SCRAPYRUS_EMBEDDINGS_API_KEY": "secret",
        },
    )

    assert result.exit_code == 0
    assert calls == [
        (
            ("sale of a house", "postgresql://db"),
            {
                "inference_server_url": "https://inference.example/v1",
                "modelname": "model",
                "api_key": "secret",
                "top_k": 2,
            },
        )
    ]
    assert result.output == (
        "rank\tsimilarity\tkeyword\n1\t0.912346\tcontract\n2\t0.750000\treceipt\n"
    )


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
        ("embeddings", "ingest", "translations"),
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
            {
                "document_kind": "translations",
                "sample": None,
                "seed": 0,
                "chunk_size": 500,
            },
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
            "transcriptions",
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
            {
                "document_kind": "transcriptions",
                "sample": 12,
                "seed": 8675309,
                "chunk_size": 750,
            },
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
            "transcriptions",
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
            "transcriptions",
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


def test_embeddings_delete_removes_model_from_selected_table(monkeypatch):
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
            "translations",
            "--database-url",
            "postgresql://db",
            "--model-name",
            "model",
        ),
    )
    assert result.exit_code == 0
    assert calls == [
        (
            "postgresql://db",
            {"modelname": "model", "document_kind": "translations"},
        )
    ]


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
            "translations",
            "--database-url",
            "postgresql://db",
            "--model-name",
            "model",
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
            "translations",
            "--database-url",
            "postgresql://db",
            "--model-name",
            "provider/model name",
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            (
                Path("translations-embeddings-provider-model-name.dump"),
                "postgresql://db",
            ),
            {"modelname": "provider/model name", "document_kind": "translations"},
        )
    ]


def test_embeddings_dump_supports_keywords_kind(tmp_path, monkeypatch):
    calls = []
    output = tmp_path / "keywords.dump"
    monkeypatch.setattr(
        "scrapyrus.__main__.dump_embeddings",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "dump",
            "keywords",
            "--model-name",
            "model",
            str(output),
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            (output, DEFAULT_DATABASE_URL),
            {"modelname": "model", "document_kind": "keywords"},
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
            "transcriptions",
            "--database-url",
            "postgresql://db",
            "--model-name",
            "model",
            str(source),
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            (source, "postgresql://db"),
            {"modelname": "model", "document_kind": "transcriptions"},
        )
    ]


def test_embeddings_import_supports_keywords_kind(tmp_path, monkeypatch):
    calls = []
    source = tmp_path / "keywords.dump"
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
            "keywords",
            "--model-name",
            "model",
            str(source),
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            (source, DEFAULT_DATABASE_URL),
            {"modelname": "model", "document_kind": "keywords"},
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
            "transcriptions",
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
                "document_kind": "transcriptions",
                "modelname": "model",
                "api_key": "secret",
                "chunk_size": 500,
            },
        )
    ]


def test_embeddings_update_keywords_updates_only_stale_rows(monkeypatch):
    calls = []

    class Store:
        def __init__(self, *args):
            calls.append(("init", args))

        def setup_store(self, *args, **kwargs):
            calls.append(("setup", args, kwargs))

    monkeypatch.setattr("scrapyrus.__main__.KeywordEmbeddingStore", Store)
    result = CliRunner().invoke(
        main,
        (
            "embeddings",
            "update",
            "keywords",
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
        ("init", ("https://example", "model", "secret")),
        (
            "setup",
            ("postgresql://db", False),
            {"stale_only": True},
        ),
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
            "transcriptions",
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
    output = tmp_path / "evaluation.md"

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
                "query_kind": "translations",
                "progressbar": False,
                "sample": 12,
                "seed": 8675309,
            },
        )
    ]
