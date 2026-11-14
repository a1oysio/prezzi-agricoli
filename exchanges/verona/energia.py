"""Prodotti petroliferi della Camera di Commercio di Verona: indice, download, lettura.

Rilevazione quindicinale (il 15 e a fine mese) di gasolio da riscaldamento, da
autotrazione e agricolo, olio combustibile e GPL, sullo stesso portale della
borsa merci.  Gli XML hanno la forma di quelli della borsa, ma ogni prodotto
porta quattro valori invece di un minimo e un massimo: prezzo netto, prezzo con
accisa, aliquota IVA e prezzo al consumo.

La numerazione e' condivisa con la borsa merci: lo stesso numero su
``borsa-merci/`` e' la media quindicinale, qui il listino dei petroliferi.  I
numeri si prendono quindi dall'indice della pagina, non contando in avanti, e i
file finiscono in un archivio a parte (``data/verona-energia``).

Non tocca i quattro file copiati da agx-scraper (vedi exchanges/__init__.py).

    python -m exchanges.verona.energia --dest data/verona-energia   # tutto l'archivio
"""
from __future__ import annotations

import argparse
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Optional

from exchanges.verona.processors import (
    MONTHS, _localname, _norm_month, _parse_number, _root_nome, parse_average_date,
)

PORTAL = "https://www.portaleprezziverona.it/camcom-verona/it/prodotti-petroliferi"
INDEX_URL = PORTAL
XML_URL = PORTAL + "/rilevazione/download/xml/{num}"
_HEADERS = {"User-Agent": "prezzi-agricoli/1.0 (+https://github.com/a1oysio/prezzi-agricoli)"}

# I quattro campi di ogni prodotto, nell'ordine delle colonne del CSV.
FIELDS = ("prezzoeuro", "prezzoconaccisa", "aliquotaiva", "prezzoalconsumo")

_RE_NUM = re.compile(r"prodotti-petroliferi/rilevazione/download/(?:xml|pdf)/(\d+)")
_RE_BOTTLE = re.compile(r"\bda\s+\d+\s*kg\b", re.IGNORECASE)
_RE_NO_YEAR = re.compile(r"\bdel\s+(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s*$", re.IGNORECASE)


def list_numbers(timeout: float = 20.0) -> list[int]:
    """I numeri delle rilevazioni pubblicate, in ordine crescente."""
    import requests     # solo per scaricare: il sito legge questo modulo senza dipendenze
    resp = requests.get(INDEX_URL, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    numbers = sorted({int(n) for n in _RE_NUM.findall(resp.text)})
    if not numbers:
        # Un indice senza link e' una pagina cambiata, non un anno senza dati.
        raise ValueError(f"nessuna rilevazione nell'indice {INDEX_URL}: la pagina e' cambiata?")
    return numbers


def fetch(num: int, dest: Path, timeout: float = 20.0) -> Path:
    """Scarica (sempre, sovrascrivendo) l'XML della rilevazione ``num``."""
    import requests
    resp = requests.get(XML_URL.format(num=num), headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{num}.xml"
    out.write_bytes(resp.content)
    return out


def unit_of(source_unit: str, name: str) -> str:
    """Unita' canonica dal campo ``unitadimisura``.

    Il GPL in bombole e' dichiarato "kg" ma il prezzo e' quello della bombola:
    34,91 per "da 10 kg miscela" sono 3,49 euro al chilo.
    """
    u = source_unit.strip().lower()
    if u == "kg" and _RE_BOTTLE.search(name):
        return "EUR/bombola"
    return {"lt": "EUR/L", "kg": "EUR/kg", "mc": "EUR/m3"}.get(u, "unknown")


def _date(root: ET.Element, near: Optional[date]) -> Optional[date]:
    """Data dal titolo.  Se manca l'anno ("RILEVAZIONE N. 17 DEL 15 SETTEMBRE",
    n. 849 del 2021) vale quello che la porta piu' vicino a ``near``, la data
    della rilevazione precedente."""
    iso = parse_average_date(root)
    if iso:
        return date.fromisoformat(iso)
    m = _RE_NO_YEAR.search(_root_nome(root))
    if m is None or near is None:
        return None
    day, month = int(m.group(1)), _norm_month(m.group(2))
    return min((date(y, month, day) for y in (near.year - 1, near.year, near.year + 1)),
               key=lambda d: abs(d - near))


def parse_file(path: Path, near: Optional[date] = None
               ) -> tuple[date, list[tuple[str, str, tuple[str, ...], str, tuple]]]:
    """Data della rilevazione e righe ``(codice, nome, percorso, unita', valori)``.

    ``valori`` segue FIELDS; zero e campi vuoti diventano None.  Una categoria
    senza prodotti (l'olio combustibile dal 2026) non produce righe.  ``near``
    serve solo ai titoli senza anno: vedi ``_date``.
    """
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"XML non valido '{path.name}': {exc}") from exc
    day = _date(root, near)
    if day is None:
        raise ValueError(f"'{path.name}': titolo senza data di rilevazione")

    rows = []

    def walk(node: ET.Element, path_: tuple[str, ...]) -> None:
        for ch in node:
            tag = _localname(ch.tag)
            if tag == "categoria":
                walk(ch, path_ + ((ch.findtext("nome") or "").strip(),))
            elif tag in ("categorie", "prodotti"):
                walk(ch, path_)
            elif tag == "prodotto":
                code = (ch.findtext("id") or "").strip()
                if not code:
                    continue
                name = (ch.findtext("nome") or "").strip()
                values = []
                for f in FIELDS:
                    v = _parse_number(ch.findtext(f) or "")
                    values.append(v if v and v > 0 else None)
                rows.append((code, name, path_, unit_of(ch.findtext("unitadimisura") or "", name),
                             tuple(values)))

    walk(root, ())
    return day, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()
    for i, num in enumerate(list_numbers()):
        if (args.dest / f"{num}.xml").exists():
            continue
        if i:
            time.sleep(args.sleep)
        print(f"  {num}", fetch(num, args.dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
