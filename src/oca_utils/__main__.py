"""Command-line interface."""
import click


@click.command()
@click.version_option()
def main() -> None:
    """Oca Utils."""


if __name__ == "__main__":
    main(prog_name="oca-utils")  # pragma: no cover
