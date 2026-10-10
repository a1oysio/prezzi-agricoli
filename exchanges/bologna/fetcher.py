"""Scarica i listini settimanali della Borsa Merci di Bologna dal sito di AGER.

A differenza di Verona non c'e' un indirizzo per numero: i PDF hanno nomi liberi
("N. 31 del 31 LUGLIO 2003.pdf", "Settimanale-n.-6-del-5-Febbraio-2026-…") e
stanno in cartelle diverse a seconda dell'epoca.  L'unico elenco e' la pagina
dell'archivio, che li riporta tutti dal 2003: si legge quella e da ogni nome si
ricavano numero e data.

    python -m exchanges.bologna.fetcher --dest data/bologna          # tutto
    python -m exchanges.bologna.fetcher --dest data/bologna --from 2026-01-01
"""
from __future__ import annotations

import argparse
import difflib
import html
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urljoin

import requests

INDEX_URL = "https://www.agerborsamerci.it/listino-borsa/settimanale-ager/"

_HEADERS = {
    "User-Agent": "prezzi-agricoli/1.0 (+https://github.com/a1oysio/prezzi-agricoli)",
}

MONTHS = {m: i + 1 for i, m in enumerate(
    ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
     "agosto", "settembre", "ottobre", "novembre", "dicembre"])}

# "N. 32-33-34 del 21 AGOSTO 2003", "n.-6-del-11-Febbraio-2016",
# "Sett-34-2-settembre-2021-listino-borsa-34": numero, poi giorno mese anno.
# Nei nomi piu' vecchi il separatore e' lo spazio, nei recenti il trattino.  Un
# listino che copre piu' settimane ("32-33-34") prende il primo dei suoi numeri.
_NUM = r"(?:n\.?|sett)[\s._-]*(?P<num>\d{1,2})(?:[\s-]+\d{1,2}){0,2}?[\s._-]*(?:del)?[\s._-]*"
_NAME = re.compile(
    _NUM + r"(?P<day>\d{1,2})[°\s._-]+(?P<month>(?!del\b)[a-zà]+)(?:[\s._-]+(?P<year>\d{4}))?",
    re.IGNORECASE,
)
# Qualche nome del 2004 ha la data in cifre: "N. 15 del 08.04.04".
_NAME_NUMERIC = re.compile(
    _NUM + r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{2})\b", re.IGNORECASE)


def _month(word: str) -> Optional[int]:
    # Tollera i refusi dei nomi veri: "GENNIO", "febbriao".
    close = difflib.get_close_matches(word.lower(), MONTHS, n=1, cutoff=0.8)
    return MONTHS[close[0]] if close else None


@dataclass(frozen=True)
class Bulletin:
    number: int
    date: date
    url: str

    @property
    def filename(self) -> str:
        return f"{self.date.isoformat()}_n{self.number:02d}.pdf"


# Cartella di caricamento di WordPress: .../wp-content/uploads/<anno>/<mese>/
_UPLOADED = re.compile(r"/uploads/(\d{4})/(\d{2})/")


def parse_name(url: str) -> Optional[tuple[int, date]]:
    """Numero e data del listino dal suo indirizzo, o None se non e' un listino."""
    name = unquote(url.rsplit("/", 1)[-1])
    m = _NAME_NUMERIC.search(name)
    if m:
        try:
            return int(m["num"]), date(2000 + int(m["year"]), int(m["month"]), int(m["day"]))
        except ValueError:
            return None
    m = _NAME.search(name)
    month = _month(m["month"]) if m else None
    if month is None:
        return None
    if m["year"]:
        year = int(m["year"])
    else:
        # Per buona parte del 2022 il nome non ha l'anno ("…-del-24-Novembre-…"):
        # resta quello della cartella in cui il file e' stato caricato, tolto il
        # caso del listino di fine dicembre caricato a gennaio.
        up = _UPLOADED.search(url)
        if not up:
            return None
        year = int(up[1]) - (1 if month == 12 and up[2] == "01" else 0)
    try:
        return int(m["num"]), date(year, month, int(m["day"]))
    except ValueError:
        return None


def parse_index(page: str, base: str = INDEX_URL) -> list[Bulletin]:
    """I listini elencati nella pagina dell'archivio, dal piu' vecchio."""
    found: dict[date, Bulletin] = {}
    for href in re.findall(r'href="([^"]+\.pdf)"', page, flags=re.IGNORECASE):
        href = html.unescape(href)
        parsed = parse_name(href)
        if parsed is None:
            continue            # statuti, condizioni generali e altri allegati
        number, day = parsed
        # Lo stesso listino compare a volte due volte, in http e in https; se
        # invece c'e' una seconda edizione ("…-Ed.-2.pdf") vale quella.
        if day not in found or re.search(r"\bed\b", unquote(href), re.IGNORECASE):
            found[day] = Bulletin(number, day, urljoin(base, href))
    return [found[d] for d in sorted(found)]


def list_bulletins(timeout: float = 30.0) -> list[Bulletin]:
    resp = requests.get(INDEX_URL, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return parse_index(resp.text)


def fetch(b: Bulletin, dest: Path, overwrite: bool = False,
          timeout: float = 30.0) -> tuple[int, Optional[Path]]:
    """Scarica un listino in ``dest/<anno>/<data>_n<numero>.pdf``.

    Restituisce (stato_http, percorso_o_None); 0 = errore di rete.
    """
    out = dest / str(b.date.year) / b.filename
    if out.exists() and not overwrite:
        return 200, out
    try:
        resp = requests.get(b.url, headers=_HEADERS, timeout=timeout)
    except requests.RequestException:
        return 0, None
    if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
        return resp.status_code, None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.content)
    return 200, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--from", dest="start", type=date.fromisoformat, default=None,
                    help="solo i listini da questa data (YYYY-MM-DD)")
    ap.add_argument("--sleep", type=float, default=0.4,
                    help="pausa fra un download e l'altro, in secondi")
    args = ap.parse_args()

    todo = [b for b in list_bulletins() if args.start is None or b.date >= args.start]
    failed = 0
    for b in todo:
        present = (args.dest / str(b.date.year) / b.filename).exists()
        status, _ = fetch(b, args.dest)
        if status != 200:
            failed += 1
            print(f"  ! {b.date} n. {b.number}: stato {status}  {b.url}")
        if not present:
            time.sleep(args.sleep)
    print(f"  listini in elenco: {len(todo)}, non scaricati: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
