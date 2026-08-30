"""Deduzione dell'unità di misura dei listini di Borsa Merci di Verona.

L'unità non è un campo dell'XML: è annotata in linguaggio naturale nel nome
del prodotto oppure nel testo di uno dei livelli di categoria, per esempio::

    CEREALI (prezzo base per Tonnellata)          ← unità qui
      └ SFARINATI
         └ Farine di frumento
            └ a) ad alto contenuto di glutine
               └ prodotto "tipo 00"               ← nessuna unità

L'ordine di risoluzione è: nome del prodotto, poi i livelli di categoria dalla
foglia verso la radice, infine la tabella di override.  Il nome viene prima
perché nella stessa categoria convivono unità diverse -- sotto
"VINI I.G.T. Verona" il merlot è quotato in grado/100 litri e il moscato in
euro/litro.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# Unità canoniche emesse da questo modulo.
EUR_TON = "EUR/t"
EUR_KG = "EUR/kg"
EUR_L = "EUR/L"
EUR_1000L = "EUR/1000L"
EUR_GRADO_HL = "EUR/grado-hL"        # euro per grado alcolico su 100 litri
EUR_GRADO_100KG = "EUR/grado-100kg"  # euro per grado alcolico su 100 kg
EUR_100PZ = "EUR/100pz"
UNKNOWN = "unknown"

# L'ordine conta: i pattern più specifici vanno prima, perché i testi si
# sovrappongono ("1 grado/100 litri" contiene sia "100" che "litri").
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"1000\s*litri"), EUR_1000L),
    (re.compile(r"grado\s*/\s*100\s*litri"), EUR_GRADO_HL),
    (re.compile(r"alcol\s*potenziale\s*/\s*100\s*kg"), EUR_GRADO_100KG),
    (re.compile(r"tonnellata|/\s*ton\b"), EUR_TON),
    (re.compile(r"kilogramm|per\s*kg|/\s*kg\b"), EUR_KG),
    (re.compile(r"litro|litri"), EUR_L),
    (re.compile(r"per\s*100\b"), EUR_100PZ),
]

# Categorie il cui testo non nomina mai l'unita'.  Sono override sul path
# anziche' sul codice prodotto perche' la borsa assegna codici nuovi ogni
# annata: agganciarsi al path copre anche le vendemmie future.
#
# Ogni ipotesi e' verificata sull'ordine di grandezza dei prezzi, confrontando
# con la categoria sorella che l'unita' ce l'ha:
#   - ripasso 2,7-3,4 contro 4,31 del Valpolicella d.o.c.        -> EUR/L
#   - uve bio 0,29-0,53 contro 1,70 delle uve atte a d.o.c.      -> EUR/kg
#   - uve in appassimento 2,4-3,4, sorelle di "UVE APPASSITE
#     (prezzo base per kg)"                                      -> EUR/kg
_PATH_OVERRIDES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"valpolicella\s+ripasso"), EUR_L),
    (re.compile(r"uve\s+da\s+vino\s+di\s+produzione\s+biologica"), EUR_KG),
    (re.compile(r"uve\s+in\s+appassimento"), EUR_KG),
    (re.compile(r"uva\s+appassita"), EUR_KG),
    (re.compile(r"prosciutto\s+veneto\s+dop"), EUR_KG),
]


def _match(text: str) -> Optional[str]:
    """Prima unita' riconosciuta in un singolo testo, None se non ce ne sono."""
    low = text.lower()
    for pattern, unit in _PATTERNS:
        if pattern.search(low):
            return unit
    return None


def resolve_unit(
    product_name: str,
    category_path: Iterable[str],
    product_code: Optional[str] = None,
) -> str:
    """Unita' di misura di un prodotto, o ``UNKNOWN`` se indeterminabile.

    Il nome del prodotto ha la precedenza sui livelli di categoria, che vengono
    poi risaliti dalla foglia verso la radice: vince l'annotazione piu' vicina
    al prodotto.  Gli override sul path intervengono solo se nessun testo nomina
    l'unita'.

    ``product_code`` non e' usato nella risoluzione: resta nella firma perche' i
    chiamanti lo hanno gia' a disposizione e serve a diagnosticare i residui.
    """
    levels = list(category_path)

    unit = _match(product_name)
    if unit:
        return unit

    for level in reversed(levels):
        unit = _match(level)
        if unit:
            return unit

    joined = " > ".join(levels).lower()
    for pattern, override in _PATH_OVERRIDES:
        if pattern.search(joined):
            return override

    return UNKNOWN
