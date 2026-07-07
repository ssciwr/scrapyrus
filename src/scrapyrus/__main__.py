from pathlib import Path

import click

from scrapyrus.images import (
    DEFAULT_BROKEN_IMAGE_FILE,
    image_log_file,
    scrape_images,
)
from scrapyrus.ingestion import dump_metadata_tables, ingest_metadata


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


if __name__ == "__main__":
    main()
