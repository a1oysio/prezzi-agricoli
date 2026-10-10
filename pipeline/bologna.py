"""Borsa Merci di Bologna: dai listini PDF ai CSV.

Stessa destinazione di Verona -- ``dataset/bologna/`` con lo stesso schema -- ma
strada diversa, per tre ragioni.

* **Non ci sono codici prodotto.**  Una voce del listino e' la coppia (percorso,
  nome) scritta esattamente com'e': quando la borsa ritocca una dicitura nasce
  una voce nuova, e la vecchia finisce li'.  Nessun raggruppamento: decidere che
  due diciture sono "lo stesso prodotto" sarebbe un giudizio nostro.  Il codice
  e' un numero progressivo assegnato alla prima comparsa e conservato in
  ``products.csv``, che per Bologna e' quindi anche il registro dei codici.
* **I listini non hanno un indirizzo per numero.**  Si legge l'elenco del sito
  e si prendono quelli con data successiva all'ultima acquisita.
* **Ogni listino riporta anche la settimana precedente.**  Serve a riempire i
  buchi: se di una settimana il PDF non esiste piu', i suoi prezzi si prendono
  dalle colonne "precedente" del listino dopo.

    python -m pipeline.update  --exchange bologna
    python -m pipeline.rebuild --exchange bologna     # da data/bologna
"""
from __future__ import annotations

import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import exchanges.bologna as exchange
from exchanges.bologna import fetcher, parser
from exchanges.bologna.layouts import Entry
from pipeline import csvstore

# Quanti listini gia' acquisiti riscaricare a ogni esecuzione: capita che la
# borsa ne ripubblichi uno corretto ("Ed. 2") allo stesso indirizzo o a uno nuovo.
RECHECK_ISSUES = 3

Prices = dict[tuple[str, str], tuple[Optional[float], Optional[float]]]


class Codebook:
    """Da (percorso, nome) al codice, con i codici nuovi in coda ai vecchi."""

    def __init__(self, products: dict[str, csvstore.Product]) -> None:
        self.products = products
        self._by_key = {(p.category_path, p.name): code for code, p in products.items()}
        self._next = max((int(c) for c in products if c.isdigit()), default=0) + 1

    def code(self, e: Entry) -> str:
        key = (" > ".join(e.path), e.name)
        code = self._by_key.get(key)
        if code is None:
            code = str(self._next)
            self._next += 1
            self._by_key[key] = code
            self.products[code] = csvstore.Product(code, e.name, key[0], e.unit)
        return code


def merge(files: list[Path], prices: Prices, book: Codebook) -> dict:
    """Unisce i listini a ``prices``, dal piu' vecchio.

    Restituisce le statistiche e, in ``before``, il valore che ogni riga gia'
    presente aveva prima di essere cambiata.
    """
    stats = {"parsed": 0, "failed": 0, "new_rows": 0, "filled": [],
             "last_issue": None, "last_date": None, "before": {}, "origin": {}}
    known_dates = {d for d, _ in prices}
    fresh: set[tuple[str, str]] = set()
    parsed: list[tuple[date, int, list[Entry]]] = []

    for path in sorted(files, key=lambda p: p.name):
        try:
            meta, entries = parser.parse_file(path)
        except ValueError as exc:
            stats["failed"] += 1
            print(f"  ! {exc}", file=sys.stderr)
            continue
        parsed.append((meta.issue_date, meta.issue_number, entries))
        stats["parsed"] += 1

    issue_dates = {d.isoformat() for d, _, _ in parsed}

    def put(day: str, e: Entry, low, high, issue: int) -> None:
        key = (day, book.code(e))
        value = (low, high)
        if key not in prices:
            fresh.add(key)
            stats["new_rows"] += 1
        elif prices[key] != value and key not in fresh:
            stats["before"].setdefault(key, prices[key])
            stats["origin"][key] = issue
        prices[key] = value

    for day, number, entries in parsed:
        # La settimana precedente, solo se di suo non ha un listino: ne' fra
        # quelli letti adesso ne' gia' nel dataset.
        prev = {e.prev_date for e in entries if e.prev_date}
        if len(prev) == 1:
            p = prev.pop().isoformat()
            if p not in issue_dates and p not in known_dates:
                for e in entries:
                    put(p, e, e.prev_low, e.prev_high, number)
                stats["filled"].append(p)
                known_dates.add(p)
        for e in entries:
            put(day.isoformat(), e, e.low, e.high, number)
        known_dates.add(day.isoformat())
        if stats["last_date"] is None or day.isoformat() >= stats["last_date"]:
            stats["last_date"], stats["last_issue"] = day.isoformat(), number
    return stats


def _write(dataset: Path, prices: Prices, book: Codebook, last_issue: Optional[int]) -> int:
    counts = csvstore.write_prices(dataset / "prices", prices)
    n_products = csvstore.write_products(dataset / "products.csv", book.products, prices)
    csvstore.write_meta(dataset / "meta.json", prices, n_products, counts,
                        last_issue, exchange=exchange)
    return n_products


def rebuild(src: Path, dataset: Path) -> dict:
    """Riscrive il dataset da tutti i PDF in ``src``.

    I codici gia' assegnati in ``products.csv`` restano: una voce non cambia
    numero perche' si e' rifatto il giro, e i link al sito continuano a valere.
    """
    book = Codebook(csvstore.read_products(dataset / "products.csv"))
    known = set(book.products)
    prices: Prices = {}
    stats = merge(sorted(src.glob("*/*.pdf")), prices, book)
    # Le voci che il parser non produce piu' -- un nome letto meglio di prima --
    # non devono restare in anagrafica senza una riga di prezzo.
    used = {code for _, code in prices}
    for code in known - used:
        del book.products[code]
    stats["products"] = _write(dataset, prices, book, stats["last_issue"])
    stats["prices"] = len(prices)
    return stats


def update(dataset: Path, staging: Path, recheck: int = RECHECK_ISSUES,
           sleep: float = 1.0, dry_run: bool = False) -> dict:
    """Scarica i listini nuovi, ricontrolla gli ultimi e li unisce ai CSV."""
    meta = csvstore.read_meta(dataset / "meta.json")
    prices = csvstore.read_prices(dataset / "prices")
    book = Codebook(csvstore.read_products(dataset / "products.csv"))
    last = meta.get("last_date")
    if last is None:
        raise SystemExit("dataset di Bologna vuoto: prima `python -m pipeline.rebuild --exchange bologna`.")

    bulletins = fetcher.list_bulletins()
    old = [b for b in bulletins if b.date.isoformat() <= last][-recheck:] if recheck else []
    new = [b for b in bulletins if b.date.isoformat() > last]

    files: list[Path] = []
    downloaded = 0
    for i, b in enumerate(old + new):
        if i:
            time.sleep(sleep)
        status, path = fetcher.fetch(b, staging, overwrite=True)
        if path is None:
            # Un listino in elenco che non si scarica e' un guasto, non una
            # settimana senza mercato: fermarsi, o resterebbe un buco muto.
            raise SystemExit(f"listino del {b.date} non scaricato (stato {status}): {b.url}")
        files.append(path)
        downloaded += b in new

    stats = merge(files, prices, book)
    if stats["failed"]:
        raise SystemExit(f"{stats['failed']} listini illeggibili: il dataset non e' stato toccato.")

    detected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    before, origin = stats["before"], stats["origin"]
    revisions = [
        [detected_at, origin[key], key[0], key[1],
         csvstore.fmt(before[key][0]), csvstore.fmt(before[key][1]),
         csvstore.fmt(prices[key][0]), csvstore.fmt(prices[key][1])]
        for key in sorted(before, key=lambda k: (k[0], csvstore.sort_key(k[1])))
        if prices[key] != before[key]
    ]
    stats.update(revisions=revisions, downloaded=downloaded, rechecked=len(old))
    # Senza listini nuovi il dataset non cambia: non si riscrive nemmeno
    # meta.json, o ogni giorno ci sarebbe un commit che sposta solo una data.
    if dry_run or not (stats["new_rows"] or revisions):
        return stats

    csvstore.append_revisions(dataset / "revisions.csv", revisions)
    _write(dataset, prices, book, stats["last_issue"] or meta.get("last_issue_number"))
    return stats


def main_update(args) -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        stats = update(args.dataset, args.staging or Path(tmp),
                       RECHECK_ISSUES if args.recheck is None else args.recheck,
                       args.sleep, args.dry_run)
    print(
        f"  listini ricontroll.: {stats['rechecked']}\n"
        f"  listini nuovi      : {stats['downloaded']}\n"
        f"  righe aggiunte     : {stats['new_rows']}\n"
        f"  righe rettificate  : {len(stats['revisions'])}\n"
        f"  settimane recuperate dal listino successivo: {', '.join(stats['filled']) or 'nessuna'}\n"
        f"  ultimo listino     : n. {stats['last_issue']} del {stats['last_date']}"
    )
    if args.dry_run:
        print("  (dry-run: nessun file scritto)")
    return 0


def main_rebuild(args) -> int:
    if not args.src.is_dir() or not any(args.src.glob("*/*.pdf")):
        print(f"Nessun PDF in {args.src}. Per scaricarli:\n"
              f"    python -m exchanges.bologna.fetcher --dest {args.src}", file=sys.stderr)
        return 1
    print(f"Ricostruzione di {args.dataset} da {args.src} …")
    s = rebuild(args.src, args.dataset)
    print(
        f"  listini letti       : {s['parsed']}\n"
        f"  illeggibili         : {s['failed']}\n"
        f"  settimane recuperate: {', '.join(s['filled']) or 'nessuna'}\n"
        f"  voci di listino     : {s['products']}\n"
        f"  rilevazioni         : {s['prices']}\n"
        f"  ultimo listino      : n. {s['last_issue']} del {s['last_date']}"
    )
    return 1 if s["failed"] else 0
