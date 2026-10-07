"""I JSON del sito: una cartella per borsa, serie unite, elenco delle borse."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import paths, publish


def write_dataset(root: Path, products, prices, series=None, meta=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "prices").mkdir(exist_ok=True)
    rows = ["code,name,category_path,unit,first_date,last_date,n_observations,n_quoted"]
    for code, name, path, unit in products:
        rows.append(f'{code},"{name}",{path},{unit},,,0,0')
    (root / "products.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    by_year = {}
    for d, code, lo, hi in prices:
        by_year.setdefault(d[:4], []).append(f"{d},{code},{lo},{hi}")
    for year, lines in by_year.items():
        (root / "prices" / f"{year}.csv").write_text(
            "date,code,low,high\n" + "\n".join(lines) + "\n", encoding="utf-8")
    if series:
        (root / "series.csv").write_text(
            "code,series\n" + "\n".join(f"{c},{s}" for c, s in series.items()) + "\n", encoding="utf-8")
    (root / "meta.json").write_text(json.dumps(meta or {"n_products": len(products)}), encoding="utf-8")


EX = paths.Exchange("XX", "Borsa di prova", "prova", "https://example.org",
                    chamber="Camera di prova", notice="Attenzione", group_cut=" - ")


class SingleExchange(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_publish(self, **kw):
        write_dataset(self.root / "ds", **kw)
        out = self.root / "out"
        stats = publish.publish(self.root / "ds", out, EX)
        return stats, json.loads((out / "index.json").read_text(encoding="utf-8")), out

    def test_products_without_quotes_are_left_out(self):
        _, idx, out = self.run_publish(
            products=[("1", "orzo", "CEREALI", "EUR/t"), ("2", "farro", "CEREALI", "EUR/t")],
            prices=[("2026-10-01", "1", "200", "210"), ("2026-10-01", "2", "", "")])
        self.assertEqual([p["code"] for p in idx["products"]], ["1"])
        self.assertTrue((out / "series" / "1.json").exists())
        self.assertFalse((out / "series" / "2.json").exists())

    def test_index_carries_the_exchange_for_the_site(self):
        _, idx, _ = self.run_publish(products=[("1", "orzo", "CEREALI", "EUR/t")],
                                     prices=[("2026-10-01", "1", "200", "210")])
        ex = idx["exchange"]
        self.assertEqual((ex["slug"], ex["chamber"], ex["notice"]),
                         ("prova", "Camera di prova", "Attenzione"))

    def test_group_is_cut_at_the_separator(self):
        _, idx, _ = self.run_publish(
            products=[("1", "n° 1", "FRUMENTO TENERO di produzione nazionale - merce posta su veicolo", "EUR/t")],
            prices=[("2026-10-01", "1", "270", "275")])
        self.assertEqual(idx["products"][0]["group"], "FRUMENTO TENERO di produzione nazionale")

    def test_codes_of_a_series_become_one_product_with_all_history(self):
        key = "FRUMENTO TENERO > n. 1 - speciali"
        stats, idx, out = self.run_publish(
            products=[("1", "n° 1 - p.s. 78/79", "FRUMENTO TENERO", "EUR/t"),
                      ("2", "n° 1 - p.s. 79/80", "FRUMENTO TENERO", "EUR/t"),
                      ("3", "orzo", "CEREALI", "EUR/t")],
            prices=[("2024-09-05", "1", "250", "255"), ("2025-09-04", "2", "260", "265"),
                    ("2025-09-11", "2", "262", "267"), ("2025-09-11", "3", "200", "210")],
            series={"1": key, "2": key})
        self.assertEqual(stats["products"], 2)                    # la serie e l'orzo
        s = next(p for p in idx["products"] if p.get("merged"))
        self.assertEqual((s["n"], s["first"], s["last"], s["merged"]), (3, "2024-09-05", "2025-09-11", 2))
        self.assertEqual(s["code"], publish.series_id(key))
        data = json.loads((out / "series" / f"{s['code']}.json").read_text(encoding="utf-8"))
        self.assertEqual([p[0] for p in data["points"]], ["2024-09-05", "2025-09-04", "2025-09-11"])
        self.assertEqual([v["name"] for v in data["variants"]], ["n° 1 - p.s. 78/79", "n° 1 - p.s. 79/80"])
        # le singole varianti non compaiono piu' da sole
        self.assertFalse((out / "series" / "1.json").exists())

    def test_same_date_quoted_twice_in_a_series_counts_once(self):
        key = "S > g"
        _, idx, out = self.run_publish(
            products=[("1", "a", "S", "EUR/t"), ("2", "a bis", "S", "EUR/t")],
            prices=[("2025-09-04", "1", "250", "255"), ("2025-09-04", "2", "250", "255")],
            series={"1": key, "2": key})
        self.assertEqual(idx["products"][0]["n"], 1)

    def test_second_row_with_the_same_label_is_told_apart(self):
        _, idx, _ = self.run_publish(
            products=[("1", "Asparagi extra", "ASPARAGI", "EUR/kg"),
                      ("2", "Asparagi extra", "ASPARAGI > #2", "EUR/kg")],
            prices=[("2013-04-18", "1", "3", "4"), ("2013-04-18", "2", "5", "6")])
        names = {p["code"]: p for p in idx["products"]}
        self.assertEqual(names["1"]["name"], "Asparagi extra")
        self.assertEqual(names["2"]["name"], "Asparagi extra (voce 2)")
        self.assertEqual(names["2"]["category"], "ASPARAGI")     # l'ordinale non e' una sezione

    def test_series_id_is_stable(self):
        self.assertEqual(publish.series_id("a > b"), publish.series_id("a > b"))
        self.assertNotEqual(publish.series_id("a > b"), publish.series_id("a > c"))


class AllExchanges(unittest.TestCase):
    def test_one_folder_per_exchange_and_the_list_for_the_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for slug in ("verona", "bologna"):
                write_dataset(tmp / "dataset" / slug,
                              products=[("1", "orzo", "CEREALI", "EUR/t")],
                              prices=[("2026-10-01", "1", "200", "210")],
                              meta={"n_products": 1, "last_date": "2026-10-01"})
            out = tmp / "api"
            with mock.patch.object(paths, "DATASET_DIR", tmp / "dataset"):
                stats = publish.publish_all(out)
            self.assertEqual(sorted(stats), ["bologna", "verona"])
            listing = json.loads((out / "exchanges.json").read_text(encoding="utf-8"))
            self.assertEqual([e["slug"] for e in listing["exchanges"]], ["verona", "bologna"])
            self.assertEqual(listing["default"], "verona")
            for slug in ("verona", "bologna"):
                self.assertTrue((out / slug / "index.json").exists())
                self.assertTrue((out / slug / "series" / "1.json").exists())

    def test_an_exchange_without_dataset_is_not_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            write_dataset(tmp / "dataset" / "verona", products=[("1", "orzo", "C", "EUR/t")],
                          prices=[("2026-10-01", "1", "200", "210")])
            with mock.patch.object(paths, "DATASET_DIR", tmp / "dataset"):
                publish.publish_all(tmp / "api")
            listing = json.loads((tmp / "api" / "exchanges.json").read_text(encoding="utf-8"))
            self.assertEqual([e["slug"] for e in listing["exchanges"]], ["verona"])


if __name__ == "__main__":
    unittest.main()
