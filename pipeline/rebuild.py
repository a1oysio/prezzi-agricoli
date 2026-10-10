"""Ricostruisce l'intero dataset dall'archivio XML.

Serve dopo aver toccato il parser o le regole sulle unita' di misura: rilegge
tutti i bollettini e riscrive i CSV da zero, invece di aggiungere in coda come fa
``pipeline.update``.

Richiede l'archivio completo degli XML, che **non e' versionato**.  Chi non ce
l'ha non ha motivo di usare questo comando: i CSV nel repository sono gia' il
risultato.  Per ricostruire l'archivio partendo da zero:

    python -m pipeline.update --from 1 --staging data/verona

    python -m pipeline.rebuild                    # da data/verona
    python -m pipeline.rebuild --src /altro/path

Per Bologna, dai PDF in data/bologna (vedi pipeline/bologna.py):

    python -m pipeline.rebuild --exchange bologna
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from exchanges.verona import parser as vr_parser
from pipeline import csvstore, paths


def _issue_number(path: Path) -> int:
    """Numero di bollettino dal nome file, per l'ordinamento."""
    digits = re.sub(r"\D", "", path.stem)
    return int(digits) if digits else 0


def rebuild(src_dir: Path, dataset: Path) -> dict:
    prices: dict[tuple[str, str], tuple[float | None, float | None]] = {}
    averages: dict[tuple[str, str], tuple[float | None, float | None]] = {}
    products: dict[str, csvstore.Product] = {}
    stats = {"files": 0, "averages": 0, "empty": 0, "failed": 0,
             "last_issue": None, "revisions": 0}

    # Ordine crescente di bollettino: quando la borsa pubblica due listini per la
    # stessa data il secondo e' una rettifica del primo.  Deve vincere l'ultimo.
    for path in sorted(src_dir.glob("*.xml"), key=_issue_number):
        try:
            meta, records = vr_parser.parse_xml_file(path)
        except ValueError as exc:
            stats["failed"] += 1
            print(f"  ! {path.name}: {exc}", file=sys.stderr)
            continue

        issue = meta.issue_number or _issue_number(path)
        if issue:
            stats["last_issue"] = issue
        if not records:
            stats["empty"] += 1          # bollettino mensile o settimana di chiusura
            continue

        # Le medie quindicinali vanno in una serie a parte: vedi
        # exchanges.verona.processors.classify_file_type.
        average = meta.file_type == vr_parser.AVERAGE_FILE_TYPE
        stats["averages" if average else "files"] += 1
        target = averages if average else prices
        for rec in records:
            key = (rec.date.isoformat(), rec.product_code)
            if key in prices and not average:
                stats["revisions"] += 1
            target[key] = (rec.low, rec.high)
            csvstore.add_product(products, rec, average)

    counts = csvstore.write_prices(dataset / "prices", prices)
    csvstore.write_prices(dataset / "averages", averages)
    n_products = csvstore.write_products(dataset / "products.csv", products, prices)
    csvstore.write_meta(dataset / "meta.json", prices, n_products, counts,
                        stats["last_issue"], len(averages))
    stats["products"] = n_products
    stats["prices"] = len(prices)
    stats["average_rows"] = len(averages)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exchange", choices=["verona", "bologna"], default="verona")
    ap.add_argument("--src", type=Path, default=None)
    ap.add_argument("--dataset", type=Path, default=None)
    args = ap.parse_args()
    if args.src is None:
        args.src = paths.archive_dir(args.exchange)
    if args.dataset is None:
        args.dataset = paths.dataset_dir(args.exchange)
    if args.exchange == "bologna":
        from pipeline import bologna
        return bologna.main_rebuild(args)

    if not args.src.is_dir() or not any(args.src.glob("*.xml")):
        print(f"Nessun XML in {args.src}. Vedi l'aiuto di questo comando.",
              file=sys.stderr)
        return 1

    print(f"Ricostruzione di {args.dataset} da {args.src} …")
    s = rebuild(args.src, args.dataset)
    print(
        f"  bollettini con dati : {s['files']}\n"
        f"  medie quindicinali  : {s['averages']} ({s['average_rows']} righe)\n"
        f"  senza dati          : {s['empty']} (mensili o settimane di chiusura)\n"
        f"  illeggibili         : {s['failed']}\n"
        f"  prodotti            : {s['products']}\n"
        f"  rilevazioni         : {s['prices']}\n"
        f"  rettifiche applicate: {s['revisions']}\n"
        f"  ultimo bollettino   : {s['last_issue']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
