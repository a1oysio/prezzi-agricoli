"""Scarica i listini settimanali PDF della Borsa Merci di Bologna.

La Camera di Commercio non numera i file in modo prevedibile (``n.38_ 1 ottobre_2026.pdf``,
``n. 6 - 13 febbraio 2020.pdf``, ``Listino del 21 agosto 2025.pdf``): l'elenco
si ricava dalle due pagine che li raccolgono, non si indovina.

  * pagina corrente   -- i listini dell'anno in corso;
  * pagina archivio   -- tutti quelli degli anni precedenti, dal 2012.
"""
from __future__ import annotations

import html
import re
import time
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote, unquote, urljoin

import requests

BASE = "https://www.bo.camcom.gov.it"
CURRENT_PAGE = BASE + "/borsa-merci/listino-settimanale-dei-prezzi-rilevati-il-giovedì"
ARCHIVE_PAGE = BASE + "/borsa-merci/archivio-anni-precedenti"

_HEADERS = {
    "User-Agent": "prezzi-agricoli/1.0 (+https://github.com/a1oysio/prezzi-agricoli)",
}

_HREF_PDF = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)
_WEEKLY_DIR = "listino-dei-prezzi-settimanali/"


def _list_page(url: str, session: requests.Session, timeout: float) -> list[str]:
    resp = session.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    out = []
    for href in _HREF_PDF.findall(resp.text):
        href = unquote(html.unescape(href))
        # Solo i settimanali: le pagine ospitano anche il listino CUN del grano
        # duro, i moduli per il deposito dei listini e le sintesi mensili.
        if _WEEKLY_DIR not in href or "listini_cun" in href:
            continue
        out.append(urljoin(BASE, href))
    return out


def list_issues(session: Optional[requests.Session] = None,
                timeout: float = 30.0) -> list[str]:
    """URL di tutti i listini settimanali pubblicati, senza doppioni."""
    session = session or requests.Session()
    seen: dict[str, None] = {}
    for page in (ARCHIVE_PAGE, CURRENT_PAGE):
        for url in _list_page(page, session, timeout):
            seen.setdefault(url)
    return sorted(seen)


def local_name(url: str) -> str:
    """Nome file locale univoco per un URL: anno + nome originale."""
    tail = url.split(_WEEKLY_DIR, 1)[1]
    return re.sub(r"[^\w.\- ]+", "_", tail.replace("/", "__")).strip()


def fetch_one(url: str, dest: Path, overwrite: bool = False,
              session: Optional[requests.Session] = None,
              timeout: float = 40.0) -> tuple[int, Optional[Path]]:
    """Scarica un listino.  Ritorna (stato http, percorso | None); 0 = errore di rete."""
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / local_name(url)
    if out.exists() and not overwrite:
        return 200, out
    session = session or requests.Session()
    try:
        resp = session.get(quote(url, safe=":/%"), headers=_HEADERS, timeout=timeout)
    except requests.RequestException:
        return 0, None
    if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
        return resp.status_code, None
    out.write_bytes(resp.content)
    return 200, out


def fetch_many(urls: Iterable[str], dest: Path, sleep: float = 1.0,
               overwrite: bool = False) -> dict[str, Optional[Path]]:
    """Scarica una richiesta al secondo: e' un sito pubblico, non c'e' fretta."""
    session = requests.Session()
    result: dict[str, Optional[Path]] = {}
    made = 0
    for url in urls:
        target = dest / local_name(url)
        if target.exists() and not overwrite:
            result[url] = target
            continue
        if made:
            time.sleep(sleep)
        made += 1
        _status, path = fetch_one(url, dest, overwrite, session)
        result[url] = path
    return result
