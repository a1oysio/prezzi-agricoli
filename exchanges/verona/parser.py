"""Parse Verona XML price-list files into standardized PriceRecord objects."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Optional

from exchanges import FileMetadata, PriceRecord
from exchanges.verona.units import resolve_unit
from exchanges.verona.processors import (
    classify_file_type,
    guess_file_number_from_name,
    iter_products_rows,
    parse_commission_date,
    parse_title_date,
)


def parse_xml_file(path: Path) -> tuple[FileMetadata, list[PriceRecord]]:
    """Parse one Verona XML file.

    Returns (FileMetadata, records).  Records is empty for MONTHLY files.
    Raises ValueError if the file cannot be parsed or the date is missing.
    """
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"XML non valido '{path.name}': {exc}") from exc

    file_type, _ = classify_file_type(root)
    issue_number = guess_file_number_from_name(path)

    if file_type in ("MONTHLY", "CLOSED"):
        return (
            FileMetadata(
                filename=path.name,
                file_type=f"XML_{file_type}",
                issue_number=issue_number,
            ),
            [],
        )

    date_str: Optional[str] = parse_commission_date(root) or parse_title_date(root)
    if date_str is None:
        raise ValueError(f"Impossibile determinare la data per '{path.name}'.")

    issue_date: date = date.fromisoformat(date_str)

    records: list[PriceRecord] = [
        PriceRecord(
            date=issue_date,
            product_code=pid,
            product_name=pname,
            low=lo,
            high=hi,
            category=cat_path[-1] if cat_path else None,
            category_path=cat_path,
            units=resolve_unit(pname, cat_path, pid),
        )
        for pid, pname, cat_path, lo, hi in iter_products_rows(root)
    ]

    return (
        FileMetadata(
            filename=path.name,
            file_type="XML",
            issue_number=issue_number,
            issue_date=issue_date,
        ),
        records,
    )
