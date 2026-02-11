"""
Listing CSV des observations d'espèces depuis les fichiers média dans un répertoire.

Module d'exportation des observations d'espèces depuis les fichiers média
dans un répertoire vers un fichier CSV.
"""

import logging
import math
import re
from pathlib import Path
from typing import List

import click
import exiftool  # type: ignore
import geopandas as gpd
import pandas as pd
import pyproj
import shapely
from shapely.geometry import Point

from oca_utils.constantes import COMMUNE_PAT
from oca_utils.constantes import MEDIA_PAT
from oca_utils.constantes import NON_FAUNE
from oca_utils.sp_sensible import sp_sensibles
from oca_utils.utilitaires import details
from oca_utils.utilitaires import noms
from oca_utils.utilitaires import qte


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def _commune(tags: List[str]) -> str:
    """Extraction du nom de commune."""
    com = "Inconnu"
    for t in tags:
        spr = COMMUNE_PAT.match(t)
        if spr:
            # Le tag commence par Continent... et se termine par la commune
            com = spr.group(1)
            break

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


@click.command()
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
    dc = "0000:00:00 00:00:00"
    tags = []
    latitude = longitude = altitude = 0.0
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
                            # if not isinstance(tags, list):
                            #     tags = [tags]
                            break

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
                            coord = shapely.transform(  # type: ignore
                                Point(latitude, longitude),
                                to_l93.transform,  # type: ignore
                                interleaved=False,
                            )

                            if s in sp_sensibles:
                                # Espèce sensible
                                grain = sp_sensibles[s]["Grain"]
                                logger.info(f"Espèce sensible {s} dégradée à {grain}")
                                coord = shapely.transform(  # type: ignore
                                    coord,
                                    lambda x, y, grain=grain: _dégrader(x, y, grain),  # type: ignore
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
