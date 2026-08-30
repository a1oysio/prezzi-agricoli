"""Tipi condivisi dai parser delle borse merci.

Versione ridotta: qui non c'e' l'applicazione Flask, quindi non servono la
classe base ``ExchangeAdapter`` ne' il registro degli adapter.  Restano i due
dataclass che i parser producono.

I file ``exchanges/verona/{fetcher,parser,processors,units}.py`` sono copie
identiche di quelli di agx-scraper: un ``diff`` basta a vedere se hanno preso
strade diverse.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class PriceRecord:
    """Una rilevazione di prezzo, normalizzata."""
    date: date
    product_code: str        # chiave stabile, ambito alla borsa
    product_name: str
    low: Optional[float]     # None = non quotato in quella rilevazione
    high: Optional[float]
    category: Optional[str] = None
    category_path: tuple[str, ...] = ()   # gerarchia completa, radice per prima
    units: str = "unknown"


@dataclass
class FileMetadata:
    """Dati del bollettino da cui provengono le rilevazioni."""
    filename: str
    file_type: str                  # 'XML', 'XML_MONTHLY', …
    issue_number: Optional[int] = None
    issue_date: Optional[date] = None
