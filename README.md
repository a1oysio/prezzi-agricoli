# prezzi-agricoli

Serie storiche dei prezzi dei prodotti agricoli delle borse merci italiane, in
formato aperto e aggiornate da sole.

**[→ Consulta i grafici](https://a1oysio.github.io/prezzi-agricoli/)** ·
**[→ Scarica i CSV](dataset/verona/)**

I listini delle camere di commercio sono pubblici, ma vivono dentro XML
settimanali senza uno storico consultabile: per sapere quanto costava il mais
tre anni fa bisogna aprire centocinquanta file. Questo repository li scarica, li
converte in CSV con uno schema stabile e li tiene aggiornati.

Copre la **Borsa Merci di Verona**: 842 prodotti, 197.745 rilevazioni dal
gennaio 2016.

## I dati

```
dataset/verona/
├── products.csv        catalogo dei prodotti, con unità di misura
├── prices/2016.csv …   quotazioni, un file per anno
└── meta.json           ultimo bollettino, conteggi, data di generazione
```

Documentazione dei campi: [`dataset/verona/README.md`](dataset/verona/README.md).

Due cose da sapere prima di usarli:

- **Un campo prezzo vuoto non è uno zero.** Vuol dire che il prodotto non è stato
  quotato quella settimana. La riga esiste comunque, perché anche l'assenza di
  quotazione è un'informazione.
- **L'unità di misura non esiste nella fonte.** Gli XML della borsa non hanno un
  campo per la misura: è scritta in italiano dentro il nome delle categorie
  (`CEREALI (prezzo base per Tonnellata)`), e viene ricavata da lì. Il 58% delle
  rilevazioni **non** è in euro/tonnellata: non sommare prodotti con unità
  diverse.

Nessun dato viene corretto. Dove la fonte sbaglia, il valore resta com'è e viene
segnalato — vedi [DISCLAIMER.md](DISCLAIMER.md).

## Com'è fatto

```
exchanges/verona/   scaricamento e parsing dei bollettini XML
pipeline/           update, rebuild, validate, publish
dataset/            ← la sorgente di verità
site/               il sito statico; site/api/ è generato, non versionato
```

Non c'è un database. I CSV sono la sorgente: gli XML grezzi pesano una
cinquantina di MB e non sono versionati, quindi la CI non potrebbe ricostruire da
quelli. Ogni comando legge e riscrive direttamente i CSV.

L'unica dipendenza è `requests`, e serve solo a scaricare. Parsing, validazione e
pubblicazione usano la libreria standard.

## Aggiornamento automatico

Un workflow GitHub Actions gira ogni giorno, cerca i bollettini nuovi, li unisce
ai CSV e committa **solo se qualcosa è cambiato**. Se il controllo di qualità
trova un errore, non pubblica nulla e apre una issue.

Per attivarlo su un fork servono quattro passaggi: [`MANUAL.md`](MANUAL.md).

## Uso locale

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m pipeline.update --dry-run    # cosa arriverebbe di nuovo
python -m pipeline.validate            # controllo di qualità
python -m pipeline.publish             # genera i JSON del sito
```

Per lavorare sui CSV non serve installare niente: sono file di testo.

```python
import pandas as pd
from pathlib import Path

prezzi = pd.concat(pd.read_csv(f) for f in sorted(Path("dataset/verona/prices").glob("*.csv")))
prodotti = pd.read_csv("dataset/verona/products.csv")
df = prezzi.merge(prodotti[["code", "name", "unit"]], on="code")
```

## Licenze

Codice [MIT](LICENSE). Dati [CC BY 4.0](LICENSE-DATA), fonte Camera di Commercio
di Verona. Ricostruzione non ufficiale: leggi il [DISCLAIMER](DISCLAIMER.md).
