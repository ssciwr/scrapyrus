import re
from pathlib import Path

import click

from scrapyrus.embeddings import (
    EMBEDDING_CORPORA,
    EmbeddingSpecification,
    EmbeddingStore,
    EmbeddingsUnavailableError,
    PgvectorUnavailableError,
    SourceUnavailableError,
    build_embedding_client,
)
from scrapyrus.embeddings.corpora import KeywordMatch, XmlCorpus
from scrapyrus.embeddings.evaluation import evaluate_embeddings
from scrapyrus.images import (
    DEFAULT_BROKEN_IMAGE_FILE,
    image_log_file,
    scrape_images,
)
from scrapyrus.ingestion import dump_metadata_tables, ingest_metadata
from scrapyrus.semantic_catalog import publish_catalog
from scrapyrus.transcriptions.core import (
    dump_transcriptions,
    import_transcriptions,
    ingest_transcriptions,
)
from scrapyrus.transcriptions.lemmatization import (
    MAX_WORDS_PER_CHUNK,
    lemmatize_transcriptions,
)

idp_data = click.option(
    "--idp-data",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("idp.data"),
    show_default=True,
    help="Path to the idp.data repository clone to work with",
)
DATABASE_URL_ENVVAR = "SCRAPYRUS_DATABASE_URL"
DEFAULT_DATABASE_URL = ""

database_url = click.option(
    "--database-url",
    envvar=DATABASE_URL_ENVVAR,
    default=DEFAULT_DATABASE_URL,
    help=(
        "PostgreSQL connection URL. Defaults to "
        f"{DATABASE_URL_ENVVAR}, then PostgreSQL connection defaults."
    ),
)


def _apply_options(function, options):
    """Apply Click option decorators in declaration order."""
    for option in reversed(options):
        function = option(function)
    return function


def embedding_client_options(function):
    return _apply_options(
        function,
        [
            click.option(
                "--inference-server-url",
                envvar="SCRAPYRUS_EMBEDDINGS_URL",
                required=True,
                help="OpenAI-compatible inference server URL.",
            ),
            click.option(
                "--api-key",
                envvar="SCRAPYRUS_EMBEDDINGS_API_KEY",
                required=True,
                help="API key for the OpenAI-compatible inference server.",
            ),
        ],
    )


def _embedding_model_options():
    """Return the shared embedding model command options."""
    return [
        click.option(
            "--model-name",
            envvar="SCRAPYRUS_EMBEDDINGS_MODEL",
            required=True,
            help="Embedding model name.",
        )
    ]


def embedding_model_options(function):
    return _apply_options(function, _embedding_model_options())


@click.group()
@idp_data
@click.pass_context
def main(context: click.Context, idp_data: Path) -> None:
    """Work with papyri.info idp.data."""

    context.ensure_object(dict)
    context.obj["idp_data"] = idp_data


@main.command("catalog")
@database_url
def publish_semantic_catalog(database_url: str) -> None:
    """Publish the current structured semantic catalog to PostgreSQL."""

    publish_catalog(database_url)


@main.command("images")
@click.argument(
    "target",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("images"),
)
@click.option(
    "--todo-file",
    "todo_filename",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("images_todo.txt"),
    show_default=True,
    help="Write URLs without a responsible scraper to this file",
)
@click.option(
    "--broken-file",
    "broken_filename",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DEFAULT_BROKEN_IMAGE_FILE,
    show_default=True,
    help="Read known broken URLs from this file",
)
@click.option(
    "--error-file",
    "error_filename",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("images_error.txt"),
    show_default=True,
    help="Write errors from this run to this file, replacing its contents",
)
@click.option(
    "--unavailable-file",
    "unavailable_filename",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("images_unavailable.txt"),
    show_default=True,
    help="Write URLs skipped because their scraper was unavailable to this file",
)
@click.option(
    "--log-file",
    "log_filename",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("images.log"),
    show_default=True,
    help="Write image scraper logs to this file",
)
@click.option(
    "--log-level",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        case_sensitive=False,
    ),
    default="INFO",
    show_default=True,
    help="Minimum level to write to the image scraper log",
)
@click.pass_context
def images(
    context: click.Context,
    target: Path,
    todo_filename: Path,
    broken_filename: Path,
    error_filename: Path,
    unavailable_filename: Path,
    log_filename: Path,
    log_level: str,
) -> None:
    """Scrape images and record unsupported, failed, or unavailable URLs."""

    with image_log_file(log_filename, log_level):
        scrape_images(
            target,
            todo_filename,
            error_filename,
            unavailable_filename,
            broken_filename=broken_filename,
            idp_data=context.obj["idp_data"],
        )


@main.group("metadata")
def metadata() -> None:
    """Work with papyrus metadata."""


@metadata.command("ingest")
@database_url
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Show a progress bar while reading idp.data records.",
)
@click.pass_context
def ingest(context: click.Context, database_url: str, progress: bool) -> None:
    """Ingest papyrus metadata into PostgreSQL."""

    ingest_metadata(
        context.obj["idp_data"],
        database_url,
        progressbar=progress,
    )


@metadata.command("dump")
@database_url
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("metadata-csv"),
    show_default=True,
    help="Directory to write one CSV file per metadata table.",
)
def dump(database_url: str, output_dir: Path) -> None:
    """Dump metadata database tables as CSV files."""

    dump_metadata_tables(output_dir, database_url)


@main.group("transcriptions")
def transcriptions() -> None:
    """Work with transcription and translation XML."""


@transcriptions.command("ingest")
@database_url
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Show a progress bar while reading idp.data records.",
)
@click.pass_context
def ingest_transcription_xml(
    context: click.Context,
    database_url: str,
    progress: bool,
) -> None:
    """Ingest transcription and translation XML into PostgreSQL."""

    ingest_transcriptions(
        context.obj["idp_data"],
        database_url,
        progressbar=progress,
    )


@transcriptions.command("dump")
@database_url
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("transcriptions-csv"),
    show_default=True,
    help="Directory to write the transcription XML and text CSV file.",
)
def dump_transcription_xml(database_url: str, output_dir: Path) -> None:
    """Dump transcription XML, rendered text, and lemmata as CSV."""

    dump_transcriptions(output_dir, database_url)


@transcriptions.command("import")
@database_url
@click.argument(
    "input_file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True, readable=True),
)
def import_transcription_xml(database_url: str, input_file: Path) -> None:
    """Rebuild the transcription table from a CSV dump."""

    try:
        import_transcriptions(input_file, database_url)
    except ValueError as error:
        raise click.ClickException(str(error)) from error


@transcriptions.command("lemmatize")
@database_url
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Show a progress bar while lemmatizing supported transcriptions.",
)
@click.option(
    "--max-words",
    type=click.IntRange(min=1),
    default=MAX_WORDS_PER_CHUNK,
    show_default=True,
    help="Maximum words to analyze in one Stanza call.",
)
def lemmatize(database_url: str, progress: bool, max_words: int) -> None:
    """Lemmatize Greek, Latin, and Coptic transcription rows."""

    lemmatize_transcriptions(
        database_url,
        progressbar=progress,
        max_words=max_words,
    )


@main.group("embeddings")
def embeddings() -> None:
    """Work with registered embedding corpora."""


def _tsv_field(value: object | None) -> str:
    """Format a value as a single TSV field without whitespace breaks."""
    return "" if value is None else " ".join(str(value).split())


def _run_embedding_operation(operation: str, corpus_name: str, **options) -> None:
    """Run an embedding store command and report CLI errors."""
    try:
        specification = EmbeddingSpecification(options.pop("model_name"))
        conninfo = options.pop("database_url")
        client = None
        if operation in {"ingest", "update", "query"}:
            client = build_embedding_client(
                options.pop("inference_server_url"),
                specification.model_name,
                options.pop("api_key"),
            )
        store = EmbeddingStore(
            corpus=corpus_name, specification=specification, client=client
        )
        if operation in {"ingest", "update"}:
            store.ingest(
                conninfo,
                stale_only=operation == "update",
                progressbar=options.pop("progress"),
                **options,
            )
        elif operation == "delete":
            store.delete(conninfo)
        elif operation == "dump":
            target = options["output_file"]
            if target is None:
                filename_model = re.sub(
                    r"[^A-Za-z0-9_.-]+", "-", specification.model_name
                ).strip("-")
                target = Path(f"{corpus_name}-embeddings-{filename_model}.dump")
            store.dump(target, conninfo)
        elif operation == "import":
            store.import_dump(options["input_file"], conninfo)
        elif operation == "query":
            matches = store.query(options["query"], conninfo, top_k=options["top_k"])
            keyword_results = not isinstance(EMBEDDING_CORPORA[corpus_name], XmlCorpus)
            click.echo(
                "rank\tsimilarity\tkeyword"
                if keyword_results
                else "rank\tsimilarity\ttm_id\tlanguage\tsource_path\ttext"
            )
            for rank, match in enumerate(matches, start=1):
                fields = (
                    (match.keyword,)
                    if isinstance(match, KeywordMatch)
                    else (
                        match.tm_id,
                        match.language,
                        match.source_path,
                        match.document_text,
                    )
                )
                click.echo(
                    "\t".join(
                        (
                            str(rank),
                            f"{match.similarity:.6f}",
                            *(_tsv_field(field) for field in fields),
                        )
                    )
                )
    except (
        PgvectorUnavailableError,
        SourceUnavailableError,
        EmbeddingsUnavailableError,
        ValueError,
    ) as error:
        raise click.ClickException(str(error)) from error


def _embedding_command(operation: str, corpus_name: str):
    """Build all operation commands from the same corpus registry."""

    def command(**options) -> None:
        _run_embedding_operation(operation, corpus_name, **options)

    command.__doc__ = f"{operation.capitalize()} {corpus_name} embeddings."
    options = [database_url, embedding_model_options]
    if operation in {"ingest", "update", "query"}:
        options.append(embedding_client_options)
    if operation in {"ingest", "update"}:
        options.append(
            click.option("--progress/--no-progress", default=True, show_default=True)
        )
        if isinstance(EMBEDDING_CORPORA[corpus_name], XmlCorpus):
            options.append(
                click.option(
                    "--chunk-size",
                    type=click.IntRange(min=1),
                    default=500,
                    show_default=True,
                    help="Maximum words per chunk; adjacent chunks overlap by 10%.",
                )
            )
            if operation == "ingest":
                options.extend(
                    [
                        click.option(
                            "--sample",
                            type=click.IntRange(min=1),
                            help="Sample records having both a transcription and a translation.",
                        ),
                        click.option("--seed", type=int, default=0, show_default=True),
                    ]
                )
    elif operation == "query":
        options.extend(
            [
                click.option(
                    "--top-k", type=click.IntRange(min=1), default=10, show_default=True
                ),
                click.argument("query"),
            ]
        )
    elif operation == "dump":
        options.append(
            click.argument(
                "output_file",
                type=click.Path(path_type=Path, dir_okay=False),
                required=False,
            )
        )
    elif operation == "import":
        options.append(
            click.argument(
                "input_file",
                type=click.Path(
                    path_type=Path, dir_okay=False, exists=True, readable=True
                ),
            )
        )
    return click.command(corpus_name)(_apply_options(command, options))


for operation_name in ("ingest", "update", "query", "delete", "dump", "import"):
    operation_group = click.Group(
        operation_name, help=f"{operation_name.capitalize()} embeddings."
    )
    embeddings.add_command(operation_group)
    for corpus_name in EMBEDDING_CORPORA:
        operation_group.add_command(_embedding_command(operation_name, corpus_name))


@embeddings.group("evaluate")
def evaluate_embedding_rows() -> None:
    """Evaluate embedding retrieval."""


def _text_evaluation_options(default_output: str):
    """Build a decorator for shared text evaluation options."""

    def decorator(function):
        return _apply_options(
            function,
            [
                database_url,
                click.option(
                    "--sample",
                    type=click.IntRange(min=1),
                    help=(
                        "Randomly select this many records that have both a "
                        "transcription and a translation."
                    ),
                ),
                click.option(
                    "--seed",
                    type=int,
                    default=0,
                    show_default=True,
                    help="Seed used to make --sample selection deterministic.",
                ),
                click.option(
                    "--output",
                    "output_file",
                    type=click.Path(path_type=Path, dir_okay=False),
                    default=Path(default_output),
                    show_default=True,
                    help="Markdown file to write evaluation findings to.",
                ),
                click.option(
                    "--progress/--no-progress",
                    default=True,
                    show_default=True,
                    help="Show progress bars while evaluating embedding retrieval.",
                ),
            ],
        )

    return decorator


def _evaluate_text_embeddings(
    query_kind: str,
    database_url: str,
    sample: int | None,
    seed: int,
    output_file: Path,
    progress: bool,
) -> None:
    """Run text embedding evaluation and report CLI errors."""
    try:
        evaluate_embeddings(
            database_url,
            query_kind=query_kind,
            output_file=output_file,
            progressbar=progress,
            sample=sample,
            seed=seed,
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error


@evaluate_embedding_rows.command("transcriptions")
@_text_evaluation_options("transcription-embedding-evaluation.md")
def evaluate_transcription_embeddings(**options) -> None:
    """Evaluate transcription queries against translation embeddings."""

    _evaluate_text_embeddings("transcriptions", **options)


@evaluate_embedding_rows.command("translations")
@_text_evaluation_options("translation-embedding-evaluation.md")
def evaluate_translation_embeddings(**options) -> None:
    """Evaluate translation queries against transcription embeddings."""

    _evaluate_text_embeddings("translations", **options)


if __name__ == "__main__":
    main()
