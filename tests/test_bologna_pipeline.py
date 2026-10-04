"""La pipeline di Bologna: codici, settimane mancanti, rettifiche, determinismo."""
import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from exchanges.bologna import identity, parser
from pipeline import bologna


def bulletin(d: date, number: int, rows, prev: date | None = None) -> parser.ParsedBulletin:
    """``rows``: (percorso, etichetta, corrente, precedente); None = cella assente."""
    b = parser.ParsedBulletin(number=number, date=d, prev_date=prev)
    for path, label, cur, prv in rows:
        b.rows.append(parser.Row(
            path=tuple(path), label=label, unit="EUR/t",
            cur=cur or (None, None), prev=prv or (None, None), printed_diff=(None, None),
            cur_listed=cur is not None, prev_listed=prv is not None))
    return b


SEC = ("FRUMENTO TENERO di produzione nazionale",)
LATER = "2026-01-01T00:00:00+00:00"


def ingest_all(*items):
    st = bologna.State()
    for b, name in items:
        bologna.ingest(st, b, name, f"{b.date}T00:00:00+00:00")
    return st


class Codes(unittest.TestCase):
    def test_same_product_keeps_its_code_across_bulletins(self):
        a = bulletin(date(2026, 9, 24), 37, [(SEC, "n° 1 - speciali", (273.0, 277.0), None)])
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "n° 1 - speciali", (275.0, 280.0), None)])
        st = ingest_all((a, "a.pdf"), (b, "b.pdf"))
        self.assertEqual(list(st.products), ["1"])

    def test_spacing_differences_do_not_split_a_product(self):
        a = bulletin(date(2026, 9, 24), 37, [(SEC, "comunitario - escl. nazionale - ad uso", (1.0, 2.0), None)])
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "comunitario -escl. nazionale -ad uso", (1.0, 2.0), None)])
        self.assertEqual(len(ingest_all((a, "a.pdf"), (b, "b.pdf")).products), 1)

    def test_a_changed_specification_is_a_new_code(self):
        # Fedele alla fonte: la specifica e' cambiata, il codice anche.
        a = bulletin(date(2025, 9, 25), 38, [(SEC, "n° 1 - speciali - p.s. 79/80", (264.0, 269.0), None)])
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "n° 1 - speciali - p.s. 80", (273.0, 277.0), None)])
        self.assertEqual(len(ingest_all((a, "a.pdf"), (b, "b.pdf")).products), 2)

    def test_the_name_shown_is_the_latest_published(self):
        a = bulletin(date(2026, 9, 24), 37, [(SEC, "orzo  -  p.s. 62/64", (198.0, 203.0), None)])
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "orzo - p.s. 62/64", (198.0, 203.0), None)])
        st = ingest_all((a, "a.pdf"), (b, "b.pdf"))
        self.assertEqual(st.products["1"].name, "orzo - p.s. 62/64")


class PreviousWeek(unittest.TestCase):
    def test_previous_week_fills_a_missing_bulletin(self):
        # Il listino del 24/9 manca dall'archivio: lo riempie la colonna del 1/10.
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "n° 1", (275.0, 280.0), (273.0, 277.0))],
                     prev=date(2026, 9, 24))
        st = ingest_all((b, "b.pdf"))
        self.assertEqual(st.prices[("2026-09-24", "1")], (273.0, 277.0))
        self.assertEqual(st.stats["filled_rows"], 1)
        self.assertEqual(st.revisions, [])

    def test_agreeing_columns_are_not_a_revision(self):
        a = bulletin(date(2026, 9, 24), 37, [(SEC, "n° 1", (273.0, 277.0), None)])
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "n° 1", (275.0, 280.0), (273.0, 277.0))],
                     prev=date(2026, 9, 24))
        self.assertEqual(ingest_all((a, "a.pdf"), (b, "b.pdf")).revisions, [])

    def test_disagreeing_columns_are_a_logged_revision_and_the_newer_wins(self):
        a = bulletin(date(2026, 9, 24), 37, [(SEC, "n° 1", (273.0, 277.0), None)])
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "n° 1", (275.0, 280.0), (270.0, 277.0))],
                     prev=date(2026, 9, 24))
        st = ingest_all((a, "a.pdf"), (b, "b.pdf"))
        self.assertEqual(st.prices[("2026-09-24", "1")], (270.0, 277.0))
        det, issue, day, code, lo_o, hi_o, lo_n, hi_n = st.revisions[0]
        self.assertEqual((issue, day, code, lo_o, hi_o, lo_n, hi_n),
                         ("2026-38", "2026-09-24", "1", "273", "277", "270", "277"))

    def test_blank_previous_cells_do_not_create_rows(self):
        # Prodotto comparso questa settimana: la colonna precedente e' vuota.
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "nuovo", (10.0, 12.0), None)], prev=date(2026, 9, 24))
        self.assertEqual(list(ingest_all((b, "b.pdf")).prices), [("2026-10-01", "1")])

    def test_dash_cells_are_kept_as_unquoted_rows(self):
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "n° 5", (None, None), (None, None))],
                     prev=date(2026, 9, 24))
        st = ingest_all((b, "b.pdf"))
        self.assertEqual(st.prices[("2026-10-01", "1")], (None, None))
        self.assertEqual(st.prices[("2026-09-24", "1")], (None, None))

    def test_blank_previous_column_never_erases_a_published_price(self):
        # Il n. 36 del 2019 mostra a trattini la colonna "precedente" di tutti i
        # vini che il n. 35 aveva quotato.  Non e' un ritiro: e' la tabella
        # svuotata.  Il prezzo del n. 35 deve restare.
        a = bulletin(date(2026, 9, 24), 37, [(SEC, "n° 1", (273.0, 277.0), None)])
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "n° 1", (275.0, 280.0), (None, None))],
                     prev=date(2026, 9, 24))
        st = ingest_all((a, "a.pdf"), (b, "b.pdf"))
        self.assertEqual(st.prices[("2026-09-24", "1")], (273.0, 277.0))
        self.assertEqual(st.revisions, [])
        self.assertEqual(st.stats["blanked_prev_ignored"], 1)

    def test_a_current_column_retraction_by_a_reissued_bulletin_is_applied(self):
        # Diverso: lo stesso listino, riscaricato, ora dice "non quotato" per la
        # propria settimana.  E' la fonte che ritira il dato.
        a = bulletin(date(2026, 10, 1), 38, [(SEC, "n° 1", (275.0, 280.0), None)])
        b = bulletin(date(2026, 10, 1), 38, [(SEC, "n° 1", (None, None), None)])
        st = ingest_all((a, "a.pdf"), (b, "b-modif.pdf"))
        self.assertEqual(st.prices[("2026-10-01", "1")], (None, None))
        self.assertEqual(st.revisions[0][6:], ["", ""])


class Republished(unittest.TestCase):
    def test_modified_file_wins_over_the_original_and_is_logged(self):
        orig = bulletin(date(2016, 7, 14), 27, [(SEC, "n° 1", (200.0, 205.0), None)])
        mod = bulletin(date(2016, 7, 14), 27, [(SEC, "n° 1", (200.0, 210.0), None)])
        st = ingest_all((orig, "anno-2016__n. 27 - 14 luglio 2016.pdf"),
                        (mod, "anno-2016__n. 27 - 14 luglio 2016 modif.pdf"))
        self.assertEqual(st.prices[("2016-07-14", "1")], (200.0, 210.0))
        self.assertEqual(st.revisions[0][1], "2016-27-mod")

    def test_which_names_count_as_modified(self):
        for name in ("n. 27 - 14 luglio 2016 modif.pdf", "n. 31 - 24 agosto 2017MOD.pdf",
                     "n. 28 - 23 luglio 2020 MOD.pdf", "n. 27 - 8 luglio 2021 corr.pdf"):
            self.assertTrue(bologna.is_modified(name), name)
        for name in ("n.38_ 1 ottobre_2026.pdf", "n. 12 - 19 marzo 2020.pdf", "Listino del 21 agosto 2025.pdf",
                     "n.-28-10-luglio-2014.pdf", "n. 6 - 13 febbraio 2020.pdf"):
            self.assertFalse(bologna.is_modified(name), name)


class Series(unittest.TestCase):
    def test_wheat_grades_join_across_specification_changes(self):
        k = identity.series_key
        a = k(SEC, "n° 1 - speciali di forza - prot. 14%, p.s. 79/80 kg/hl, c.e. 1%")
        b = k(SEC, "n° 1 - speciali di forza - prot. 13,5%, p.s. 80 kg/hl min., c.e. 1%")
        self.assertEqual(a, b)
        self.assertEqual(a, "FRUMENTO TENERO di produzione nazionale > n. 1 - speciali di forza")

    def test_old_heading_with_delivery_terms_joins_the_new_one(self):
        old = ("FRUMENTO TENERO di produzione nazionale - merce posta su veicolo partenza magazzino produttore",)
        self.assertEqual(identity.series_key(old, "n° 3 - fino - p.s. 78 kg/hl"),
                         identity.series_key(SEC, "n° 3 - fino - prot. 11% min"))

    def test_durum_areas_stay_apart(self):
        nord = ("FRUMENTO DURO di produzione nazionale, nord",)
        centro = ("FRUMENTO DURO di produzione nazionale, centro",)
        self.assertNotEqual(identity.series_key(nord, "fino - prot. 13%"),
                            identity.series_key(centro, "fino - prot. 13%"))

    def test_barley_is_never_merged_automatically(self):
        # "p.s. 58/60" diventa "62/64": e' un giudizio agronomico, non una regex.
        sec = ("CEREALI MINORI E LEGUMINOSE",)
        self.assertIsNone(identity.series_key(sec, "orzo - p.s. 62/64"))

    def test_fino_outside_wheat_is_not_a_grade(self):
        self.assertIsNone(identity.series_key(("FARINE",), "fino - tipo 00"))


class Files(unittest.TestCase):
    def build(self, tmp: Path):
        items = [
            (bulletin(date(2026, 9, 24), 37, [(SEC, "n° 1", (273.0, 277.0), None)]), "a.pdf"),
            (bulletin(date(2026, 10, 1), 38, [(SEC, "n° 1", (275.0, 280.0), (270.0, 277.0))],
                      prev=date(2026, 9, 24)), "b.pdf"),
        ]
        st = bologna.State()
        for b, name in items:
            bologna.ingest(st, b, name, f"{b.date}T00:00:00+00:00")
        bologna.write(tmp, st, rewrite_revisions=True)

    def test_two_writes_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.build(Path(a))
            self.build(Path(b))
            for f in ("products.csv", "prices/2026.csv", "revisions.csv", "issues.csv", "series.csv"):
                self.assertEqual((Path(a) / f).read_bytes(), (Path(b) / f).read_bytes(), f)

    def test_load_roundtrip_keeps_codes_and_continues_numbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.build(Path(tmp))
            st = bologna.load(Path(tmp))
            self.assertEqual(list(st.products), ["1"])
            self.assertEqual(set(st.issues), {"a.pdf", "b.pdf"})
            nxt = bulletin(date(2026, 10, 8), 39, [(SEC, "n° 1", (276.0, 281.0), (275.0, 280.0)),
                                                    (SEC, "n° 2", (264.0, 268.0), None)],
                           prev=date(2026, 10, 1))
            bologna.ingest(st, nxt, "c.pdf", LATER)
            self.assertEqual(list(st.products), ["1", "2"])    # n° 1 riconosciuto, n° 2 nuovo
            self.assertEqual(st.revisions, [])                 # il 1/10 coincide con quanto salvato

    def test_series_overrides_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "series_overrides.csv").write_text("code,series\n1,orzo\n", encoding="utf-8")
            self.build(tmp)
            with (tmp / "series.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows, [{"code": "1", "series": "orzo"}])

    def test_revision_registry_is_appended_not_rewritten_on_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.build(tmp)
            first = (tmp / "revisions.csv").read_text(encoding="utf-8")
            st = bologna.load(tmp)
            nxt = bulletin(date(2026, 10, 8), 39, [(SEC, "n° 1", (276.0, 281.0), (275.0, 282.0))],
                           prev=date(2026, 10, 1))
            bologna.ingest(st, nxt, "c.pdf", LATER)
            bologna.write(tmp, st, rewrite_revisions=False)
            now = (tmp / "revisions.csv").read_text(encoding="utf-8")
            self.assertTrue(now.startswith(first))
            self.assertEqual(now.count("\n"), first.count("\n") + 1)


class UpdateFlow(unittest.TestCase):
    """``update`` con rete e PDF simulati."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ds, self.stage = self.root / "ds", self.root / "stage"
        self.urls = {
            "a": "https://x/listino-dei-prezzi-settimanali/anno-2026/a.pdf",
            "b": "https://x/listino-dei-prezzi-settimanali/anno-2026/b.pdf",
            "c": "https://x/listino-dei-prezzi-settimanali/anno-2026/c.pdf",
            "old": "https://x/listino-dei-prezzi-settimanali/anno-2013/old.pdf",
        }
        self.bulletins = {
            "anno-2026__a.pdf": bulletin(date(2026, 9, 24), 37, self.rows(273.0), None),
            "anno-2026__b.pdf": bulletin(date(2026, 10, 1), 38, self.rows(275.0, 273.0), date(2026, 9, 24)),
            "anno-2026__c.pdf": bulletin(date(2026, 10, 8), 39, self.rows(276.0, 275.0), date(2026, 10, 1)),
        }
        # dataset iniziale: a e b gia' acquisiti, "old" scartato
        st = bologna.State()
        for name in ("anno-2026__a.pdf", "anno-2026__b.pdf"):
            bologna.ingest(st, self.bulletins[name], name, LATER)
        st.skipped["anno-2013__old.pdf"] = "illeggibile"
        bologna.write(self.ds, st, rewrite_revisions=True)
        self.fetched: list[tuple[str, bool]] = []

    @staticmethod
    def rows(cur, prev=None):
        # 120 righe: sopra la soglia sotto la quale un listino e' considerato sospetto
        return [(SEC, f"voce {i}", (cur + i, cur + i + 4),
                 None if prev is None else (prev + i, prev + i + 4)) for i in range(120)]

    def run_update(self, **kw):
        def fake_fetch(urls, dest, sleep=1.0, overwrite=False):
            out = {}
            for u in urls:
                name = bologna.fetcher.local_name(u)
                self.fetched.append((name, overwrite))
                (dest / name).parent.mkdir(parents=True, exist_ok=True)
                (dest / name).write_bytes(b"%PDF")
                out[u] = dest / name
            return out
        with mock.patch.object(bologna.fetcher, "list_issues", return_value=list(self.urls.values())), \
             mock.patch.object(bologna.fetcher, "fetch_many", side_effect=fake_fetch), \
             mock.patch.object(parser, "parse_pdf", side_effect=lambda f: self.bulletins[f.name]):
            return bologna.update(self.ds, self.stage, sleep=0, **kw)

    def test_fetches_only_the_new_one_and_rechecks_only_the_newest_known(self):
        r = self.run_update()
        self.assertEqual(sorted(self.fetched), sorted([
            ("anno-2026__c.pdf", False), ("anno-2026__b.pdf", True)]))
        self.assertEqual((r["new_files"], r["rechecked"]), (1, 1))
        self.assertIn("anno-2026__c.pdf", bologna.load(self.ds).issues)

    def test_skipped_bulletins_are_never_retried(self):
        self.run_update()
        self.assertNotIn("anno-2013__old.pdf", [n for n, _ in self.fetched])

    def test_no_recheck_option(self):
        self.run_update(recheck=False)
        self.assertEqual(self.fetched, [("anno-2026__c.pdf", False)])

    def test_unreadable_new_bulletin_stops_the_run_and_writes_nothing(self):
        before = (self.ds / "meta.json").read_bytes()
        self.bulletins["anno-2026__c.pdf"] = bulletin(date(2026, 10, 8), 39, [], date(2026, 10, 1))
        with self.assertRaises(SystemExit):
            self.run_update()
        self.assertEqual((self.ds / "meta.json").read_bytes(), before)

    def test_garbled_new_bulletin_is_recorded_and_does_not_block(self):
        def parse(f):
            if f.name == "anno-2026__c.pdf":
                raise parser.UnreadablePdf("c: titolo del listino non trovato", garbled=True)
            return self.bulletins[f.name]
        self.bulletins["anno-2026__c.pdf"] = None
        with mock.patch.object(bologna.fetcher, "list_issues", return_value=list(self.urls.values())), \
             mock.patch.object(bologna.fetcher, "fetch_many", side_effect=lambda urls, dest, **k: {
                 u: dest / bologna.fetcher.local_name(u) for u in urls}), \
             mock.patch.object(parser, "parse_pdf", side_effect=parse):
            r = bologna.update(self.ds, self.stage, sleep=0)
        self.assertEqual(r["garbled"], ["anno-2026__c.pdf"])
        self.assertIn("anno-2026__c.pdf", bologna.load(self.ds).skipped)

    def test_dry_run_writes_nothing(self):
        before = (self.ds / "issues.csv").read_bytes()
        self.run_update(dry_run=True)
        self.assertEqual((self.ds / "issues.csv").read_bytes(), before)

    def test_recheck_of_an_unchanged_bulletin_records_no_revision(self):
        r = self.run_update()
        self.assertEqual(r["revisions"], 0)


if __name__ == "__main__":
    unittest.main()
