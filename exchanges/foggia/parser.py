"""Da un listino PDF della Borsa Merci di Foggia alle sue righe di prezzo.

Il listino e' un foglio Excel stampato in PDF: una tabella per comparto
("GRANO DURO", "CEREALI MINORI E LEGUMINOSE", "SFARINATI"…), con la testata
"Riunione del <precedente>  Riunione del <corrente>" e sotto le colonne prezzo
min. / prezzo max. per le due settimane, la variazione e l'andamento.

Due cose da sapere per leggerlo:

* **I nomi vanno a capo dentro la cella**, e Excel centra il testo in verticale:
  di "ORZO NAZIONALE / Pesante (peso min. 62 kg/hl…)" la prima riga sta sopra
  quella dei prezzi e la seconda sotto.  Una riga di solo testo appartiene quindi
  ai prezzi piu' vicini, se distano meno di mezza riga di tabella; altrimenti e'
  un sottotitolo ("di GRANO DURO", "FARINE DI GRANO TENERO…") che vale per le
  voci seguenti.
* **In fondo c'e' il listino della Commissione Unica Nazionale del grano duro**,
  riportato dalla Camera: e' un'altra fonte, con altre date, e qui si scarta.

I listini non hanno codici prodotto: come per Bologna, la voce e' la coppia
(percorso, nome) e il codice lo assegna ``pipeline.foggia``.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from exchanges import FileMetadata
from exchanges.bologna.layouts.base import Entry, clean, unit_of
from exchanges.bologna.pdfwords import Page, Word, read_pages
from exchanges.bologna.table import parse_number

_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_MINMAX = re.compile(r"^(min|max)\.?$", re.IGNORECASE)
_BLANK = re.compile(r"^(n\.?q\.?|-+)$", re.IGNORECASE)
_SKIP = re.compile(r"^(\*|Andamento del mercato|Nota\b|Camera di Commercio|via Michele|PEC\b)", re.IGNORECASE)
_STOP = re.compile(r"COMMISSIONE UNICA NAZIONALE", re.IGNORECASE)
_UNIT_WORD = re.compile(r"^€/(t|ton)\.?$", re.IGNORECASE)
# Un'interlinea e mezza, in proporzione al corpo: piu' in la' una riga di testo
# non e' parte della cella.  Le righe di una cella distano 1,2-1,35 volte il
# corpo; un sottotitolo almeno 1,6 volte dalla voce sotto.
CELL_REACH = 1.45
# I titoli dei comparti sono in un corpo piu' grande del resto (8,6, 9,5 o 12,6
# contro 5,8, 6,4 o 8,3); fra le righe della testata vale il corpo maggiore.
TITLE_HEIGHT = 8.5
# I sottotitoli non si distinguono dai nomi ne' per corpo ne' per posizione:
# sono pochi, e si elencano.  Una riga di testo che non e' un sottotitolo e non
# sta accanto a dei prezzi e' una voce senza celle: non quotata, si scarta come
# a Bologna.
_SUB = re.compile(r"^(di GRANO (DURO|TENERO)\b|SEMOLA DI GRANO DURO\b|FARINE DI GRANO TENERO\b)",
                  re.IGNORECASE)
# Il seguito delle condizioni di resa che va a capo sotto un sottotitolo.
_TERMS = re.compile(r"\b(franco|esclusa|i\.v\.a\.|si intendono|merce rinfusa)\b", re.IGNORECASE)
# L'inizio di un nome: una parola tutta in maiuscolo, di almeno tre lettere.
_OPENS = re.compile(r"^[A-ZÀ-Ý]{3,}\b")
# Caratteri invisibili che alcuni listini del 2021 hanno dentro ogni parola.
_INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff]")
# In alcuni listini pdftotext perde le legature "ti" e "tt": "spezza" per
# "spezzati", "cube ato" per "cubettato".  Si rimettono, o la stessa voce
# risulterebbe un'altra.
_LIGATURES = [(re.compile(p), r) for p, r in (
    (r"\bspezza\b", "spezzati"), (r"\bbiancona\b", "bianconati"),
    (r"\bcube ato\b", "cubettato"), (r"\bFarine a\b", "Farinetta"),
    (r"^- po\b", "- tipo"), (r"\bstrimin\s?zi\b", "striminziti"),
)]


def _date(text: str) -> date:
    return datetime.strptime(text, "%d/%m/%Y").date()


class _Table:
    """Una tabella: testata, colonne e il testo che la descrive."""

    def __init__(self, left: float) -> None:
        self.left = left                # da qui a destra: date e colonne
        self.section = ""
        self.title_h = 0.0
        self.dates: list[Word] = []
        self.prev: Optional[date] = None
        self.cur: Optional[date] = None
        # Centri delle colonne di prezzo, precedente min/max e corrente min/max.
        # Il primo listino (23/06/2021) ha solo la settimana corrente.
        self.cols: Optional[list[Optional[float]]] = None
        self.caption = ""
        self.sub = ""


class _Line:
    """Una riga di tabella: con prezzi (``cells``) o di solo testo."""

    def __init__(self, y: float, words: list[Word], cells=None) -> None:
        self.y = y
        self.words = words              # la parte a sinistra delle colonne
        self.cells = cells
        self.text = " ".join(w.text for w in words)
        self.x0 = words[0].x0 if words else None
        self.h = max((w.h for w in words), default=0.0)


def parse_file(path: Path) -> tuple[FileMetadata, list[Entry]]:
    """Legge un listino.  Solleva ValueError se non trova la data, se non ci sono
    prezzi o se le colonne dicono un'altra settimana."""
    return parse_pages(read_pages(path), path.name)


def parse_pages(pages: list[Page], name: str) -> tuple[FileMetadata, list[Entry]]:
    """Come ``parse_file``, dalle pagine gia' estratte (i test le tengono in un file)."""
    pages = [_normalize(p) for p in pages]
    issue, number = _header(pages[0]) if pages else (None, None)
    if issue is None:
        raise ValueError(f"'{name}': data del listino non trovata")
    entries: list[Entry] = []
    for page in pages:
        if _read_page(page, entries):
            break
    if not entries:
        raise ValueError(f"nessun prezzo trovato in '{name}'")
    wrong = sorted({str(e.date) for e in entries if e.date != issue})
    if wrong:
        raise ValueError(f"'{name}' e' del {issue} ma le colonne dicono {', '.join(wrong)}")
    return FileMetadata(name, "PDF", number, issue), entries


def _normalize(page: Page) -> Page:
    """Toglie i caratteri invisibili e riattacca le parole che ne erano spezzate.

    In alcuni listini del 2021 fra una parola e l'altra non c'e' uno spazio ma
    un carattere invisibile, e qualche iniziale finisce in una parola a se'
    ("D" + "URO~").  Si uniscono due pezzi contigui solo se nessuno dei due ha
    un invisibile dalla parte del contatto: li', l'invisibile era lo spazio."""
    if not any(_INVISIBLE.search(w.text) for w in page.words):
        return page                 # i listini normali: spazi veri, niente da fare
    words: list[Word] = []
    glued = False                   # la parola precedente finiva con un invisibile
    for w in sorted(page.words, key=lambda w: (round(w.y), w.x0)):
        text = _INVISIBLE.sub("", w.text)
        prev = words[-1] if words else None
        if not text:
            # Un invisibile da solo dopo la parola fa da spazio; sovrapposto
            # alla parola (come quello fra "D" e "URO") no.
            if prev and w.x0 >= prev.x1 - 0.1:
                glued = True
            continue
        if (prev and not glued and not _INVISIBLE.match(w.text)
                and abs(prev.y - w.y) < 1 and -0.5 <= w.x0 - prev.x1 < 0.6):
            words[-1] = Word(prev.x0, w.x1, prev.y, max(prev.h, w.h), prev.text + text)
        else:
            words.append(Word(w.x0, w.x1, w.y, w.h, text))
        glued = bool(_INVISIBLE.search(w.text[-1:]))
    return Page(page.number, page.width, page.height, words)


def _header(page: Page) -> tuple[Optional[date], Optional[int]]:
    """"Anno 2026   N.40   Data 21/10/2026" (o "… del 14/07/2021") in cima."""
    for row in page.rows():
        texts = [w.text for w in row]
        if "Anno" in texts:
            days = [t for t in texts if _DATE.match(t)]
            if days:
                m = re.search(r"\bN\.?\s*(\d+)", " ".join(texts))
                return _date(days[-1]), int(m[1]) if m else None
    return None, None


def _read_page(page: Page, out: list[Entry]) -> bool:
    """Aggiunge a ``out`` le voci della pagina.  True se ha incontrato il listino
    CUN, dopo il quale non c'e' piu' niente da leggere."""
    table: Optional[_Table] = None
    lines: list[_Line] = []

    def flush() -> None:
        if table is not None and table.cols is not None:
            _emit(table, lines, page.number, out)
        lines.clear()

    for row in page.rows():
        text = " ".join(w.text for w in row)
        if _STOP.search(text):
            flush()
            return True
        riunione = [w for w in row if w.text == "Riunione"]
        if riunione:
            flush()
            table = _Table(riunione[0].x0)
        if table is None or _SKIP.match(text):
            continue
        # "prezzo min." puo' cominciare un po' a sinistra di "Riunione".
        marks = [w for w in row if _MINMAX.match(w.text) and w.x0 >= table.left - 30]
        if table.cols is None:
            # La testata: titolo e condizioni a sinistra, le date di riunione
            # sopra le colonne -- sulla riga di "Riunione" o su quella sotto.
            left = [w for w in row if w.x1 < table.left]
            table.dates += [w for w in row if _DATE.match(w.text) and w.x0 >= table.left - 30]
            # Il titolo e' il testo nel corpo piu' grande: in qualche listino
            # anche le condizioni di resa superano TITLE_HEIGHT, ma restano piu'
            # piccole del titolo.
            big = [w for w in left if w.h >= TITLE_HEIGHT and not _UNIT_WORD.match(w.text)]
            top = max((w.h for w in big), default=0)
            if top > table.title_h + 0.5:
                table.section, table.title_h = "", top
            title = [w.text for w in big if w.h >= table.title_h - 0.5]
            if title:
                table.section = clean(f"{table.section} {' '.join(title)}")
            table.caption += " " + " ".join(w.text for w in left)
            if len(marks) >= 2:
                _columns(table, marks)
            continue
        if len(marks) >= 2:
            continue
        cells, name = _cells(row, table.cols)
        if cells is not None:
            lines.append(_Line(row[0].y, name, cells))
        elif name:
            lines.append(_Line(row[0].y, name))
    flush()
    return False


def _columns(table: _Table, marks: list[Word]) -> None:
    days = sorted(table.dates, key=lambda w: w.x0)
    if len(days) >= 2 and len(marks) >= 4:
        table.prev, table.cur = _date(days[0].text), _date(days[1].text)
        table.cols = [w.xc for w in marks[:4]]
    elif len(days) == 1:
        table.cur = _date(days[0].text)
        table.cols = [None, None, marks[0].xc, marks[1].xc]


def _cells(row: list[Word], cols) -> tuple[Optional[list[Optional[float]]], list[Word]]:
    """I prezzi della riga, None se non ne ha (nemmeno un "NQ"), e le parole a
    sinistra delle colonne."""
    xs = [c for c in cols if c is not None]
    tol = min(b - a for a, b in zip(xs, xs[1:])) / 2
    edge = xs[0] - tol
    cells: list[Optional[float]] = [None] * 4
    has = False
    for w in row:
        if w.xc < edge:
            continue
        i = min((k for k in range(4) if cols[k] is not None), key=lambda k: abs(w.xc - cols[k]))
        if abs(w.xc - cols[i]) > tol:
            continue                # variazione e andamento: si ricalcolano
        value = parse_number(w.text)
        if value is None and not _BLANK.match(w.text):
            continue
        has = True
        cells[i] = value or None    # 0,00 = non quotato
    return (cells if has else None), [w for w in row if w.xc < edge]


def _owners(texts: list[_Line], priced: list[_Line], reach: float) -> dict[int, _Line]:
    """A quale riga di prezzi appartiene ogni riga di testo.

    Le righe si raccolgono prima in blocchi: un blocco comincia con una parola
    tutta in maiuscolo ("FINO (peso…", "CECE NAZIONALE") e prosegue con le righe
    che lo seguono a meno di ``reach``.  Poi ogni blocco va ai prezzi che
    stanno dentro la sua altezza (la cella centrata, il caso comune) o, se non
    ce ne sono, ai piu' vicini sotto di lui (la cella allineata in basso, coi
    prezzi sull'ultima riga del nome).  Mai a prezzi che hanno gia' un nome
    tutto loro in maiuscolo, ne' a prezzi sopra un blocco che apre un nome:
    in quei casi il blocco e' una voce senza celle e si scarta.
    """
    blocks: list[list[_Line]] = []
    for ln in sorted(texts, key=lambda ln: ln.y):
        if (blocks and not _OPENS.match(ln.text) and ln.y - blocks[-1][-1].y <= reach
                and not any(blocks[-1][-1].y < r.y < ln.y and _OPENS.match(r.text) for r in priced)):
            blocks[-1].append(ln)
        else:
            blocks.append([ln])
    owner: dict[int, _Line] = {}
    for block in blocks:
        top, bottom = block[0].y, block[-1].y
        opens = bool(_OPENS.match(block[0].text))
        inside = [r for r in priced if top - 1 <= r.y <= bottom + 1 and not _OPENS.match(r.text)]
        if inside:
            target = min(inside, key=lambda r: abs(r.y - (top + bottom) / 2))
        else:
            near = [r for r in priced if not _OPENS.match(r.text)
                    and (bottom < r.y <= bottom + reach or (not opens and top - reach <= r.y < top))]
            if not near:
                continue
            target = min(near, key=lambda r: min(abs(r.y - top), abs(r.y - bottom)))
        for ln in block:
            owner[id(ln)] = target
    return owner


def _emit(table: _Table, lines: list[_Line], page: int, out: list[Entry]) -> None:
    """Attacca a ogni riga di prezzi le righe di nome della sua cella; le altre
    righe di testo nel corpo e al margine dei nomi sono sottotitoli, il resto
    (condizioni di resa, note) si scarta."""
    priced = [ln for ln in lines if ln.cells is not None]
    if not priced:
        return
    named = [ln for ln in priced if ln.words]
    body = max(ln.h for ln in named) if named else max(ln.h for ln in lines)
    texts = [ln for ln in lines if ln.cells is None and ln.h >= body * 0.9]
    margin = min(ln.x0 for ln in (named or texts or priced) if ln.x0 is not None)
    texts = [ln for ln in texts if ln.x0 <= margin + 10]

    subs = [ln for ln in texts if _SUB.match(ln.text)]
    texts = [ln for ln in texts if ln in subs or not _TERMS.search(ln.text)]
    owner = _owners([ln for ln in texts if ln not in subs], priced, CELL_REACH * body)

    unit = unit_of(table.caption)
    for ln in sorted(texts + priced, key=lambda ln: ln.y):
        if ln.cells is None:
            if ln in subs:
                # "SEMOLA DI GRANO DURO ITALIANO i prezzi in €/t si intendono…":
                # il sottotitolo e' la merce, il resto sono le condizioni.
                table.sub = clean(re.sub(r"\s+i prezzi\b.*$", "", ln.text, flags=re.IGNORECASE))
                if unit_of(ln.text) != "unknown":
                    unit = unit_of(ln.text)
            continue
        parts = sorted([t for t in texts if owner.get(id(t)) is ln] + [ln], key=lambda t: t.y)
        name = clean(" ".join(t.text for t in parts if t.text))
        for pattern, repl in _LIGATURES:
            name = pattern.sub(repl, name)
        if not name:
            continue
        c = ln.cells
        path = tuple(p for p in (table.section, table.sub) if p)
        out.append(Entry(page, path, name, unit, table.cur, c[2], c[3], table.prev, c[0], c[1]))
