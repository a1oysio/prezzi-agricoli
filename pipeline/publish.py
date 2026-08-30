"""Genera i JSON statici che alimentano il sito su GitHub Pages.

Il sito e' statico: niente backend, niente query.  Serve quindi un indice
leggero per il catalogo e una serie per prodotto, caricata solo quando l'utente
la apre -- scaricare i 4 MB del dataset intero per disegnare un grafico sarebbe
inaccettabile.

    python -m pipeline.publish
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

from pipeline import csvstore, paths


def publish(dataset: Path, out_dir: Path) -> dict[str, int]:
    products = csvstore.read_products(dataset / "products.csv")
    prices = csvstore.read_prices(dataset / "prices")
    meta = csvstore.read_meta(dataset / "meta.json")

    series: dict[str, list] = defaultdict(list)
    for (d, code), (low, high) in prices.items():
        if low is None and high is None:
            continue            # non quotato: nel grafico e' un buco, non un punto
        series[code].append((d, low, high))

    series_dir = out_dir / "series"
    if series_dir.exists():
        shutil.rmtree(series_dir)
    series_dir.mkdir(parents=True, exist_ok=True)

    index = []
    for code in sorted(products, key=csvstore.sort_key):
        p = products[code]
        points = sorted(series.get(code, []))
        levels = [x for x in p.category_path.split(" > ") if x]
        index.append({
            "code": code,
            "name": p.name,
            "category": levels[-1] if levels else "",
            "group": levels[0] if levels else "",
            "path": p.category_path,
            "unit": p.unit,
            "n": len(points),
            "first": points[0][0] if points else None,
            "last": points[-1][0] if points else None,
        })
        if points:
            (series_dir / f"{code}.json").write_text(
                json.dumps({"code": code, "unit": p.unit, "name": p.name,
                            "points": [[d, lo, hi] for d, lo, hi in points]},
                           separators=(",", ":")),
                encoding="utf-8",
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.json").write_text(
        json.dumps({"meta": meta, "products": index}, ensure_ascii=False,
                   separators=(",", ":")),
        encoding="utf-8",
    )
    return {"products": len(index), "series": len(list(series_dir.glob('*.json')))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=paths.dataset_dir())
    ap.add_argument("--out", type=Path, default=paths.SITE_API_DIR)
    args = ap.parse_args()

    stats = publish(args.dataset, args.out)
    size = sum(f.stat().st_size for f in args.out.rglob("*") if f.is_file())
    print(f"  prodotti in indice : {stats['products']}")
    print(f"  serie generate     : {stats['series']}")
    print(f"  peso totale        : {size/1024/1024:.1f} MB in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
