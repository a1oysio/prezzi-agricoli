"""Low-level XML helpers for Borsa Merci di Verona price files."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple

MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    # abbreviations used in some years
    "gen": 1, "feb": 2, "mar": 3, "apr": 4,
    "mag": 5, "giu": 6, "lug": 7, "ago": 8,
    "set": 9, "sett": 9, "ott": 10, "nov": 11, "dic": 12,
    # typos found in source files
    "novemebre": 11,
}


def _norm_month(m: str) -> int:
    return MONTHS[m.strip().lower()]


def _localname(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _child_text(node: ET.Element, name: str) -> str:
    for ch in list(node):
        if _localname(ch.tag) == name:
            return (ch.text or "").strip()
    return ""


def _child(node: ET.Element, name: str) -> Optional[ET.Element]:
    for ch in list(node):
        if _localname(ch.tag) == name:
            return ch
    return None


def _child_text_any(node: ET.Element, names: Iterable[str]) -> str:
    names_lc = {n.lower() for n in names}
    for ch in list(node):
        if _localname(ch.tag).lower() in names_lc:
            return (ch.text or "").strip()
    return ""


PRICE_LOW_TAGS = ("prezzomin", "prezzoMin", "prezzo_min", "quot_min", "min")
PRICE_HIGH_TAGS = ("prezzomax", "prezzoMax", "prezzo_max", "quot_max", "max")

NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _parse_number(raw: str, *, prefer_last: bool = False) -> Optional[float]:
    s = (raw or "").strip().replace("€", "").replace("EUR", "").replace("\xa0", " ").strip()
    nums = NUM_RE.findall(s)
    if not nums:
        return None
    token = nums[-1] if prefer_last else nums[0]
    return float(token.replace(".", "").replace(",", "."))


def _parse_price_range(raw: str) -> Optional[Tuple[float, float]]:
    s = (raw or "").strip().replace("€", "").replace("EUR", "").replace("\xa0", " ").strip()
    nums = NUM_RE.findall(s)
    if not nums:
        return None
    floats = [float(x.replace(".", "").replace(",", ".")) for x in nums]
    if len(floats) >= 2:
        lo, hi = floats[0], floats[1]
    else:
        lo = hi = floats[0]
    return (lo, hi) if lo <= hi else (hi, lo)


def _parse_single_price(raw: str, prefer_max: bool = False) -> Optional[float]:
    return _parse_number(raw, prefer_last=prefer_max)


def _fallback_price_from_children(node: ET.Element, prefer_max: bool) -> Optional[float]:
    needle = "max" if prefer_max else "min"
    for ch in list(node):
        if needle in _localname(ch.tag).lower():
            val = _parse_single_price(ch.text or "", prefer_max=prefer_max)
            if val is not None:
                return val
    return None


def _extract_price_pair(node: ET.Element) -> Tuple[Optional[float], Optional[float]]:
    pairs = [
        ("prezzomin", "prezzomax"),
        ("prezzoMin", "prezzoMax"),
        ("min", "max"),
        ("prezzo_min", "prezzo_max"),
        ("quot_min", "quot_max"),
    ]
    for a, b in pairs:
        lo_el = _child(node, a) or _child(node, a.capitalize())
        hi_el = _child(node, b) or _child(node, b.capitalize())
        if lo_el is not None and hi_el is not None:
            lo = _parse_single_price(lo_el.text or "", prefer_max=False)
            hi = _parse_single_price(hi_el.text or "", prefer_max=True)
            if lo is not None and hi is not None:
                return lo, hi

    lo = _fallback_price_from_children(node, prefer_max=False)
    hi = _fallback_price_from_children(node, prefer_max=True)
    if lo is not None and hi is not None:
        return lo, hi

    p_el = node.find("prezzo")
    if p_el is not None and (p_el.text or "").strip():
        rng = _parse_price_range(p_el.text or "")
        if rng is not None:
            return rng

    return None, None


# --- Date helpers ----------------------------------------------------------

RE_MONTHLY = re.compile(
    r"^\s*(?:medie\s+)?(?:anno\b|(?:" + "|".join(MONTHS.keys()) + r")\b)",
    flags=re.IGNORECASE,
)
RE_CLOSED = re.compile(r"\bchius", re.IGNORECASE)
RE_DATE_DD_MONTH_YYYY = re.compile(
    r"^\s*(\d{1,2})[\/\s\-](" + "|".join(MONTHS.keys()) + r")[\/\s\-](\d{4})\s*$",
    flags=re.IGNORECASE,
)
RE_DATE_DD_MM_YYYY = re.compile(r"^\s*(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\s*$")

DAYS = [
    "lunedi'", "lunedì", "martedi'", "martedì", "mercoledi'", "mercoledì",
    "giovedi'", "giovedì", "venerdi'", "venerdì", "sabato", "domenica",
]
RE_TITLE_DOW_DATE = re.compile(
    r"""(?ix)
    ^\s*
    (""" + "|".join(DAYS) + r""")
    \s+(\d{1,2})\s+
    (""" + "|".join(MONTHS.keys()) + r""")
    \s+(\d{4})\s*$
    """,
)
RE_TITLE_RIL_DEL_DATE = re.compile(
    r"""(?ix)
    \brilevazione\b
    (?:\s+(?:n|no)\.?|\s+n[°º])?
    (?:\s*\d+)?
    \s+del\s+
    (\d{1,2})\s+
    (""" + "|".join(MONTHS.keys()) + r""")\s+
    (\d{4})
    """,
)
RE_TITLE_RIL_DEL_DATE_NUM = re.compile(
    r"""(?ix)
    \brilevazione\b
    (?:\s+(?:n|no)\.?|\s+n[°º])?
    (?:\s*\d+)?
    \s+del\s+
    (\d{1,2})[/\-](\d{1,2})[/\-](\d{4})
    """,
)


def parse_commission_date(root: ET.Element) -> Optional[str]:
    el = root.find(".//commissione/data")
    if el is None:
        return None
    raw = (el.text or "").strip()
    if not raw:
        return None
    m = RE_DATE_DD_MONTH_YYYY.match(raw)
    if m:
        dd, mm, yyyy = int(m.group(1)), _norm_month(m.group(2)), int(m.group(3))
        return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    m = RE_DATE_DD_MM_YYYY.match(raw)
    if m:
        dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", ""))
        return dt.date().isoformat()
    except Exception:
        return None


def _root_nome(root: ET.Element) -> str:
    """Return the text of the top-level <nome> element regardless of nesting."""
    el = root.find(".//rilevazione/nome") or root.find("nome")
    return (el.text or "").strip() if el is not None else ""


def parse_title_date(root: ET.Element) -> Optional[str]:
    name = _root_nome(root)
    m = RE_TITLE_RIL_DEL_DATE.search(name)
    if m:
        dd, mm, yyyy = int(m.group(1)), _norm_month(m.group(2)), int(m.group(3))
        return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    m = RE_TITLE_RIL_DEL_DATE_NUM.search(name)
    if m:
        dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    m = RE_TITLE_DOW_DATE.match(name)
    if m:
        dd, mm, yyyy = int(m.group(2)), _norm_month(m.group(3)), int(m.group(4))
        return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    return None


def classify_file_type(root: ET.Element) -> Tuple[str, Optional[Tuple[int, int]]]:
    if parse_commission_date(root):
        return "WEEKLY", None
    if parse_title_date(root):
        return "WEEKLY", None
    name = _root_nome(root)
    if RE_MONTHLY.match(name):
        return "MONTHLY", None
    if RE_CLOSED.search(name):
        return "CLOSED", None
    return "UNKNOWN", None


def guess_file_number_from_name(file_path: Path) -> Optional[int]:
    try:
        return int(Path(file_path).stem)
    except Exception:
        return None


def iter_products_rows(
    root: ET.Element,
) -> Iterator[Tuple[str, str, Tuple[str, ...], Optional[float], Optional[float]]]:
    """Yield (product_id, product_name, category_path, low, high) from an XML root.

    low/high sono None quando il prodotto non e' stato quotato.

    category_path is the full chain of 'categoria' ancestors, outermost first.

    Serve il path intero, non la sola foglia: l'unita' di misura e' annotata in
    un livello qualsiasi della gerarchia (vedi exchanges.verona.units) e il nome
    della foglia da solo non identifica il prodotto -- "a busto" compare sotto
    POLLI, ANITRE, TACCHINI e FARAONE.
    """
    # Build parent map so we can walk up the tree
    parent_map: dict[ET.Element, ET.Element] = {
        child: parent for parent in root.iter() for child in parent
    }

    def _category_path(node: ET.Element) -> Tuple[str, ...]:
        levels: list[str] = []
        current = parent_map.get(node)
        while current is not None:
            if _localname(current.tag) == "categoria":
                name = _child_text(current, "nome")
                if name:
                    levels.append(name)
            current = parent_map.get(current)
        return tuple(reversed(levels))

    for node in root.iter():
        if _localname(node.tag) != "prodotti":
            continue
        cat_path = _category_path(node)
        for prod in list(node):
            if _localname(prod.tag) != "prodotto":
                continue
            pid = _child_text(prod, "id")
            if not pid:
                continue
            pname = _child_text(prod, "nome") or f"prod-{pid}"
            lo_s = _child_text_any(prod, PRICE_LOW_TAGS)
            hi_s = _child_text_any(prod, PRICE_HIGH_TAGS)
            lo = _parse_single_price(lo_s, prefer_max=False)
            hi = _parse_single_price(hi_s, prefer_max=True)
            if lo is None or hi is None:
                rng = _parse_price_range(_child_text(prod, "prezzo"))
                if rng is not None:
                    lo, hi = rng
            if lo is None:
                lo = _fallback_price_from_children(prod, prefer_max=False)
            if hi is None:
                hi = _fallback_price_from_children(prod, prefer_max=True)
            # Zero e negativi non sono prezzi.
            #
            # Lo zero e' l'assenza di quotazione per quella rilevazione: va
            # emesso come None, perche' "questa settimana il prodotto non e'
            # stato quotato" e' un'informazione, e salvarlo come 0.0 falserebbe
            # medie e grafici.
            #
            # I negativi sono due convenzioni diverse della borsa che finiscono
            # negli stessi campi: uno scarto rispetto al massimo (il Carnaroli
            # quotato "-50 / 1900" la settimana dopo un "2100 / 2150"), oppure
            # la variazione settimanale (min = max = -13). Nessuna delle due e'
            # un prezzo, e ricostruire l'intento significherebbe indovinare:
            # meglio dichiarare non quotato il campo che non sappiamo leggere.
            lo = None if lo is None or lo <= 0.0 else lo
            hi = None if hi is None or hi <= 0.0 else hi
            yield pid.strip(), pname.strip(), cat_path, lo, hi
