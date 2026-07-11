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


def test_embeddings_ingest_subcommand_triggers_embedding_store(tmp_path, monkeypatch):
    init_calls = []
    setup_calls = []

    class FakeEmbeddingStore:
        def __init__(self, inference_server_url, model_name, api_key):
            init_calls.append((inference_server_url, model_name, api_key))

        def setup_store(
            self,
            idp_data,
            database_url,
            progress,
            *,
            abbrev,
            break_on_gap,
            lost,
            unclear,
            regularize,
            translation,
        ):
            setup_calls.append(
                (
                    idp_data,
                    database_url,
                    progress,
                    abbrev,
                    break_on_gap,
                    lost,
                    unclear,
                    regularize,
                    translation,
                )
            )

    monkeypatch.setattr("scrapyrus.__main__.EmbeddingStore", FakeEmbeddingStore)
    idp_data = tmp_path / "idp.data"
    runner = CliRunner()

    result = runner.invoke(
        main,
        (
            "--idp-data",
            str(idp_data),
            "embeddings",
            "ingest",
            "--database-url",
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            "--inference-server-url",
            "https://inference.example/v1",
            "--model-name",
            "text-embedding-model",
            "--api-key",
            "api-secret",
            "--translation",
            "--abbrev",
            "--break-on-gap",
            "--lost",
            "--unclear",
            "--regularize",
            "--no-progress",
        ),
    )

    assert result.exit_code == 0
    assert init_calls == [
        ("https://inference.example/v1", "text-embedding-model", "api-secret")
    ]
    assert setup_calls == [
        (
            idp_data,
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            False,
            True,
            True,
            True,
            True,
            True,
            True,
        )
    ]
    assert result.output == ""


def test_embeddings_ingest_subcommand_uses_envvars(monkeypatch):
    init_calls = []
    setup_calls = []

    class FakeEmbeddingStore:
        def __init__(self, inference_server_url, model_name, api_key):
            init_calls.append((inference_server_url, model_name, api_key))

        def setup_store(self, idp_data, database_url, progress, **kwargs):
            setup_calls.append((idp_data, database_url, progress, kwargs))

    monkeypatch.setattr("scrapyrus.__main__.EmbeddingStore", FakeEmbeddingStore)
    runner = CliRunner()

    result = runner.invoke(
        main,
        ("embeddings", "ingest"),
        env={
            "SCRAPYRUS_DATABASE_URL": (
                "postgresql://scrapyrus:secret@postgres:5432/scrapyrus"
            ),
            "SCRAPYRUS_EMBEDDINGS_URL": "https://inference.example",
            "SCRAPYRUS_EMBEDDINGS_MODEL": "text-embedding-model",
            "SCRAPYRUS_EMBEDDINGS_API_KEY": "api-secret",
        },
    )

    assert result.exit_code == 0
    assert init_calls == [
        ("https://inference.example", "text-embedding-model", "api-secret")
    ]
    assert setup_calls == [
        (
            Path("idp.data"),
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            True,
            {
                "abbrev": False,
                "break_on_gap": False,
                "lost": False,
                "unclear": False,
                "regularize": False,
                "translation": False,
            },
        )
    ]


def test_embeddings_delete_subcommand_deletes_embedding_configuration(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.delete_embeddings",
        lambda database_url, **kwargs: calls.append((database_url, kwargs)),
    )
    runner = CliRunner()

    result = runner.invoke(
        main,
        (
            "embeddings",
            "delete",
            "--database-url",
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            "--model-name",
            "text-embedding-model",
            "--translation",
            "--abbrev",
            "--break-on-gap",
            "--lost",
            "--unclear",
            "--regularize",
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            {
                "modelname": "text-embedding-model",
                "abbrev": True,
                "break_on_gap": True,
                "lost": True,
                "unclear": True,
                "regularize": True,
                "translation": True,
            },
        )
    ]
    assert result.output == ""


def test_embeddings_delete_subcommand_uses_envvars(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scrapyrus.__main__.delete_embeddings",
        lambda database_url, **kwargs: calls.append((database_url, kwargs)),
    )
    runner = CliRunner()

    result = runner.invoke(
        main,
        ("embeddings", "delete"),
        env={
            "SCRAPYRUS_DATABASE_URL": (
                "postgresql://scrapyrus:secret@postgres:5432/scrapyrus"
            ),
            "SCRAPYRUS_EMBEDDINGS_MODEL": "text-embedding-model",
        },
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            {
                "modelname": "text-embedding-model",
                "abbrev": False,
                "break_on_gap": False,
                "lost": False,
                "unclear": False,
                "regularize": False,
                "translation": False,
            },
        )
    ]


def test_embeddings_update_subcommand_updates_all_embedding_configurations(
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_update_embeddings(
        idp_data,
        database_url,
        progress,
        *,
        inference_server_url,
        api_key,
    ):
        calls.append((idp_data, database_url, progress, inference_server_url, api_key))

    monkeypatch.setattr(
        "scrapyrus.__main__.update_embeddings",
        fake_update_embeddings,
    )
    idp_data = tmp_path / "idp.data"
    runner = CliRunner()

    result = runner.invoke(
        main,
        (
            "--idp-data",
            str(idp_data),
            "embeddings",
            "update",
            "--database-url",
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            "--inference-server-url",
            "https://inference.example/v1",
            "--api-key",
            "api-secret",
            "--no-progress",
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            idp_data,
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            False,
            "https://inference.example/v1",
            "api-secret",
        )
    ]
    assert result.output == ""


def test_embeddings_update_subcommand_uses_envvars(monkeypatch):
    calls = []

    def fake_update_embeddings(
        idp_data,
        database_url,
        progress,
        *,
        inference_server_url,
        api_key,
    ):
        calls.append((idp_data, database_url, progress, inference_server_url, api_key))

    monkeypatch.setattr(
        "scrapyrus.__main__.update_embeddings",
        fake_update_embeddings,
    )
    runner = CliRunner()

    result = runner.invoke(
        main,
        ("embeddings", "update"),
        env={
            "SCRAPYRUS_DATABASE_URL": (
                "postgresql://scrapyrus:secret@postgres:5432/scrapyrus"
            ),
            "SCRAPYRUS_EMBEDDINGS_URL": "https://inference.example",
            "SCRAPYRUS_EMBEDDINGS_API_KEY": "api-secret",
        },
    )

    assert result.exit_code == 0
    assert calls == [
        (
            Path("idp.data"),
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            True,
            "https://inference.example",
            "api-secret",
        )
    ]


def test_embeddings_evaluate_subcommand_writes_markdown(tmp_path, monkeypatch):
    calls = []

    def fake_evaluate_embeddings_model(database_url, **kwargs):
        calls.append((database_url, kwargs))

    monkeypatch.setattr(
        "scrapyrus.__main__.evaluate_embeddings_model",
        fake_evaluate_embeddings_model,
    )
    output_file = tmp_path / "evaluation.md"
    runner = CliRunner()

    result = runner.invoke(
        main,
        (
            "embeddings",
            "evaluate",
            "--database-url",
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            "--model-name",
            "text-embedding-model",
            "--output",
            str(output_file),
            "--abbrev",
            "--break-on-gap",
            "--lost",
            "--unclear",
            "--regularize",
        ),
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            {
                "modelname": "text-embedding-model",
                "output_file": output_file,
                "abbrev": True,
                "break_on_gap": True,
                "lost": True,
                "unclear": True,
                "regularize": True,
            },
        )
    ]
    assert result.output == ""


def test_embeddings_evaluate_subcommand_uses_envvars(monkeypatch):
    calls = []

    def fake_evaluate_embeddings_model(database_url, **kwargs):
        calls.append((database_url, kwargs))

    monkeypatch.setattr(
        "scrapyrus.__main__.evaluate_embeddings_model",
        fake_evaluate_embeddings_model,
    )
    runner = CliRunner()

    result = runner.invoke(
        main,
        ("embeddings", "evaluate"),
        env={
            "SCRAPYRUS_DATABASE_URL": (
                "postgresql://scrapyrus:secret@postgres:5432/scrapyrus"
            ),
            "SCRAPYRUS_EMBEDDINGS_MODEL": "text-embedding-model",
        },
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "postgresql://scrapyrus:secret@postgres:5432/scrapyrus",
            {
                "modelname": "text-embedding-model",
                "output_file": Path("embedding-evaluation.md"),
                "abbrev": False,
                "break_on_gap": False,
                "lost": False,
                "unclear": False,
                "regularize": False,
            },
        )
    ]
    assert result.output == ""
