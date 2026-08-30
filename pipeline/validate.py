"""Gate di qualita' sui CSV pubblicati.

Gira in CI prima del commit: se trova un errore il workflow non pubblica nulla e
apre una issue.  Serve perche' la pipeline scrive senza supervisione umana, e un
parser che si rompe in silenzio e' peggio di un parser che si ferma.

    python -m pipeline.validate          # 0 = ok, 1 = errori

Le anomalie sono divise in errori (bloccano) e avvisi (si segnalano soltanto):
un dato assurdo puo' essere assurdo alla fonte, e in quel caso va pubblicato
com'e' e segnalato, non corretto di nascosto.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from pipeline import paths

VALID_UNITS = {
    "EUR/t", "EUR/kg", "EUR/L", "EUR/1000L",
    "EUR/grado-hL", "EUR/grado-100kg", "EUR/100pz", "unknown",
}

# Un prezzo che si scosta dalla mediana storica del suo prodotto di piu' di
# questo fattore e' quasi sempre un errore di scala alla fonte.  Riferimento:
# le olive per olio d.o.p. hanno mediana 1,15-1,40 EUR/kg ma fra ottobre e
# dicembre 2022 la borsa le ha pubblicate fra 70 e 140.
OUTLIER_FACTOR = 10.0
MIN_HISTORY_FOR_OUTLIER = 12
FIRST_PLAUSIBLE_DATE = date(2000, 1, 1)

# La borsa data il listino al giorno della rilevazione e lo pubblica prima: un
# bollettino scaricato oggi puo' portare legittimamente la data della settimana
# entrante.  Oltre questo margine, pero', e' un anno o un mese letto male.
FUTURE_TOLERANCE_DAYS = 15


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def render(self) -> str:
        out = []
        if self.errors:
            out.append(f"ERRORI ({len(self.errors)}):")
            out += [f"  ✗ {e}" for e in self.errors[:40]]
            if len(self.errors) > 40:
                out.append(f"  … e altri {len(self.errors) - 40}")
        if self.warnings:
            out.append(f"AVVISI ({len(self.warnings)}):")
            out += [f"  ! {w}" for w in self.warnings[:40]]
            if len(self.warnings) > 40:
                out.append(f"  … e altri {len(self.warnings) - 40}")
        if not self.errors and not self.warnings:
            out.append("Nessuna anomalia.")
        return "\n".join(out)


def _read_products(path: Path, rep: Report) -> dict[str, dict]:
    products: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = row["code"]
            if code in products:
                rep.error(f"products.csv: codice duplicato '{code}'")
            if row["unit"] not in VALID_UNITS:
                rep.error(f"products.csv: unita' ignota '{row['unit']}' per il codice {code}")
            if row["unit"] == "unknown":
                rep.warn(f"codice {code}: unita' non determinata")
            products[code] = row
    return products


def _read_prices(dir_: Path, products: dict[str, dict], rep: Report):
    seen: set[tuple[str, str]] = set()
    series: dict[str, list[tuple[str, float]]] = defaultdict(list)
    total = 0

    for csv_file in sorted(dir_.glob("*.csv")):
        year = csv_file.stem
        with csv_file.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != ["date", "code", "low", "high"]:
                rep.error(f"{csv_file.name}: intestazione inattesa {reader.fieldnames}")
                continue
            for n, row in enumerate(reader, start=2):
                total += 1
                where = f"{csv_file.name}:{n}"
                try:
                    d = date.fromisoformat(row["date"])
                except ValueError:
                    rep.error(f"{where}: data non valida '{row['date']}'")
                    continue
                if str(d.year) != year:
                    rep.error(f"{where}: data {d} nel file dell'anno {year}")
                horizon = date.today() + timedelta(days=FUTURE_TOLERANCE_DAYS)
                if d < FIRST_PLAUSIBLE_DATE or d > horizon:
                    rep.error(f"{where}: data fuori intervallo plausibile ({d})")

                code = row["code"]
                if code not in products:
                    rep.error(f"{where}: codice {code} assente da products.csv")
                key = (row["date"], code)
                if key in seen:
                    rep.error(f"{where}: coppia (data, codice) duplicata {key}")
                seen.add(key)

                lo = float(row["low"]) if row["low"] else None
                hi = float(row["high"]) if row["high"] else None
                # Il parser converte zeri e negativi in campi vuoti: se ne
                # ricompare uno, e' la nostra pipeline ad essersi rotta.
                if lo is not None and lo <= 0:
                    rep.error(f"{where}: prezzo minimo non positivo ({lo})")
                if hi is not None and hi <= 0:
                    rep.error(f"{where}: prezzo massimo non positivo ({hi})")
                if lo is not None and hi is not None and lo > hi:
                    # Errore della fonte, non nostro: capita che la borsa
                    # pubblichi una coppia incoerente (2022-03-30, codice 672:
                    # 480/250 fra vicini a 480/490).  Va segnalato, non deve
                    # bloccare la pubblicazione per sempre.
                    rep.warn(f"{where}: minimo {lo} maggiore del massimo {hi}")
                if lo is not None and hi is not None:
                    series[code].append((row["date"], (lo + hi) / 2))
    return total, series


def _check_outliers(series, rep: Report) -> None:
    for code, points in series.items():
        if len(points) < MIN_HISTORY_FOR_OUTLIER:
            continue
        med = statistics.median(v for _, v in points)
        if med <= 0:
            continue
        odd = [(d, v) for d, v in points
               if v > med * OUTLIER_FACTOR or v < med / OUTLIER_FACTOR]
        if odd:
            span = f"{min(d for d, _ in odd)}…{max(d for d, _ in odd)}"
            rep.warn(
                f"codice {code}: {len(odd)} valori oltre {OUTLIER_FACTOR:g}x "
                f"dalla mediana {med:.2f} ({span})"
            )


def _check_no_regression(meta_file: Path, total: int, rep: Report) -> None:
    """Il dataset puo' solo crescere: un calo segnala un parser che si e' rotto."""
    if not meta_file.exists():
        return
    previous = json.loads(meta_file.read_text(encoding="utf-8")).get("n_observations")
    if previous is not None and total < previous:
        rep.error(
            f"il dataset e' passato da {previous} a {total} osservazioni: "
            f"mancano {previous - total} righe"
        )


def validate(dataset: Path) -> Report:
    rep = Report()
    products_file = dataset / "products.csv"
    prices = dataset / "prices"

    if not products_file.exists():
        rep.error(f"manca {products_file}")
        return rep
    if not prices.is_dir() or not any(prices.glob("*.csv")):
        rep.error(f"nessun CSV di prezzi in {prices}")
        return rep

    products = _read_products(products_file, rep)
    total, series = _read_prices(prices, products, rep)
    _check_outliers(series, rep)
    _check_no_regression(dataset / "meta.json", total, rep)

    orphans = set(products) - {c for c in series} - {
        c for c in products if products[c]["n_observations"] == "0"
    }
    for code in sorted(orphans, key=lambda c: int(c) if c.isdigit() else 0):
        if products[code]["n_quoted"] == "0":
            rep.warn(f"codice {code}: nessuna quotazione, solo righe vuote")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=paths.dataset_dir())
    args = ap.parse_args()

    rep = validate(args.dataset)
    print(rep.render())
    if rep.errors:
        print(f"\nValidazione FALLITA: {len(rep.errors)} errori.", file=sys.stderr)
        return 1
    print(f"\nValidazione superata ({len(rep.warnings)} avvisi).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
