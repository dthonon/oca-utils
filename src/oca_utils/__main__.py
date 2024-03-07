"""Command-line interface."""

import datetime
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict
from typing import List

import click
import exiftool  # type: ignore
import xmltodict
from ffmpeg import FFmpeg  # type: ignore
from ffmpeg import Progress
from unidecode import unidecode


logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


@click.version_option()
@click.group()
@click.option(
    "--in_dir",
    required=True,
    type=click.Path(exists=True, dir_okay=True, readable=True),
)
@click.option(
    "--out_dir",
    required=True,
    type=click.Path(exists=False, dir_okay=True, writable=True),
)
@click.pass_context
def main(
    ctx: click.Context,
    in_dir: str,
    out_dir: str,
) -> None:
    """OCA Utils."""
    logging.info("Transfert des vidéos au format OCA")
    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)

    if not Path(in_dir).is_dir():
        logging.fatal(f"Le répertoire d'entrée {in_dir} n'est pas valide")
        raise FileNotFoundError
    if not Path(out_dir).is_dir():
        logging.fatal(f"Le répertoire de sortie {out_dir} n'est pas valide")
        raise FileNotFoundError
    ctx.obj["INPUT_DIRECTORY"] = in_dir
    ctx.obj["OUTPUT_DIRECTORY"] = out_dir


@main.command()
@click.pass_context
def convertir(ctx: click.Context) -> None:
    """Convertit les vidéos AVI en mp4."""
    input_directory = ctx.obj["INPUT_DIRECTORY"]
    output_directory = ctx.obj["OUTPUT_DIRECTORY"]

    in_path = Path(input_directory)
    logging.info(f"Conversion des vidéos depuis {in_path}")
    out_path = Path(output_directory)
    logging.info(f"Conversion des vidéos vers {out_path}")
    out_path.mkdir(exist_ok=True)

    video_pat = r"\.(AVI|avi|MP4|mp4)"
    with exiftool.ExifToolHelper() as et:
        for f in [f for f in in_path.glob("*.*")]:
            if re.match(video_pat, f.suffix):
                g = out_path / f"{f.stem}_c.mp4"
                # g = g.with_suffix(".mp4")
                logging.info(f"Conversion de {f.name} en {g.name}")
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
                    logging.debug(progress)

                ffmpeg.execute()

                # Revert to original timestamp
                os.utime(g, (mtime, mtime))

                # Copy EXIF tags
                fx = Path(str(f) + ".xmp")
                gx = Path(str(g) + ".xmp")
                if fx.exists():
                    et.execute("-Tagsfromfile", str(fx), str(gx))


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
def renommer(ctx: click.Context) -> None:
    """Renomme les photos et vidéos au format OCA."""
    input_directory = ctx.obj["INPUT_DIRECTORY"]
    output_directory = ctx.obj["OUTPUT_DIRECTORY"]

    in_path = Path(input_directory)
    logging.info(f"Renommage des photos et vidéos depuis {in_path}")
    out_path = Path(output_directory)
    logging.info(f"Renommage des photos et vidéos vers {out_path}")
    out_path.mkdir(exist_ok=True)

    # Extraction de la date de création du média
    video_pat = r"\.(AVI|avi|MP4|mp4)"
    s_files = []
    with exiftool.ExifToolHelper() as et:
        files = in_path.glob("*.*")
        for f in files:
            if re.match(video_pat, f.suffix):
                # Recherche de la date de prise de vue
                for d in et.get_tags(f, tags=["DateTimeOriginal"]):
                    dc = d["XMP:DateTimeOriginal"]
                    s_files.append((dc, f))
        # Renommage
        seq = 1
        for dc, f in sorted(s_files, key=lambda dcf: dcf[0]):
            # Création du préfixe IMG_nnnn
            racine = f"IMG_{seq:04}"
            seq += 1
            de = ""
            s = "Inconnu"
            qt = "1"
            # for d in det:
            #     if s in d:
            #         de = d[s]
            if len(de) == 0:
                # Pas de détails
                dest = racine + "_" + corrige(s) + "_" + str(qt) + ".mp4"
            else:
                # Avec détails
                dest = racine + "_" + corrige(s) + "_" + str(qt) + "_" + de + ".mp4"
            dest = unidecode(dest)
            if input_directory == output_directory:
                logging.info(f"Photo/Vidéo {f.name}, datée {dc} à renommer en : {dest}")
                f.rename(out_path / dest)
                sc = f.with_suffix(f.suffix + ".xmp")
                if sc.is_file():
                    dsc = dest + ".xmp"
                    logging.info(f"Sidecar {sc.name} à renommer en : {dsc}")
                    sc.rename(out_path / dsc)
            else:
                logging.info(f"Photo/Vidéo {f.name} à copier vers : {dest}")
                shutil.copy(f, dest)
                sc = f.with_suffix(f.suffix + ".xmp")
                if sc.is_file():
                    dsc = dest + ".xmp"
                    logging.info(f"Sidecar {sc.name} à renommer en : {dsc}")
                    shutil.copy(sc, dsc)

    # with open(f) as fd:
    #     sidecar = xmltodict.parse(fd.read(), process_namespaces=False)
    # tags = sidecar["x:xmpmeta"]["rdf:RDF"]["rdf:Description"]["digiKam:TagsList"]
    # tags = tags["rdf:Seq"]["rdf:li"]
    # sp = noms(tags)
    # nb = qte(tags)
    # det = details(tags)
    # for s in sp:
    #     qt = 1
    #     for n in nb:
    #         if s in n:
    #             qt = int(n[s])
    #         else:
    #             qt = max(1, qt)


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
