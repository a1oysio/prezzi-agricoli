"""Quale lettore usare per un listino, in base alla sua data.

Un elenco ordinato di (primo giorno di validita', lettore): vale l'ultimo la cui
data non supera quella del listino.
"""
from __future__ import annotations

from datetime import date

from exchanges.bologna.layouts.a3 import A3
from exchanges.bologna.layouts.a4 import A4
from exchanges.bologna.layouts.base import Entry, Layout

REGISTRY: list[tuple[date, Layout]] = [
    (date(2004, 1, 1), A3()),
    (date(2016, 6, 9), A4()),
]


def for_date(day: date) -> Layout:
    chosen = REGISTRY[0][1]
    for start, layout in REGISTRY:
        if day >= start:
            chosen = layout
    return chosen
