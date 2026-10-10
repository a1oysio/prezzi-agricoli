"""Borsa Merci di Bologna (AGER) — scaricamento e parsing dei listini PDF.

    from exchanges.bologna import fetcher, parser
    meta, entries = parser.parse_file(path)
"""

CODE = "BO"
NAME = "Borsa Merci di Bologna"
SLUG = "bologna"
SOURCE_URL = "https://www.agerborsamerci.it/listino-borsa/settimanale-ager/"
# Condizioni di riuso dei listini non verificate: in meta.json resta vuota.
LICENSE = None
