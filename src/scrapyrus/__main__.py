from pathlib import Path
import re

import click

from scrapyrus.images import (
    DEFAULT_BROKEN_IMAGE_FILE,
    image_log_file,
    scrape_images,
)
from scrapyrus.ingestion import dump_metadata_tables, ingest_metadata
from scrapyrus.keyword_embeddings import (
    KeywordEmbeddingStore,
    KeywordEmbeddingsUnavailableError,
    KeywordsUnavailableError,
    find_similar_keywords,
)
from scrapyrus.semantic_catalog import publish_catalog
from scrapyrus.transcriptions.core import (
    dump_transcriptions,
    import_transcriptions,
    ingest_transcriptions,
)
from scrapyrus.transcriptions.embeddings import (
    EmbeddingStore,
    PgvectorUnavailableError,
    TranscriptionsUnavailableError,
    delete_embeddings,
    dump_embeddings,
    import_embeddings,
    update_embeddings,
)
from scrapyrus.transcriptions.evaluation import evaluate_embeddings
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
    return [
        click.option(
            "--model-name",
            "--modelname",
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
    """Work with transcription, translation, and keyword embeddings."""


@embeddings.group("ingest")
def ingest_embedding_rows() -> None:
    """Create embeddings from source data."""


def _text_ingestion_options(function):
    return _apply_options(
        function,
        [
            database_url,
            embedding_client_options,
            embedding_model_options,
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
                "--chunk-size",
                type=click.IntRange(min=1),
                default=500,
                show_default=True,
                help=(
                    "Maximum words per embedding chunk; adjacent chunks overlap by 10%."
                ),
            ),
            click.option(
                "--progress/--no-progress",
                default=True,
                show_default=True,
                help="Show progress bars while embedding database XML rows.",
            ),
        ],
    )


def _ingest_text_embeddings(
    document_kind: str,
    database_url: str,
    inference_server_url: str,
    model_name: str,
    api_key: str,
    sample: int | None,
    seed: int,
    chunk_size: int,
    progress: bool,
) -> None:
    store = EmbeddingStore(inference_server_url, model_name, api_key)
    try:
        store.setup_store(
            database_url,
            progress,
            document_kind=document_kind,
            sample=sample,
            seed=seed,
            chunk_size=chunk_size,
        )
    except (PgvectorUnavailableError, TranscriptionsUnavailableError) as error:
        raise click.ClickException(str(error)) from error


@ingest_embedding_rows.command("transcriptions")
@_text_ingestion_options
def ingest_transcription_embeddings(**options) -> None:
    """Embed transcription XML rows in PostgreSQL."""

    _ingest_text_embeddings("transcriptions", **options)


@ingest_embedding_rows.command("translations")
@_text_ingestion_options
def ingest_translation_embeddings(**options) -> None:
    """Embed translation XML rows in PostgreSQL."""

    _ingest_text_embeddings("translations", **options)


@ingest_embedding_rows.command("keywords")
@database_url
@embedding_client_options
@embedding_model_options
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Show a progress bar while embedding distinct keyword strings.",
)
def ingest_keyword_embeddings(
    database_url: str,
    inference_server_url: str,
    model_name: str,
    api_key: str,
    progress: bool,
) -> None:
    """Embed distinct metadata keyword strings in PostgreSQL."""

    store = KeywordEmbeddingStore(inference_server_url, model_name, api_key)
    try:
        store.setup_store(database_url, progress, stale_only=False)
    except (PgvectorUnavailableError, KeywordsUnavailableError) as error:
        raise click.ClickException(str(error)) from error


@embeddings.group("dump")
def dump_embedding_rows() -> None:
    """Dump embeddings in PostgreSQL binary COPY format."""


def _dump_options(function):
    return _apply_options(
        function,
        [
            database_url,
            embedding_model_options,
            click.argument(
                "output_file",
                type=click.Path(path_type=Path, dir_okay=False),
                required=False,
            ),
        ],
    )


def _dump_embeddings(
    document_kind: str,
    database_url: str,
    model_name: str,
    output_file: Path | None,
) -> None:
    if output_file is None:
        filename_model = re.sub(r"[^A-Za-z0-9_.-]+", "-", model_name).strip("-")
        output_file = Path(f"{document_kind}-embeddings-{filename_model}.dump")
    try:
        dump_embeddings(
            output_file,
            database_url,
            modelname=model_name,
            document_kind=document_kind,
        )
    except PgvectorUnavailableError as error:
        raise click.ClickException(str(error)) from error


@dump_embedding_rows.command("transcriptions")
@_dump_options
def dump_transcription_embeddings(**options) -> None:
    """Dump transcription embeddings for one model."""

    _dump_embeddings("transcriptions", **options)


@dump_embedding_rows.command("translations")
@_dump_options
def dump_translation_embeddings(**options) -> None:
    """Dump translation embeddings for one model."""

    _dump_embeddings("translations", **options)


@dump_embedding_rows.command("keywords")
@_dump_options
def dump_keyword_embeddings(**options) -> None:
    """Dump keyword embeddings for one model."""

    _dump_embeddings("keywords", **options)


@embeddings.group("import")
def import_embedding_rows() -> None:
    """Import embeddings from PostgreSQL binary COPY format."""


def _import_options(function):
    return _apply_options(
        function,
        [
            database_url,
            embedding_model_options,
            click.argument(
                "input_file",
                type=click.Path(
                    path_type=Path, dir_okay=False, exists=True, readable=True
                ),
            ),
        ],
    )


def _import_embeddings(
    document_kind: str,
    database_url: str,
    model_name: str,
    input_file: Path,
) -> None:
    try:
        import_embeddings(
            input_file,
            database_url,
            modelname=model_name,
            document_kind=document_kind,
        )
    except (PgvectorUnavailableError, ValueError) as error:
        raise click.ClickException(str(error)) from error


@import_embedding_rows.command("transcriptions")
@_import_options
def import_transcription_embeddings(**options) -> None:
    """Import transcription embeddings for one model."""

    _import_embeddings("transcriptions", **options)


@import_embedding_rows.command("translations")
@_import_options
def import_translation_embeddings(**options) -> None:
    """Import translation embeddings for one model."""

    _import_embeddings("translations", **options)


@import_embedding_rows.command("keywords")
@_import_options
def import_keyword_embeddings(**options) -> None:
    """Import keyword embeddings for one model."""

    _import_embeddings("keywords", **options)


@embeddings.group("update")
def update_embedding_rows() -> None:
    """Compute missing or stale embeddings."""


def _text_update_options(function):
    return _apply_options(
        function,
        [
            database_url,
            embedding_client_options,
            embedding_model_options,
            click.option(
                "--chunk-size",
                type=click.IntRange(min=1),
                default=500,
                show_default=True,
                help=(
                    "Maximum words per embedding chunk; adjacent chunks overlap by 10%."
                ),
            ),
            click.option(
                "--progress/--no-progress",
                default=True,
                show_default=True,
                help="Show progress bars while embedding stale database XML rows.",
            ),
        ],
    )


def _update_text_embeddings(
    document_kind: str,
    database_url: str,
    inference_server_url: str,
    model_name: str,
    api_key: str,
    chunk_size: int,
    progress: bool,
) -> None:
    try:
        update_embeddings(
            database_url,
            progress,
            document_kind=document_kind,
            inference_server_url=inference_server_url,
            modelname=model_name,
            api_key=api_key,
            chunk_size=chunk_size,
        )
    except (PgvectorUnavailableError, TranscriptionsUnavailableError) as error:
        raise click.ClickException(str(error)) from error


@update_embedding_rows.command("transcriptions")
@_text_update_options
def update_transcription_embeddings(**options) -> None:
    """Update transcription embeddings for one model."""

    _update_text_embeddings("transcriptions", **options)


@update_embedding_rows.command("translations")
@_text_update_options
def update_translation_embeddings(**options) -> None:
    """Update translation embeddings for one model."""

    _update_text_embeddings("translations", **options)


@update_embedding_rows.command("keywords")
@database_url
@embedding_client_options
@embedding_model_options
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Show a progress bar while embedding new keyword strings.",
)
def update_keyword_embeddings(
    database_url: str,
    inference_server_url: str,
    model_name: str,
    api_key: str,
    progress: bool,
) -> None:
    """Update keyword embeddings for one model."""

    store = KeywordEmbeddingStore(inference_server_url, model_name, api_key)
    try:
        store.setup_store(database_url, progress, stale_only=True)
    except (PgvectorUnavailableError, KeywordsUnavailableError) as error:
        raise click.ClickException(str(error)) from error


@embeddings.group("delete")
def delete_embedding_rows() -> None:
    """Delete embeddings for one model."""


def _delete_embeddings(document_kind: str, database_url: str, model_name: str) -> None:
    try:
        delete_embeddings(
            database_url,
            modelname=model_name,
            document_kind=document_kind,
        )
    except PgvectorUnavailableError as error:
        raise click.ClickException(str(error)) from error


@delete_embedding_rows.command("transcriptions")
@database_url
@embedding_model_options
def delete_transcription_embeddings(database_url: str, model_name: str) -> None:
    """Delete transcription embeddings for one model."""

    _delete_embeddings("transcriptions", database_url, model_name)


@delete_embedding_rows.command("translations")
@database_url
@embedding_model_options
def delete_translation_embeddings(database_url: str, model_name: str) -> None:
    """Delete translation embeddings for one model."""

    _delete_embeddings("translations", database_url, model_name)


@delete_embedding_rows.command("keywords")
@database_url
@embedding_model_options
def delete_keyword_embeddings(database_url: str, model_name: str) -> None:
    """Delete keyword embeddings for one model."""

    _delete_embeddings("keywords", database_url, model_name)


@embeddings.group("evaluate")
def evaluate_embedding_rows() -> None:
    """Evaluate embedding retrieval."""


def _text_evaluation_options(default_output: str):
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


@evaluate_embedding_rows.command("keywords")
@database_url
@embedding_client_options
@embedding_model_options
@click.option(
    "--top-k",
    type=click.IntRange(min=1),
    default=10,
    show_default=True,
    help="Number of nearest keyword candidates to print.",
)
@click.argument("query")
def evaluate_keyword_embeddings(
    database_url: str,
    inference_server_url: str,
    model_name: str,
    api_key: str,
    top_k: int,
    query: str,
) -> None:
    """Embed QUERY and print its nearest stored keyword candidates."""

    try:
        matches = find_similar_keywords(
            query,
            database_url,
            inference_server_url=inference_server_url,
            modelname=model_name,
            api_key=api_key,
            top_k=top_k,
        )
    except (KeywordEmbeddingsUnavailableError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo("rank\tsimilarity\tkeyword")
    for rank, match in enumerate(matches, start=1):
        click.echo(f"{rank}\t{match.similarity:.6f}\t{match.keyword}")


if __name__ == "__main__":
    main()
