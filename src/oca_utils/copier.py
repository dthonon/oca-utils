"""
Copie des fichiers média vers le répertoire OCA.

Module de copie des fichiers média depuis un répertoire vers le répertoire OCA,
avec renommage au format OCA et duplication si plusieurs espèces dans le même fichier.
"""

import logging
import os
import re
import shutil
import subprocess  # noqa: S404
import tempfile
from pathlib import Path

import click
import exiftool  # type: ignore
import yaml
from unidecode import unidecode

from .constantes import DEPT_PAT
from .constantes import MEDIA_PAT
from .constantes import NON_FAUNE
from .utilitaires import corrige
from .utilitaires import details
from .utilitaires import noms
from .utilitaires import qte


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.command()
@click.option(
    "--from_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des fichiers à copier",
)
@click.option(
    "--to_dir",
    required=False,
    default="",
    type=click.Path(),
    help="Répertoire de destination des fichiers, pour la commande copier uniquement",
)
@click.option("--dry_run", is_flag=True, help="Mode test, sans renommage des fichiers.")
@click.option("--full", is_flag=True, help="Copie complète de tous les médias.")
@click.pass_context
def copier(  # noqa: max-complexity=13
    ctx: click.Context,
    from_dir: str,
    to_dir: str,
    full: bool = False,
    dry_run: bool = False,
) -> None:
    """Copie et renomme au format OCA les photos et vidéos."""
    if not Path(from_dir).expanduser().is_dir():
        logger.fatal(f"Le répertoire d'entrée {from_dir} n'est pas valide")
        raise FileNotFoundError
    rep_origine = Path(from_dir).expanduser()
    logger.info(f"Copie des photos et vidéos depuis {rep_origine}")
    if not Path(to_dir).expanduser().is_dir():
        logger.fatal(f"Le répertoire de destination {to_dir} n'est pas valide")
        raise FileNotFoundError
    rep_destination = Path(to_dir).expanduser()
    logger.info(f"Copie des photos et vidéos vers {rep_destination}")

    # Création des chemin par date de relevé
    dernier = "00000000"
    tags = None
    relevés = []
    rep_racine = ""
    with open(rep_origine / "information.yaml") as info:
        infos = yaml.safe_load(info)
        if "export_oca" not in infos:
            logger.fatal(
                "Le fichier information.yaml ne contient pas le tag export_oca"
            )
            raise KeyError
        elif infos["export_oca"]:
            nom = infos["caméra"]["nom"]
            p = rep_origine.parts
            rep_racine = "_".join(
                (nom, re.sub(DEPT_PAT, "", p[-2]), p[-1].replace("_", ""))
            )
            if not Path(rep_destination / rep_racine).is_dir():
                logger.info(f"Création du répertoire racine : {rep_racine}")
                Path(rep_destination / rep_racine).mkdir(parents=False)
            shutil.copy2(
                rep_origine / "information.yaml", Path(rep_destination / rep_racine)
            )

            def date_oca(dt: str) -> str:
                """Convertit une date du format YYYY/MM/DD au format OCA YYYYMMDD."""
                dts = dt.split("/")
                return "".join((dts[2], dts[1], dts[0]))

            relevés = [date_oca(dt) for dt in infos["relevé"]]

            for dt in sorted(relevés):
                if Path(rep_destination / rep_racine / dt).is_dir():
                    # Mémorisation de la date de dernier relevé, pour incrément
                    dernier = dt
                else:
                    logger.info(
                        f"Création du répertoire par relevé : {rep_racine}/{dt}"
                    )
                    Path(rep_destination / rep_racine / dt).mkdir(
                        parents=True, exist_ok=True
                    )
        else:
            logger.info(
                "Le fichier information.yaml contient le tag export_oca à False,"
                + " pas de copie"
            )

    type_cp = "complète" if full else "incrémentale"
    logger.info(f"Copie {type_cp}" + f" depuis {dernier}")
    with exiftool.ExifToolHelper() as et:
        # Détermination du nom OCA
        seq = 1
        fichiers = rep_origine.glob("**")
        for f in fichiers:
            if re.match(MEDIA_PAT, f.suffix):
                date_prise = f.name.split("_")[1]
                tags = []
                if full or date_prise > dernier:
                    logger.debug(f"Copie/renommage de {f.name}, daté {date_prise}")
                    # Recherche des tags de classification
                    for d in et.get_tags(f, tags=["HierarchicalSubject"]):
                        if "XMP:HierarchicalSubject" in d:
                            tags = d["XMP:HierarchicalSubject"]
                            break

                    # print(tags)
                    # Vérification des tags
                    sp = noms(tags)
                    if len(sp) == 0:
                        logger.warning(f"Pas d'espèce définie dans {f.name}")
                    nb = qte(tags)
                    det = details(tags)
                    logger.debug(f"tags : {sp}/{nb}/{det}")

                    # Création du préfixe IMG_nnnn
                    racine = f"IMG_{seq:04}"
                    seq += 1
                    # Parcours des espèces pour copier vers autant de fichiers
                    sph = len(set(sp) & NON_FAUNE)
                    with tempfile.NamedTemporaryFile(suffix=f.suffix) as fp:
                        if sph > 0:
                            # Présence humaine possible => deface
                            logger.info(f"Deface de {f} vers {fp.name}")
                            if not dry_run:
                                subprocess.run(  # noqa: S603
                                    [
                                        "/home/daniel/.local/bin/poetry",
                                        "run",
                                        "deface",
                                        "--keep-metadata",
                                        "--ffmpeg-config",
                                        '{"macro_block_size": 8}',
                                        "--execution-provider",
                                        "CUDAExecutionProvider",
                                        "--output",
                                        f"{fp.name}",
                                        f"{f}",
                                    ]
                                )
                            fi = Path(fp.name)
                        else:
                            # Pas d'humain visible
                            fi = f
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
                            if len(de) == 0:
                                # Pas de détails
                                dest = (
                                    racine + "_" + corrige(s) + "_" + str(qt) + f.suffix
                                )
                            else:
                                # Avec détails
                                dest = (
                                    racine
                                    + "_"
                                    + corrige(s)
                                    + "_"
                                    + str(qt)
                                    + "_"
                                    + de
                                    + f.suffix
                                )
                            dest = unidecode(dest)

                            # Recherche du sous-répertoire
                            ssrep = ""
                            for dt in relevés:
                                ssrep = dt
                                if date_prise <= dt:
                                    break
                            logger.info(
                                f"Photo/Vidéo {fi.name}, à copier vers : {ssrep}/{dest}"
                            )

                            # Copie des fichiers
                            if not dry_run:
                                g = Path(rep_destination / rep_racine / ssrep / dest)
                                shutil.copy2(fi, g)
                                # Retour à la date originelle
                                mtime = f.stat().st_mtime
                                os.utime(g, (mtime, mtime))

                                # Copie des tags EXIF vers le nouveau fichier
                                fx = Path(str(f) + ".xmp")
                                gx = Path(str(g) + ".xmp")
                                if fx.exists():
                                    et.execute(
                                        "-Tagsfromfile",
                                        str(fx),
                                        "-IPTC:All",
                                        "-XMP:All",
                                        str(gx),
                                    )
                                    os.utime(gx, (mtime, mtime))
                                    gx.with_suffix(".xmp_original").unlink(
                                        missing_ok=True
                                    )
                                fx = Path(str(f))
                                gx = Path(str(g))
                                if fx.exists():
                                    et.execute(
                                        "-Tagsfromfile",
                                        str(fx),
                                        "-IPTC:All",
                                        "-XMP:All",
                                        str(gx),
                                    )
                                    os.utime(gx, (mtime, mtime))
                                    gx.with_suffix(".jpg_original").unlink(
                                        missing_ok=True
                                    )
                                    gx.with_suffix(".mp4_original").unlink(
                                        missing_ok=True
                                    )
