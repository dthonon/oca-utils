"""
Vérification du tagging des photos et vidéos.

Vérification de la présence et de la cohérence des tags
des photos et vidéos transmises, avec génération d'un
bilan de la vérification affiché en fin de traitement.
"""

import logging
import re
from pathlib import Path

import click
import exiftool  # type: ignore
from rich.console import Console
from rich.table import Table

from oca_utils.constantes import CORRECT_PAT
from oca_utils.constantes import MEDIA_PAT
from oca_utils.utilitaires import details
from oca_utils.utilitaires import noms
from oca_utils.utilitaires import qte


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.command()
@click.option(
    "--input_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des fichiers AVI à convertir",
)
@click.pass_context
def vérifier(ctx: click.Context, input_dir: str) -> None:  # noqa: max-complexity=13
    """Vérification du tagging des photos et vidéos."""
    rep_origine = Path(input_dir).expanduser()
    if not rep_origine.is_dir():
        logger.fatal(f"Le répertoire d'entrée {input_dir} n'est pas valide")
        raise FileNotFoundError
    logger.info(f"Vérification du tagging des photos et vidéos dans {rep_origine}")

    fichiers = sorted(rep_origine.glob("*.*"))
    nb_fic = 0
    nb_err = 0
    nb_sp = 0
    nb_qte = 0
    nb_det = 0
    nb_geo = 0
    with exiftool.ExifToolHelper() as et:
        for f in fichiers:
            # Liste des fichiers triés par date de prise de vue
            if re.match(MEDIA_PAT, f.suffix):
                nb_fic += 1
                logger.debug(f.name)

                # Vérification du nommage
                if not re.match(CORRECT_PAT, f.name):
                    logger.warning(f"Fichier mal nommé : {f.name}")
                    nb_err += 1

                # Recherche des tags de classification
                for d in et.get_tags(f, tags=["HierarchicalSubject"]):
                    if "XMP:HierarchicalSubject" in d:
                        tags = d["XMP:HierarchicalSubject"]
                    else:
                        tags = []
                    if not isinstance(tags, list):
                        tags = [tags]
                logger.debug(tags)

                # Vérification des tags
                sp = noms(tags)
                if len(sp) > 0:
                    nb_sp += 1
                else:
                    logger.warning(f"Fichier sans espèce : {f.name}")
                nb = qte(tags)
                if len(nb) > 0:
                    nb_qte += 1
                det = details(tags)
                if len(det) > 0:
                    nb_det += 1
                logger.debug(f"{f.name} : {sp}/{nb}/{det}")

                # Recherche des tags de géolocalisation
                for d in et.get_tags(
                    f, tags=["XMP:GPSLatitude", "XMP:GPSLongitude", "XMP:GPSAltitude"]
                ):
                    if (
                        ("XMP:GPSLatitude" in d)
                        and ("XMP:GPSLongitude" in d)
                        and ("XMP:GPSAltitude" in d)
                    ):
                        nb_geo += 1
                    else:
                        logger.warning(f"Fichier sans géolocalisation : {f.name}")

    table = Table(title=f"Contenu de {rep_origine.name}")
    table.add_column("Item", justify="left", no_wrap=True)
    table.add_column("Valeur", justify="right")
    table.add_row("Fichiers", str(nb_fic), style="bold")
    if nb_err > 0:
        table.add_row("Fichiers mal nommés", str(nb_err), style="bold bright_red")
    if nb_sp < nb_fic:
        table.add_row(
            "Fichiers sans espèce", str(nb_fic - nb_sp), style="bold bright_red"
        )
    table.add_row("Tags espèce", str(nb_sp))
    table.add_row("Tags quantité", str(nb_qte))
    table.add_row("Tags détails", str(nb_det))
    table.add_row("Géolocalisation", str(nb_geo))
    if nb_geo < nb_fic:
        table.add_row(
            "Fichiers sans localisation", str(nb_fic - nb_geo), style="bold bright_red"
        )
    console = Console()
    console.print(table)
