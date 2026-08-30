"""Pipeline dei dati: scaricamento, validazione, pubblicazione.

I CSV in ``dataset/`` sono la sorgente di verita'.  Non c'e' un database: i file
XML grezzi non sono versionati, quindi la CI non potrebbe ricostruire da quelli
e ogni comando legge e riscrive direttamente i CSV.
"""
