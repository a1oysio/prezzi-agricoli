"""Il mestiere comune a tutte le epoche: percorrere le righe di un listino e
decidere, per ognuna, se e' un titolo, un sottotitolo, una nota o un prodotto.

Ogni epoca e' una sottoclasse di ``Layout`` che dice soltanto in che cosa
differisce: come riconosce i titoli, dove la tabella finisce.  Quando un anno
cambia qualcosa si aggiunge una sottoclasse in un file suo e la si registra in
``layouts/__init__.py`` con la data da cui vale -- senza toccare le altre, i cui
anni restano letti come prima.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from exchanges.bologna import table
from exchanges.bologna.pdfwords import Page

# Richiami di nota: "(1)", "(4 - 8)", "(*)", "(**)".
_FOOTNOTE = re.compile(r"\s*\((?:\d+(?:\s*-\s*\d+)?|\*+)\)")
_UNIT = re.compile(r"(?:€|euro)\s*/\s*(t\b|ton|100\s*kg|q\.?le|kg)", re.IGNORECASE)
_UNITS = {"t": "EUR/t", "ton": "EUR/t", "kg": "EUR/kg"}


@dataclass
class Entry:
    """Una riga di prodotto, con la settimana corrente e quella precedente.

    La precedente non finisce nel dataset -- e' gia' nel listino di una
    settimana prima -- ma serve a controllare la lettura: i due listini devono
    dire la stessa cosa.
    """
    page: int
    path: tuple[str, ...]       # resa, titolo, eventuale sottotitolo
    name: str
    unit: str
    date: Optional[date]
    low: Optional[float]
    high: Optional[float]
    prev_date: Optional[date]
    prev_low: Optional[float]
    prev_high: Optional[float]


def clean(text: str) -> str:
    text = _FOOTNOTE.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" :")


def unit_of(caption: str) -> str:
    m = _UNIT.search(caption)
    if not m:
        return "unknown"
    key = re.sub(r"[\s.]", "", m[1].lower())
    return _UNITS.get(key, "unknown")


class Layout:
    name = "base"
    # Righe che chiudono la tabella: da li' in giu' non ci sono piu' prezzi.
    stop: Optional[re.Pattern] = None
    # Righe senza prezzi che non sono titoli: note, avvisi.
    note = re.compile(r"^\(|^\*|^N\.?B\b|^AVVISO|^Quotazion", re.IGNORECASE)

    # -- che cosa cambia da un'epoca all'altra --------------------------------

    def is_heading(self, name: str) -> bool:
        raise NotImplementedError

    def is_super(self, name: str) -> bool:
        """Un titolo che vale per tutti quelli che seguono, fino a fine tabella."""
        return False

    def is_sub(self, name: str) -> bool:
        """Una riga senza prezzi sotto un titolo: sottotitolo o altro?"""
        return False

    def terms(self, caption: str) -> str:
        """La resa: "FRANCO PARTENZA" o "FRANCO ARRIVO", scritta accanto alle
        date della testata ("F.CO PARTENZA") e nella riga "Prezzi in …"."""
        m = re.search(r"F(?:RAN|\.)CO\s+(PARTENZA|ARRIVO)", caption, re.IGNORECASE)
        return f"FRANCO {m[1].upper()}" if m else ""

    def heading(self, name: str, previous: str, seen: set[str]) -> str:
        """Il titolo come entra nel percorso dei prodotti che gli stanno sotto."""
        return clean(name)

    # -- il percorso -----------------------------------------------------------

    def entries(self, pages: list[Page], issue: date) -> list[Entry]:
        out: list[Entry] = []
        caption = ""            # l'ultima riga "Prezzi in …" incontrata
        seen: set[str] = set()  # i titoli gia' usati in questo listino
        for page in pages:
            headers = table.find_headers(page)
            if not headers:
                continue
            rows_above: list[tuple[float, str]] = [
                (r[0].y, " ".join(w.text for w in r)) for r in page.rows()]
            for h in headers:
                table.read_dates(page, h, issue)
                # Le pagine successive alla prima non ripetono "Prezzi in €/t…":
                # vale l'ultima letta.  La resa invece e' scritta su ogni
                # testata, a sinistra delle date.
                caps = [t for y, t in rows_above if y < h.y and re.search(r"prezzi\s+in\b", t, re.IGNORECASE)]
                caption = caps[-1] if caps else caption
                label = " ".join(w.text for w in page.words
                                 if h.y - 30 <= w.y < h.y - 1 and h.left <= w.x0 and w.xc < h.cols[0] - h.tol)
                h.caption = f"{label} | {caption}"
            state: dict[tuple[float, float], _State] = {}
            closed: set[float] = set()
            for row in table.iter_rows(page, headers):
                h = row.header
                if h.left in closed:
                    continue
                name = row.name.strip()
                if self.stop and self.stop.search(name):
                    closed.add(h.left)
                    continue
                st = state.setdefault((h.left, h.y), _State())
                if not name or self.note.search(name):
                    continue
                if row.has_cells:
                    self._product(out, page.number, row, st)
                elif self.is_super(name):
                    st.super, st.section, st.sub = clean(name), "", ""
                elif self.is_heading(name):
                    st.section = self.heading(name, st.section, seen)
                    seen.add(st.section)
                    st.sub, st.lead, st.dashed, st.base_x = "", "", False, row.x
                elif self.is_sub(name):
                    st.sub, st.dashed, st.lead = clean(name), False, ""
                    st.base_x = row.x
        return out

    def _product(self, out: list[Entry], page: int, row: table.Row, st: "_State") -> None:
        h = row.header
        name = clean(row.name)
        path = [p for p in (self.terms(h.caption), st.super, st.section) if p]
        path += self.place(row, name, st)
        name = self.rename(row, name, st)
        if not name:
            return              # riga segnaposto: solo trattini
        c = row.cells
        out.append(Entry(page, tuple(path), name, unit_of(h.caption),
                         h.current, c[2], c[3], h.previous, c[0], c[1]))

    def place(self, row: table.Row, name: str, st: "_State") -> list[str]:
        """Il sottotitolo sotto cui sta il prodotto, se ce n'e' uno."""
        return [st.sub] if st.sub else []

    def rename(self, row: table.Row, name: str, st: "_State") -> str:
        return name


@dataclass
class _State:
    super: str = ""
    section: str = ""
    sub: str = ""
    dashed: bool = False        # il sottotitolo ha sotto di se' voci col trattino
    lead: str = ""              # "1° taglio in campo: ", premesso alle righe rientrate
    base_x: float = 0.0         # margine sinistro dei nomi non rientrati
