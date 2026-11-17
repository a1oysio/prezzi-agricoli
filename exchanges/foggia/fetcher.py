"""Scarica i listini settimanali della Borsa Merci di Foggia.

L'elenco e' la pagina "Storico dei listini settimanali" della Camera di
Commercio: per ogni anno una voce per listino, con data e link.  Si prendono
solo i listini della borsa merci ricostituita, dal 23 giugno 2021, in
``.../borsa_merci/listini/<anno>/``.  La stessa pagina elenca anche:

* fino al 16 giugno 2021, in ``.../storico_listini_settimanali/``, il vecchio
  listino della Camera: dieci pagine su tutt'altro impianto (vini, olio,
  bestiame, prodotti petroliferi) che chiederebbe un parser suo;
* dall'ottobre 2024, in ``.../listini_po/``, i listini dei prodotti olivicoli.

La data dell'elenco serve solo a scegliere cosa scaricare e a dare il nome al
file: a volte e' sbagliata (n. 26 e 27 del 2024 sono tutti e due "17 luglio").
Quella che finisce nel dataset la legge il parser dal PDF.

    python -m exchanges.foggia.fetcher --dest data/foggia
"""
from __future__ import annotations

import argparse
import html
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests

from exchanges.bologna.fetcher import _HEADERS, MONTHS, Bulletin, fetch

INDEX_URL = "https://www.fg.camcom.gov.it/servizi/storico-dei-listini-settimanali"

_LINK = re.compile(r'href="([^"]*/borsa_merci/listini/\d{4}/\d{4}_(\d+)\.pdf)"')
_DATE = re.compile(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})")


def parse_index(page: str, base: str = INDEX_URL) -> list[Bulletin]:
    """I listini cerealicoli della pagina, dal piu' vecchio.  Ogni voce e' un
    ``<li>`` con la data in grassetto e il link al PDF."""
    found: dict[str, Bulletin] = {}
    for item in page.split("<li")[1:]:
        link = _LINK.search(item)
        text = html.unescape(re.sub(r"<[^>]+>", " ", item)).replace("\xa0", " ").lower()
        # "18 aprile 2018 2 maggio 2018": vale l'ultima data della voce.
        dates = [(int(d), MONTHS.get(m), int(y)) for d, m, y in _DATE.findall(text)]
        dates = [x for x in dates if x[1]]
        if not link or not dates:
            continue
        d, m, y = dates[-1]
        b = Bulletin(int(link[2]), date(y, m, d), urljoin(base, html.unescape(link[1])))
        found[b.url] = b
    return sorted(found.values(), key=lambda b: (b.date, b.number))


def list_bulletins(timeout: float = 30.0) -> list[Bulletin]:
    resp = requests.get(INDEX_URL, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return parse_index(resp.text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()
    failed = 0
    for b in list_bulletins():
        present = (args.dest / str(b.date.year) / b.filename).exists()
        status, _ = fetch(b, args.dest)
        if status != 200:
            failed += 1
            print(f"  ! {b.date} n. {b.number}: stato {status}  {b.url}")
        if not present:
            time.sleep(args.sleep)
    print(f"  non scaricati: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
