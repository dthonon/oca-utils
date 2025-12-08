"""
Docstring pour oca_utils.constantes
"""

import re

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
