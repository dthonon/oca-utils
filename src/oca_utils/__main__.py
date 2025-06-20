"""Command-line interface."""

import datetime
import logging
import math
import os
import re
import secrets
import shutil
import subprocess  # noqa: S404
import tempfile
import uuid
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional

import click
import exiftool  # type: ignore
import geopandas as gpd
import humanize
import pandas as pd
import pyproj
from shapely import Point
import shapely
import yaml
from ffmpeg import FFmpeg  # type: ignore
from ffmpeg import Progress
from rich.console import Console
from rich.table import Table
from unidecode import unidecode

from oca_utils.sp_sensible import sp_sensibles

NON_FAUNE = {
    "Agriculteur",
    "Chasseur",
    "Cueilleur",
    "Cycliste",
    # "Moto",
    "Pêcheur",
    # "Quad",
    "Randonneur",
    "Traileur",
    # "Voiture",
}
MEDIA_PAT = re.compile(r"\.(MP4|mp4|JPG|jpg)")
PHOTO_PAT = re.compile(r"\.(JPG|jpg)")
VIDEO_PAT = re.compile(r"\.(MP4|mp4)")
AVI_PAT = re.compile(r"\.(AVI|avi)")
CORRECT_PAT = re.compile(r"IMG_\d{8}_\d{6}_\d{2}\..*")
XMPO_PAT = re.compile(r".*xmp_original")
COMMUNE_PAT = re.compile(
    r"Continents et pays\|Europe\|France {France} {FR} {FRA}\|Auvergne-Rhône-Alpes\|Isère\|(.*)"
)
NATURE_PAT = re.compile(r"Nature.*")
ESPECE_PAT = re.compile(r"(\w|\s|')+ {")
QTE_PAT = re.compile(r"Quantité.*")
NB_PAT = re.compile(r"((\w|\s)+)_(\d+)")
DET_PAT = re.compile(r"Détails.*")
DETAILS_PAT = re.compile(r"((\w|\s)+)_((\w|\s)+)")
DEPT_PAT = re.compile(r"FR\d\d_")
OCA_PAT = re.compile(r"IMG_\d{4}_([\sa-zA-Z\']*)_(\d*).*")

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.version_option()
@click.group()
@click.option("--trace", is_flag=True, help="Traces détaillées")
@click.option("--essai", is_flag=True, help="Mode essai, sans action effectuée")
# @click.option(
#     "--incrément", default=True, help="Traitement incrémental depuis le dernier relevé"
# )
# @click.option(
#     "--force", is_flag=True, help="Force le traitement, même s'il n'est pas nécessaire"
# )
# @click.option(
#     "--origine",
#     required=True,
#     type=click.Path(exists=True, dir_okay=True, readable=True),
#     help="Répertoire des fichiers à traiter",
# )
# @click.option(
#     "--destination",
#     required=False,
#     default="",
#     type=click.Path(exists=False, dir_okay=True, writable=True),
#     help="Répertoire de destination des fichiers, pour la commande copier uniquement",
# )
@click.pass_context
def main(
    ctx: click.Context,
    trace: bool,
    essai: bool,
    # force: bool,
    # incrément: bool,
    # origine: str,
    # destination: str,
) -> None:
    """OCA Utils."""
    logging.info("Transfert des vidéos au format OCA")
    # ensure that ctx.obj exists and is a dict
    ctx.ensure_object(dict)

    if trace:
        logger.setLevel(logging.DEBUG)

    # if not Path(origine).expanduser().is_dir():
    #     logger.fatal(f"Le répertoire d'entrée {origine} n'est pas valide")
    #     raise FileNotFoundError
    # if destination != "" and not Path(destination).expanduser().is_dir():
    #     logger.fatal(f"Le répertoire de sortie {destination} n'est pas valide")
    #     raise FileNotFoundError
    # ctx.obj["FORCE"] = force
    ctx.obj["ESSAI"] = essai
    # ctx.obj["INCREMENT"] = incrément
    # ctx.obj["ORIGINE"] = origine
    # ctx.obj["DESTINATION"] = destination


def df_to_table(
    pandas_dataframe: pd.DataFrame,
    rich_table: Table,
    show_index: bool = True,
    index_name: Optional[str] = None,
) -> Table:
    """Convert a pandas.DataFrame obj into a rich.Table obj.

    :param pandas_dataframe:
        A Pandas DataFrame to be converted to a rich Table.
    :param rich_table:
        A rich Table that should be populated by the DataFrame values.
    :param show_index:
        Add a column with a row count to the table. Defaults to True.
    :param index_name:
        The column name to give to the index column. Defaults to None, showing no value.

    :returns:
        Table: The rich Table instance passed, populated with the DataFrame values.
    """
    if show_index:
        index_name = str(index_name) if index_name else ""
        rich_table.add_column(index_name)
        rich_indexes = pandas_dataframe.index.to_list()

    for column in pandas_dataframe.columns:
        rich_table.add_column(str(column), justify="right")

    for index, value_list in enumerate(pandas_dataframe.values.tolist()):
        row = [str(rich_indexes[index])] if show_index else []
        row += [str(x) for x in value_list]
        rich_table.add_row(*row)

    return rich_table


@main.command()
@click.option(
    "--input_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des fichiers AVI à convertir",
)
@click.option(
    "--output_dir",
    required=False,
    default="",
    type=click.Path(),
    help="Répertoire de destination des fichiers MP4",
)
@click.option(
    "--remplace", is_flag=True, help="Remplace le fichier d'export s'il existe déjà."
)
@click.pass_context
def convertir(
    ctx: click.Context, input_dir: str, output_dir: str, remplace: bool
) -> None:
    """Convertit les vidéos AVI ou  MP4 en mp4 optimisé."""
    rep_origine = Path(input_dir).expanduser()
    if not rep_origine.is_dir():
        logger.fatal(f"Le répertoire d'entrée {input_dir} n'est pas valide")
        raise FileNotFoundError
    logger.info(f"Conversion des vidéos depuis {rep_origine}")
    rep_destination = Path(output_dir)
    rep_destination.mkdir(exist_ok=True)
    logger.info(f"Conversion des vidéos vers {rep_destination}")

    with exiftool.ExifToolHelper() as et:
        for f in [f for f in rep_origine.glob("*.*")]:
            if re.match(AVI_PAT, f.suffix):
                g = rep_destination / f"{f.stem}_c.mp4"
                # g = g.with_suffix(".mp4")
                logger.info(f"Conversion de {f.name} en {g.name}")
                if not ctx.obj["ESSAI"]:
                    mtime = f.stat().st_mtime
                    timestamp_str = datetime.datetime.fromtimestamp(mtime).isoformat(
                        timespec="seconds"
                    )
                    ffmpeg = (
                        FFmpeg()
                        .option("y")
                        .option("hwaccel", "cuda")
                        .option("hwaccel_output_format", "cuda")
                        .input(f)
                        .output(
                            g,
                            {
                                "map_metadata": "0:s:0",
                                "metadata": f"creation_time={timestamp_str}",
                                # "vf": "scale_cuda=1920:1080",
                                "c:v": "hevc_nvenc",
                                "preset": "p7",
                                "tune": "hq",
                                "profile": "main",
                                "rc": "vbr",
                                "rc-lookahead": "60",
                                "fps_mode": "passthrough",
                                "multipass": "fullres",
                                "temporal-aq": "1",
                                "spatial-aq": "1",
                                "aq-strength": "12",
                                "cq": "24",
                                "b:v": "0M",
                                "bufsize": "500M",
                                "maxrate": "250M",
                                "qmin": "0",
                                "g": "250",
                                "bf": "3",
                                "b_ref_mode": "each",
                                "i_qfactor": "0.75",
                                "b_qfactor": "1.1",
                            },
                        )
                    )

                    # Conversion vidéo
                    @ffmpeg.on("progress")  # type:ignore
                    def on_progress(progress: Progress) -> None:
                        logger.debug(progress)

                    ffmpeg.execute()

                    # Retour à la date originelle
                    os.utime(g, (mtime, mtime))

                    # Copie des tags EXIF
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
                    gx.with_suffix(".mp4_original").unlink(missing_ok=True)
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
                    gx.with_suffix(".xmp_original").unlink(missing_ok=True)


def _renommer_temp(rep_origine: Path, dry_run: bool, force: bool) -> None:
    # Renommer en UUID, si le fichier n'est pas déjà bien nommé
    with exiftool.ExifToolHelper() as et:
        # Renommage temporaire pour éviter les écrasements
        fichiers = rep_origine.glob("*")
        for f in fichiers:
            if re.match(MEDIA_PAT, f.suffix) and (
                force or not re.match(CORRECT_PAT, f.name)
            ):
                mtime = f.stat().st_mtime
                g = rep_origine / (uuid.uuid4().hex + f.suffix.lower())
                logger.info(f"Photo/Vidéo {f.name} renommée en : {g.name}")
                if not dry_run:
                    f.rename(g)
                    # Retour à la date originelle
                    os.utime(g, (mtime, mtime))
                    # Copie des tags EXIF vers le nouveau fichier
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
                        gx.with_suffix(".mp4_original").unlink(missing_ok=True)
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
                        fx.unlink()
                        os.utime(gx, (mtime, mtime))
                        gx.with_suffix(".xmp_original").unlink(missing_ok=True)

    return None


def _renommer_seq_date(  # noqa: max-complexity=13
    rep_origine: Path, dry_run: bool
) -> None:
    s_fichiers = []
    fichiers = rep_origine.glob("*.*")
    with exiftool.ExifToolHelper() as et:
        for f in fichiers:
            # Liste des fichiers triés par date de prise de vue
            if re.match(MEDIA_PAT, f.suffix) and not re.match(CORRECT_PAT, f.name):
                logger.debug(f.name)
                # Extraction de la date de prise de vue
                for d in et.get_tags(
                    f, tags=["CreateDate", "DateTimeOriginal", "MediaCreateDate"]
                ):
                    logger.debug(d)
                    # Recherche de la date de prise de vue
                    if "EXIF:DateTimeOriginal" in d:
                        dc = d["EXIF:DateTimeOriginal"]
                    elif "XMP:DateTimeOriginal" in d:
                        dc = d["XMP:DateTimeOriginal"]
                    elif "XMP:CreateDate" in d:
                        dc = d["XMP:CreateDate"]
                    elif "QuickTime:MediaCreateDate" in d:
                        dc = d["QuickTime:MediaCreateDate"]
                    else:
                        dc = ""
                    s_fichiers.append((dc, f))

        for dc, f in sorted(s_fichiers, key=lambda dcf: dcf[0]):
            # Création du préfixe IMG_nnnn
            racine = "IMG_"
            # Formattage de la date
            fdate = dc.replace(":", "").replace(" ", "_")
            dest = unidecode(
                racine + fdate + "_" + f"{secrets.randbelow(10):02}" + f.suffix
            )
            logger.info(f"Photo/Vidéo {f.name}, datée {dc} à renommée en : {dest}")
            if not dry_run:
                mtime = f.stat().st_mtime
                g = rep_origine / dest
                f.rename(g)
                # Retour à la date originelle
                os.utime(g, (mtime, mtime))

                # Copie des tags EXIF vers le nouveau fichier
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
                    gx.with_suffix(".mp4_original").unlink(missing_ok=True)
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
                    fx.unlink()
                    os.utime(gx, (mtime, mtime))
                    gx.with_suffix(".xmp_original").unlink(missing_ok=True)

    return None


@main.command()
@click.option(
    "--input_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des fichiers AVI à convertir",
)
@click.option("--dry_run", is_flag=True, help="Mode test, sans renommage des fichiers.")
@click.option(
    "--force",
    is_flag=True,
    help="Force le renommage même si le nom du fichier est correct.",
)
@click.pass_context
def renommer(ctx: click.Context, input_dir: str, dry_run: bool, force: bool) -> None:
    """Convertit les vidéos AVI ou  MP4 en mp4 optimisé."""
    rep_origine = Path(input_dir).expanduser()
    if not rep_origine.is_dir():
        logger.fatal(f"Le répertoire d'entrée {input_dir} n'est pas valide")
        raise FileNotFoundError
    logger.info(f"Renommage des photos et vidéos dans {rep_origine}")

    # Renommage temporaire pour éviter les écrasements de fichier
    _renommer_temp(rep_origine, dry_run, force)

    # Renommage final
    _renommer_seq_date(rep_origine, dry_run)


def noms(tags: List[str]) -> List[str]:
    """Extraction des noms d'espèces."""
    noms_l = []

    for t in tags:
        if NATURE_PAT.match(t):
            # Le tag commence par Nature et se termine par l'espèce
            spr = re.search(ESPECE_PAT, t.split("|")[-1])
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

    for t in tags:
        if QTE_PAT.match(t):
            # Le tag commence par Quantité et contient une chaîne
            # indiquant l'espèce et sa quantité
            nbr = re.search(NB_PAT, t.split("|")[-1])
            if nbr:
                nb = {nbr.group(1): nbr.group(3)}
            else:
                nb = {"Inconnu": "1"}
            qte_l.append(nb)
    return qte_l


def details(tags: List[str]) -> List[Dict[str, str]]:
    """Extraction des détails par espèce."""
    det_l = []

    for t in tags:
        if DET_PAT.match(t):
            # Le tag commence par Détails et contient une chaîne
            # indiquant l'indice de l'espèce et ses détails
            détails = re.search(DETAILS_PAT, t.split("|")[-1])
            if détails:
                détail = {détails.group(1): détails.group(3)}
            else:
                détail = {"Inconnu": ""}
            det_l.append(détail)
    return det_l


def corrige(sp: str) -> str:
    """Correction des cas particuliers des espèces au format OCA."""
    corresp = {"Canidés": "CANIDE SP"}
    if sp in corresp:
        renom = corresp[sp]
    else:
        renom = sp
    return renom


@main.command()
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

    fichiers = rep_origine.glob("*.*")
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


@main.command()
@click.option(
    "--input_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des fichiers AVI à convertir",
)
@click.option("--dry_run", is_flag=True, help="Mode test, sans renommage des fichiers.")
@click.pass_context
def géotagger(ctx: click.Context, input_dir: str, dry_run: bool) -> None:
    """Géotagging des photos et vidéos."""
    rep_origine = Path(input_dir).expanduser()
    if not rep_origine.is_dir():
        logger.fatal(f"Le répertoire d'entrée {input_dir} n'est pas valide")
        raise FileNotFoundError
    logger.info(f"Géotagging des photos et vidéos dans {rep_origine}")

    with open(rep_origine / "information.yaml") as info:
        infos = yaml.safe_load(info)
        latitude = infos["caméra"]["latitude"]
        longitude = infos["caméra"]["longitude"]
        altitude = infos["caméra"]["altitude"]
        logger.debug(f"Localisation : {latitude}, {longitude}, {altitude}")

    fichiers = rep_origine.glob("*.*")
    with exiftool.ExifToolHelper() as et:
        for f in fichiers:
            # Liste des fichiers triés par date de prise de vue
            if re.match(MEDIA_PAT, f.suffix):
                fx = Path(str(f) + ".xmp")
                if fx.is_file():
                    logger.debug(f"Géotagging de {f.name}")
                    if not dry_run:
                        et.set_tags(
                            fx,
                            {
                                "XMP:GPSLatitude": latitude,
                                "XMP:GPSLongitude": longitude,
                                "XMP:GPSAltitude": altitude,
                            },
                        )
                else:
                    logger.warning(f"Pas de fichier sidecar pour {f.name}")

    # Suppression des xmp_original
    fichiers = rep_origine.glob("*.*")
    for f in fichiers:
        # Liste des fichiers triés par date de prise de vue
        if re.match(XMPO_PAT, f.suffix):
            logger.debug(f"Suppression de {f.name}")
            f.unlink(missing_ok=True)


@main.command()
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
@click.option(
    "--increment", is_flag=True, help="Copie incrémentale des nouveaux médias."
)
@click.pass_context
def copier(  # noqa: max-complexity=13
    ctx: click.Context, from_dir: str, to_dir: str, increment: bool, dry_run: bool
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
                dts = dt.split("/")
                return "".join((dts[2], dts[1], dts[0]))

            relevés = [date_oca(dt) for dt in infos["relevé"]]

            dernier = "00000000"
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
                "Le fichier information.yaml contient le tag export_oca à False, pas de copie"
            )

    type_cp = "incrémentale" if increment else "complète"
    logger.info(f"Copie {type_cp}" + f" depuis {dernier}")
    with exiftool.ExifToolHelper() as et:
        # Détermination du nom OCA
        seq = 1
        fichiers = rep_origine.glob("*.*")
        for f in fichiers:
            if re.match(MEDIA_PAT, f.suffix):
                date_prise = f.name.split("_")[1]
                if not increment or date_prise > dernier:
                    logger.debug(f"Copie/renommage de {f.name}, daté {date_prise}")
                    # Recherche des tags de classification
                    for d in et.get_tags(f, tags=["HierarchicalSubject"]):
                        if "XMP:HierarchicalSubject" in d:
                            tags = d["XMP:HierarchicalSubject"]
                        else:
                            tags = []
                        if not isinstance(tags, list):
                            tags = [tags]

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
                            subprocess.run(  # noqa: S603
                                [
                                    "/home/daniel/.local/bin/poetry",
                                    "run",
                                    "deface",
                                    "--keep-metadata",
                                    "--execution-provider",
                                    "CPUExecutionProvider",
                                    # "TensorrtExecutionProvider",
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
                            for dt in relevés:
                                ssrep = dt
                                if date_prise <= dt:
                                    break
                            logger.info(
                                f"Photo/Vidéo {fi.name}, à copier vers : {ssrep}/{dest}"
                            )

                            # Copie des fichiers
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
                                gx.with_suffix(".xmp_original").unlink(missing_ok=True)
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
                                gx.with_suffix(".mp4_original").unlink(missing_ok=True)


@main.command()
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
    synthèse.Taille = synthèse.Taille.apply(lambda t: humanize.naturalsize(t, True))
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


@main.command()
@click.option(
    "--input_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des fichiers AVI à convertir",
)
@click.pass_context
def analyser(ctx: click.Context, input_dir: str) -> None:  # noqa: max-complexity=13
    """Analyse les photos et vidéos transmises."""
    rep_origine = Path(input_dir).expanduser()
    if not rep_origine.is_dir():
        logger.fatal(f"Le répertoire d'entrée {input_dir} n'est pas valide")
        raise FileNotFoundError
    logger.info(f"Bilan des photos et vidéos transférées dans {rep_origine}")

    espèces = pd.DataFrame(columns=("Espèce", "Occurrences", "Individus"))
    espèces.set_index(["Espèce"], inplace=True)

    # Parcours des répértoires destination pour chercher les photos et vidéos
    for chemin, _dirs, fichiers in rep_origine.walk(on_error=print):
        logger.debug(f"Compte dans le répertoire de destination {chemin}")
        # Comptage des espèces
        for f in fichiers:
            fp = Path(chemin / f)
            if re.match(MEDIA_PAT, fp.suffix):
                logger.debug(f"Analyse du fichier {fp}")

                spq = OCA_PAT.match(f)

                if spq is not None:
                    sp = spq.group(1)
                    nb = int(spq.group(2))

                    if sp in espèces.index:
                        espèces.loc[sp, "Occurrences"] += 1  # type: ignore
                        espèces.loc[sp, "Individus"] += nb  # type: ignore
                    else:
                        espèces.loc[sp, "Occurrences"] = 1
                        espèces.loc[sp, "Individus"] = nb

    console = Console()
    table_e = Table(title="Synthèse espèces OCA")
    espèces.sort_values("Occurrences", inplace=True, ascending=False)
    console.print(df_to_table(espèces, table_e))


def _commune(tags: List[str]) -> str:
    """Extraction du nom de commune."""
    for t in tags:
        spr = COMMUNE_PAT.match(t)
        if spr:
            # Le tag commence par Continent... et se termine par la commune
            com = spr.group(1)

    return com


def _dégrader(x: float, y: float, grain: str) -> tuple[List[float], List[float]]:
    """Dégradation des coordonnées géographiques."""
    logger.debug(f"Avant dégradation de {x}, {y} en {grain}")
    if grain == "M1":
        # Dégradation à 1 km
        x = math.floor(x / 1000) * 1000 + 500.0
        y = math.floor(y / 1000) * 1000 + 500.0
    elif grain == "M2":
        # Dégradation à 2 km
        x = math.floor(x / 2000) * 2000 + 1000.0
        y = math.floor(y / 2000) * 2000 + 1000.0

    elif grain == "M5":
        # Dégradation à 5 km
        x = math.floor(x / 5000) * 5000 + 2500.0
        y = math.floor(y / 5000) * 5000 + 2500.0

    elif grain == "M10":
        # Dégradation à 10 km
        x = math.floor(x / 10000) * 10000 + 5000.0
        y = math.floor(y / 10000) * 10000 + 5000.0

    else:
        # Pas de dégradation
        logger.error(f"Pas de dégradation pour {grain}")
    logger.debug(f"Après dégradation de {[x]}, {[y]} en {grain}")
    return ([x], [y])


@main.command()
@click.option(
    "--input_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des fichiers à traiter",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Fichier CSV d'export, pour la commande exporter uniquement",
)
@click.option(
    "--remplace", is_flag=True, help="Remplace le fichier d'export s'il existe déjà."
)
@click.pass_context
def exporter(  # noqa: max-complexity=13
    ctx: click.Context, input_dir: str, output: str, remplace: bool
) -> None:
    """Export des espèces depuis les répertoires d'origine."""
    fic_export = Path(output)
    if fic_export.exists() and not remplace:
        logger.fatal(f"Le fichier d'export {fic_export} existe déjà")
        raise FileExistsError
    if not Path(input_dir).expanduser().is_dir():
        logger.fatal(f"Le répertoire d'entrée {input_dir} n'est pas valide")
        raise FileNotFoundError
    input_dirp = Path(input_dir).expanduser()
    logger.info(f"Export des espèces depuis {input_dir} vers {fic_export}")

    observations = []
    obs_table = pd.DataFrame(
        columns=(
            "Commune",
            "Date",
            "Espèce",
            "Quantité",
            "Détails",
            "X_L93",
            "Y_L93",
            "Altitude",
            "Géometrie",
        )
    )
    # Reprojection en Lambert 93
    from_crs = pyproj.CRS("EPSG:4326")
    to_crs = pyproj.CRS("EPSG:2154")
    to_l93 = pyproj.Transformer.from_crs(from_crs, to_crs, always_xy=True)

    # Parcours des répértoires pour chercher les médias
    for chemin, _dirs, fichiers in input_dirp.walk(on_error=print):
        logger.info(f"Export depuis le répertoire {chemin}")
        with exiftool.ExifToolHelper() as et:
            # Analyse des fichiers
            for f in fichiers:
                fp = Path(chemin / f)
                if re.match(MEDIA_PAT, fp.suffix):
                    logger.debug(f"Analyse du fichier {fp}")
                    # Extraction de la date de prise de vue
                    for d in et.get_tags(
                        fp,
                        tags=["CreateDate", "DateTimeOriginal", "MediaCreateDate"],
                    ):
                        logger.debug(d)
                        # Recherche de la date de prise de vue
                        if "EXIF:DateTimeOriginal" in d:
                            dc = d["EXIF:DateTimeOriginal"]
                        elif "XMP:DateTimeOriginal" in d:
                            dc = d["XMP:DateTimeOriginal"]
                        elif "XMP:CreateDate" in d:
                            dc = d["XMP:CreateDate"]
                        elif "QuickTime:MediaCreateDate" in d:
                            dc = d["QuickTime:MediaCreateDate"]
                        else:
                            logger.error("Pas de date de prise de vue définie")
                    # Rechercher les tags de classification
                    for d in et.get_tags(fp, tags=["HierarchicalSubject"]):
                        if "XMP:HierarchicalSubject" in d:
                            tags = d["XMP:HierarchicalSubject"]
                        else:
                            tags = []
                        if not isinstance(tags, list):
                            tags = [tags]
                    # Rechercher les tags de localisation
                    for d in et.get_tags(
                        fp,
                        tags=[
                            "XMP:GPSLatitude",
                            "XMP:GPSLongitude",
                            "XMP:GPSAltitude",
                        ],
                    ):
                        if (
                            ("XMP:GPSLatitude" in d)
                            and ("XMP:GPSLongitude" in d)
                            and ("XMP:GPSAltitude" in d)
                        ):
                            latitude = float(d["XMP:GPSLatitude"])
                            longitude = float(d["XMP:GPSLongitude"])
                            altitude = float(d["XMP:GPSAltitude"])
                        else:
                            logger.error(
                                f"Pas de coordonnées géographiques définies dans {fp.name}"
                            )
                    # Vérification des tags
                    logger.debug(tags)
                    sp = noms(tags)
                    if len(sp) == 0:
                        logger.error(f"Pas d'espèce définie dans {fp.name}")
                    nb = qte(tags)
                    det = details(tags)
                    logger.debug(f"tags : {sp}/{nb}/{det}")
                    # Parcours des espèces pour exporter vers autant de lignes
                    for s in sp:
                        if s in NON_FAUNE:
                            # Espèce humaine
                            logger.info(f"Espèce humaine {s} non exportée")
                        else:
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
                            com = _commune(tags)
                            coord = shapely.transform(
                                Point(latitude, longitude),
                                to_l93.transform,
                                interleaved=False,
                            )

                            if s in sp_sensibles:
                                # Espèce sensible
                                grain = sp_sensibles[s]["Grain"]
                                logger.info(f"Espèce sensible {s} dégradée à {grain}")
                                coord = shapely.transform(
                                    coord,
                                    lambda x, y, grain=grain: _dégrader(x, y, grain),
                                    interleaved=False,
                                )

                            logger.debug(f"{com};{dc};{s};{qt};{de};{coord};{altitude}")
                            observations.append(
                                {
                                    "Commune": com,
                                    "Date": dc,
                                    "Espèce": s,
                                    "Quantité": qt,
                                    "Détails": de,
                                    "X_L93": coord.x,
                                    "Y_L93": coord.y,
                                    "Altitude": altitude,
                                    "Géometrie": coord,
                                }
                            )

    obs_table = pd.DataFrame(observations)
    obs_geotable = gpd.GeoDataFrame(
        obs_table,
        geometry="Géometrie",
        crs="EPSG:2154",
    )
    # obs_geotable = obs_geotable.drop(columns=["Longitude", "Latitude"])
    # obs_geotable = obs_geotable.to_crs("EPSG:2154")
    # obs_geotable["geometry_wkt"] = obs_geotable["geometry"].apply(lambda geom: geom.wkt)
    # obs_geotable = obs_geotable.drop(columns=["geometry"])
    obs_geotable.to_csv(fic_export, sep=";", index=False)
    logger.info(f"Export vers {fic_export} terminé")


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
