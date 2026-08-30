"""Percorsi e costanti condivisi dalla pipeline."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATASET_DIR = ROOT / "dataset"          # versionato: la sorgente di verita'
SITE_DIR = ROOT / "site"                # versionato: HTML, CSS, JS
SITE_API_DIR = SITE_DIR / "api"         # generato a ogni deploy, non versionato
ARCHIVE_DIR = ROOT / "data" / "verona"  # XML grezzi, non versionati

EXCHANGE_CODE = "VR"
EXCHANGE_NAME = "Borsa Merci di Verona"
EXCHANGE_SLUG = "verona"
SOURCE_URL = "https://www.portaleprezziverona.it/camcom-verona/it/borsa-merci"


def dataset_dir() -> Path:
    return DATASET_DIR / EXCHANGE_SLUG


def prices_dir() -> Path:
    return dataset_dir() / "prices"
