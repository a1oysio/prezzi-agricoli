"""Borsa Merci di Foggia: dai listini PDF ai CSV.

Stessa strada di Bologna (vedi ``pipeline/bologna.py``): listini senza codici
prodotto, codici assegnati alla prima comparsa e conservati in
``products.csv``, settimana precedente usata per riempire i buchi.  Cambiano
solo l'elenco da cui si scarica e il modo di leggere il PDF.

    python -m pipeline.update  --exchange foggia
    python -m pipeline.rebuild --exchange foggia      # da data/foggia
"""
from __future__ import annotations

import exchanges.foggia as exchange
from exchanges.foggia import fetcher, parser
from pipeline import bologna

FOGGIA = bologna.Source(exchange, fetcher, parser)


def main_update(args) -> int:
    return bologna.main_update(args, FOGGIA)


def main_rebuild(args) -> int:
    return bologna.main_rebuild(args, FOGGIA)
