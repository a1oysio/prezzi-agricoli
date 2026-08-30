"""Lettura e scrittura del dataset CSV.

Unico punto in cui si scrivono i CSV.  Sia l'aggiornamento incrementale
(``pipeline.update``) sia la ricostruzione integrale (``pipeline.rebuild``)
passano di qui: gli stessi dati devono dare gli stessi file, qualunque strada
abbiano preso.  Quando i due percorsi avevano ciascuno la propria scrittura,
divergevano gia' sulla definizione di "quotato".
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pipeline import paths

PRICE_HEADER = ["date", "code", "low", "high"]
PRODUCT_HEADER = [
    "code", "name", "category_path", "unit",
    "first_date", "last_date", "n_observations", "n_quoted",
]


@dataclass
class Product:
    code: str
    name: str
    category_path: str
    unit: str


def sort_key(code: str) -> tuple[int, str]:
    """I codici Verona sono numerici: ordinali come numeri, non come stringhe."""
    return (int(code), "") if code.isdigit() else (10**9, code)


def fmt(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.10g}"


def parse(value: str) -> Optional[float]:
    return float(value) if value else None


def read_prices(prices_dir: Path) -> dict[tuple[str, str], tuple[Optional[float], Optional[float]]]:
    """Tutti i prezzi indicizzati per (data, codice)."""
    out: dict[tuple[str, str], tuple[Optional[float], Optional[float]]] = {}
    if not prices_dir.is_dir():
        return out
    for f in sorted(prices_dir.glob("*.csv")):
        with f.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                out[(row["date"], row["code"])] = (parse(row["low"]), parse(row["high"]))
    return out


def read_products(path: Path) -> dict[str, Product]:
    out: dict[str, Product] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["code"]] = Product(
                row["code"], row["name"], row["category_path"], row["unit"]
            )
    return out


def write_prices(prices_dir: Path, prices: dict) -> dict[str, int]:
    by_year = defaultdict(list)
    for (d, code), (lo, hi) in prices.items():
        by_year[d[:4]].append((d, code, lo, hi))

    prices_dir.mkdir(parents=True, exist_ok=True)
    for stale in prices_dir.glob("*.csv"):
        if stale.stem not in by_year:
            stale.unlink()

    counts = {}
    for year, items in sorted(by_year.items()):
        # Ordine deterministico: gli stessi dati producono lo stesso file byte per
        # byte, quindi git non registra diff spuri.
        items.sort(key=lambda r: (r[0], sort_key(r[1])))
        with (prices_dir / f"{year}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(PRICE_HEADER)
            for d, code, lo, hi in items:
                w.writerow([d, code, fmt(lo), fmt(hi)])
        counts[year] = len(items)
    return counts


def write_products(path: Path, products: dict[str, Product], prices: dict) -> int:
    agg = defaultdict(lambda: {"dates": [], "quoted": 0})
    for (d, code), (lo, hi) in prices.items():
        a = agg[code]
        a["dates"].append(d)
        if lo is not None or hi is not None:
            a["quoted"] += 1

    rows = []
    for code in sorted(products, key=sort_key):
        p = products[code]
        a = agg.get(code)
        dates = sorted(a["dates"]) if a else []
        rows.append([
            p.code, p.name, p.category_path, p.unit,
            dates[0] if dates else "", dates[-1] if dates else "",
            len(dates), a["quoted"] if a else 0,
        ])

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(PRODUCT_HEADER)
        w.writerows(rows)
    return len(rows)


def write_meta(path: Path, prices: dict, n_products: int,
               counts: dict[str, int], last_issue: Optional[int]) -> None:
    dates = sorted({d for d, _ in prices})
    quoted = sum(1 for lo, hi in prices.values() if lo is not None or hi is not None)
    path.write_text(json.dumps({
        "exchange_code": paths.EXCHANGE_CODE,
        "exchange_name": paths.EXCHANGE_NAME,
        "source_url": paths.SOURCE_URL,
        "license": "CC-BY-4.0",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "last_issue_number": last_issue,
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "n_products": n_products,
        "n_observations": len(prices),
        "n_quoted": quoted,
        "observations_per_year": counts,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
