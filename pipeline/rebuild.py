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
    products: dict[str, csvstore.Product] = {}
    stats = {"files": 0, "empty": 0, "failed": 0, "last_issue": None, "revisions": 0}

    # Ordine crescente di bollettino: su 63 date la borsa ne pubblica due, e il
    # secondo e' una rettifica del primo.  Deve vincere l'ultimo.
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

        stats["files"] += 1
        for rec in records:
            key = (rec.date.isoformat(), rec.product_code)
            if key in prices:
                stats["revisions"] += 1
            prices[key] = (rec.low, rec.high)
            products[rec.product_code] = csvstore.Product(
                rec.product_code, rec.product_name,
                " > ".join(rec.category_path), rec.units,
            )

    counts = csvstore.write_prices(dataset / "prices", prices)
    n_products = csvstore.write_products(dataset / "products.csv", products, prices)
    csvstore.write_meta(dataset / "meta.json", prices, n_products, counts,
                        stats["last_issue"])
    stats["products"] = n_products
    stats["prices"] = len(prices)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=paths.ARCHIVE_DIR)
    ap.add_argument("--dataset", type=Path, default=paths.dataset_dir())
    args = ap.parse_args()

    if not args.src.is_dir() or not any(args.src.glob("*.xml")):
        print(f"Nessun XML in {args.src}. Vedi l'aiuto di questo comando.",
              file=sys.stderr)
        return 1

    print(f"Ricostruzione di {args.dataset} da {args.src} …")
    s = rebuild(args.src, args.dataset)
    print(
        f"  bollettini con dati : {s['files']}\n"
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
