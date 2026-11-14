# Contribuire

## Segnalare un problema nei dati

Apri una issue indicando borsa, codice prodotto, data e, se possibile, il link
al bollettino originale. Prima di farlo verifica due cose:

- il valore compare in `dataset/<borsa>/revisions.csv`? Allora è una correzione
  pubblicata dalla fonte, e il valore attuale è quello valido;
- il caso è già elencato in [DISCLAIMER.md](DISCLAIMER.md) fra gli errori della
  fonte lasciati com'è?

Il progetto non corregge a mano i valori pubblicati dalle borse: un errore della
fonte viene documentato, non modificato.

## Modificare il codice

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Ogni modifica a parser, unità di misura o pipeline va verificata ricostruendo il
dataset e controllando che cambi solo ciò che ci si aspetta:

```bash
python -m pipeline.rebuild            # richiede l'archivio locale, vedi MANUAL.md
python -m pipeline.validate
git diff --stat dataset/
```

Non committare a mano dentro `dataset/` se non per una ricostruzione motivata:
gli aggiornamenti ordinari li fa il workflow giornaliero.

## Aggiungere una borsa

La procedura è descritta in [MANUAL.md](MANUAL.md#7-aggiungere-unaltra-borsa).
