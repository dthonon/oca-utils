"""
Tagging des photos et vidéos avec les informations de Deepfaune
"""

import logging
from pathlib import Path

import click
import exiftool  # type: ignore
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.command()
@click.option(
    "--input_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des médias à tagger avec la prédiction de l'espèce et du nombre d'individus.",
)
@click.option("--dry_run", is_flag=True, help="Mode test, sans renommage des fichiers.")
@click.pass_context
def autotagger(ctx: click.Context, input_dir: str, dry_run: bool) -> None:
    """Tagging des photos et vidéos."""
    rep_origine = Path(input_dir).expanduser()
    if not rep_origine.is_dir():
        logger.fatal(f"Le répertoire d'entrée {input_dir} n'est pas valide")
        raise FileNotFoundError
    logger.info(f"Tagging deepfaune des photos et vidéos dans {rep_origine}")

    classif = pd.read_csv(rep_origine / "../deepfaune.csv", sep=",")

    with exiftool.ExifToolHelper() as et:
        for ld in classif.itertuples():
            # Parcours des fichier classés par deepfaune
            f = Path(str(ld.filename))
            fx = Path(str(f) + ".xmp")
            if fx.is_file():
                logger.info(f"Tagging de {f.name} : {ld.top1}, {ld.score}")
                # Recherche des tags de classification
                tags = []
                for d in et.get_tags(f, tags=["TagsList"]):
                    if "XMP:TagsList" in d:
                        tags = d["XMP:TagsList"]
                        break
                if not isinstance(tags, list):
                    tags = [tags]
                tags.append(f"Deepfaune/{ld.top1}/{ld.score}")
                print(tags)
                if not dry_run:
                    et.set_tags(
                        fx,
                        {
                            "XMP:TagsList": tags,
                        },
                    )
            else:
                logger.warning(f"Pas de fichier sidecar pour {f.name}")

    # # Suppression des xmp_original
    # fichiers = rep_origine.glob("*.*")
    # for f in fichiers:
    #     # Liste des fichiers triés par date de prise de vue
    #     if re.match(XMPO_PAT, f.suffix):
    #         logger.debug(f"Suppression de {f.name}")
    #         f.unlink(missing_ok=True)
