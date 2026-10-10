"""Da un listino PDF di Bologna alle sue righe di prezzo.

I listini di Bologna non hanno codici prodotto: una voce e' identificata da dove
sta nel listino e da come e' scritta.  Qui si restituiscono quindi le righe cosi'
come sono, con percorso e nome; il codice glielo assegna chi tiene l'anagrafica
(``pipeline.bologna``).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from exchanges import FileMetadata
from exchanges.bologna import layouts
from exchanges.bologna.layouts import Entry
from exchanges.bologna.pdfwords import read_pages

# Il nome che il fetcher da' ai file: "2026-10-08_n39.pdf".
_FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})_n(\d+)\.pdf$")


def parse_file(path: Path) -> tuple[FileMetadata, list[Entry]]:
    """Legge un listino.

    Data e numero vengono dal nome del file, cioe' dall'elenco del sito; la data
    scritta sopra le colonne dei prezzi deve confermarla.  Solleva ValueError se
    il file non si lascia leggere, se non contiene prezzi o se le date non
    tornano: meglio un listino saltato che uno finito sotto la data sbagliata.
    """
    m = _FILENAME.match(path.name)
    if not m:
        raise ValueError(f"nome non riconosciuto '{path.name}': atteso AAAA-MM-GG_nNN.pdf")
    issue, number = date.fromisoformat(m[1]), int(m[2])

    entries = layouts.for_date(issue).entries(read_pages(path), issue)
    if not entries:
        raise ValueError(f"nessun prezzo trovato in '{path.name}'")
    wrong = sorted({str(e.date) for e in entries if e.date != issue})
    if wrong:
        raise ValueError(f"'{path.name}' e' del {issue} ma le colonne dicono {', '.join(wrong)}")

    return FileMetadata(path.name, "PDF", number, issue), entries
