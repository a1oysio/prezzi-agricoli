"""Identita' dei prodotti di Bologna: il codice e la serie.

Il listino non ha codici prodotto e **cambia le specifiche ogni anno**: il
frumento tenero "n. 1 - speciali di forza" e' pubblicato con "p.s. 78/79" in un
anno, "p.s. 79/80" nel successivo e "prot. 13,5%, p.s. 80" dopo ancora.  Per un
agronomo e' sempre la stessa serie; per un programma sono tre etichette.

Due livelli, entrambi deterministici:

``code``
    Un intero per ogni (percorso, etichetta) *esatti* come pubblicati, a meno
    delle spaziature.  Fedele alla fonte: se la specifica cambia, il codice
    cambia.  Non si fonde mai nulla per errore.

``series``
    Una chiave di serie, assegnata solo dove e' sicuro che cambino i soli
    parametri numerici: i **gradi commerciali del frumento** (n. 1-5, fino,
    buono mercantile, mercantile, sotto mercantile).  Per tutto il resto la
    serie e' il codice stesso.

    Non si e' voluto estendere la fusione automatica all'orzo, al mais e agli
    altri: li' le classi spostano i confini ("p.s. 58/60" diventa "62/64"), e
    decidere se la classe di ieri e' quella di oggi e' un giudizio agronomico,
    non un'espressione regolare.  Per correggere a mano esiste
    ``dataset/bologna/series_overrides.csv`` (codice -> serie).
"""
from __future__ import annotations

import re
from typing import Optional, Sequence

_WHEAT_SECTION = re.compile(r"^frumento\s+(?:tenero|duro)\b", re.IGNORECASE)

# Il grado commerciale e' la prima parte dell'etichetta, prima delle specifiche:
#   "n. 1 - speciali di forza - prot. 14%, p.s. 79/80 kg/hl, c.e. 1%"
#   "fino - prot. 13% min, p.s. 81 kg/hl min, c.e. 2+2%, ..."
_GRADE = re.compile(
    r"^(?P<grade>n°\s*\d+\s*-\s*[^-,;(]+?|fino|buono\s+mercantile"
    r"|sotto\s+mercantile|mercantile)\s*(?:-|,|;|\(|$)",
    re.IGNORECASE)


def canon(text: str) -> str:
    """Forma di confronto: minuscola e senza spazi.

    I listini scrivono lo stesso testo con spaziature diverse da un anno
    all'altro ("-escl. nazionale -ad uso" / "- escl. nazionale - ad uso").
    """
    return re.sub(r"\s+", "", text.lower())


def product_key(path: Sequence[str], label: str) -> str:
    return "|".join(canon(h) for h in path) + "||" + canon(label)


def _section_stem(heading: str) -> str:
    """Il titolo senza la condizione di resa ("... - merce posta su veicolo ...")."""
    return re.sub(r"\s+", " ", heading.split(" - ")[0]).strip()


def series_key(path: Sequence[str], label: str) -> Optional[str]:
    """Chiave di serie per i gradi del frumento, None per tutto il resto."""
    if not path or not _WHEAT_SECTION.match(path[0]):
        return None
    m = _GRADE.match(label.strip())
    if not m:
        return None
    grade = re.sub(r"\s+", " ", m.group("grade")).strip().lower()
    grade = re.sub(r"^n\u00b0\s*(\d+)\s*-\s*", r"n. \1 - ", grade)
    ordinal = next((h for h in path if h.startswith("#")), "")
    return f"{_section_stem(path[0])} > {grade}{(' ' + ordinal) if ordinal else ''}"
