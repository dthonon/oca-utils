"""Sphinx configuration."""
project = "Oca Utils"
author = "Daniel Thonon"
copyright = "2023, Daniel Thonon"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_click",
    "myst_parser",
]
autodoc_typehints = "description"
html_theme = "furo"
