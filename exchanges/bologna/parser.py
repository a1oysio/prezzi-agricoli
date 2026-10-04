"""Estrae le quotazioni da un listino settimanale PDF della Borsa Merci di Bologna.

Il PDF e' testo vero (generato da Excel/PDFCreator), non una scansione: si
estrae con ``pdftotext -layout``, che conserva l'allineamento a colonne.  Ogni
riga di prezzo ha, nell'ordine::

    etichetta   min  max  |  min  max  |  diff. min  diff. max
                settimana    settimana
                precedente   corrente

Un trattino ``-`` significa "non quotato".  Una cella vuota significa un'altra
cosa: il prodotto non esisteva ancora (o non esiste piu') in quella settimana.
Per distinguerle e per assegnare le celle alle colonne giuste quando ne mancano,
si usa la posizione orizzontale dei numeri, non il loro ordine.

La differenza stampata nell'ultima coppia di colonne e' ridondante e per questo
preziosa: ``corrente - precedente`` deve coincidere con essa.  Il parser la usa
come controllo e riporta le righe in cui non torna (``ParsedBulletin.mismatches``).
Non corregge nulla: il valore resta quello stampato.

Le etichette lunghe vanno a capo con i numeri sulla riga *in mezzo*::

    granoturco ... (afla B1 max. 3 ppb/DON max.        <- testo
                                       360,00 390,00 ...   <- solo numeri
    3000 ppb)                                          <- seguito dell'etichetta

Una riga di solo testo seguita da una di soli numeri e' quindi l'inizio
dell'etichetta; una riga di solo testo seguita da una riga completa e' invece un
titolo di sezione.

Identita' dei prodotti
----------------------
La fonte non ha codici.  Un prodotto e' identificato da ``(percorso, etichetta)``,
dove il percorso e' l'ultimo titolo scritto in MAIUSCOLO piu' gli eventuali
sottotitoli che lo seguono.  Non si usano i titoli piu' in alto perche' le
sezioni vuote vanno e vengono di settimana in settimana: legare l'identita' a
una gerarchia che cambia spezzerebbe ogni serie storica.

Il criterio di fondo e' che, nel dubbio, **meglio spezzare una serie che
fonderne due diverse**: una serie spezzata si ricuce con una tabella di
corrispondenze, una fusa per errore inquina i dati senza che nessuno se ne
accorga.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from statistics import median
from typing import Optional

from exchanges.bologna.units import (
    DEFAULT_UNIT, UNKNOWN, is_ton_section, resets_unit, resolve_unit, unit_hint,
)

MONTHS = {
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
}

# Un prezzo ha sempre due decimali.  I petroliferi (1,427 EUR/l) ne hanno tre:
# non sono prezzi di borsa e non devono passare.
_NUM = r"-?\d{1,3}(?:\.\d{3})+,\d{2}(?!\d)|-?\d+,\d{2}(?!\d)"
# "-" e "n.r." (non rilevato, dal 2019) significano entrambi "non quotato".
# Il PDF esportato da Excel puo' anche portare il testo di un errore di formula
# ("#VALORE!") al posto del prezzo: e' un buco della fonte, non un numero.
_EXCEL_ERROR = r"#(?:VALORE|RIF|DIV/0|N/D|NOME|NUM)[!?]?"
NOT_QUOTED = ("-", "n.r.")
_TOKEN = re.compile(rf"(?<!\S)(?:{_NUM}|-|n\.r\.|{_EXCEL_ERROR})(?!\S)")
_DATE = re.compile(r"(\d{1,2})[\s\-.]+([A-Za-zà-ù]{3,9})[\s\-.]+(\d{2,4})")
_TITLE = re.compile(
    r"Listino\s+settimanale\s+dei\s+prezzi\s+all.ingrosso\s+n\.?\s*(\d+)\s+"
    r"del(?:\s+|l['\u2019]\s*)(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)
_FOOTNOTE = re.compile(r"^(?:\(\s*[\d*]+\s*\)|\d+\))")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_FOOTREF = re.compile(r"(?:\s*(?:\(\s*[\d*]+\s*\)|\(\*+\)))+\s*$")
# Sezioni fuori schema, ignorate finche' non comincia un'altra sezione:
#  * petroliferi: prezzi alla pompa, tre decimali, rilevazione quindicinale;
#  * suini e carni: una sola colonna di prezzo e tre decimali (sono i prezzi
#    della Borsa di Modena, ripubblicati), non il min/max delle altre tabelle.
_SKIP_SECTION = re.compile(
    r"PETROLIFER|GASOLIO|CARBURANT|BENZINA|AUTOTRAZIONE|RISCALDAMENTO|COMBUSTIBIL"
    r"|^SUINI\b|^CARNI\b|^SALUMI\b|CARCASS|OSSERVAPREZZI", re.IGNORECASE)

# Una riga di dati con tre decimali (i suini del 2013 stanno sotto "BURRO e
# FORMAGGI", senza un titolo proprio da saltare) non e' un titolo.
_DECIMALS = re.compile(r"\d,\d{2,3}(?!\d)")

# Un titolo comincia al margine sinistro: il testo rientrato e' un commento
# dell'andamento ("in buona vista"), un frammento o la parte redazionale.
MAX_HEADING_INDENT = 20
_HEADER_WORDS = re.compile(
    r"\b(?:min|max|franco\s+partenza|franco\s+arrivo|differenza|andamento|preval\w*|fds)\b",
    re.IGNORECASE)
# Parole d'intestazione in coda alla riga: "... min max min max", "... differenza",
# oppure la coppia di date delle colonne.
_HEADER_TAIL = re.compile(
    r"\s(?:min\s+max(?:\s+min\s+max)?|differenza|(?:\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\s*){2})\s*$",
    re.IGNORECASE)
_TABLE_LINE = re.compile(r"(?i)^(?:i\s+)?prezzi\s+(?:in|si\s+intendono|medi)\b")

# Righe di solo testo che non sono titoli: numeri di pagina, indirizzi, la parola
# d'andamento che i listini vecchi stampano sotto le righe ("stazionario").
_NOISE = re.compile(
    r"^(?:\d{1,3}|_+|campagna\s*\d{4}|stazionari[oa]|calm[oa]|sostenut[oa]|ferm[oa]|debole|invariat[oa]"
    r"|in buona vista|meglio tenuto|direttore responsabile|redazione|dott\.?s?s?a?\b.*)$"
    r"|https?://|@|\bwww\.|\btel\.", re.IGNORECASE)

# Le griglie delle carcasse bovine ("U3  284,85   O2  202,60"): classi EUROP, non
# prezzi per prodotto.  Fuori dallo schema: si ignorano senza segnalarle.
_BEEF_GRID = re.compile(r"^[UREOP][1-5]\s")

# Distanza massima (in caratteri) fra la fine di un numero e il centro della
# colonna a cui lo assegniamo.  Due colonne contigue distano circa 10-14.
COLUMN_TOLERANCE = 5


class UnreadablePdf(ValueError):
    """Il listino non si legge.

    ``garbled`` distingue due cose molto diverse.  Vero: il PDF ha caratteri
    codificati male (il 2012 e circa il 3% dei listini successivi) e non c'e'
    testo da leggere -- un difetto del file, che la settimana dopo rimedia
    perche' ripete i prezzi.  Falso: il testo c'e' ma non e' quello atteso,
    cioe' l'impaginazione e' cambiata, ed e' un guasto del parser.
    """

    def __init__(self, message: str, garbled: bool = False):
        super().__init__(message)
        self.garbled = garbled


_KNOWN_WORDS = re.compile(r"\b(?:prezzi|listino|frumento|camera|commercio|bologna|granoturco)\b",
                          re.IGNORECASE)


@dataclass
class Row:
    path: tuple[str, ...]          # titoli di sezione, dal piu' generale
    label: str
    unit: str
    cur: tuple[Optional[float], Optional[float]]
    prev: tuple[Optional[float], Optional[float]]
    printed_diff: tuple[Optional[float], Optional[float]]
    cur_listed: bool               # c'e' una cella (anche "-") nelle colonne correnti
    prev_listed: bool


@dataclass
class ParsedBulletin:
    number: int
    date: date
    prev_date: Optional[date]
    rows: list[Row] = field(default_factory=list)
    mismatches: list[Row] = field(default_factory=list)    # la differenza non torna
    unassigned: list[str] = field(default_factory=list)    # righe con numeri non collocabili


def extract_text(pdf: Path) -> str:
    try:
        out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                             capture_output=True, check=True, timeout=60)
    except FileNotFoundError as exc:
        raise RuntimeError("pdftotext non trovato: installa poppler-utils") from exc
    except subprocess.CalledProcessError as exc:
        raise UnreadablePdf(f"{pdf.name}: {exc.stderr.decode(errors='replace')[:200]}")
    return out.stdout.decode("utf-8", errors="replace")


def _num(token: str) -> float:
    return float(token.replace(".", "").replace(",", "."))


def _price(token: Optional[str]) -> Optional[float]:
    """Zero e negativi non sono prezzi: come a Verona, restano campo vuoto."""
    if token is None or token in NOT_QUOTED or token.startswith("#"):
        return None
    v = _num(token)
    return v if v > 0 else None


def _printed_diff(token: Optional[str]) -> Optional[float]:
    if token is None or token in NOT_QUOTED or token.startswith("#"):
        return None
    return _num(token)


def _parse_date(day: str, month: str, year: str) -> Optional[date]:
    m = MONTHS.get(month[:3].lower())
    if not m:
        return None
    y = int(year)
    y += 2000 if y < 100 else 0
    try:
        return date(y, m, int(day))
    except ValueError:
        return None


@dataclass
class _Line:
    text: str
    label: str
    tokens: list[tuple[str, int]]          # (token, posizione finale)
    raw: str = ""                          # la riga com'era, per le intestazioni
    indent: int = 0                        # spazi a sinistra


def _split(raw: str) -> _Line:
    ln = _split_numbers(raw)
    ln.indent = len(raw) - len(raw.lstrip())
    ln.raw = raw.strip()
    return ln


def _split_numbers(raw: str) -> _Line:
    """Separa l'etichetta dalla zona dei numeri, a destra."""
    raw = raw.rstrip()
    toks = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(raw)]
    run: list[tuple[str, int, int]] = []
    for t in reversed(toks):
        if not run:
            tail = raw[t[2]:]
            if tail.strip() and re.search(r"\d", tail):
                break               # dopo il token c'e' altro con cifre: non e' una coda
            run.append(t)
        elif not raw[t[2]:run[-1][1]].strip():
            run.append(t)
        else:
            break
    run.reverse()
    # "RISONI - per merce sfusa": il trattino separa, non vuol dire "non quotato".
    # Una riga di soli trattini ne ha almeno quattro (due prezzi, due prezzi).
    if run and all(t[0] == "-" for t in run) and len(run) < 4:
        run = []
    if not run:
        # Il commento dell'andamento ("stazio..."), staccato da un largo vuoto, non
        # fa parte del testo della riga.
        text = re.split(r"\s{10,}", raw.strip())[0]
        return _Line(text, text, [])
    return _Line(raw.strip(), raw[:run[0][1]].strip(), [(t[0], t[2]) for t in run])


def _header_leftover(raw: str) -> Optional[str]:
    """Se la riga e' un'intestazione di colonna ritorna il testo che le sta accanto.

    ``""`` per un'intestazione pura (solo min/max/differenza e date), ``None`` se
    non e' un'intestazione.  Non basta cercare "min" e "max": le etichette dei
    prodotti li contengono ("prot. 12% min ... volp.6% max"), quindi le parole
    d'intestazione devono stare da sole o in coda alla riga.
    """
    t = raw.strip()
    if not _HEADER_WORDS.search(t):
        return None
    rest = re.sub(r"\s+", " ", _DATE.sub("", _HEADER_WORDS.sub("", t))).strip(" -")
    if not re.search(r"[A-Za-zÀ-ÿ]", rest):
        return ""
    tail = _HEADER_TAIL.search(t)
    if tail:
        return re.sub(r"\s+", " ", t[:tail.start()]).strip()
    return None


def _is_upper_heading(text: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-Üà-ü]+", text)
    return bool(words) and len(words[0]) >= 3 and words[0].isupper()


# Una cella di titolo va a capo oltre circa 52 caratteri: la riga che segue,
# se comincia in minuscolo, ne e' il seguito ("... - merce posta" / "su veicolo
# partenza ...").  Una o due parole minuscole isolate ("arrivo", "rinfusa
# arrivo") sono frammenti dello stesso genere.
WRAP_WIDTH = 52


def _continues_heading(prev_width: int, text: str) -> bool:
    if not text[:1].islower() or " - " in text or text.endswith(":"):
        return False        # un sottotitolo vero ("vini a I.G.T. - sfusi ... :") ha trattino o due punti
    words = len(text.split())
    return words <= 2 or (prev_width >= WRAP_WIDTH and words <= 8)


def _is_label_tail(text: str) -> bool:
    """Il seguito di un'etichetta spezzata, non un nuovo titolo.

    "3000 ppb)" o "max CENTRO" lo sono; "SEMI OLEOSI" no.  Una sola parola
    maiuscola e breve ("CENTRO", "NORD") e' un suffisso d'area, non una sezione.
    """
    if not _is_upper_heading(text):
        return True
    words = text.split()
    return len(words) == 1 and len(words[0]) <= 8


def _clean_heading(text: str) -> str:
    """Un titolo di sezione senza l'anno di raccolto e senza richiami di nota.

    L'annata cambia ogni anno ("produzione nazionale 2025" -> "... 2026"): se
    restasse nel titolo ogni raccolto avrebbe un prodotto proprio e nessuna
    serie storica supererebbe luglio.  La data della quotazione dice gia' a che
    annata si riferisce.
    """
    t = _YEAR.sub("", _FOOTREF.sub("", text))
    return re.sub(r"\s+", " ", t).strip(" -,:")


def clean_label(text: str) -> str:
    return re.sub(r"\s+", " ", _FOOTREF.sub("", text)).strip()


def _column_centres(rows: list[list[tuple[str, int]]]) -> Optional[list[int]]:
    """Posizione finale tipica di ciascuna colonna, dalle righe che le hanno tutte.

    Sono sei (prezzi e differenze); alcune tabelle ne hanno una settima, il prezzo
    "prevalente" dell'ortofrutta biologica, che qui non serve ma va riconosciuta
    per non scambiarla per un prezzo.
    """
    full = [r for r in rows if len(r) >= 6]
    if not full:
        return None
    n = 7 if sum(1 for r in full if len(r) >= 7) >= 2 else 6
    return [int(median(r[i][1] for r in full if len(r) > i)) for i in range(n)]


def _assign(tokens: list[tuple[str, int]], centres: Optional[list[int]]
            ) -> Optional[list[Optional[str]]]:
    """Colloca i token nelle sei colonne.  None se non si puo' farlo con certezza."""
    # Un trattino molto a sinistra della prima colonna e' un separatore
    # dell'etichetta ("orzo - 198,00 203,00").  Nei PDF Excel i trattini "non
    # quotato" sono centrati nella cella, non allineati a destra come i numeri:
    # possono stare qualche carattere a sinistra della colonna senza essere
    # separatori.  Si scarta solo oltre una colonna intera di distanza.
    if centres and len(tokens) != 6:
        while tokens and tokens[0][0] == "-" and tokens[0][1] < centres[0] - 12:
            tokens = tokens[1:]
    cols: list[Optional[str]] = [None] * 7
    if len(tokens) in (6, 7):
        for i, (tok, _end) in enumerate(tokens):
            cols[i] = tok
        return cols[:6]
    if len(tokens) > 7 or centres is None:
        return None
    for tok, end in tokens:
        best = min(range(len(centres)), key=lambda i: abs(centres[i] - end))
        if abs(centres[best] - end) > COLUMN_TOLERANCE or cols[best] is not None:
            return None
        cols[best] = tok
    return cols[:6]


def _pair(a: Optional[str], b: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    return _price(a), _price(b)


def _classify(text: str) -> list[tuple[str, _Line]]:
    """Righe del testo con il loro tipo.

    PAGE/TITLE  inizio pagina
    HEADER      intestazione di colonna (``text`` e' il testo accanto, se c'e')
    N           solo numeri (l'etichetta e' nella riga precedente)
    R           etichetta e numeri
    T           solo testo: titolo, nota o inizio/seguito di un'etichetta
    """
    out: list[tuple[str, _Line]] = []
    for page in text.split("\f"):
        out.append(("PAGE", _split("")))
        for raw in page.splitlines():
            if not raw.strip():
                continue
            ln = _split(raw)
            if _TITLE.search(raw):
                out.append(("TITLE", ln))
                continue
            leftover = None if ln.tokens else _header_leftover(raw)
            if leftover is not None:
                out.append(("HEADER", _Line(leftover, leftover, [], raw.strip())))
            elif ln.tokens and not ln.label:
                out.append(("N", ln))
            elif ln.tokens:
                out.append(("R", ln))
            else:
                out.append(("T", ln))
    return out


def parse_text(text: str, source: str = "") -> ParsedBulletin:
    """Interpreta il testo di un listino.  Solleva UnreadablePdf se non ne e' uno."""
    title = _TITLE.search(text)
    if not title:
        raise UnreadablePdf(f"{source}: titolo del listino non trovato",
                            garbled=len(_KNOWN_WORDS.findall(text)) < 3)
    day = _parse_date(title.group(2), title.group(3), title.group(4))
    if day is None:
        raise UnreadablePdf(f"{source}: data illeggibile '{title.group(0)}'")
    out = ParsedBulletin(number=int(title.group(1)), date=day, prev_date=None)

    # Il primo paio di date nelle intestazioni di colonna e' (precedente, corrente).
    for line in text.splitlines():
        found = [d for d in (_parse_date(*m.groups()) for m in _DATE.finditer(line)) if d]
        if len(found) == 2 and found[1] == day and found[0] < day:
            out.prev_date = found[0]
            break

    lines = _classify(text)

    # Centri di colonna per blocco (fra due intestazioni): servono a collocare le
    # righe che hanno celle vuote.  Un blocco senza righe complete ne eredita.
    centres_at: dict[int, Optional[list[int]]] = {}
    block: list[list[tuple[str, int]]] = []
    start = 0
    for i, (kind, ln) in enumerate(lines + [("PAGE", _split(""))]):
        if kind in ("HEADER", "PAGE", "TITLE"):
            c = _column_centres(block)
            for j in range(start, i):
                centres_at[j] = c
            block, start = [], i
        elif kind in ("R", "N"):
            block.append(ln.tokens)
    inherited: Optional[list[int]] = None
    for j in range(len(lines) - 1, -1, -1):
        if centres_at.get(j) is None:
            centres_at[j] = inherited
        else:
            inherited = centres_at[j]

    run: list[str] = []                 # titoli dall'ultima riga o intestazione
    run_widths: list[int] = []          # lunghezza della riga di ciascun titolo (se e' andato a capo)
    path: tuple[str, ...] = ()
    last_upper: Optional[str] = None
    sticky_unit = DEFAULT_UNIT
    skipping = False
    in_footnote = False
    pending: Optional[str] = None       # inizio d'etichetta in attesa dei numeri
    open_row: Optional[Row] = None      # riga con etichetta spezzata: la coda puo' seguire

    def commit_run() -> None:
        nonlocal path, last_upper, run
        if not run:
            return
        idx = [i for i, h in enumerate(run) if _is_upper_heading(h)]
        if idx:
            last_upper = run[idx[-1]]
            path = tuple(_clean_heading(h) for h in run[idx[-1]:])
        elif last_upper:
            path = (_clean_heading(last_upper),) + tuple(_clean_heading(h) for h in run)
        else:
            path = tuple(_clean_heading(h) for h in run)
        path = tuple(h for h in path if h)
        run = []
        run_widths.clear()

    def ignorable(kind: str, ln: _Line) -> bool:
        """Righe di solo testo che non fanno parte del flusso etichetta/numeri."""
        return kind == "T" and (ln.indent >= MAX_HEADING_INDENT or bool(_NOISE.search(ln.text))
                                or len(_DECIMALS.findall(ln.raw)) >= 2)

    def following(i: int) -> str:
        """Il tipo della riga successiva, saltando commenti e rumore."""
        j = i + 1
        while j < len(lines) and ignorable(*lines[j]):
            j += 1
        return lines[j][0] if j < len(lines) else "PAGE"

    for i, (kind, ln) in enumerate(lines):
        nxt = following(i)

        if kind in ("PAGE", "TITLE"):
            run, pending, open_row, in_footnote = [], None, None, False
            run_widths.clear()
            continue
        if kind == "HEADER" and open_row is not None and ln.raw.lower() in ("min", "max"):
            # "...volp.6%" / numeri / "max": e' la coda dell'etichetta, non l'intestazione.
            open_row.label = clean_label(f"{open_row.label} {ln.raw}")
            open_row.unit = resolve_unit(open_row.label, open_row.path, sticky_unit)
            open_row = None
            continue
        if kind == "HEADER":
            run, pending, open_row, in_footnote = [], None, None, False
            run_widths.clear()
            if ln.text:                       # intestazione con testo: e' un titolo
                hint = unit_hint(ln.text)
                if hint:
                    sticky_unit = hint
                run.append(ln.text)
                run_widths.append(len(ln.text))
            continue

        if kind == "T":
            text = ln.text
            if _TABLE_LINE.match(text) and not _is_upper_heading(text):
                hint = unit_hint(text)
                if hint:
                    sticky_unit = hint
                continue
            if _FOOTNOTE.match(text):
                in_footnote = True
                continue
            if (in_footnote or " = " in text or text.endswith("=") or _NOISE.search(text)
                    or ln.indent >= MAX_HEADING_INDENT or len(_DECIMALS.findall(ln.raw)) >= 2):
                continue                      # note a pie' di tabella, legende, rumore
            # Il seguito di un'etichetta spezzata sta subito dopo i numeri.
            if open_row is not None and nxt != "N" and _is_label_tail(text):
                open_row.label = clean_label(f"{open_row.label} {text}")
                open_row.unit = resolve_unit(open_row.label, open_row.path, sticky_unit)
                open_row = None
                continue
            open_row = None
            if nxt == "N" or (nxt == "R" and text.rstrip().endswith(",") and not _is_upper_heading(text)):
                # L'etichetta continua nella riga dei numeri: o i numeri stanno da
                # soli in mezzo, o la seconda meta' ("volp.8%") ha i numeri accanto.
                pending = text
                continue
            upper = _is_upper_heading(text)
            if _SKIP_SECTION.search(text) and upper:
                skipping = True
                continue
            if skipping:
                if not upper:
                    continue                  # righe della sezione ignorata
                skipping = False
            if text.count(")") > text.count("("):
                continue                      # frammento di una frase a capo
            if resets_unit(text):
                sticky_unit = UNKNOWN
            elif is_ton_section(text):
                sticky_unit = DEFAULT_UNIT
            hint = unit_hint(text)
            if hint:
                sticky_unit = hint
            if len(text.split()) >= 9 and not upper and " - " not in text and not text.endswith(":"):
                continue                      # una frase, non un titolo: conta solo l'unita'
            if run and _continues_heading(run_widths[-1], text):
                run[-1] = f"{run[-1]} {text}"
                run_widths[-1] = 0
                continue
            run.append(text)
            run_widths.append(len(text))
            continue

        # R o N: una riga di numeri
        in_footnote = False
        if skipping:
            pending = None
            continue
        wrapped = kind == "N"
        label = ln.label if kind == "R" else (pending or "")
        if kind == "R" and pending:
            label = f"{pending} {ln.label}"
        pending = None
        if not label:
            # Righe di soli trattini senza etichetta non portano informazione.
            if not _BEEF_GRID.match(ln.text) and any(t != "-" for t, _ in ln.tokens):
                out.unassigned.append(ln.text)
            continue
        cols = _assign(ln.tokens, centres_at.get(i))
        if cols is None:
            if not _BEEF_GRID.match(ln.text):
                out.unassigned.append(f"{label} | {ln.text}")
            continue

        commit_run()
        clean = clean_label(label)
        row = Row(
            path=path,
            label=clean,
            unit=resolve_unit(clean, path, sticky_unit),
            cur=_pair(cols[2], cols[3]),
            prev=_pair(cols[0], cols[1]),
            printed_diff=(
                _printed_diff(cols[4]), _printed_diff(cols[5]),
            ),
            cur_listed=cols[2] is not None or cols[3] is not None,
            prev_listed=cols[0] is not None or cols[1] is not None,
        )
        out.rows.append(row)
        open_row = row if wrapped else None

        # Controllo aritmetico: corrente - precedente = differenza stampata.
        if all(c is not None and c not in NOT_QUOTED and not c.startswith("#") for c in cols[:6]):
            vals = [_num(c) for c in cols[:6]]
            if any(abs((vals[2 + k] - vals[k]) - vals[4 + k]) > 0.011 for k in (0, 1)):
                out.mismatches.append(row)

    _disambiguate(out)
    return out


def _disambiguate(bulletin: ParsedBulletin) -> None:
    """Etichette identiche sotto lo stesso titolo, nello stesso listino.

    Succede quando due tabelle ripetono le stesse voci (i vini sfusi "Bianco
    Emilia" in due formati di vendita).  Alla seconda e alle seguenti si aggiunge
    un ordinale al percorso: la prima conserva l'identita' di sempre, e nessuna
    delle due si fonde con l'altra nello stesso listino.
    """
    seen: Counter[tuple[tuple[str, ...], str]] = Counter()
    for row in bulletin.rows:
        key = (row.path, row.label)
        seen[key] += 1
        if seen[key] > 1:
            row.path = row.path + (f"#{seen[key]}",)


def parse_pdf(pdf: Path) -> ParsedBulletin:
    return parse_text(extract_text(pdf), source=pdf.name)
