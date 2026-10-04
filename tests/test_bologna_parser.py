"""Il parser dei listini di Bologna, caso limite per caso limite.

Ognuno dei casi qui sotto e' un difetto realmente incontrato leggendo i PDF
della Camera di Commercio, non un'ipotesi.
"""
import unittest

from exchanges.bologna import parser
from tests.layout import bulletin, page, row


def parse(*lines: str) -> parser.ParsedBulletin:
    return parser.parse_text(bulletin(page(*lines)))


class Dates(unittest.TestCase):
    def test_title_and_previous_week(self):
        b = parse("FRUMENTO TENERO", row("n° 1 - speciali", ["273,00", "277,00", "273,00", "277,00", "0,00", "0,00"]))
        self.assertEqual((b.date.isoformat(), b.number), ("2026-10-01", 38))
        self.assertEqual(b.prev_date.isoformat(), "2026-09-24")

    def test_unreadable_pdf_is_an_error_not_an_empty_bulletin(self):
        # 2012: i caratteri sono codificati male e il titolo non si trova.
        with self.assertRaises(parser.UnreadablePdf) as ctx:
            parser.parse_text("\x01\x02 ,/,/./+/+/  0  -\n")
        self.assertTrue(ctx.exception.garbled)

    def test_readable_text_with_an_unknown_title_is_a_parser_failure_not_garbled(self):
        # Se la Camera riscrive il titolo il testo c'e': e' un guasto, non un file rotto.
        text = ("Listino dei prezzi all'ingrosso, Camera di Commercio di Bologna\n"
                "FRUMENTO TENERO - prezzi del frumento\n")
        with self.assertRaises(parser.UnreadablePdf) as ctx:
            parser.parse_text(text)
        self.assertFalse(ctx.exception.garbled)

    def test_title_with_elided_article(self):
        # "n. 31 dell'1 agosto 2013"
        t = bulletin(page("FRUMENTO TENERO", row("n° 1", ["1,00"] * 6),
                          title="C.C.I.A.A. di Bologna - Listino settimanale dei prezzi all'ingrosso n. 31 dell'1 agosto 2013"))
        b = parser.parse_text(t)
        self.assertEqual((b.date.isoformat(), b.number), ("2013-08-01", 31))


class Rows(unittest.TestCase):
    def test_full_row(self):
        b = parse("FRUMENTO TENERO di produzione nazionale 2026",
                  row("n° 1 - speciali di forza", ["273,00", "277,00", "275,00", "280,00", "2,00", "3,00"]))
        r, = b.rows
        self.assertEqual(r.prev, (273.0, 277.0))
        self.assertEqual(r.cur, (275.0, 280.0))
        self.assertEqual(b.mismatches, [])

    def test_dash_means_not_quoted_but_row_exists(self):
        b = parse("CEREALI", row("sorgo", ["-", "-", "-", "-", "-", "-"]))
        r, = b.rows
        self.assertEqual(r.cur, (None, None))
        self.assertTrue(r.cur_listed)

    def test_nr_means_not_quoted(self):
        # Dal 2019 la colonna "precedente" puo' avere "n.r." al posto del trattino.
        b = parse("FORAGGI", row("1° taglio in campo", ["n.r.", "n.r.", "-", "-", "-", "-"]),
                  row("2° taglio in cascina", ["n.r.", "n.r.", "115,00", "116,00", "-", "-"]))
        self.assertEqual([r.cur for r in b.rows], [(None, None), (115.0, 116.0)])
        self.assertEqual([r.prev for r in b.rows], [(None, None), (None, None)])
        self.assertTrue(all(r.prev_listed for r in b.rows))

    def test_blank_cells_are_not_dashes(self):
        # Prodotto nuovo: nessuna colonna "precedente".  Non e' "non quotato".
        b = parse("CEREALI", row("riferimento", ["1,00", "2,00", "1,00", "2,00", "0,00", "0,00"]),
                  row("pisello", [None, None, "255,00", "260,00", None, None]))
        r = b.rows[1]
        self.assertFalse(r.prev_listed)
        self.assertTrue(r.cur_listed)
        self.assertEqual(r.cur, (255.0, 260.0))

    def test_product_that_stopped_has_no_current_cells(self):
        b = parse("CEREALI", row("riferimento", ["1,00", "2,00", "1,00", "2,00", "0,00", "0,00"]),
                  row("pisello", ["255,00", "260,00", None, None, None, None]))
        r = b.rows[1]
        self.assertTrue(r.prev_listed)
        self.assertFalse(r.cur_listed)

    def test_single_price_in_min_column_only(self):
        b = parse("GRANOTURCO", row("riferimento", ["1,00", "2,00", "1,00", "2,00", "0,00", "0,00"]),
                  row("comunitario", ["247,00", None, "247,00", None, "0,00", None]))
        self.assertEqual(b.rows[1].cur, (247.0, None))

    def test_partial_row_without_a_reference_is_reported_not_guessed(self):
        # Senza una riga completa non si sa dove stanno le colonne: meglio
        # dichiararlo che attribuire un prezzo alla colonna sbagliata.
        b = parse("GRANOTURCO", row("comunitario", ["247,00", None, "247,00", None, "0,00", None]))
        self.assertEqual(b.rows, [])
        self.assertEqual(len(b.unassigned), 1)

    def test_zero_is_not_a_price(self):
        # L'aggregatore stampa "0,00" dove la Camera mette "-".
        b = parse("CEREALI", row("orzo", ["0,00", "0,00", "0,00", "0,00", "0,00", "0,00"]))
        self.assertEqual(b.rows[0].cur, (None, None))

    def test_thousands_separator(self):
        b = parse("CEREALI", row("grasso", ["1.050,00", "1.055,00", "1.055,00", "1.060,00", "5,00", "5,00"]))
        self.assertEqual(b.rows[0].cur, (1055.0, 1060.0))

    def test_three_decimals_are_not_prices(self):
        # Petroliferi: EUR/l con tre decimali.  Fuori dallo schema.
        b = parse("CEREALI", row("benzina", ["1,427", None, None, None, None, None]))
        self.assertEqual(b.rows, [])

    def test_trend_word_after_the_numbers(self):
        # Listini 2013-2016: "stazionario" a destra dei numeri.
        line = row("n° 3 - fino", ["181,00", "187,00", "181,00", "187,00", "0,00", "0,00"]) + "   stazionario"
        b = parse("FRUMENTO TENERO", line)
        self.assertEqual(b.rows[0].cur, (181.0, 187.0))
        self.assertEqual(b.rows[0].label, "n° 3 - fino")


class PrintedDifferenceCheck(unittest.TestCase):
    def test_consistent_difference_passes(self):
        b = parse("X", row("a", ["10,00", "12,00", "11,00", "14,00", "1,00", "2,00"]))
        self.assertEqual(b.mismatches, [])

    def test_inconsistent_difference_is_reported_not_corrected(self):
        # Il valore pubblicato resta quello stampato; il parser segnala soltanto.
        b = parse("X", row("a", ["93,00", "125,00", "93,00", "125,00", "0,00", "5,00"]))
        self.assertEqual(len(b.mismatches), 1)
        self.assertEqual(b.rows[0].cur, (93.0, 125.0))


class Labels(unittest.TestCase):
    def test_hyphen_separator_in_a_heading_is_not_a_dash_cell(self):
        # "RISONI - per merce sfusa" non e' una riga con una cella "non quotato".
        b = parse("RISONI - per merce sfusa, al netto dei diritti",
                  row("riferimento", ["1,00", "2,00", "1,00", "2,00", "0,00", "0,00"]),
                  row("Baldo", ["-", "-", "835,00", "1035,00", None, None]))
        self.assertEqual(len(b.rows), 2)
        self.assertEqual(b.rows[0].path, ("RISONI - per merce sfusa, al netto dei diritti",))

    def test_label_containing_min_and_max_is_not_a_header(self):
        label = "fino - prot. 13% min, p.s. 81 kg/hl min, c.e. 2+2%, volp. 6% max"
        b = parse("FRUMENTO DURO", row(label, ["286,00", "291,00", "283,00", "288,00", "-3,00", "-3,00"]))
        self.assertEqual(b.rows[0].label, label)

    def test_wrapped_label_has_numbers_on_the_middle_line(self):
        b = parse("GRANOTURCO",
                  "granoturco ad uso zootecnico estero (afla B1 max. 3 ppb/DON max.",
                  row("", ["360,00", "390,00", "360,00", "390,00", "0,00", "0,00"]),
                  "3000 ppb)",
                  row("sorgo", ["295,00", "305,00", "295,00", "305,00", "0,00", "0,00"]))
        self.assertEqual([r.label for r in b.rows], [
            "granoturco ad uso zootecnico estero (afla B1 max. 3 ppb/DON max. 3000 ppb)", "sorgo"])
        self.assertEqual(b.rows[0].cur, (360.0, 390.0))

    def test_wrapped_label_whose_tail_is_the_word_max(self):
        # Il caso del frumento duro 2025: "...volp.6%" / numeri / "max".
        b = parse("FRUMENTO DURO",
                  "buono mercantile - prot. 12% min, volp.6%",
                  row("", ["271,00", "276,00", "266,00", "271,00", "-5,00", "-5,00"]),
                  "max",
                  row("mercantile", ["261,00", "266,00", "256,00", "261,00", "-5,00", "-5,00"]))
        self.assertEqual(b.rows[0].label, "buono mercantile - prot. 12% min, volp.6% max")
        self.assertEqual(b.rows[1].label, "mercantile")

    def test_label_split_in_two_with_numbers_on_the_second_half(self):
        # Layout 2016: prima meta' con la virgola (e un commento nel margine destro),
        # seconda meta' ("volp.8%") con i numeri accanto.
        b = parse("FRUMENTO DURO di produzione nazionale, centro",
                  "buono mercantile - prot. 11,5% min, bianc.50/60%," + " " * 80 + "stazio",
                  row("volp.8%", ["173,00", "178,00", "173,00", "178,00", "0,00", "0,00"]),
                  row("mercantile", ["163,00", "168,00", "163,00", "168,00", "0,00", "0,00"]))
        self.assertEqual(b.rows[0].label, "buono mercantile - prot. 11,5% min, bianc.50/60%, volp.8%")
        self.assertEqual(b.rows[0].path, b.rows[1].path)

    def test_area_suffix_after_the_numbers_belongs_to_the_label(self):
        b = parse("FRUMENTO DURO",
                  "buono mercantile - volp.6%",
                  row("", ["283,00", "288,00", "278,00", "283,00", "-5,00", "-5,00"]),
                  "max CENTRO",
                  row("mercantile", ["261,00", "266,00", "256,00", "261,00", "-5,00", "-5,00"]))
        self.assertEqual(b.rows[0].label, "buono mercantile - volp.6% max CENTRO")
        # e non ha aperto una sezione "CENTRO" che sporcherebbe le righe seguenti
        self.assertEqual(b.rows[1].path, b.rows[0].path)

    def test_footnote_references_are_dropped_from_the_label(self):
        b = parse("CEREALI", row("estero (2) (3)", ["-", "-", "-", "-", "-", "-"]))
        self.assertEqual(b.rows[0].label, "estero")

    def test_footnote_text_never_becomes_a_heading(self):
        b = parse("CRUSCAMI",
                  row("cubettato", ["160,00", "162,00", "163,00", "165,00", "3,00", "3,00"]),
                  "(3) Min. farina, max. pellet     (4) Trasformata in Italia",
                  "continua la nota su un'altra riga",
                  row("farinaccio", ["172,00", "175,00", "167,00", "170,00", "-5,00", "-5,00"]))
        self.assertEqual(b.rows[1].path, ("CRUSCAMI",))

    def test_legend_with_equals_is_not_a_heading(self):
        b = parse("PRODOTTI ORTOFRUTTICOLI BIOLOGICI - in €/kg.",
                  "PVN = provenienze varie nazionali - PVE = provenienze varie estere)",
                  row("Aglio", ["6,80", "7,20", "6,80", "7,20", "0,00", "0,00"]))
        self.assertEqual(b.rows[0].path, ("PRODOTTI ORTOFRUTTICOLI BIOLOGICI - in €/kg.",))

    def test_excel_error_cell_is_not_a_price(self):
        # Il PDF di Excel stampa "#VALORE!" dove la formula e' rotta.
        b = parse("SEMENTI", row("riferimento", ["1,00", "2,00", "1,00", "2,00", "0,00", "0,00"]),
                  row("sulla sgusciata", ["-", "-", "#VALORE!", "#VALORE!", "-", "-"]))
        self.assertEqual(b.rows[1].cur, (None, None))

    def test_wrapped_heading_is_one_heading(self):
        # "... - merce posta" / "su veicolo partenza ...": una sola cella andata a capo.
        a = parse("FRUMENTO TENERO di produzione nazionale 2015 - merce posta",
                  "su veicolo partenza magazzino produttore",
                  row("n° 1", ["1,00"] * 6))
        b = parse("FRUMENTO TENERO di produzione nazionale 2015 - merce posta",
                  row("n° 1", ["1,00"] * 6))
        self.assertEqual(a.rows[0].path[0].split(" - ")[0], b.rows[0].path[0].split(" - ")[0])
        self.assertEqual(len(a.rows[0].path), 1)

    def test_short_lowercase_fragment_after_a_heading_is_not_a_subheading(self):
        b = parse("SFARINATI di grano duro - rinfusa", "arrivo", row("semola", ["1,00"] * 6))
        self.assertEqual(len(b.rows[0].path), 1)

    def test_a_real_subheading_is_not_swallowed(self):
        b = parse("VINI - franco partenza produttore - in €/grado x 100 litri",
                  "vini a I.G.T. - sfusi per grossi quantitativi - in €/litro:",
                  row("bianco", ["1,00"] * 6))
        self.assertEqual(len(b.rows[0].path), 2)

    def test_right_margin_comment_is_not_a_heading(self):
        b = parse("CEREALI MINORI",
                  " " * 100 + "in buona vista",
                  row("orzo", ["1,00"] * 6))
        self.assertEqual(b.rows[0].path, ("CEREALI MINORI",))

    def test_pork_rows_with_three_decimals_do_not_become_headings(self):
        b = parse("BURRO e FORMAGGI - franco partenza - in €/kg",
                  "lardo fresco cm. 3+                      2,480    2,480    0,000",
                  row("zampone", ["1,00"] * 6))
        self.assertEqual(b.rows[0].path, ("BURRO e FORMAGGI - franco partenza - in €/kg",))

    def test_beef_class_grid_is_ignored(self):
        b = parse("CEREALI", "U3             284,85             O2            202,60")
        self.assertEqual((b.rows, b.unassigned), ([], []))

    def test_petroleum_section_is_skipped(self):
        b = parse("PRODOTTI PETROLIFERI",
                  row("gasolio", ["1,45", "1,50", "1,45", "1,50", "0,00", "0,00"]),
                  "FRUMENTO TENERO",
                  row("n° 1", ["273,00", "277,00", "273,00", "277,00", "0,00", "0,00"]))
        self.assertEqual([r.label for r in b.rows], ["n° 1"])


class Paths(unittest.TestCase):
    def test_crop_year_is_not_part_of_the_path(self):
        a = parse("FRUMENTO TENERO di produzione nazionale 2025", row("n° 1", ["1,00"] * 6))
        b = parse("FRUMENTO TENERO di produzione nazionale 2026", row("n° 1", ["1,00"] * 6))
        self.assertEqual(a.rows[0].path, b.rows[0].path)

    def test_empty_sections_do_not_change_the_path(self):
        # "FRUMENTO DURO" senza righe una settimana, con righe quella dopo: il
        # percorso della sezione successiva non deve dipenderne.
        with_empty = parse("FRUMENTO DURO di produzione nazionale", "CEREALI MINORI E LEGUMINOSE",
                           row("sorgo", ["1,00"] * 6))
        without = parse("CEREALI MINORI E LEGUMINOSE", row("sorgo", ["1,00"] * 6))
        self.assertEqual(with_empty.rows[0].path, without.rows[0].path)

    def test_subheading_keeps_its_parent(self):
        b = parse("VINI - franco partenza produttore - in €/grado x 100 litri",
                  "Vini generici anche con annata",
                  row("bianco, gr. 10/12", ["4,50", "4,90", "4,30", "4,70", "-0,20", "-0,20"]),
                  "Vini varietali anche con annata",
                  row("merlot", ["4,70", "5,00", "4,40", "4,70", "-0,30", "-0,30"]))
        self.assertEqual(b.rows[1].path, (
            "VINI - franco partenza produttore - in €/grado x 100 litri",
            "Vini varietali anche con annata"))

    def test_repeated_label_in_one_bulletin_gets_an_ordinal(self):
        b = parse("VINI IGP", row("Bianco Emilia", ["4,70", "5,00", "4,50", "4,80", "-0,20", "-0,20"]),
                  "VINI IGP", row("Bianco Emilia", ["-", "-", "-", "-", "-", "-"]))
        self.assertEqual(b.rows[0].path, ("VINI IGP",))
        self.assertEqual(b.rows[1].path, ("VINI IGP", "#2"))


class Units(unittest.TestCase):
    def units(self, *lines):
        return [r.unit for r in parse(*lines).rows]

    def test_default_is_tonnes_as_the_source_states(self):
        self.assertEqual(self.units("FRUMENTO TENERO", row("n° 1", ["1,00"] * 6)), ["EUR/t"])

    def test_declared_unit_in_the_heading(self):
        self.assertEqual(self.units("PRODOTTI ORTOFRUTTICOLI di 1ª qualità - in €/kg.",
                                    "MELE - alla rinfusa", row("Fuji", ["1,00"] * 6)), ["EUR/kg"])

    def test_hay_after_fruit_is_not_inherited_as_kg(self):
        # Listini 2013-2016: il fieno viene dopo l'ortofrutta.
        u = self.units("PRODOTTI ORTOFRUTTICOLI - in €/kg.", row("mele", ["1,00"] * 6),
                       "ERBA MEDICA - franco partenza", row("1° taglio", ["105,00", "120,00", "105,00", "120,00", "0,00", "0,00"]))
        self.assertEqual(u, ["EUR/kg", "EUR/t"])

    def test_subsection_inherits_the_family_unit(self):
        u = self.units("VINI - franco partenza produttore - in €/grado x 100 litri",
                       row("a", ["4,50", "4,90", "4,30", "4,70", "-0,20", "-0,20"]),
                       "VINI IGP", row("b", ["4,70", "5,00", "4,50", "4,80", "-0,20", "-0,20"]))
        self.assertEqual(u, ["EUR/grado-hL", "EUR/grado-hL"])

    def test_undeclared_family_is_unknown_not_inherited(self):
        u = self.units("PRODOTTI ORTOFRUTTICOLI - in €/kg.", row("mele", ["1,00"] * 6),
                       "MOSTI - franco partenza produttore", row("mosto", ["4,80", "5,00", "4,30", "4,50", "-0,50", "-0,50"]))
        self.assertEqual(u, ["EUR/kg", "unknown"])

    def test_unit_in_the_label_wins(self):
        u = self.units("MOSTI - franco partenza produttore",
                       row("mosto refrigerato bianco gr. 10,5/12 - € al kg", ["-"] * 6))
        self.assertEqual(u, ["EUR/kg"])

    def test_two_possible_units_are_unknown(self):
        u = self.units("in contenitori da 6 a 60 litri - in € al kg/litro", row("Bianco", ["-"] * 6))
        self.assertEqual(u, ["unknown"])

    def test_quintal(self):
        self.assertEqual(self.units("UVE DA VINO - in € al q", row("Bianche", ["30,00"] * 6)), ["EUR/q"])


if __name__ == "__main__":
    unittest.main()
