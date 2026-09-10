"""Scarica i bollettini nuovi, ricontrolla quelli recenti e li unisce ai CSV.
Punto d'ingresso della CI.

Legge i CSV, ci aggiunge le rilevazioni nuove e li riscrive.  Il workflow su
GitHub non ha quindi bisogno dell'archivio XML, che pesa una cinquantina di MB e
non e' versionato.

Oltre ai bollettini nuovi riscarica ogni volta gli ultimi gia' acquisiti.  Non e'
zelo: capita che la borsa pubblichi l'XML prima del bollettino PDF ufficiale, con
dentro dati incompleti o sbagliati, e che nei giorni seguenti lo riallinei al PDF
**senza cambiare numero**.  Chi legge solo i numeri nuovi non lo vedrebbe mai, e
si terrebbe la prima versione per sempre.  Le differenze trovate sostituiscono i
valori pubblicati e finiscono in ``dataset/<borsa>/revisions.csv``.

    python -m pipeline.update              # dal bollettino successivo all'ultimo noto
    python -m pipeline.update --from 1424  # forza il punto di partenza
    python -m pipeline.update --recheck 30 # allarga la finestra di ricontrollo
    python -m pipeline.update --dry-run    # scarica e riferisce, non scrive nulla
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from exchanges.verona import fetcher, parser as vr_parser
from pipeline import csvstore, paths

# Quanti numeri consecutivi mancanti prima di concludere che siamo in pari.
# La borsa salta qualche numero (bollettini mensili, settimane di chiusura), per
# cui il primo 404 non significa "non c'e' altro".
PROBE_LIMIT = 6

# Quanti bollettini gia' acquisiti riscaricare a ogni esecuzione per vedere se la
# fonte li ha nel frattempo corretti.  La borsa ne pubblica due o tre a
# settimana: otto numeri coprono circa tre settimane, molto piu' del ritardo con
# cui il PDF ufficiale segue l'XML.  Costa otto richieste al giorno.
RECHECK_ISSUES = 8


def _fetch(number: int, staging: Path, overwrite: bool) -> Path | None:
    status, path = fetcher.fetch_one(number, dest=staging, overwrite=overwrite,
                                     timeout=20.0)
    return path if status == 200 else None


def update(dataset: Path, staging: Path, start: int | None = None,
           sleep: float = 1.0, dry_run: bool = False,
           recheck: int = RECHECK_ISSUES) -> dict:
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
    stats = {"probed": 0, "rechecked": 0, "downloaded": 0, "parsed": 0,
             "new_rows": 0, "updated_rows": 0,
             "last_issue": meta.get("last_issue_number"), "revisions": []}

    downloaded: list[tuple[int, Path]] = []
    requests_made = 0

    # 1. I bollettini gia' acquisiti piu' recenti, riscaricati per forza: la copia
    #    in staging, se c'e', e' proprio quella che vogliamo rimpiazzare.
    for number in range(max(1, start - recheck), start):
        if requests_made:
            time.sleep(sleep)
        requests_made += 1
        stats["rechecked"] += 1
        path = _fetch(number, staging, overwrite=True)
        if path is not None:
            downloaded.append((number, path))

    # 2. I numeri nuovi, finche' non ne mancano PROBE_LIMIT di fila.
    number, misses = start, 0
    while misses < PROBE_LIMIT:
        if requests_made:
            time.sleep(sleep)       # una richiesta al secondo verso un portale pubblico
        requests_made += 1
        stats["probed"] += 1
        path = _fetch(number, staging, overwrite=False)
        if path is not None:
            downloaded.append((number, path))
            stats["downloaded"] += 1
            misses = 0
        else:
            misses += 1
        number += 1

    # Le righe comparse in questa esecuzione non sono mai rettifiche: se un
    # bollettino successivo le ritocca prima che siano finite su disco, il valore
    # "vecchio" non e' mai stato pubblicato e non va nel registro.
    fresh: set[tuple[str, str]] = set()
    before: dict[tuple[str, str], tuple] = {}
    origin: dict[tuple[str, str], int] = {}

    # Ordine crescente: le rettifiche hanno numero piu' alto e devono vincere.
    for issue, path in sorted(downloaded):
        try:
            _meta, records = vr_parser.parse_xml_file(path)
        except ValueError as exc:
            print(f"  ! bollettino {issue}: {exc}", file=sys.stderr)
            continue
        if stats["last_issue"] is None or issue > int(stats["last_issue"]):
            stats["last_issue"] = issue
        if not records:
            continue                # bollettino mensile o settimana di chiusura
        stats["parsed"] += 1
        for rec in records:
            key = (rec.date.isoformat(), rec.product_code)
            value = (rec.low, rec.high)
            if key not in prices:
                fresh.add(key)
                stats["new_rows"] += 1
            elif prices[key] != value and key not in fresh:
                before.setdefault(key, prices[key])
                origin[key] = issue
            prices[key] = value
            products[rec.product_code] = csvstore.Product(
                rec.product_code, rec.product_name,
                " > ".join(rec.category_path), rec.units,
            )

    # Un valore puo' essere cambiato e poi tornato al punto di partenza dentro la
    # stessa esecuzione: confrontare con lo stato iniziale, non passo per passo.
    detected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    revisions = [
        [detected_at, origin[key], key[0], key[1],
         csvstore.fmt(before[key][0]), csvstore.fmt(before[key][1]),
         csvstore.fmt(prices[key][0]), csvstore.fmt(prices[key][1])]
        for key in sorted(before, key=lambda k: (k[0], csvstore.sort_key(k[1])))
        if prices[key] != before[key]
    ]
    stats["revisions"] = revisions
    stats["updated_rows"] = len(revisions)

    if dry_run:
        return stats

    counts = csvstore.write_prices(dataset / "prices", prices)
    n_products = csvstore.write_products(dataset / "products.csv", products, prices)
    csvstore.append_revisions(dataset / "revisions.csv", revisions)
    csvstore.write_meta(dataset / "meta.json", prices, n_products, counts,
                        stats["last_issue"])
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=paths.dataset_dir())
    ap.add_argument("--staging", type=Path, default=None,
                    help="dove salvare gli XML scaricati (default: cartella temporanea)")
    ap.add_argument("--from", dest="start", type=int, default=None)
    ap.add_argument("--recheck", type=int, default=RECHECK_ISSUES,
                    help="quanti bollettini gia' acquisiti riscaricare (0 = nessuno)")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.recheck < 0:
        ap.error("--recheck non puo' essere negativo")

    with tempfile.TemporaryDirectory() as tmp:
        staging = args.staging or Path(tmp)
        stats = update(args.dataset, staging, args.start, args.sleep,
                       args.dry_run, args.recheck)

    print(
        f"  numeri sondati    : {stats['probed']}\n"
        f"  numeri ricontroll.: {stats['rechecked']}\n"
        f"  bollettini nuovi  : {stats['downloaded']} (con dati: {stats['parsed']})\n"
        f"  righe aggiunte    : {stats['new_rows']}\n"
        f"  righe rettificate : {stats['updated_rows']}\n"
        f"  ultimo bollettino : {stats['last_issue']}"
    )
    for row in stats["revisions"][:20]:
        _, issue, day, code, lo_old, hi_old, lo_new, hi_new = row
        print(f"    ~ {day} codice {code} (boll. {issue}): "
              f"{lo_old or '-'}/{hi_old or '-'} → {lo_new or '-'}/{hi_new or '-'}")
    if len(stats["revisions"]) > 20:
        print(f"    … e altre {len(stats['revisions']) - 20}")
    if args.dry_run:
        print("  (dry-run: nessun file scritto)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
