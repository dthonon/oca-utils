"""Command-line interface."""
import logging
import re
from pathlib import Path
from typing import Dict
from typing import List

import click
import xmltodict
from unidecode import unidecode


logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.version_option()
@click.group()
@click.option(
    "--input_directory",
    help="Répertoire feuille contenant les vidéos à traiter",
)
@click.option(
    "--output_directory",
    help="Répertoire racine destiné à recevoir les vidéos traitées",
)
@click.option(
    "--output_directory",
    help="Répertoire racine destiné à recevoir les vidéos traitées",
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

    if not Path(input_directory).is_dir():
        logging.fatal(f"Le répertoire d'entrée {input_directory} n'est pas valide")
        raise FileNotFoundError
    if not Path(output_directory).is_dir():
        logging.fatal(f"Le répertoire de sortie {output_directory} n'est pas valide")
        raise FileNotFoundError
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


def qte(tags: List[str]) -> List[Dict[str, str]]:
    """Extraction des quantités d'individus."""
    qte_l = []
    qte_re = re.compile(r"Quantité.*")
    nb_re = re.compile(r"((\w|\s)+)_(\d+)")
    for t in tags:
        if qte_re.match(t):
            # Le tag commence par Quantité et contient une chaîne
            # indiquant l'espèce et sa quantité
            nbr = re.search(nb_re, t.split("/")[-1])
            if nbr:
                nb = {nbr.group(1): nbr.group(3)}
            else:
                nb = {"Inconnu": "1"}
            qte_l.append(nb)
    return qte_l


def details(tags: List[str]) -> List[Dict[str, str]]:
    """Extraction des détails par espèce."""
    det_l = []
    det_re = re.compile(r"Détails.*")
    détails_re = re.compile(r"((\w|\s)+)_((\w|\s)+)")
    for t in tags:
        if det_re.match(t):
            # Le tag commence par Détails et contient une chaîne
            # indiquant l'indice de l'espèce et ses détails
            détails = re.search(détails_re, t.split("/")[-1])
            if détails:
                détail = {détails.group(1): détails.group(3)}
            else:
                détail = {"Inconnu": ""}
            det_l.append(détail)
    return det_l


def renomme(sp: str) -> str:
    """Renommage des espèces au format OCA."""
    corresp = {"Canidés": "CANIDE SP"}
    if sp in corresp:
        renom = corresp[sp]
    else:
        renom = sp
    return renom


@main.command()
@click.pass_context
def copie(ctx: click.Context) -> None:
    """Liste des vidéos à traiter."""
    input_directory = ctx.obj["INPUT_DIRECTORY"]
    output_directory = ctx.obj["OUTPUT_DIRECTORY"]

    in_path = Path(input_directory)
    logging.info(f"Copie des vidéos depuis {in_path}")
    loc = input_directory.split("/")
    out_path = Path(output_directory).joinpath(loc[-3] + "_" + loc[-2])
    logging.info(f"Copie des vidéos vers {out_path}")
    out_path.mkdir(exist_ok=True)

    files = [f for f in in_path.glob("*.mp4.xmp")]
    seq = 1
    for f in files:
        with open(f) as fd:
            sidecar = xmltodict.parse(fd.read(), process_namespaces=False)
        tags = sidecar["x:xmpmeta"]["rdf:RDF"]["rdf:Description"]["digiKam:TagsList"]
        tags = tags["rdf:Seq"]["rdf:li"]
        sp = noms(tags)
        nb = qte(tags)
        det = details(tags)
        for s in sp:
            qt = 1
            for n in nb:
                if s in n:
                    qt = int(n[s])
                else:
                    qt = max(1, qt)
            de = ""
            for d in det:
                if s in d:
                    de = d[s]
            # Création du préfixe IMG_nnnn
            racine = f"IMG_{seq:04}"
            seq += 1
            if len(de) == 0:
                # Pas de détails
                dest = racine + "_" + renomme(s) + "_" + str(qt) + ".mp4"
            else:
                # Avec détails
                dest = racine + "_" + renomme(s) + "_" + str(qt) + "_" + de + ".mp4"
            dest = unidecode(dest)
            print(f"Vidéo {f.name} à copier vers : {dest}")


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
