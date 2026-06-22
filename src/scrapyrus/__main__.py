from pathlib import Path

import click

from scrapyrus.images import scrape_images


idp_data = click.option(
    "--idp-data",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("idp.data"),
    show_default=True,
    help="Path to the idp.data repository clone to work with",
)


@click.group()
@idp_data
@click.pass_context
def main(context: click.Context, idp_data: Path) -> None:
    """Work with papyri.info HGV data."""

    context.ensure_object(dict)
    context.obj["idp_data"] = idp_data


@main.command("images")
@click.argument(
    "target",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("images"),
)
@click.argument("todo_filename", default="images_todo.txt")
@click.argument("error_filename", default="images_error.txt")
@click.argument("unavailable_filename", default="images_unavailable.txt")
@click.pass_context
def images(
    context: click.Context,
    target: Path,
    todo_filename: str,
    error_filename: str,
    unavailable_filename: str,
) -> None:
    """Scrape images and record unsupported, failed, or unavailable URLs."""

    scrape_images(
        target,
        todo_filename,
        error_filename,
        unavailable_filename,
        idp_data=context.obj["idp_data"],
    )


if __name__ == "__main__":
    main()
