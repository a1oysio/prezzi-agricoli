"""Le parole di un PDF con la loro posizione sulla pagina.

I listini sono tabelle: a dire in che colonna sta un numero non e' il testo ma
la sua ascissa.  ``pdftotext -layout`` le ricostruisce con gli spazi e quando
due tabelle stanno affiancate le impasta; ``pdftotext -tsv`` restituisce invece
ogni parola col suo rettangolo, e le colonne si ritrovano per coordinate.

Serve ``pdftotext`` (pacchetto poppler-utils).
"""
from __future__ import annotations

import csv
import io
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Word:
    x0: float       # bordo sinistro
    x1: float       # bordo destro: i numeri sono allineati a destra
    y: float        # bordo superiore
    h: float
    text: str

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Page:
    number: int             # da 1
    width: float
    height: float
    words: list[Word]

    def rows(self, tol: float = 3.0) -> list[list[Word]]:
        """Le parole raggruppate in righe, dall'alto, ognuna da sinistra.

        Due parole stanno sulla stessa riga se i loro bordi superiori distano
        meno di ``tol`` punti: nelle tabelle il nome e i suoi prezzi non sono
        mai allineati al decimo di punto.
        """
        out: list[list[Word]] = []
        for w in sorted(self.words, key=lambda w: (w.y, w.x0)):
            if out and abs(w.y - out[-1][0].y) <= tol:
                out[-1].append(w)
            else:
                out.append([w])
        return [sorted(r, key=lambda w: w.x0) for r in out]


def read_pages(path: Path) -> list[Page]:
    """Tutte le pagine di un PDF.  Solleva ValueError se non si lascia leggere."""
    try:
        proc = subprocess.run(["pdftotext", "-tsv", str(path), "-"],
                              capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("pdftotext non trovato: installa poppler-utils") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"PDF illeggibile '{path.name}': "
                         f"{exc.stderr.decode(errors='replace').strip()}") from exc

    pages: list[Page] = []
    reader = csv.DictReader(io.StringIO(proc.stdout.decode("utf-8", errors="replace")),
                            delimiter="\t", quoting=csv.QUOTE_NONE)
    for r in reader:
        level = r["level"]
        if level == "1":
            pages.append(Page(int(r["page_num"]), float(r["width"]), float(r["height"]), []))
        elif level == "5" and pages and r["text"].strip():
            x0, y, w, h = (float(r[k]) for k in ("left", "top", "width", "height"))
            pages[-1].words.append(Word(x0, x0 + w, y, h, r["text"]))
    return pages
