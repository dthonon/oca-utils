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
            spr = re.search(sp_re, t.split("/")[-1])
            if spr:
                sp = spr.group(0)
                sp = sp[0 : len(sp) - 2]
            else:
                sp = "Inconnu"
            noms_l.append(sp)
    return noms_l


def qte(tags: List[str]) -> List[str]:
    """Extraction des quantités d'individus."""
    qte_l = []
    qte_re = re.compile(r"Quantité.*")
    nb_re = re.compile(r"((\w|\s)+)_(\d+)")
    for t in tags:
        if qte_re.match(t):
            # Le tag commence par Quantité et contient une chaîne
            # indiquant l'indice de l'espèce et sa quantité
            nbr = re.search(nb_re, t.split("/")[-1])
            if nbr:
                nb = {nbr.group(1): nbr.group(3)}
            else:
                nb = "1"
            qte_l.append(nb)
    return qte_l


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
        nb = qte(tags)
        for s in sp:
            qt = 1
            for n in nb:
                if s in n:
                    qt = int(n[s])
                else:
                    qt = max(1, qt)
            dest = racine + "_" + s + "_" + str(qt) + ".mp4"
            print(f"Vidéo {f.name} copiée vers : {dest}")


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
