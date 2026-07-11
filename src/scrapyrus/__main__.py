from pathlib import Path

import click

from scrapyrus.images import (
    DEFAULT_BROKEN_IMAGE_FILE,
    image_log_file,
    scrape_images,
)
from scrapyrus.ingestion import dump_metadata_tables, ingest_metadata
from scrapyrus.transcriptions.embeddings import (
    EmbeddingStore,
    delete_embeddings,
    update_embeddings,
)


idp_data = click.option(
    "--idp-data",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("idp.data"),
    show_default=True,
    help="Path to the idp.data repository clone to work with",
)
database_url = click.option(
    "--database-url",
    envvar="SCRAPYRUS_DATABASE_URL",
    required=True,
    help="PostgreSQL connection URL. Defaults to SCRAPYRUS_DATABASE_URL.",
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


def embedding_configuration_options(function):
    return _apply_options(
        function,
        [
            click.option(
                "--model-name",
                "--modelname",
                envvar="SCRAPYRUS_EMBEDDINGS_MODEL",
                required=True,
                help="Embedding model name.",
            ),
            click.option(
                "--translation/--transcription",
                default=False,
                show_default=True,
                help="Select translation embeddings instead of transcription embeddings.",
            ),
            click.option(
                "--abbrev",
                is_flag=True,
                help="Include expansion text when selecting transcription embeddings.",
            ),
            click.option(
                "--break-on-gap",
                is_flag=True,
                help="Insert line breaks at gaps when selecting transcription embeddings.",
            ),
            click.option(
                "--lost",
                is_flag=True,
                help="Include supplied lost text when selecting transcription embeddings.",
            ),
            click.option(
                "--unclear",
                is_flag=True,
                help="Include unclear readings when selecting transcription embeddings.",
            ),
            click.option(
                "--regularize",
                is_flag=True,
                help="Use regularized readings when selecting transcription embeddings.",
            ),
        ],
    )


@click.group()
@idp_data
@click.pass_context
def main(context: click.Context, idp_data: Path) -> None:
    """Work with papyri.info idp.data."""

    context.ensure_object(dict)
    context.obj["idp_data"] = idp_data


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


@main.group("embeddings")
def embeddings() -> None:
    """Work with transcription and translation embeddings."""


@embeddings.command("ingest")
@database_url
@embedding_client_options
@embedding_configuration_options
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Show progress bars while reading idp.data records and embedding documents.",
)
@click.pass_context
def ingest_embeddings(
    context: click.Context,
    database_url: str,
    inference_server_url: str,
    model_name: str,
    api_key: str,
    translation: bool,
    abbrev: bool,
    break_on_gap: bool,
    lost: bool,
    unclear: bool,
    regularize: bool,
    progress: bool,
) -> None:
    """Ingest transcription or translation embeddings into PostgreSQL."""

    store = EmbeddingStore(inference_server_url, model_name, api_key)
    store.setup_store(
        context.obj["idp_data"],
        database_url,
        progress,
        abbrev=abbrev,
        break_on_gap=break_on_gap,
        lost=lost,
        unclear=unclear,
        regularize=regularize,
        translation=translation,
    )


@embeddings.command("delete")
@database_url
@embedding_configuration_options
def delete_embedding_configuration(
    database_url: str,
    model_name: str,
    translation: bool,
    abbrev: bool,
    break_on_gap: bool,
    lost: bool,
    unclear: bool,
    regularize: bool,
) -> None:
    """Delete one selected embedding configuration from PostgreSQL."""

    delete_embeddings(
        database_url,
        modelname=model_name,
        abbrev=abbrev,
        break_on_gap=break_on_gap,
        lost=lost,
        unclear=unclear,
        regularize=regularize,
        translation=translation,
    )


@embeddings.command("update")
@database_url
@embedding_client_options
@click.option(
    "--progress/--no-progress",
    default=True,
    show_default=True,
    help="Show progress bars while reading idp.data records and embedding documents.",
)
@click.pass_context
def update_embedding_configurations(
    context: click.Context,
    database_url: str,
    inference_server_url: str,
    api_key: str,
    progress: bool,
) -> None:
    """Compute missing or stale embeddings for all stored configurations."""

    update_embeddings(
        context.obj["idp_data"],
        database_url,
        progress,
        inference_server_url=inference_server_url,
        api_key=api_key,
    )


if __name__ == "__main__":
    main()
