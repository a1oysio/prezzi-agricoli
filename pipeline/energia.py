"""Prodotti petroliferi di Verona: dagli XML quindicinali ai CSV.

Dataset a parte, ``dataset/verona-energia/``, perche' lo schema e' diverso: per
ogni prodotto e rilevazione non c'e' un minimo e un massimo ma quattro valori
(prezzo netto, con accisa, aliquota IVA, al consumo).  Il prezzo con accisa resta
accanto al netto perche' l'accisa cambia per decreto: senza, un salto della
serie sembrerebbe un movimento di mercato.

Per il resto segue Bologna: i numeri vengono dall'indice della pagina, a ogni
esecuzione si riscaricano anche le ultime rilevazioni e le correzioni della
fonte finiscono in ``revisions.csv``.

    python -m pipeline.update  --exchange verona-energia
    python -m pipeline.rebuild --exchange verona-energia   # da data/verona-energia
"""
from __future__ import annotations

import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from exchanges.verona import energia as source
from pipeline import csvstore

# Per csvstore.write_meta, che legge questi nomi dal modulo della borsa.
CODE = "VR-EN"
NAME = "Prodotti petroliferi di Verona"
SLUG = "verona-energia"
SOURCE_URL = source.PORTAL
LICENSE = "CC-BY-4.0"

VALUES = ["price", "price_with_excise", "vat_rate", "consumer_price"]
PRICE_HEADER = ["date", "code", *VALUES]
REVISION_HEADER = (["detected_at", "issue", "date", "code"]
                   + [f"{c}_old" for c in VALUES] + [f"{c}_new" for c in VALUES])

# Due rilevazioni al mese: tre numeri coprono sei settimane.
RECHECK_ISSUES = 3

# Il sito disegna un minimo e un massimo per serie.  Ogni prezzo diventa quindi
# una voce a se', con minimo = massimo; l'aliquota IVA resta nei soli CSV.
SITE_SERIES = (("netto", 0, "prezzo netto"),
               ("accisa", 1, "con accisa"),
               ("consumo", 3, "al consumo, IVA inclusa"))

Prices = dict[tuple[str, str], tuple[Optional[float], ...]]


def merge(files: list[tuple[int, Path]], prices: Prices,
          products: dict[str, csvstore.Product], near: Optional[date] = None) -> dict:
    """Unisce le rilevazioni a ``prices``, dal numero piu' basso: se la fonte ne
    ripubblica una con un numero nuovo, vince l'ultima."""
    stats = {"parsed": 0, "failed": 0, "new_rows": 0, "last_issue": None,
             "before": {}, "origin": {}}
    fresh: set[tuple[str, str]] = set()
    for issue, path in sorted(files):
        try:
            day, rows = source.parse_file(path, near)
        except ValueError as exc:
            stats["failed"] += 1
            print(f"  ! {exc}", file=sys.stderr)
            continue
        near = day
        stats["parsed"] += 1
        stats["last_issue"] = max(issue, stats["last_issue"] or 0)
        for code, name, path_, unit, values in rows:
            key = (day.isoformat(), code)
            if key not in prices:
                fresh.add(key)
                stats["new_rows"] += 1
            elif prices[key] != values and key not in fresh:
                stats["before"].setdefault(key, prices[key])
                stats["origin"][key] = issue
            prices[key] = values
            products[code] = csvstore.Product(code, name, " > ".join(path_), unit)
    return stats


def _write(dataset: Path, prices: Prices, products, last_issue: Optional[int]) -> int:
    counts = csvstore.write_prices(dataset / "prices", prices, PRICE_HEADER)
    n_products = csvstore.write_products(dataset / "products.csv", products, prices)
    csvstore.write_meta(dataset / "meta.json", prices, n_products, counts,
                        last_issue, exchange=sys.modules[__name__])
    return n_products


def rebuild(src: Path, dataset: Path) -> dict:
    files = [(int(p.stem), p) for p in src.glob("*.xml") if p.stem.isdigit()]
    prices: Prices = {}
    products: dict[str, csvstore.Product] = {}
    stats = merge(files, prices, products)
    stats["products"] = _write(dataset, prices, products, stats["last_issue"])
    stats["prices"] = len(prices)
    return stats


def update(dataset: Path, staging: Path, recheck: int = RECHECK_ISSUES,
           sleep: float = 1.0, dry_run: bool = False) -> dict:
    """Scarica le rilevazioni nuove, ricontrolla le ultime e le unisce ai CSV."""
    import requests

    meta = csvstore.read_meta(dataset / "meta.json")
    prices = csvstore.read_prices(dataset / "prices")
    products = csvstore.read_products(dataset / "products.csv")
    last = meta.get("last_issue_number")
    if last is None:
        raise SystemExit("dataset dei petroliferi vuoto: prima "
                         "`python -m pipeline.rebuild --exchange verona-energia`.")

    numbers = source.list_numbers()
    old = [n for n in numbers if n <= last][-recheck:] if recheck else []
    new = [n for n in numbers if n > last]

    files: list[tuple[int, Path]] = []
    for i, num in enumerate(old + new):
        if i:
            time.sleep(sleep)
        try:
            files.append((num, source.fetch(num, staging)))
        except requests.RequestException as exc:
            # In indice ma non scaricabile: un guasto, non una quindicina vuota.
            raise SystemExit(f"rilevazione {num} non scaricata: {exc}")

    stats = merge(files, prices, products, date.fromisoformat(meta["last_date"]))
    if stats["failed"]:
        raise SystemExit(f"{stats['failed']} rilevazioni illeggibili: il dataset non e' stato toccato.")

    detected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    before, origin = stats["before"], stats["origin"]
    revisions = [
        [detected_at, origin[key], key[0], key[1],
         *map(csvstore.fmt, before[key]), *map(csvstore.fmt, prices[key])]
        for key in sorted(before, key=lambda k: (k[0], csvstore.sort_key(k[1])))
        if prices[key] != before[key]
    ]
    stats.update(revisions=revisions, downloaded=len(new), rechecked=len(old))
    # Niente di nuovo: non si riscrive nemmeno meta.json, o ci sarebbe un commit
    # al giorno che sposta solo una data.
    if dry_run or not (stats["new_rows"] or revisions):
        return stats

    csvstore.append_revisions(dataset / "revisions.csv", revisions, REVISION_HEADER)
    _write(dataset, prices, products, max(stats["last_issue"] or 0, last))
    return stats


def for_site(products: dict[str, csvstore.Product], prices: Prices):
    """Prodotti e prezzi nella forma (minimo, massimo) che il sito disegna."""
    site_products, site_prices = {}, {}
    for code, p in products.items():
        for suffix, _, label in SITE_SERIES:
            c = f"{code}-{suffix}"
            site_products[c] = csvstore.Product(c, f"{p.name} · {label}", p.category_path, p.unit)
    for (d, code), values in prices.items():
        for suffix, i, _ in SITE_SERIES:
            site_prices[(d, f"{code}-{suffix}")] = (values[i], values[i])
    return site_products, site_prices


def main_update(args) -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        stats = update(args.dataset, args.staging or Path(tmp),
                       RECHECK_ISSUES if args.recheck is None else args.recheck,
                       args.sleep, args.dry_run)
    print(
        f"  rilevazioni ricontroll.: {stats['rechecked']}\n"
        f"  rilevazioni nuove      : {stats['downloaded']}\n"
        f"  righe aggiunte         : {stats['new_rows']}\n"
        f"  righe rettificate      : {len(stats['revisions'])}\n"
        f"  ultima rilevazione     : n. {stats['last_issue']}"
    )
    if args.dry_run:
        print("  (dry-run: nessun file scritto)")
    return 0


def main_rebuild(args) -> int:
    if not args.src.is_dir() or not any(args.src.glob("*.xml")):
        print(f"Nessun XML in {args.src}. Per scaricarli:\n"
              f"    python -m exchanges.verona.energia --dest {args.src}", file=sys.stderr)
        return 1
    print(f"Ricostruzione di {args.dataset} da {args.src} …")
    s = rebuild(args.src, args.dataset)
    print(
        f"  rilevazioni lette  : {s['parsed']}\n"
        f"  illeggibili        : {s['failed']}\n"
        f"  prodotti           : {s['products']}\n"
        f"  righe              : {s['prices']}\n"
        f"  ultima rilevazione : n. {s['last_issue']}"
    )
    return 1 if s["failed"] else 0
