"""
Fonctions utilitairess pour OCA Utils.

Fonctions utilitairess pour OCA Utils, notamment :
  - la conversion des DataFrame en tableaux Rich,
  - l'extraction des noms, quantités et détails des espèces,
  - la correction des noms d'espèces au format OCA.
"""

import re
from typing import Dict
from typing import List
from typing import Optional

import pandas as pd
from rich.table import Table

from oca_utils.constantes import DET_PAT
from oca_utils.constantes import DETAILS_PAT
from oca_utils.constantes import ESPECE_PAT
from oca_utils.constantes import NATURE_PAT
from oca_utils.constantes import NB_PAT
from oca_utils.constantes import PLACE_PAT
from oca_utils.constantes import QTE_PAT


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


def locs(tags: List[str]) -> List[str]:
    """Extraction des noms de localisations."""
    locs_l = []

    for t in tags:
        if PLACE_PAT.match(t):
            # Le tag commence par Continents et pays et se termine par la localisation
            locs_l.append(t.split("|")[-1])
    return locs_l


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
