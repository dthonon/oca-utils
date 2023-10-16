"""Command-line interface."""
import click
import logging
from pathlib import Path
import xmltodict
import pprint

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.version_option()
@click.group()
@click.option(
    "--input_directory",
    default=".",
    help="Répertoire contenant les vidéos à traiter",
)
@click.option(
    "--output_directory",
    default=".",
    help="Répertoire destiné à recevoir les vidéos traitées",
)
@click.pass_context
def main(
    ctx: click.Context,
    input_directory: str,
    output_directory: str,
) -> None:
    """OCA Utils."""
    logging.info("Transfert des vidéos au format OCA")
    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)

    ctx.obj["INPUT_DIRECTORY"] = input_directory
    ctx.obj["OUTPUT_DIRECTORY"] = output_directory


@main.command()
@click.pass_context
def liste(ctx: click.Context) -> None:
    """Liste des vidéos à traiter."""
    input_directory = ctx.obj["INPUT_DIRECTORY"]
    pp = pprint.PrettyPrinter(indent=4)

    logging.info(f"Liste des vidéos à traiter dans {input_directory}")
    files = [f for f in Path(input_directory).glob("*.mp4.xmp")]
    for f in files:
        with open(f) as fd:
            sidecar = xmltodict.parse(fd.read(), process_namespaces=False)
        tags = sidecar["x:xmpmeta"]["rdf:RDF"]["rdf:Description"]["digiKam:TagsList"]
        tags = tags["rdf:Seq"]["rdf:li"]
        logging.info(f"Vidéo {f.name} avec tags : {tags[0]}")


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
