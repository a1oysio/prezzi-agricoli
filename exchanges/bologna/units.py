"""Unita' di misura dei listini della Borsa Merci di Bologna.

Come a Verona, l'unita' non e' una colonna: sta nel testo.  Qui sta in tre posti,
in ordine di priorita':

  1. nell'etichetta del prodotto ("mosto refrigerato bianco ... - EUR al kg");
  2. in un titolo di sezione ("PRODOTTI ORTOFRUTTICOLI di 1a qualita' - in EUR/kg.");
  3. nella riga che apre la tabella ("Prezzi in EUR/t, pronta consegna, ...").

L'ultima vale finche' un'altra non la sostituisce, perche' le tabelle successive
alla prima non la ripetono.  Se nulla la dichiara l'unita' resta ``unknown``:
meglio un buco dichiarato di un'unita' indovinata.

Le unita' canoniche sono quelle di ``exchanges.verona.units``, cosi' i due
dataset si leggono con lo stesso vocabolario.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

EUR_TON = "EUR/t"
EUR_KG = "EUR/kg"
EUR_L = "EUR/L"
EUR_GRADO_HL = "EUR/grado-hL"
EUR_Q = "EUR/q"
EUR_PZ = "EUR/pz"
UNKNOWN = "unknown"

# Il simbolo dell'euro e' scritto in modi diversi a seconda dell'anno e del
# programma che ha prodotto il PDF.
_EURO = r"(?:€|euro|eur)"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # "in EUR/grado x 100 litri": piu' specifico di "litri", va prima.
    # "in EUR al kg/litro": due unita' possibili, la fonte non dice quale.
    (re.compile(rf"{_EURO}\s*(?:/|al)\s*kg\s*/\s*l"), UNKNOWN),
    (re.compile(rf"{_EURO}\s*/\s*grado\s*x?\s*100\s*litri"), EUR_GRADO_HL),
    (re.compile(rf"{_EURO}\s*(?:/|al)\s*q(?:\.le|uintale)?(?![a-z])"), EUR_Q),
    (re.compile(rf"{_EURO}\s*/\s*cadauno|{_EURO}\s*/\s*capo"), EUR_PZ),
    (re.compile(rf"{_EURO}\s*/\s*t\b|{_EURO}\s*/\s*ton"), EUR_TON),
    (re.compile(rf"{_EURO}\s*(?:/|al)\s*kg\b"), EUR_KG),
    (re.compile(rf"{_EURO}\s*(?:/|al)\s*(?:l|litro)\b"), EUR_L),
]


# Il listino stesso dichiara il default: "I prezzi si intendono in EUR/t, pronta
# consegna, al netto dell'I.V.A., salvo diversa indicazione".  Le sezioni che
# escono dal default (ortofrutta, vini, formaggi) lo dichiarano nel proprio titolo.
DEFAULT_UNIT = EUR_TON

# Una sezione dichiarata in EUR/kg o in EUR/litro non si chiude con un cartello:
# il fieno che segue l'ortofrutta nei listini 2013-2016 non e' in EUR/kg.  Un
# titolo che apre una di queste sezioni "da tonnellata" riporta l'unita' al
# default.  L'elenco e' di dominio (cereali, mangimi, foraggi, riso, sementi) e
# chiuso: un titolo che non vi compare eredita l'unita' della sezione aperta,
# che e' quel che serve a "VINI IGP" sotto "VINI - ... in EUR/grado x 100 litri".
_TON_SECTIONS = re.compile(
    r"^(?:frument|granoturc|cereal|semi\b|semi\s|farin|sfarinat|cruscam|agricoltura\s+biolog"
    r"|prodotti\s+vegetal|derivat|grass|melass|varie\b|ris[io]|sottoprodott|foragg|paglia"
    r"|trinciat|sement|mais\b|erba\s+medica|polpe|artigianal|fieno|orzo|soia|sorgo|avena"
    r"|legumi|proteagin|oleagin)",
    re.IGNORECASE)

# Famiglie che non dichiarano mai l'unita': ereditare quella della sezione
# precedente darebbe un numero sbagliato (i mosti dopo l'ortofrutta non sono in
# EUR/kg).  Un titolo di queste famiglie azzera l'unita' ereditata.
_UNDECLARED_FAMILIES = re.compile(r"^(?:vini\s+e\s+mosti|mosti)\b", re.IGNORECASE)


def resets_unit(heading: str) -> bool:
    return bool(_UNDECLARED_FAMILIES.match(heading.strip()))


def is_ton_section(heading: str) -> bool:
    return bool(_TON_SECTIONS.match(heading.strip()))


def unit_hint(text: str) -> Optional[str]:
    """L'unita' dichiarata in un testo, o None."""
    low = text.lower()
    for pattern, unit in _PATTERNS:
        if pattern.search(low):
            return unit
    return None


def resolve_unit(label: str, path: Iterable[str], inherited: str = UNKNOWN) -> str:
    """Unita' di una riga: etichetta, poi titoli (dal piu' vicino), poi eredita'."""
    unit = unit_hint(label)
    if unit:
        return unit
    for heading in reversed(list(path)):
        unit = unit_hint(heading)
        if unit:
            return unit
    return inherited
