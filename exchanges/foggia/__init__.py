"""Borsa Merci di Foggia (Camera di Commercio di Foggia) — listini PDF.

    from exchanges.foggia import fetcher, parser
    meta, entries = parser.parse_file(path)
"""

CODE = "FG"
NAME = "Borsa Merci di Foggia"
SLUG = "foggia"
SOURCE_URL = "https://www.fg.camcom.gov.it/servizi/storico-dei-listini-settimanali"
LICENSE = "Listini pubblici della Camera di Commercio di Foggia, riutilizzabili citando la fonte"
