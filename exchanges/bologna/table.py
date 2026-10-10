"""Dalle parole di una pagina alle righe di un listino.

Tutti i listini di Bologna, dal 2004 a oggi, hanno la stessa ossatura: una
testata "min max min max" -- settimana precedente e settimana corrente -- e sotto
le righe, col nome a sinistra e i prezzi incolonnati.  Cambia il contorno: fino
al 2015 un foglio A3 con tre tabelle affiancate, poi piu' pagine A4 con una
tabella sola.  Qui sta quello che non cambia; il resto e' in ``layouts/``.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Iterator, Optional

from exchanges.bologna.pdfwords import Page, Word

_NUMBER = re.compile(r"^-?\d{1,3}(?:\.\d{3})*(?:,\d+)?$|^-?\d+(?:,\d+)?$")
_MINMAX = re.compile(r"^(min|max)\.?$", re.IGNORECASE)
# Come il listino scrive "non quotato" o "invariato" in una cella.
_BLANK = re.compile(r"^(n\.?q\.?|-+|inv\.?|=+)$", re.IGNORECASE)

MONTHS = ["gen", "feb", "mar", "apr", "mag", "giu",
          "lug", "ago", "set", "ott", "nov", "dic"]


def parse_number(text: str) -> Optional[float]:
    """"1.234,50" -> 1234.5; None se non e' un numero ("n.q.", "-", "inv")."""
    if not _NUMBER.match(text):
        return None
    return float(text.replace(".", "").replace(",", "."))


@dataclass
class Header:
    """Una testata "min max min max": dove comincia una tabella e dove stanno
    le sue quattro colonne di prezzo."""
    page: int
    y: float
    left: float                 # da qui in poi le parole sono di questa tabella
    right: float                # e fino a qui
    cols: tuple[float, float, float, float]     # centri: prec. min/max, corr. min/max
    previous: Optional[date] = None
    current: Optional[date] = None
    caption: str = ""           # la riga "Prezzi in €/t, … FRANCO PARTENZA …"

    @property
    def tol(self) -> float:
        return min(b - a for a, b in zip(self.cols, self.cols[1:])) / 2


@dataclass
class Row:
    """Una riga sotto una testata.  ``cells`` ha un valore per colonna di prezzo;
    None e' la cella vuota, "n.q." o lo zero che il foglio mette al suo posto."""
    header: Header
    y: float
    x: float                    # rientro del nome
    name: str
    cells: tuple[Optional[float], ...] = (None, None, None, None)
    has_cells: bool = False     # c'era almeno una cella, anche "n.q."
    extra: list[Word] = field(default_factory=list)   # parole oltre l'ultima colonna


def find_headers(page: Page, gap: float = 80.0) -> list[Header]:
    """Le testate di una pagina, dall'alto e poi da sinistra.

    Su una stessa riga possono starcene piu' d'una, una per tabella affiancata:
    si separano dove fra un "max" e il "min" seguente c'e' un salto.
    """
    headers: list[Header] = []
    for row in page.rows():
        # Parole "min"/"max" di fila, senza altro in mezzo: cosi' non passa per
        # testata una nota a pie' di tabella che parla di prezzo minimo e massimo.
        runs: list[list[Word]] = []
        prev: Optional[Word] = None
        for w in row:
            if _MINMAX.match(w.text):
                if prev is not None and w.x0 - prev.x1 < gap:
                    runs[-1].append(w)
                else:
                    runs.append([w])
                prev = w
            else:
                prev = None
        first = True
        for run in runs:
            cols = [w.xc for w in run]
            # In qualche listino il primo "min." e' coperto da un nome troppo
            # lungo: la colonna c'e' lo stesso, un passo a sinistra del "max.".
            if run[0].text.lower().startswith("max") and len(run) >= 3:
                cols.insert(0, cols[0] - (cols[2] - cols[1]))
            if len(cols) < 4:
                continue
            # La tabella accanto finisce piu' o meno dove finisce la sua ultima
            # intestazione di colonna.  Il margine e' largo apposta: meglio
            # prendersi una cifra che ne sborda (la toglie iter_rows) che perdere
            # la prima parola dei nomi.
            before = [w.x1 for w in row if w.x1 < run[0].x0]
            left = max(before) - 8 if not first and before else 0.0
            first = False
            headers.append(Header(page.number, row[0].y, left, float("inf"), tuple(cols[:4])))
    by_row: dict[float, list[Header]] = {}
    for h in headers:
        by_row.setdefault(h.y, []).append(h)
    for hs in by_row.values():
        for h, nxt in zip(hs, hs[1:]):
            h.right = nxt.left
    return headers


def parse_day(text: str, near: date) -> Optional[date]:
    """La data di una testata -- "25 mar", "8 MAR 2018", "1-ott-26" -- con l'anno,
    quando manca, scelto in modo che cada vicino alla data del listino."""
    m = re.search(r"(\d{1,2})[\s°-]*([a-zA-Z]{3})[a-zA-Z]*\.?(?:[\s-]*(\d{4}|\d{2}))?", text)
    if not m or m[2].lower() not in MONTHS:
        return None
    day, month = int(m[1]), MONTHS.index(m[2].lower()) + 1
    years = ([int(m[3]) + (2000 if len(m[3]) == 2 else 0)] if m[3]
             else [near.year, near.year - 1, near.year + 1])
    best: Optional[date] = None
    for y in years:
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if best is None or abs((d - near).days) < abs((best - near).days):
            best = d
    return best


def read_dates(page: Page, h: Header, near: date, above: float = 30.0) -> None:
    """Riempie ``h.previous`` e ``h.current`` con le date scritte sopra le colonne."""
    mid = (h.cols[1] + h.cols[2]) / 2
    rows = [[w for w in r if h.cols[0] - h.tol * 2 <= w.xc <= h.cols[3] + h.tol * 2]
            for r in page.rows() if h.y - above <= r[0].y < h.y - 1]
    # Dalla riga piu' vicina alla testata in su: la prima che contiene una data
    # plausibile.  Piu' in alto ci sono altre date che non c'entrano, come
    # quella del decreto che ha istituito la borsa.
    for side in ("previous", "current"):
        for r in reversed(rows):
            text = " ".join(w.text for w in r if (w.xc < mid) == (side == "previous"))
            d = parse_day(text, near)
            if d and abs((d - near).days) <= 45:
                setattr(h, side, d)
                break


def iter_rows(page: Page, headers: list[Header]) -> Iterator[Row]:
    """Le righe di una pagina, ognuna con la testata che la governa: l'ultima
    sopra di lei fra quelle della sua stessa tabella."""
    all_rows = page.rows()
    # Dove cominciano i nomi di ogni tabella: l'ascissa piu' frequente fra le
    # prime parole delle righe.
    starts: dict[float, Counter] = {}
    for words in all_rows:
        for h in _governing(headers, page.number, words[0].y):
            mine = [w for w in words if h.left <= w.x0 < h.cols[0] - h.tol]
            if mine and not mine[0].text.isdigit():
                starts.setdefault(h.left, Counter())[round(mine[0].x0)] += 1
    start = {left: c.most_common(1)[0][0] for left, c in starts.items()}

    for words in all_rows:
        y = words[0].y
        for h in _governing(headers, page.number, y):
            mine = [w for w in words if h.left <= w.x0 < h.right]
            # Una cifra isolata a sinistra dei nomi e' l'ultima di un numero
            # della tabella accanto, tagliato dal bordo della sua colonna.
            while mine and mine[0].x0 < start.get(h.left, 0) - 3 and len(mine[0].text) <= 2 \
                    and not mine[0].text.isalpha():
                mine = mine[1:]
            if not mine:
                continue
            edge = h.cols[0] - h.tol
            name = [w for w in mine if w.xc < edge]
            cells: list[Optional[float]] = [None] * 4
            has_cells = False
            extra: list[Word] = []
            for w in mine:
                if w.xc < edge:
                    continue
                col = min(range(4), key=lambda i: abs(w.xc - h.cols[i]))
                if abs(w.xc - h.cols[col]) > h.tol:
                    extra.append(w)
                    continue
                value = parse_number(w.text)
                if value is None and not _BLANK.match(w.text):
                    # Una parola dove dovrebbe stare un prezzo: e' un titolo o
                    # una nota tanto lunghi da invadere le colonne.
                    name, cells, has_cells, extra = mine, [None] * 4, False, []
                    break
                has_cells = True
                cells[col] = value or None      # 0,00 = non quotato
            if name or has_cells:
                yield Row(h, y, name[0].x0 if name else edge,
                          " ".join(w.text for w in name), tuple(cells), has_cells, extra)


def _governing(headers: list[Header], page: int, y: float) -> list[Header]:
    """Per ogni tabella affiancata, la testata piu' vicina sopra la riga."""
    out: dict[float, Header] = {}
    for h in headers:
        if h.page == page and h.y < y - 1:
            cur = out.get(h.left)
            if cur is None or h.y > cur.y:
                out[h.left] = h
    return list(out.values())
