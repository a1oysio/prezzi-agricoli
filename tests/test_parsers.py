"""I parser delle borse, su bollettini veri tenuti in tests/fixtures/.

``python -m tests.test_parsers`` (o pytest).  Non serve la rete, e nemmeno
poppler: dei listini di Bologna c'e' l'uscita di ``pdftotext -tsv`` gia' estratta.

Il controllo principale e' che ogni bollettino, riletto oggi, dica esattamente
quello che sta nel dataset pubblicato: se un ritocco al parser cambia anche un
solo prezzo, o va ricostruito il dataset (``pipeline.rebuild``) o il ritocco e'
sbagliato.  I bollettini sono scelti fuori dalla finestra di ricontrollo della
pipeline (gli ultimi 8 numeri di Verona, 3 listini di Bologna): una rettifica
della fonte non puo' piu' toccarli e far fallire il test senza colpa del parser.
"""
import csv
import gzip
from datetime import date
from pathlib import Path

from exchanges.bologna import layouts
from exchanges.bologna.pdfwords import parse_tsv
from exchanges.bologna.table import parse_day, parse_number
from exchanges.foggia import parser as fg_parser
from exchanges.verona import parser as vr_parser

FIXTURES = Path(__file__).parent / "fixtures"
DATASET = Path(__file__).parent.parent / "dataset"


def _published(exchange: str, day: date, folder: str = "prices") -> dict[str, tuple]:
    out = {}
    with (DATASET / exchange / folder / f"{day.year}.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["date"] == day.isoformat():
                out[r["code"]] = (float(r["low"]) if r["low"] else None,
                                  float(r["high"]) if r["high"] else None)
    return out


def _contained(records, published: dict[str, tuple]) -> None:
    """A Verona lo stesso giorno puo' venire da piu' bollettini (il 14/09/2026:
    303 righe, 293 da questo): di questo devono esserci tutte, uguali."""
    parsed = {r.product_code: (r.low, r.high) for r in records}
    assert {k: published.get(k) for k in parsed} == parsed


def _codes(exchange: str = "bologna") -> dict[tuple[str, str], str]:
    with (DATASET / exchange / "products.csv").open(encoding="utf-8") as fh:
        return {(r["category_path"], r["name"]): r["code"] for r in csv.DictReader(fh)}


def _bologna(name: str, day: date) -> list:
    text = gzip.open(FIXTURES / f"{name}.tsv.gz", "rt", encoding="utf-8").read()
    return layouts.for_date(day).entries(parse_tsv(text), day)


def _check_bologna(name: str, day: date, n: int) -> None:
    entries = _bologna(name, day)
    assert len(entries) == n, len(entries)
    assert {e.date for e in entries} == {day}
    codes = _codes()
    parsed = {codes[(" > ".join(e.path), e.name)]: (e.low, e.high) for e in entries}
    assert parsed == _published("bologna", day)


def test_bologna_a3():
    _check_bologna("2004-01-29_n05", date(2004, 1, 29), 108)
    e = next(e for e in _bologna("2004-01-29_n05", date(2004, 1, 29))
             if e.name.startswith("Nazionale comune"))
    assert (e.path, e.low, e.high, e.prev_date) == (("GRANOTURCO",), 193, 194, date(2004, 1, 22))


def test_bologna_a4():
    _check_bologna("2026-10-08_n39", date(2026, 10, 8), 191)
    first = _bologna("2026-10-08_n39", date(2026, 10, 8))[0]
    assert first.path == ("FRANCO PARTENZA", "FRUMENTO TENERO di produzione nazionale 2026")
    assert (first.low, first.high, first.unit) == (273, 277, "EUR/t")


def _foggia(name: str):
    text = gzip.open(FIXTURES / f"foggia_{name}.tsv.gz", "rt", encoding="utf-8").read()
    return fg_parser.parse_pages(parse_tsv(text), f"{name}.pdf")


def _check_foggia(name: str, day: date, n: int) -> list:
    meta, entries = _foggia(name)
    assert meta.issue_date == day and len(entries) == n, (meta.issue_date, len(entries))
    codes = _codes("foggia")
    parsed = {codes[(" > ".join(e.path), e.name)]: (e.low, e.high) for e in entries}
    assert parsed == _published("foggia", day)
    return entries


def test_foggia_2026():
    entries = _check_foggia("2026-10-21_n40", date(2026, 10, 21), 27)
    by_name = {e.name: e for e in entries}
    # Nome su due righe, una sopra e una sotto i prezzi.
    orzo = by_name["ORZO NAZIONALE Pesante (peso min. 62 kg/hl, umidità max. 12%)"]
    assert (orzo.path, orzo.low, orzo.high) == (("CEREALI MINORI E LEGUMINOSE",), 200, 205)
    # Sottotitolo, e unita' scritta solo li'.
    semola = by_name["Ceneri 0.86-0.90%"]
    assert semola.path == ("SFARINATI", "SEMOLA DI GRANO DURO ITALIANO") and semola.unit == "EUR/t"
    # Il listino CUN in fondo non c'e'.
    assert not any("Fino alto proteico" in e.name for e in entries)


def test_foggia_2021_invisible_characters():
    # Un carattere invisibile al posto di ogni spazio, e iniziali staccate
    # ("GRANO D URO"): devono uscire nomi normali.
    entries = _check_foggia("2021-08-25_n08", date(2021, 8, 25), 27)
    assert entries[0].path == ("GRANO DURO",)
    assert any(e.name.startswith("ORZO NAZIONALE Pesante") for e in entries)


def test_verona_weekly():
    meta, records = vr_parser.parse_xml_file(FIXTURES / "1451.xml")
    assert (meta.issue_number, meta.issue_date, meta.file_type) == (1451, date(2026, 9, 14), "XML")
    assert len(records) == 293
    _contained(records, _published("verona", date(2026, 9, 14)))
    polli = next(r for r in records if r.product_code == "674")
    assert polli.units == "EUR/kg"


def test_verona_fortnightly_goes_to_averages():
    meta, records = vr_parser.parse_xml_file(FIXTURES / "1452.xml")
    assert meta.file_type == vr_parser.AVERAGE_FILE_TYPE
    assert {r.date for r in records} == {date(2026, 9, 15)}
    _contained(records, _published("verona", date(2026, 9, 15), "averages"))


def test_numbers_and_dates():
    assert parse_number("1.234,50") == 1234.5
    assert parse_number("193,00") == 193
    assert parse_number("n.q.") is None
    assert parse_day("25 mar", date(2026, 3, 26)) == date(2026, 3, 25)
    assert parse_day("30 dic", date(2026, 1, 2)) == date(2025, 12, 30)
    assert parse_day("1-ott-26", date(2026, 10, 1)) == date(2026, 10, 1)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
