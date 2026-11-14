"""Controlli sui petroliferi di Verona.  ``python -m tests.test_energia`` (o pytest)."""
import xml.etree.ElementTree as ET
from datetime import date

from exchanges.verona.energia import _date, unit_of


def _root(title):
    return ET.fromstring(f"<rilevazione><nome>{title}</nome></rilevazione>")


def test_date_without_year_takes_nearest():
    # n. 849: "DEL 15 SETTEMBRE" senza anno, dopo il 30 agosto 2021.
    assert _date(_root("RILEVAZIONE N. 17 DEL 15 SETTEMBRE"), date(2021, 8, 30)) == date(2021, 9, 15)
    assert _date(_root("RILEVAZIONE N. 24 DEL 30 DICEMBRE"), date(2026, 1, 15)) == date(2025, 12, 30)
    assert _date(_root("RILEVAZIONE N. 1 DEL 15 GENNAIO"), date(2025, 12, 30)) == date(2026, 1, 15)
    assert _date(_root("RILEVAZIONE N. 1 DEL 15 GENNAIO"), None) is None
    assert _date(_root("RILEVAZIONE N. 20 DEL 30 OTTOBRE 2026"), None) == date(2026, 10, 30)


def test_bottle_is_not_per_kg():
    assert unit_of("kg", "da 10 kg miscela") == "EUR/bombola"
    assert unit_of("kg", "fino a 2.000") == "EUR/kg"
    assert unit_of("lt", "fino a 2.000") == "EUR/L"
    assert unit_of("mc", "(1 atmosfera e 15° di temperatura)") == "EUR/m3"


if __name__ == "__main__":
    test_date_without_year_takes_nearest()
    test_bottle_is_not_per_kg()
    print("ok")
