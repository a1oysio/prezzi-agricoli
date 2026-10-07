"""Genera i JSON statici che alimentano il sito su GitHub Pages.

Il sito e' statico: niente backend, niente query.  Serve quindi un indice
leggero per il catalogo e una serie per prodotto, caricata solo quando l'utente
la apre -- scaricare i 4 MB del dataset intero per disegnare un grafico sarebbe
inaccettabile.

Una cartella per borsa, piu' un elenco delle borse che il sito usa per il
selettore:

    api/exchanges.json
    api/<borsa>/index.json
    api/<borsa>/series/<codice>.json

    python -m pipeline.publish                     # tutte le borse
    python -m pipeline.publish --exchange bologna  # una sola

Se il dataset ha un ``series.csv`` (Bologna), i codici che formano una serie
compaiono nell'indice come **un solo prodotto** con tutta la storia, e non uno
per ogni variante dell'etichetta; le varianti restano elencate nel dettaglio.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from pipeline import csvstore, paths


def series_id(series: str) -> str:
    """Identificativo stabile di una serie: sopravvive all'aggiunta di altre serie."""
    return "s-" + hashlib.sha1(series.encode("utf-8")).hexdigest()[:8]


def read_series(dataset: Path) -> dict[str, str]:
    """code -> chiave di serie, dai soli codici che ne hanno una."""
    f = dataset / "series.csv"
    if not f.exists():
        return {}
    with f.open(encoding="utf-8") as fh:
        return {r["code"]: r["series"] for r in csv.DictReader(fh)}


def _group_of(levels: list[str], cut: str) -> str:
    if not levels:
        return ""
    return levels[0].split(cut)[0].strip() if cut else levels[0]


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def publish(dataset: Path, out_dir: Path,
            exchange: Optional[paths.Exchange] = None) -> dict[str, int]:
    products = csvstore.read_products(dataset / "products.csv")
    prices = csvstore.read_prices(dataset / "prices")
    meta = csvstore.read_meta(dataset / "meta.json")
    cut = exchange.group_cut if exchange else ""

    series: dict[str, list] = defaultdict(list)
    for (d, code), (low, high) in prices.items():
        if low is None and high is None:
            continue            # non quotato: nel grafico e' un buco, non un punto
        series[code].append((d, low, high))

    # Le serie fra piu' codici (Bologna): un prodotto solo, con tutta la storia.
    merged: dict[str, list[str]] = defaultdict(list)
    for code, key in read_series(dataset).items():
        if code in products:
            merged[key].append(code)
    in_series = {c for codes in merged.values() for c in codes}

    series_dir = out_dir / "series"
    if series_dir.exists():
        shutil.rmtree(series_dir)
    series_dir.mkdir(parents=True, exist_ok=True)

    index = []

    def add(code: str, name: str, path: str, unit: str, points: list,
            extra: Optional[dict] = None, payload: Optional[dict] = None) -> None:
        if not points:
            return              # senza quotazioni non c'e' niente da disegnare: resta nei CSV
        points = sorted(points)
        # "#2" e' l'ordinale che il parser da' alla seconda riga con la stessa
        # etichetta nello stesso listino: non e' una sezione.
        levels = [x for x in path.split(" > ") if x and not x.startswith("#")]
        index.append({
            "code": code,
            "name": name,
            "category": levels[-1] if levels else "",
            "group": _group_of(levels, cut),
            "path": path,
            "unit": unit,
            "n": len(points),
            "first": points[0][0],
            "last": points[-1][0],
            **(extra or {}),
        })
        _write_json(series_dir / f"{code}.json", {
            "code": code, "unit": unit, "name": name,
            "points": [[d, lo, hi] for d, lo, hi in points],
            **(payload or {}),
        })

    for code in sorted((c for c in products if c not in in_series), key=csvstore.sort_key):
        p = products[code]
        ordinal = next((x for x in p.category_path.split(" > ") if x.startswith("#")), "")
        name = f"{p.name} (voce {ordinal[1:]})" if ordinal else p.name
        add(code, name, p.category_path, p.unit, series.get(code, []))

    for key in sorted(merged):
        codes = sorted(merged[key], key=lambda c: min((d for d, _, _ in series.get(c, [("9999", 0, 0)])),
                                                      default="9999"))
        # Se due varianti quotano la stessa data (la settimana di passaggio, con
        # valori identici: lo garantisce pipeline.validate) vale una volta sola.
        by_date: dict[str, tuple] = {}
        for c in codes:
            for d, lo, hi in series.get(c, []):
                by_date[d] = (d, lo, hi)
        stem, _, grade = key.partition(" > ")
        unit = Counter(products[c].unit for c in codes).most_common(1)[0][0]
        variants = []
        for c in codes:
            pts = sorted(series.get(c, []))
            if pts:
                variants.append({"name": products[c].name, "first": pts[0][0],
                                 "last": pts[-1][0], "n": len(pts)})
        add(series_id(key), f"{stem} — {grade}", key, unit, list(by_date.values()),
            extra={"merged": len(variants)}, payload={"variants": variants})

    index.sort(key=lambda e: (e["group"].lower(), e["name"].lower()))
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "index.json", {
        "meta": meta,
        "exchange": _exchange_info(exchange, meta) if exchange else None,
        "products": index,
    })
    return {"products": len(index), "series": len(list(series_dir.glob("*.json")))}


def _exchange_info(ex: paths.Exchange, meta: dict) -> dict:
    return {
        "slug": ex.slug,
        "code": ex.code,
        "name": ex.name,
        "chamber": ex.chamber,
        "source_url": ex.source_url,
        "dataset_url": f"https://github.com/a1oysio/prezzi-agricoli/tree/main/dataset/{ex.slug}",
        "notice": ex.notice,
        "n_products": meta.get("n_products"),
        "first_date": meta.get("first_date"),
        "last_date": meta.get("last_date"),
    }


def publish_all(out_root: Path, only: Optional[str] = None) -> dict[str, dict]:
    """Una borsa per cartella e l'elenco per il selettore.

    Una borsa senza dataset (ancora da costruire) non compare nel selettore.
    """
    chosen = [only] if only else list(paths.EXCHANGES)
    stats: dict[str, dict] = {}
    listed = []
    for slug in paths.EXCHANGES:
        ex = paths.EXCHANGES[slug]
        dataset = paths.dataset_dir(slug)
        if not (dataset / "products.csv").exists():
            continue
        if slug in chosen:
            stats[slug] = publish(dataset, out_root / slug, ex)
        meta = csvstore.read_meta(dataset / "meta.json")
        listed.append(_exchange_info(ex, meta))
    out_root.mkdir(parents=True, exist_ok=True)
    _write_json(out_root / "exchanges.json", {
        "default": listed[0]["slug"] if listed else None,
        "exchanges": listed,
    })
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exchange", choices=sorted(paths.EXCHANGES), default=None,
                    help="una sola borsa (default: tutte)")
    ap.add_argument("--out", type=Path, default=paths.SITE_API_DIR)
    args = ap.parse_args()

    # Versioni precedenti scrivevano Verona in api/index.json: i file sciolti
    # non servono piu' e resterebbero sul sito come dati vecchi.
    for stale in (args.out / "index.json",):
        stale.unlink(missing_ok=True)
    if (args.out / "series").is_dir():
        shutil.rmtree(args.out / "series")

    stats = publish_all(args.out, args.exchange)
    size = sum(f.stat().st_size for f in args.out.rglob("*") if f.is_file())
    for slug, s in stats.items():
        print(f"  {slug:8} prodotti in indice: {s['products']:5}   serie generate: {s['series']}")
    print(f"  peso totale: {size/1024/1024:.1f} MB in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
