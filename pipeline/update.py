"""Scarica i bollettini nuovi e li unisce ai CSV.  Punto d'ingresso della CI.

Legge i CSV, ci aggiunge le rilevazioni nuove e li riscrive.  Il workflow su
GitHub non ha quindi bisogno dell'archivio XML, che pesa una cinquantina di MB e
non e' versionato.

    python -m pipeline.update              # dal bollettino successivo all'ultimo noto
    python -m pipeline.update --from 1424  # forza il punto di partenza
    python -m pipeline.update --dry-run    # scarica e riferisce, non scrive nulla
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from exchanges.verona import fetcher, parser as vr_parser
from pipeline import csvstore, paths

# Quanti numeri consecutivi mancanti prima di concludere che siamo in pari.
# La borsa salta qualche numero (bollettini mensili, settimane di chiusura), per
# cui il primo 404 non significa "non c'e' altro".
PROBE_LIMIT = 6


def update(dataset: Path, staging: Path, start: int | None = None,
           sleep: float = 1.0, dry_run: bool = False) -> dict:
    meta = csvstore.read_meta(dataset / "meta.json")
    prices = csvstore.read_prices(dataset / "prices")
    products = csvstore.read_products(dataset / "products.csv")

    if start is None:
        last = meta.get("last_issue_number")
        if last is None:
            raise SystemExit(
                "meta.json non indica l'ultimo bollettino: passa --from esplicitamente."
            )
        start = int(last) + 1

    staging.mkdir(parents=True, exist_ok=True)
    stats = {"probed": 0, "downloaded": 0, "parsed": 0,
             "new_rows": 0, "updated_rows": 0, "last_issue": meta.get("last_issue_number")}

    downloaded: list[tuple[int, Path]] = []
    number, misses = start, 0
    while misses < PROBE_LIMIT:
        if stats["probed"]:
            time.sleep(sleep)       # una richiesta al secondo verso un portale pubblico
        stats["probed"] += 1
        status, path = fetcher.fetch_one(number, dest=staging, timeout=20.0)
        if status == 200 and path is not None:
            downloaded.append((number, path))
            stats["downloaded"] += 1
            misses = 0
        else:
            misses += 1
        number += 1

    # Ordine crescente: le rettifiche hanno numero piu' alto e devono vincere.
    for issue, path in sorted(downloaded):
        try:
            _meta, records = vr_parser.parse_xml_file(path)
        except ValueError as exc:
            print(f"  ! bollettino {issue}: {exc}", file=sys.stderr)
            continue
        stats["last_issue"] = issue
        if not records:
            continue                # bollettino mensile o settimana di chiusura
        stats["parsed"] += 1
        for rec in records:
            key = (rec.date.isoformat(), rec.product_code)
            if key in prices:
                if prices[key] != (rec.low, rec.high):
                    stats["updated_rows"] += 1
            else:
                stats["new_rows"] += 1
            prices[key] = (rec.low, rec.high)
            products[rec.product_code] = csvstore.Product(
                rec.product_code, rec.product_name,
                " > ".join(rec.category_path), rec.units,
            )

    if dry_run:
        return stats

    counts = csvstore.write_prices(dataset / "prices", prices)
    n_products = csvstore.write_products(dataset / "products.csv", products, prices)
    csvstore.write_meta(dataset / "meta.json", prices, n_products, counts,
                        stats["last_issue"])
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=paths.dataset_dir())
    ap.add_argument("--staging", type=Path, default=None,
                    help="dove salvare gli XML scaricati (default: cartella temporanea)")
    ap.add_argument("--from", dest="start", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        staging = args.staging or Path(tmp)
        stats = update(args.dataset, staging, args.start, args.sleep, args.dry_run)

    print(
        f"  numeri sondati   : {stats['probed']}\n"
        f"  bollettini nuovi : {stats['downloaded']} (con dati: {stats['parsed']})\n"
        f"  righe aggiunte   : {stats['new_rows']}\n"
        f"  righe corrette   : {stats['updated_rows']}\n"
        f"  ultimo bollettino: {stats['last_issue']}"
    )
    if args.dry_run:
        print("  (dry-run: nessun file scritto)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
