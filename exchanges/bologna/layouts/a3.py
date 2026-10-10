"""Listini dal 2004: un foglio solo con tre tabelle affiancate.

I titoli sono tutti in maiuscolo ("FRUMENTO TENERO NAZ.LE"); ogni altra riga
senza prezzi e' un sottotitolo ("Produzione Nord", "Risoni:"), perche' in questi
anni un prodotto non quotato ha comunque le sue celle "n.q.".
"""
from __future__ import annotations

import re

from exchanges.bologna.layouts.base import Layout, _State, clean
from exchanges.bologna import table


class A3(Layout):
    name = "a3"
    # Sotto le tabelle c'e' il riquadro "TENDENZE", con parole al posto dei prezzi.
    stop = re.compile(r"^TENDENZ|^Indici AgerBoM", re.IGNORECASE)
    # "(rinfusa - arrivo)", "(Sacco - arrivo)" sono sottotitoli, non note: le
    # note vere stanno sotto la tabella, dopo "Indici AgerBoM".
    note = re.compile(r"^\*|^N\.?B\b", re.IGNORECASE)

    def terms(self, caption: str) -> str:
        # Una sola riga in cima al foglio, "resa franco arrivo o partenza": quale
        # delle due lo dicono le note dei singoli titoli, non la tabella.
        return ""

    def is_heading(self, name: str) -> bool:
        letters = [c for c in clean(name) if c.isalpha()]
        return len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) >= 0.8

    def is_sub(self, name: str) -> bool:
        return True

    def place(self, row: table.Row, name: str, st: _State) -> list[str]:
        # "Erba medica disidratata cubettata" ha sotto di se' "- Qualità extra",
        # "- Iª Qualità": il sottotitolo vale per le voci col trattino e finisce
        # alla prima che non ce l'ha.
        if not st.sub:
            return []
        if name.startswith("-"):
            st.dashed = True
        elif st.dashed:
            st.sub, st.dashed = "", False
            return []
        return [st.sub]

    def rename(self, row: table.Row, name: str, st: _State) -> str:
        return name.lstrip("- ").strip()
