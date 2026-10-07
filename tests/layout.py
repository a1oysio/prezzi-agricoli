"""Costruisce testo nel formato di ``pdftotext -layout`` per i test del parser.

I numeri sono allineati a destra su colonne fisse, come nei listini veri; le
celle vuote restano vuote.  Cosi' i test esercitano l'assegnazione per posizione
e non solo l'ordine dei token.
"""
from __future__ import annotations

# Posizione finale (1-based) delle sei colonne: prec. min/max, corr. min/max, diff.
ENDS = [90, 103, 116, 129, 143, 157]
TITLE = "CAMERA DI COMMERCIO DI BOLOGNA - Listino settimanale dei prezzi all'ingrosso n. 38 del 1 ottobre 2026"
DATES = "24 SET 2026".rjust(ENDS[1]) + "1 OTT 2026".rjust(ENDS[3] - ENDS[1])
HEADER = "min".rjust(ENDS[0]) + "max".rjust(13) + "min".rjust(13) + "max".rjust(13)


def row(label: str, vals: list) -> str:
    """Una riga: etichetta a sinistra, sei celle (None = vuota) allineate a destra."""
    line = label
    for end, v in zip(ENDS, vals):
        if v is None:
            continue
        line = line.ljust(end - len(v)) + v
    return line


def page(*lines: str, title: str = TITLE) -> str:
    return "\n".join([title, "", DATES, HEADER, "differenza".rjust(ENDS[5]), *lines]) + "\n"


def bulletin(*pages: str) -> str:
    return "\f".join(pages)
