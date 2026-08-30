"""Download XML files from Borsa Merci di Verona."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import requests

BASE_URL = (
    "https://www.portaleprezziverona.it"
    "/camcom-verona/it/borsa-merci/rilevazione/download/xml/{num}"
)

_HEADERS = {
    "User-Agent": "prezzi-agricoli/1.0 (+https://github.com/a1oysio/prezzi-agricoli)",
    "Accept": "application/xml,text/xml,*/*;q=0.8",
}


def fetch_one(
    num: int,
    dest: Path,
    overwrite: bool = False,
    timeout: float = 15.0,
) -> tuple[int, Optional[Path]]:
    """Download a single XML file by its sequential number.

    Returns (http_status, saved_path_or_None).
    - 200 : file saved (or already present when overwrite=False)
    - 404 : not found on remote
    - 0   : network error
    """
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{num}.xml"

    if out.exists() and not overwrite:
        return 200, out

    try:
        resp = requests.get(BASE_URL.format(num=num), headers=_HEADERS, timeout=timeout)
    except requests.RequestException:
        return 0, None

    if resp.status_code == 200:
        out.write_bytes(resp.content)
        return 200, out
    return resp.status_code, None


def parse_target(
    target: Optional[str],
    from_n: Optional[int],
    to_n: Optional[int],
) -> list[int]:
    """Resolve a target string / range arguments to a list of issue numbers.

    Raises ValueError for invalid input.
    """
    if target is not None:
        m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", target)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return list(range(min(a, b), max(a, b) + 1))
        if target.strip().isdigit():
            return [int(target.strip())]
        raise ValueError(f"Target non valido: '{target}'. Usa un numero o un range (es. 1200-1210).")

    if from_n is not None and to_n is not None:
        return list(range(min(from_n, to_n), max(from_n, to_n) + 1))

    raise ValueError("Specifica un numero, un range o usa --next.")


def max_number_in(*dirs: Path) -> Optional[int]:
    """Return the highest integer stem found across the given directories."""
    mx: Optional[int] = None
    for d in dirs:
        if not d.exists():
            continue
        for f in d.glob("*.xml"):
            try:
                n = int(f.stem)
                if mx is None or n > mx:
                    mx = n
            except ValueError:
                pass
    return mx
