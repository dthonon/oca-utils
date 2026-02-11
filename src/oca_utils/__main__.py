"""Command-line interface."""

import datetime
import logging
import os
import re
import secrets

import uuid
from pathlib import Path

import click
import exiftool  # type: ignore
import pandas as pd
import yaml
from ffmpeg import FFmpeg  # type: ignore
from ffmpeg import Progress
from rich.console import Console
from rich.table import Table
from unidecode import unidecode

from . import comparer
from . import exporter
from . import vérifier
from . import copier
from .constantes import AVI_PAT
from .constantes import CORRECT_PAT
from .constantes import MEDIA_PAT
from .constantes import OCA_PAT
from .constantes import XMPO_PAT

from .utilitaires import df_to_table


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.version_option()
@click.group()
@click.option("--trace", is_flag=True, help="Traces détaillées")
@click.option("--essai", is_flag=True, help="Mode essai, sans action effectuée")
@click.pass_context
def main(
    ctx: click.Context,
    trace: bool,
    essai: bool,
) -> None:
    """OCA Utils."""
    logging.info("Transfert des vidéos au format OCA")
    # ensure that ctx.obj exists and is a dict
    ctx.ensure_object(dict)

    if trace:
        logger.setLevel(logging.DEBUG)

    ctx.obj["ESSAI"] = essai


main.add_command(exporter.exporter)
main.add_command(vérifier.vérifier)
main.add_command(comparer.comparer)
main.add_command(copier.copier)


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

                    try:
                        # Conversion AVI vers MP4
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
                    except Exception as e:
                        logger.error(f"Erreur de conversion de {f.name} : {e}")


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
                dc = ""
                try:
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
                        s_fichiers.append((dc, f))
                except Exception as e:
                    logger.error(f"Erreur d'extraction de la date de {f.name} : {e}")

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
    """Renomme les photos et vidéos selon leur date de prise de vue."""
    rep_origine = Path(input_dir).expanduser()
    if not rep_origine.is_dir():
        logger.fatal(f"Le répertoire d'entrée {input_dir} n'est pas valide")
        raise FileNotFoundError
    logger.info(f"Renommage des photos et vidéos dans {rep_origine}")

    # Renommage temporaire pour éviter les écrasements de fichier
    _renommer_temp(rep_origine, dry_run, force)

    # Renommage final
    _renommer_seq_date(rep_origine, dry_run)


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

    with open(rep_origine / "../information.yaml") as info:
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
    "--input_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire racine des fichiers au format OCA à analyser",
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


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
