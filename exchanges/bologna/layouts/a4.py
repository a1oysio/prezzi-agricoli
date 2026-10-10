"""Listini recenti: piu' pagine A4, una tabella per pagina.

Il titolo comincia con una parola in maiuscolo e prosegue in minuscolo ("FARINE
di grano tenero di produzione nazionale…").  Un prodotto non quotato a volte non
ha celle affatto, quindi una riga senza prezzi non e' di per se' un sottotitolo:
lo e' solo se finisce coi due punti o e' una di quelle elencate qui.
"""
from __future__ import annotations

import re

from exchanges.bologna.layouts.base import Layout, _State
from exchanges.bologna import table


class A4(Layout):
    name = "a4"
    stop = re.compile(r"^AVVISO IMPORTANTE", re.IGNORECASE)
    _subs = re.compile(r":$|^Merce nuda in natura$", re.IGNORECASE)

    def is_heading(self, name: str) -> bool:
        first = re.match(r"[^\W\d_]+", name)
        return bool(first) and len(first[0]) >= 2 and first[0].isupper()

    def heading(self, name: str, previous: str, seen: set[str]) -> str:
        # Fra il 2022 e il 2023 i foraggi biologici di collina hanno lo stesso
        # titolo di quelli convenzionali: a distinguerli e' solo il venire dopo
        # "…di pianura - CERTIFICATI BIOLOGICI".  Dal 2024 il listino lo scrive.
        title = super().heading(name, previous, seen)
        bio = " - CERTIFICATI BIOLOGICI"
        if title in seen and previous.endswith(bio) and not title.endswith(bio):
            title += bio
        return title

    def is_super(self, name: str) -> bool:
        # Le sementi sono elencate due volte: a calo convenzionale e, sotto
        # questo titolo, ricalcolate a calo zero.
        return name.upper().startswith("PREZZI CALCOLATI")

    def is_sub(self, name: str) -> bool:
        return bool(self._subs.search(name.strip()))

    def place(self, row: table.Row, name: str, st: _State) -> list[str]:
        return [st.sub] if st.sub else []

    def rename(self, row: table.Row, name: str, st: _State) -> str:
        # Nei foraggi una riga rientrata completa quella sopra:
        #     1° taglio in campo: erba medica min. 20%, in rotoballe
        #                         erba medica min. 20%, in balloni quadri
        #     2° taglio in campo, in rotoballe
        #                         in balloni quadri
        # Il suo nome intero e' l'inizio della riga sopra, fino ai due punti o
        # alla prima virgola, piu' quello che c'e' scritto.
        if row.x > st.base_x + 15:
            return f"{st.lead} {name}" if st.lead else name
        m = re.match(r"(.*?[:,])\s", name)
        st.lead = m[1] if m else ""
        return name
