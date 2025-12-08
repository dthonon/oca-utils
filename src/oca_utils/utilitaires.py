"""Docstring pour oca_utils.utilitaires"""

import re
from typing import Dict, List
from oca_utils.constantes import (
    NATURE_PAT,
    ESPECE_PAT,
    QTE_PAT,
    NB_PAT,
    DET_PAT,
    DETAILS_PAT,
)


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
