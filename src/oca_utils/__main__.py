"""Command-line interface."""

import datetime
import logging
import os
import secrets
import re

# import shutil
import uuid
from pathlib import Path
from typing import Dict
from typing import List

import click
import exiftool  # type: ignore

# import xmltodict
from ffmpeg import FFmpeg  # type: ignore
from ffmpeg import Progress
from unidecode import unidecode


media_pat = r"\.(AVI|avi|MP4|mp4|JPG|jpg)"
video_pat = r"\.(AVI|avi|MP4|mp4)"
correct_pat = r"IMG_\d{8}_\d{6}_\d{2}\..*"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.version_option()
@click.group()
@click.option("--trace", default=False, help="Traces détaillées")
@click.option("--essai", default=False, help="Mode essai, sans action effectuée")
@click.option(
    "--origine",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
    help="Répertoire des fichiers à traiter",
)
@click.option(
    "--destination",
    required=False,
    default="~/tmp",
    type=click.Path(exists=False, dir_okay=True, writable=True),
    help="Répertoire de destination des fichiers, pour la commande copier uniquement",
)
@click.pass_context
def main(
    ctx: click.Context,
    trace: bool,
    essai: bool,
    origine: str,
    destination: str,
) -> None:
    """OCA Utils."""
    logging.info("Transfert des vidéos au format OCA")
    # ensure that ctx.obj exists and is a dict
    ctx.ensure_object(dict)

    if trace:
        logger.setLevel(logging.DEBUG)

    if not Path(origine).expanduser().is_dir():
        logger.fatal(f"Le répertoire d'entrée {origine} n'est pas valide")
        raise FileNotFoundError
    if not Path(destination).expanduser().is_dir():
        logger.fatal(f"Le répertoire de sortie {destination} n'est pas valide")
        raise FileNotFoundError
    ctx.obj["ESSAI"] = essai
    ctx.obj["ORIGINE"] = origine
    ctx.obj["DESTINATION"] = destination


@main.command()
@click.pass_context
def convertir(ctx: click.Context) -> None:
    """Convertit les vidéos AVI en mp4."""
    in_path = Path(ctx.obj["ORIGINE"])
    logger.info(f"Conversion des vidéos depuis {in_path}")
    out_path = Path(ctx.obj["DESTINATION"])
    logger.info(f"Conversion des vidéos vers {out_path}")
    out_path.mkdir(exist_ok=True)

    with exiftool.ExifToolHelper() as et:
        for f in [f for f in in_path.glob("*.*")]:
            if re.match(video_pat, f.suffix):
                g = out_path / f"{f.stem}_c.mp4"
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
                    # print(ffmpeg.arguments)

                    # Execute conversion
                    @ffmpeg.on("progress")  # type:ignore
                    def on_progress(progress: Progress) -> None:
                        logger.debug(progress)

                    ffmpeg.execute()

                    # Retour à la date originelle
                    os.utime(g, (mtime, mtime))

                    # Copie des tags EXIF
                    fx = Path(str(f) + ".xmp")
                    gx = Path(str(g) + ".xmp")
                    if fx.exists():
                        et.execute("-Tagsfromfile", str(fx), str(gx))
                        os.utime(gx, (mtime, mtime))


def _renommer_temp(in_path: Path, ctx: click.Context) -> None:
    # Renommer en UUID, si le fichier n'est pas déjà bien nommé
    with exiftool.ExifToolHelper() as et:
        # Renommage temporaire pour éviter les écrasements
        files = in_path.glob("*")
        for f in files:
            if re.match(media_pat, f.suffix) and not re.match(correct_pat, f.name):
                mtime = f.stat().st_mtime
                g = in_path / (uuid.uuid4().hex + f.suffix.lower())
                logger.info(f"Photo/Vidéo {f.name} renommée en : {g.name}")
                if not ctx.obj["ESSAI"]:
                    f.rename(g)
                    # Retour à la date originelle
                    os.utime(g, (mtime, mtime))

                    # Copie des tags EXIF vers le nouveau fichier
                    fx = Path(str(f) + ".xmp")
                    gx = Path(str(g) + ".xmp")
                    if fx.exists():
                        et.execute("-Tagsfromfile", str(fx), str(gx))
                        fx.unlink()
                        os.utime(gx, (mtime, mtime))

    return None


def _renommer_seq_date(  # noqa: max-complexity=13
    in_path: Path, ctx: click.Context
) -> None:
    s_files = []
    files = in_path.glob("*.*")
    with exiftool.ExifToolHelper() as et:
        for f in files:
            # Liste des fichiers triés par date de prise de vue
            if re.match(media_pat, f.suffix) and not re.match(correct_pat, f.name):
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
                    s_files.append((dc, f))

        for dc, f in sorted(s_files, key=lambda dcf: dcf[0]):
            # Création du préfixe IMG_nnnn
            racine = "IMG_"
            # Formattage de la date
            fdate = dc.replace(":", "").replace(" ", "_")
            dest = unidecode(
                racine + fdate + "_" + f"{secrets.randbelow(10):02}" + f.suffix
            )
            logger.info(f"Photo/Vidéo {f.name}, datée {dc} à renommée en : {dest}")
            if not ctx.obj["ESSAI"]:
                mtime = f.stat().st_mtime
                g = in_path / dest
                f.rename(g)
                # Retour à la date originelle
                os.utime(g, (mtime, mtime))

                # Copie des tags EXIF vers le nouveau fichier
                fx = Path(str(f) + ".xmp")
                gx = Path(str(g) + ".xmp")
                if fx.exists():
                    et.execute("-Tagsfromfile", str(fx), str(gx))
                    fx.unlink()
                    os.utime(gx, (mtime, mtime))

    return None


@main.command()
@click.pass_context
def renommer(ctx: click.Context) -> None:
    """Renomme au format personnel les photos et vidéos."""
    in_path = Path(ctx.obj["ORIGINE"])
    logger.info(f"Renommage des photos et vidéos depuis {in_path}")

    # Renommage temporaire pour éviter les écrasements de fichier
    _renommer_temp(in_path, ctx)

    # Renommage final
    _renommer_seq_date(in_path, ctx)


def noms(tags: List[str]) -> List[str]:
    """Extraction des noms d'espèces."""
    noms_l = []
    nature_re = re.compile(r"Nature.*")
    sp_re = re.compile(r"(\w|\s|')+ {")
    for t in tags:
        if nature_re.match(t):
            # Le tag commence par Nature et se termine par l'espèce
            spr = re.search(sp_re, t.split("|")[-1])
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
            nbr = re.search(nb_re, t.split("|")[-1])
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
            détails = re.search(détails_re, t.split("|")[-1])
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
@click.pass_context
def copier(ctx: click.Context) -> None:
    """Copie et renomme au format OCA les photos et vidéos."""
    in_path = Path(ctx.obj["ORIGINE"])
    logger.info(f"Renommage des photos et vidéos depuis {in_path}")
    out_path = Path(ctx.obj["DESTINATION"])
    logger.info(f"Renommage des photos et vidéos vers {out_path}")
    out_path.mkdir(exist_ok=True)

    # # Extraction de la date de création du média
    # video_pat = r"\.(AVI|avi|MP4|mp4|JPG|jpg)"
    # with exiftool.ExifToolHelper() as et:
    #     # Renommage
    #     files = in_path.glob("*.*")
    #     seq = 1  # Numéro de séquence des fichiers
    #     for f in files:
    #         if re.match(video_pat, f.suffix):
    #             # Recherche des tags de classification
    #             for d in et.get_tags(f, tags=["HierarchicalSubject"]):
    #                 if "XMP:HierarchicalSubject" in d:
    #                     tags = d["XMP:HierarchicalSubject"]
    #                 else:
    #                     tags = []
    #                 if not isinstance(tags, list):
    #                     tags = [tags]

    #             # print(tags)
    #             sp = noms(tags)
    #             nb = qte(tags)
    #             det = details(tags)
    #             # logger.info(f"{f.name} : {sp}/{nb}/{det}")

    #             for s in sp:
    #                 qt = 1
    #                 for n in nb:
    #                     if s in n:
    #                         qt = int(n[s])
    #                     else:
    #                         qt = max(1, qt)
    #             # Création du préfixe IMG_nnnn
    #             racine = f"IMG_{seq:04}"
    #             seq += 1
    #             de = ""
    #             for d in det:
    #                 if s in d:
    #                     de = d[s]
    #             if len(de) == 0:
    #                 # Pas de détails
    #                 dest = racine + "_" + corrige(s) + "_" + str(qt) + f.suffix
    #             else:
    #                 # Avec détails
    #                 dest = (
    #                     racine + "_" + corrige(s) + "_" + str(qt)
    #                       + "_" + de + f.suffix
    #                 )
    #             dest = unidecode(dest)

    #             logger.info(
    #               f"Photo/Vidéo {f.name}, datée {dc} à renommer en : {dest}")
    #             mtime = f.stat().st_mtime
    #             g = out_path / dest
    #             f.rename(g)
    #             # Retour à la date originelle
    #             os.utime(g, (mtime, mtime))

    #             # Copie des tags EXIF vers le nouveau fichier
    #             fx = Path(str(f) + ".xmp")
    #             gx = Path(str(g) + ".xmp")
    #             if fx.exists():
    #                 et.execute("-Tagsfromfile", str(fx), str(gx))
    #                 fx.unlink()
    #                 os.utime(gx, (mtime, mtime))


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
