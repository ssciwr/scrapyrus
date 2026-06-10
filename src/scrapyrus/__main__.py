import click


idp_data = click.option(
    "--idp-data",
    help="Path to the idp.data repository clone to work with",
)


@click.command()
@idp_data
def main(idp_data):
    click.echo("This is scrapyrus's command line interface.")


if __name__ == "__main__":
    main()
