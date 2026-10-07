"""Aggiorna e ricostruisce il dataset della Borsa Merci di Bologna.

Come Verona, ma la fonte e' diversa: PDF settimanali invece di XML numerati.
Tre differenze guidano il codice:

* **Niente numeri di bollettino consecutivi.**  I file non hanno un numero
  prevedibile (la numerazione riparte ogni anno), quindi si elencano dalle
  pagine della Camera di Commercio e si ricorda quali sono gia' stati acquisiti
  in ``issues.csv``, che e' anche la provenienza di ogni data.

* **Ogni data compare due volte.**  Un listino riporta la settimana corrente e
  la precedente.  Il valore di una data e' quindi stampato nel suo listino e
  poi ancora in quello successivo: se i due non coincidono, la fonte si e'
  corretta, e la correzione finisce in ``revisions.csv`` come a Verona.  Le
  colonne "precedente" servono anche a riempire una settimana il cui listino
  manca dall'archivio.

* **Niente codici.**  Li assegna ``exchanges.bologna.identity``.

    python -m pipeline.bologna rebuild              # da data/bologna (PDF scaricati)
    python -m pipeline.bologna download             # scarica l'archivio in data/bologna
    python -m pipeline.bologna update               # nuovi listini + ricontrollo degli ultimi
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from exchanges.bologna import fetcher, identity, parser
from pipeline import csvstore, paths

EXCHANGE = paths.EXCHANGES["bologna"]

# Si riscarica solo il listino piu' recente.  Non e' parsimonia: riscaricarne
# di piu' vecchi sarebbe sbagliato.  Il valore di una data e' stampato nel suo
# listino e poi, eventualmente corretto, in quello successivo; rileggere il
# listino D dopo che D+1 l'ha corretto riscriverebbe il valore *vecchio* sopra
# quello nuovo, e la rettifica rimbalzerebbe avanti e indietro a ogni giorno.
# Sul piu' recente non puo' succedere: nessun listino successivo l'ha toccato.
# Le correzioni dei listini precedenti le vediamo comunque, nella colonna
# "settimana precedente" di quelli nuovi.

# Un listino con meno righe di questo ha cambiato layout o e' un file sbagliato:
# fermarsi e' meglio che pubblicare un'altra settimana quasi vuota.
MIN_ROWS = 100

ISSUES_HEADER = ["date", "number", "source"]
SKIPPED_HEADER = ["source", "reason"]
SERIES_HEADER = ["code", "series"]


@dataclass
class State:
    prices: dict = field(default_factory=dict)
    products: dict[str, csvstore.Product] = field(default_factory=dict)
    by_key: dict[str, str] = field(default_factory=dict)
    issues: dict[str, tuple[str, int]] = field(default_factory=dict)  # source -> (data, numero)
    skipped: dict[str, str] = field(default_factory=dict)             # source -> motivo
    revisions: list[list] = field(default_factory=list)
    origin: dict[tuple[str, str], str] = field(default_factory=dict)  # chi ha scritto il valore, in questa esecuzione
    stats: dict = field(default_factory=lambda: {
        "bulletins": 0, "new_rows": 0, "filled_rows": 0, "revisions": 0,
        "mismatches": 0, "unassigned": 0, "blanked_prev_ignored": 0})

    def next_code(self) -> str:
        return str(1 + max((int(c) for c in self.products), default=0))


_MODIFIED = re.compile(r"(?i)(?:modif|\bmod\b|\d\s*mod\b|\bcorr\b|errata)")


def is_modified(source: str) -> bool:
    """Il file e' una ripubblicazione corretta ("... 2016 modif.pdf", "... MOD.pdf")."""
    return bool(_MODIFIED.search(source))


def _issue_id(b: parser.ParsedBulletin, source: str = "") -> str:
    # Una ripubblicazione ha un'identita' propria: se coesiste con l'originale
    # deve vincere ed essere registrata come rettifica, non sovrascritta in silenzio.
    return f"{b.date.year}-{b.number}" + ("-mod" if is_modified(source) else "")


def load(dataset: Path) -> State:
    st = State()
    st.prices = csvstore.read_prices(dataset / "prices")
    st.products = csvstore.read_products(dataset / "products.csv")
    for code, p in st.products.items():
        path = tuple(p.category_path.split(" > ")) if p.category_path else ()
        st.by_key[identity.product_key(path, p.name)] = code
    f = dataset / "issues.csv"
    if f.exists():
        with f.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                st.issues[row["source"]] = (row["date"], int(row["number"]))
    f = dataset / "skipped.csv"
    if f.exists():
        with f.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                st.skipped[row["source"]] = row["reason"]
    return st


def _code_for(st: State, row: parser.Row) -> str:
    key = identity.product_key(row.path, row.label)
    code = st.by_key.get(key)
    if code is None:
        code = st.next_code()
        st.by_key[key] = code
    # Il nome e l'unita' sono quelli dell'ultimo listino, come a Verona.
    st.products[code] = csvstore.Product(code, row.label, " > ".join(row.path), row.unit)
    return code


def _set(st: State, key: tuple[str, str], value: tuple, issue: str, detected_at: str,
         from_prev: bool = False) -> None:
    """Scrive un valore.  Se ne esisteva uno diverso, di un altro listino, e' una rettifica.

    Un valore preso dalla colonna "settimana precedente" puo' riempire un buco o
    cambiarne un altro, ma **non puo' cancellare un prezzo**: a volte la Camera
    svuota quella colonna senza che nulla sia stato ritirato (il listino n. 36
    del 2019 la mostra a trattini per tutti i vini, che il n. 35 aveva quotato).
    Applicarlo azzererebbe quotazioni vere; si conta e basta.
    """
    old = st.prices.get(key)
    if old is None and key not in st.prices:
        st.prices[key] = value
        st.origin[key] = issue
        st.stats["filled_rows" if from_prev else "new_rows"] += 1
        return
    if (from_prev and value == (None, None) and old != (None, None)
            and st.origin.get(key) != issue):
        st.stats["blanked_prev_ignored"] += 1
        return
    if old != value and st.origin.get(key) != issue:
        st.revisions.append([
            detected_at, issue, key[0], key[1],
            csvstore.fmt(old[0]), csvstore.fmt(old[1]),
            csvstore.fmt(value[0]), csvstore.fmt(value[1]),
        ])
        st.stats["revisions"] += 1
    st.prices[key] = value
    st.origin[key] = issue


def ingest(st: State, b: parser.ParsedBulletin, source: str, detected_at: str) -> None:
    """Un listino nel dataset: la settimana corrente e la precedente."""
    issue = _issue_id(b, source)
    st.stats["bulletins"] += 1
    st.stats["mismatches"] += len(b.mismatches)
    st.stats["unassigned"] += len(b.unassigned)
    st.issues[source] = (b.date.isoformat(), b.number)

    for row in b.rows:
        code = _code_for(st, row)
        if row.cur_listed:
            _set(st, (b.date.isoformat(), code), row.cur, issue, detected_at)
        if row.prev_listed and b.prev_date is not None:
            _set(st, (b.prev_date.isoformat(), code), row.prev, issue, detected_at,
                 from_prev=True)


def write(dataset: Path, st: State, rewrite_revisions: bool) -> dict:
    counts = csvstore.write_prices(dataset / "prices", st.prices)
    n_products = csvstore.write_products(dataset / "products.csv", st.products, st.prices)

    rev_file = dataset / "revisions.csv"
    if rewrite_revisions:
        rev_file.unlink(missing_ok=True)
    csvstore.append_revisions(rev_file, st.revisions)

    with (dataset / "issues.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(ISSUES_HEADER)
        for source, (d, n) in sorted(st.issues.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[0])):
            w.writerow([d, n, source])

    skipped_file = dataset / "skipped.csv"
    if st.skipped:
        with skipped_file.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(SKIPPED_HEADER)
            for source in sorted(st.skipped):
                w.writerow([source, st.skipped[source]])
    else:
        skipped_file.unlink(missing_ok=True)

    overrides = _read_overrides(dataset / "series_overrides.csv")
    with (dataset / "series.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(SERIES_HEADER)
        for code in sorted(st.products, key=csvstore.sort_key):
            p = st.products[code]
            s = overrides.get(code) or identity.series_key(
                tuple(p.category_path.split(" > ")) if p.category_path else (), p.name)
            if s:
                w.writerow([code, s])

    last = max(st.issues.values(), default=None)
    csvstore.write_meta(
        dataset / "meta.json", st.prices, n_products, counts, None, EXCHANGE,
        extra={"last_issue": f"{last[0][:4]}-{last[1]}" if last else None,
               "n_issues": len(st.issues)})
    return {"products": n_products, "prices": len(st.prices)}


def _read_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return {r["code"]: r["series"] for r in csv.DictReader(fh)}


GARBLED = "testo del PDF illeggibile (encoding): la settimana si recupera dal listino successivo"


def _parse_all(files: list[Path]) -> tuple[list[tuple[parser.ParsedBulletin, Path]],
                                           dict[str, str], dict[str, str]]:
    """(letti, difetti del file, guasti del parser).

    I primi sono noti e innocui; i secondi, layout cambiato, vanno segnalati.
    """
    parsed: list[tuple[parser.ParsedBulletin, Path]] = []
    garbled: dict[str, str] = {}
    broken: dict[str, str] = {}
    for f in files:
        try:
            b = parser.parse_pdf(f)
        except parser.UnreadablePdf as exc:
            if exc.garbled:
                garbled[f.name] = GARBLED
            else:
                broken[f.name] = str(exc).split(": ", 1)[-1]
            continue
        if len(b.rows) < MIN_ROWS:
            broken[f.name] = f"solo {len(b.rows)} righe: layout cambiato o file sbagliato"
            continue
        parsed.append((b, f))
    parsed.sort(key=lambda x: (x[0].date, x[0].number, is_modified(x[1].name), x[1].name))
    return parsed, garbled, broken


def rebuild(src_dir: Path, dataset: Path) -> dict:
    """Ricostruisce tutto dai PDF in ``src_dir``, da zero."""
    files = sorted(src_dir.glob("*.pdf"))
    parsed, garbled, broken = _parse_all(files)
    failed = {**garbled, **broken}
    st = State()
    st.skipped = dict(failed)
    for b, f in parsed:
        # Nella ricostruzione non sappiamo quando una rettifica e' stata vista:
        # si usa il giorno del listino che la porta, cosi' due esecuzioni sugli
        # stessi file danno lo stesso registro.
        ingest(st, b, f.name, f"{b.date.isoformat()}T00:00:00+00:00")
    stats = write(dataset, st, rewrite_revisions=True)
    return {**st.stats, **stats, "files": len(files), "failed": failed}


def update(dataset: Path, staging: Path, recheck: bool = True,
           sleep: float = 1.0, dry_run: bool = False) -> dict:
    st = load(dataset)
    if not st.issues:
        raise SystemExit("Dataset vuoto: parti da `python -m pipeline.bologna rebuild`.")

    urls = [u for u in fetcher.list_issues() if "anno-2012" not in u]
    known = set(st.issues) | set(st.skipped)    # gli scartati non si riprovano ogni giorno
    new = [u for u in urls if fetcher.local_name(u) not in known]
    # I piu' recenti gia' acquisiti, da riscaricare per confrontarli con la fonte.
    latest = sorted(st.issues, key=lambda s: st.issues[s])[-1:] if recheck else []
    by_name = {fetcher.local_name(u): u for u in urls}
    again = [by_name[s] for s in latest if s in by_name]

    staging.mkdir(parents=True, exist_ok=True)
    fetched_new = fetcher.fetch_many(new, staging, sleep=sleep)
    fetched_again = fetcher.fetch_many(again, staging, sleep=sleep, overwrite=True)
    files = [p for p in {**fetched_again, **fetched_new}.values() if p is not None]
    missing = [u for u, p in {**fetched_again, **fetched_new}.items() if p is None]
    if missing:
        raise SystemExit("Download fallito: " + ", ".join(missing[:5]))

    parsed, garbled, broken = _parse_all(files)
    if broken:
        # Un listino nuovo con testo regolare ma non riconosciuto e' il segnale
        # che il layout e' cambiato: ci si ferma, non si pubblica una settimana vuota.
        raise SystemExit("Listini non riconosciuti (layout cambiato?):\n  "
                         + "\n  ".join(f"{k}: {v}" for k, v in broken.items()))
    # Un PDF con i caratteri corrotti e' un difetto della fonte: si registra e si
    # va avanti, la settimana arriva dal listino successivo.
    st.skipped.update(garbled)

    detected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    before = len(st.revisions)
    for b, f in parsed:
        ingest(st, b, f.name, detected_at)
    result = {**st.stats, "new_files": len(new), "rechecked": len(again),
              "garbled": sorted(garbled), "revision_rows": st.revisions[before:]}
    if not dry_run:
        # Il registro delle rettifiche si scrive in coda, mai riscritto.
        write(dataset, st, rewrite_revisions=False)
    return result


def download(dest: Path, sleep: float = 1.0) -> dict:
    urls = [u for u in fetcher.list_issues() if "anno-2012" not in u]
    got = fetcher.fetch_many(urls, dest, sleep=sleep)
    return {"urls": len(urls), "ok": sum(1 for p in got.values() if p),
            "failed": [u for u, p in got.items() if p is None]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("rebuild", "download", "update"):
        sp = sub.add_parser(name)
        sp.add_argument("--dataset", type=Path, default=paths.dataset_dir("bologna"))
        sp.add_argument("--archive", type=Path, default=paths.archive_dir("bologna"),
                        help="dove stanno i PDF scaricati")
    sub.choices["update"].add_argument(
        "--no-recheck", dest="recheck", action="store_false",
        help="non riscaricare il listino piu' recente gia' acquisito")
    sub.choices["update"].add_argument("--dry-run", action="store_true")
    for name in ("download", "update"):
        sub.choices[name].add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    if args.cmd == "download":
        r = download(args.archive, args.sleep)
        print(f"  elenco: {r['urls']}  scaricati: {r['ok']}  falliti: {len(r['failed'])}")
        return 1 if r["failed"] else 0

    if args.cmd == "rebuild":
        if not any(args.archive.glob("*.pdf")):
            print(f"Nessun PDF in {args.archive}: esegui prima `download`.", file=sys.stderr)
            return 1
        r = rebuild(args.archive, args.dataset)
        print(f"  file letti        : {r['files']} (non letti: {len(r['failed'])})\n"
              f"  listini acquisiti : {r['bulletins']}\n"
              f"  prodotti          : {r['products']}\n"
              f"  rilevazioni       : {r['prices']}\n"
              f"    dai listini     : {r['new_rows']}\n"
              f"    dalla colonna 'precedente' (settimane senza listino): {r['filled_rows']}\n"
              f"  rettifiche della fonte: {r['revisions']}\n"
              f"  colonne 'precedente' svuotate dalla fonte, ignorate: {r['blanked_prev_ignored']}\n"
              f"  differenze che non tornano (stampato vs calcolato): {r['mismatches']}\n"
              f"  righe non collocate: {r['unassigned']}")
        for name, why in list(r["failed"].items())[:40]:
            print(f"  ! non letto: {name}: {why}", file=sys.stderr)
        return 0

    r = update(args.dataset, args.archive, args.recheck, args.sleep, args.dry_run)
    print(f"  listini nuovi     : {r['new_files']}\n"
          f"  ricontrollati     : {r['rechecked']}\n"
          f"  righe aggiunte    : {r['new_rows']} (+{r['filled_rows']} da colonna 'precedente')\n"
          f"  rettifiche        : {r['revisions']}\n"
          f"  differenze che non tornano: {r['mismatches']}")
    for row in r["revision_rows"][:20]:
        _, issue, day, code, lo_o, hi_o, lo_n, hi_n = row
        print(f"    ~ {day} codice {code} (listino {issue}): "
              f"{lo_o or '-'}/{hi_o or '-'} → {lo_n or '-'}/{hi_n or '-'}")
    for name in r["garbled"]:
        print(f"  ! testo illeggibile, saltato: {name}", file=sys.stderr)
    if args.dry_run:
        print("  (dry-run: nessun file scritto)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
