"""
Comparaison entre répertoires source et destination des photos et vidéos OCA.
"""

import logging
import re
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
import humanize

import pandas as pd
import yaml
from .utilitaires import df_to_table
from oca_utils.constantes import DEPT_PAT
from oca_utils.constantes import PHOTO_PAT
from oca_utils.constantes import VIDEO_PAT

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.command()
@click.option(
    "--from_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des fichiers à traiter",
)
@click.option(
    "--to_dir",
    required=False,
    default="",
    type=click.Path(),
    help="Fichier CSV d'export, pour la commande exporter uniquement",
)
@click.pass_context
def comparer(  # noqa: max-complexity=13
    ctx: click.Context, from_dir: str, to_dir: str
) -> None:
    """Vérification et bilan des photos et vidéos transmises."""
    if not Path(from_dir).expanduser().is_dir():
        logger.fatal(f"Le répertoire d'entrée {from_dir} n'est pas valide")
        raise FileNotFoundError
    rep_origine = Path(from_dir).expanduser()
    if not Path(to_dir).expanduser().is_dir():
        logger.fatal(f"Le répertoire de destination {to_dir} n'est pas valide")
        raise FileNotFoundError
    rep_destination = Path(to_dir).expanduser()
    logger.info(
        f"Vérification et bilan des photos et vidéos transférées dans {rep_destination}"
    )
    lg_destination = len(rep_destination.parts)

    synthèse = pd.DataFrame(
        columns=(
            "Répertoire",
            "Source",
            "Destination",
            "Ecart",
            "Taille",
            "Médias",
            "Photos",
            "Vidéos",
        )
    )
    synthèse.set_index(["Répertoire"], inplace=True)

    # Parcours des répértoires d'origine pour chercher les photos et vidéos
    for chemin, _dirs, fichiers in rep_origine.walk(on_error=print):
        chemin_p = chemin.parts
        if Path(chemin / "information.yaml").exists():
            with open(chemin / "information.yaml") as info:
                infos = yaml.safe_load(info)
                if not ("export_oca" in infos and not infos["export_oca"]):
                    nom = infos["caméra"]["nom"]
                    rep_racine = "_".join(
                        (
                            nom,
                            re.sub(DEPT_PAT, "", chemin_p[-2]),
                            chemin_p[-1].replace("_", ""),
                        )
                    )
                    logger.debug(
                        f"Compte dans le répertoire d'origine {chemin} vers {rep_racine}"
                    )
                    synthèse.loc[rep_racine, "Source"] = len(fichiers)
                    synthèse.loc[rep_racine, "Destination"] = (
                        1  # En comptant information.yaml
                    )
                    synthèse.loc[rep_racine, "Taille"] = 0
                    synthèse.loc[rep_racine, "Photos"] = 0
                    synthèse.loc[rep_racine, "Vidéos"] = 0

    # Parcours des répértoires destination pour chercher les photos et vidéos
    for chemin, _dirs, fichiers in rep_destination.walk(on_error=print):
        logger.debug(f"Compte dans le répertoire de destination {chemin}")
        chemin_p = chemin.parts
        if len(chemin_p) == lg_destination + 2 and not chemin_p[-2].startswith("."):
            # Répertoire contenant les médias
            # Calcul des tailles et types de médias
            synthèse.loc[chemin_p[-2], "Destination"] += len(fichiers)
            synthèse.loc[chemin_p[-2], "Taille"] += sum(
                (chemin / file).stat().st_size for file in fichiers
            )
            synthèse.loc[chemin_p[-2], "Photos"] += len(
                [f for f in fichiers if re.match(PHOTO_PAT, Path(f).suffix)]
            )
            synthèse.loc[chemin_p[-2], "Vidéos"] += len(
                [f for f in fichiers if re.match(VIDEO_PAT, Path(f).suffix)]
            )

    synthèse["Médias"] = synthèse["Photos"] + synthèse["Vidéos"]
    synthèse["Ecart"] = synthèse["Destination"] - synthèse["Source"]
    synthèse.sort_index(inplace=True)
    total = synthèse.aggregate(func="sum")
    synthèse["Taille"] = synthèse["Taille"].apply(
        lambda t: humanize.naturalsize(t, True)
    )
    console = Console()

    table_f = Table(title="Synthèse fichiers OCA")
    table_f = df_to_table(synthèse, table_f)
    table_f.add_section()
    table_f.add_row(
        "TOTAL",
        str(total.Source),
        str(total.Destination),
        str(total.Ecart),
        humanize.naturalsize(total.Taille, True),
        str(total.Médias),
        str(total.Photos),
        str(total.Vidéos),
    )
    console.print(table_f)
