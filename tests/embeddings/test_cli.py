from pathlib import Path

import pytest
from click.testing import CliRunner

from scrapyrus.__main__ import main
from tests.embeddings.helpers import specification
from scrapyrus.embeddings import (
    EMBEDDING_CORPORA,
    DocumentMatch,
    KeywordMatch,
    SourceUnavailableError,
)


@pytest.fixture
def cli_store(monkeypatch):
    calls = []
    client = object()
    monkeypatch.setattr(
        "scrapyrus.__main__.build_embedding_client",
        lambda **kwargs: calls.append(("client", kwargs)) or client,
    )

    class Store:
        def __init__(self, *, corpus, specification, client):
            self.corpus = corpus
            calls.append(("store", corpus, specification.model_name, client))

        @classmethod
        def from_database(cls, *, corpus, model_name, conninfo):
            return cls(
                corpus=corpus, specification=specification(model_name, 2), client=None
            )

        @classmethod
        def from_dump(cls, *, corpus, model_name, source):
            return cls(
                corpus=corpus, specification=specification(model_name, 2), client=None
            )

        def ingest(self, conninfo, **options):
            calls.append(("ingest", conninfo, options))

        def query(self, text, conninfo, **options):
            calls.append(("query", text, conninfo, options))
            return (
                (KeywordMatch("lease, land", 0.9),)
                if self.corpus == "keywords"
                else (DocumentMatch("source.xml", "42", "en", "land\nlease", 0.9),)
            )

        def delete(self, conninfo):
            calls.append(("delete", conninfo))

        def dump(self, target, conninfo):
            calls.append(("dump", target, conninfo))

        def import_dump(self, source, conninfo, *, force):
            calls.append(("import", source, conninfo, {"force": force}))

    monkeypatch.setattr("scrapyrus.__main__.EmbeddingStore", Store)
    return calls, client


def invoke(*args):
    return CliRunner().invoke(
        main,
        ("embeddings", *args),
        env={
            "SCRAPYRUS_DATABASE_URL": "postgresql://db",
            "SCRAPYRUS_EMBEDDINGS_URL": "https://server/v1",
            "SCRAPYRUS_EMBEDDINGS_MODEL": "model",
            "SCRAPYRUS_EMBEDDINGS_API_KEY": "secret",
        },
    )


@pytest.mark.parametrize("corpus_name", tuple(EMBEDDING_CORPORA))
@pytest.mark.parametrize("operation", ["ingest", "update"])
def test_ingestion_commands_use_the_shared_store(operation, corpus_name, cli_store):
    calls, client = cli_store
    result = invoke(operation, corpus_name, "--no-progress")
    assert result.exit_code == 0, result.output
    assert calls[:2] == [
        (
            "client",
            {
                "provider": "vllm",
                "model_name": "model",
                "api_key": "secret",
                "inference_server_url": "https://server/v1",
                "provider_options": {"check_embedding_ctx_length": False},
            },
        ),
        ("store", corpus_name, "model", client),
    ]
    expected = {
        "stale_only": operation == "update",
        "progressbar": False,
        "force": False,
    }
    if corpus_name != "keywords":
        expected["chunk_size"] = 500
        if operation == "ingest":
            expected.update(sample=None, seed=0)
    assert calls[-1] == ("ingest", "postgresql://db", expected)


@pytest.mark.parametrize("corpus_name", tuple(EMBEDDING_CORPORA))
def test_query_commands_use_the_bound_store_and_format_corpus_results(
    corpus_name, cli_store
):
    calls, client = cli_store
    result = invoke("query", corpus_name, "lease", "--top-k", "2")
    assert result.exit_code == 0, result.output
    assert calls[1] == ("store", corpus_name, "model", client)
    assert calls[-1] == ("query", "lease", "postgresql://db", {"top_k": 2})
    expected = (
        "rank\tsimilarity\tkeyword\n1\t0.900000\tlease, land\n"
        if corpus_name == "keywords"
        else (
            "rank\tsimilarity\ttm_id\tlanguage\tsource_path\ttext\n"
            "1\t0.900000\t42\ten\tsource.xml\tland lease\n"
        )
    )
    assert result.output == expected


@pytest.mark.parametrize("corpus_name", tuple(EMBEDDING_CORPORA))
@pytest.mark.parametrize("operation", ["delete", "dump", "import"])
def test_file_and_delete_commands_use_the_shared_store_without_a_client(
    operation, corpus_name, cli_store, tmp_path
):
    calls, _ = cli_store
    source = tmp_path / "corpus.dump"
    source.write_bytes(b"binary")
    args = (str(source),) if operation == "import" else ()
    result = invoke(operation, corpus_name, *args)
    assert result.exit_code == 0, result.output
    assert calls[0] == ("store", corpus_name, "model", None)
    expected = (
        ("delete", "postgresql://db")
        if operation == "delete"
        else (
            operation,
            Path(f"{corpus_name}-embeddings-model.dump")
            if operation == "dump"
            else source,
            "postgresql://db",
        )
    )
    if operation == "import":
        expected = (*expected, {"force": False})
    assert calls[-1] == expected


def test_xml_ingestion_passes_chunking_and_sampling_options(cli_store):
    calls, _ = cli_store
    result = invoke(
        "ingest",
        "translations",
        "--sample",
        "3",
        "--seed",
        "17",
        "--chunk-size",
        "20",
        "--no-progress",
    )
    assert result.exit_code == 0
    assert calls[-1] == (
        "ingest",
        "postgresql://db",
        {
            "stale_only": False,
            "force": False,
            "progressbar": False,
            "sample": 3,
            "seed": 17,
            "chunk_size": 20,
        },
    )


def test_cli_reports_shared_store_source_errors(cli_store, monkeypatch):
    class Store:
        def __init__(self, **options):
            pass

        def ingest(self, *args, **options):
            raise SourceUnavailableError("Run metadata ingest first")

    monkeypatch.setattr("scrapyrus.__main__.EmbeddingStore", Store)
    result = invoke("ingest", "keywords", "--no-progress")
    assert result.exit_code == 1
    assert "Error: Run metadata ingest first" in result.output


def test_cli_reports_invalid_client_configuration(monkeypatch, cli_store):
    def fail(**kwargs):
        raise ValueError("Unsupported inference server")

    monkeypatch.setattr("scrapyrus.__main__.build_embedding_client", fail)
    result = invoke("query", "keywords", "lease")
    assert result.exit_code == 1
    assert result.output == "Error: Unsupported inference server\n"


@pytest.mark.parametrize("corpus_name", tuple(EMBEDDING_CORPORA))
@pytest.mark.parametrize("operation", ["ingest", "update", "import"])
def test_force_is_forwarded_for_all_model_writing_commands(
    operation, corpus_name, cli_store, tmp_path
):
    calls, _ = cli_store
    source = tmp_path / "corpus.dump"
    source.write_bytes(b"binary")
    args = (str(source),) if operation == "import" else ("--no-progress",)
    result = invoke(operation, corpus_name, *args, "--force")
    assert result.exit_code == 0, result.output
    assert calls[-1][-1]["force"] is True
