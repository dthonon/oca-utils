"""Command-line interface."""
import logging
import re
from pathlib import Path
from typing import List

import click
import xmltodict


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


def noms(tags: List[str]) -> List[str]:
    """Extraction des noms d'espèces."""
    noms_l = []
    nature_re = re.compile(r"Nature.*")
    sp_re = re.compile(r"(\w|\s)+ {")
    for t in tags:
        if nature_re.match(t):
            # Le tag commence par Nature et se termine par l'espèce
            sp = re.search(sp_re, t.split("/")[-1])
            if sp:
                sp = sp.group(0)[0 : len(sp) - 2]
            else:
                sp = ""
            noms_l.append(sp)

    return noms_l


@main.command()
@click.pass_context
def liste(ctx: click.Context) -> None:
    """Liste des vidéos à traiter."""
    input_directory = ctx.obj["INPUT_DIRECTORY"]

    logging.info(f"Liste des vidéos à traiter dans {input_directory}")
    files = [f for f in Path(input_directory).glob("*.mp4.xmp")]
    for f in files:
        with open(f) as fd:
            sidecar = xmltodict.parse(fd.read(), process_namespaces=False)
        tags = sidecar["x:xmpmeta"]["rdf:RDF"]["rdf:Description"]["digiKam:TagsList"]
        tags = tags["rdf:Seq"]["rdf:li"]
        racine = f.name[0 : len(f.name) - 8]
        sp = noms(tags)
        for s in sp:
            dest = racine + "_" + s
            print(f"Vidéo {f.name} copiée ver : {dest}")


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
