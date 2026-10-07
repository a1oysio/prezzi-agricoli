"""Percorsi e costanti condivisi dalla pipeline."""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class Exchange:
    code: str
    name: str
    slug: str
    source_url: str
    chamber: str = ""        # chi pubblica il listino, per il pie' di pagina del sito
    notice: str = ""         # avvertenza da mostrare accanto ai dati di questa borsa
    group_cut: str = ""      # taglia il titolo di sezione a questo separatore per il filtro "comparto"


# L'ordine e' quello del selettore del sito; il primo e' la borsa mostrata
# all'apertura.
EXCHANGES = {
    "verona": Exchange(
        EXCHANGE_CODE, EXCHANGE_NAME, EXCHANGE_SLUG, SOURCE_URL,
        chamber="Camera di Commercio di Verona",
    ),
    "bologna": Exchange(
        "BO", "Borsa Merci di Bologna", "bologna",
        "https://www.bo.camcom.gov.it/borsa-merci",
        chamber="Camera di Commercio di Bologna",
        notice=(
            "Fonte: listini PDF. La Camera cambia le specifiche dei prodotti ogni "
            "anno (ad esempio \"p.s. 78/79\" diventa \"79/80\") e per la fonte "
            "diventa un prodotto nuovo: le serie si interrompono dove cambia la "
            "descrizione. Sono unite automaticamente solo per i gradi commerciali "
            "del frumento."
        ),
        group_cut=" - ",
    ),
}


def dataset_dir(slug: str = EXCHANGE_SLUG) -> Path:
    return DATASET_DIR / slug


def archive_dir(slug: str = EXCHANGE_SLUG) -> Path:
    return ROOT / "data" / slug


def prices_dir() -> Path:
    return dataset_dir() / "prices"
