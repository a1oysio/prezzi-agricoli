# Prezzi agricoli

[![Aggiorna i dati](https://github.com/a1oysio/prezzi-agricoli/actions/workflows/update-data.yml/badge.svg)](https://github.com/a1oysio/prezzi-agricoli/actions/workflows/update-data.yml)
[![Pubblica il sito](https://github.com/a1oysio/prezzi-agricoli/actions/workflows/pages.yml/badge.svg)](https://github.com/a1oysio/prezzi-agricoli/actions/workflows/pages.yml)
[![Codice: MIT](https://img.shields.io/badge/codice-MIT-blue.svg)](LICENSE)
[![Dati: CC BY 4.0](https://img.shields.io/badge/dati-CC%20BY%204.0-lightgrey.svg)](LICENSE-DATA)

Serie storiche dei prezzi all'ingrosso dei prodotti agricoli rilevati dalle
borse merci italiane, in formato aperto (CSV) e aggiornate automaticamente ogni
giorno.

**[Consulta i grafici](https://a1oysio.github.io/prezzi-agricoli/)** ·
**[Scarica i dati](dataset/)** ·
**[Avvertenze](DISCLAIMER.md)**

## Perché

Le Camere di Commercio pubblicano i listini delle borse merci, ma come bollettini
settimanali separati (XML o PDF) senza uno storico consultabile: per ricostruire
l'andamento di un prezzo su più anni bisogna aprire centinaia di file. Questo
progetto li scarica, li converte in CSV con uno schema stabile e documentato, e
li mantiene aggiornati.

## Copertura

| Borsa | Fonte | Dal | Comparti | Documentazione |
|---|---|---|---|---|
| Borsa Merci di Verona | Camera di Commercio di Verona, bollettini XML | 2016 | cereali, sfarinati, mangimi, semi oleosi, foraggi, vini e uve, ortofrutta, avicunicoli, suini, lattiero-caseari | [`dataset/verona/`](dataset/verona/README.md) |
| Borsa Merci di Bologna | AGER per la Camera di Commercio di Bologna, listini PDF | 2004 | frumenti, granoturco, cereali minori, farine, semi oleosi, risi, foraggi, sementi | [`dataset/bologna/`](dataset/bologna/README.md) |

I conteggi aggiornati (prodotti, rilevazioni, ultimo bollettino) sono in
`dataset/<borsa>/meta.json`, rigenerato a ogni aggiornamento.

## I dati

```
dataset/<borsa>/
├── products.csv        catalogo dei prodotti, con unità di misura e categoria
├── prices/<anno>.csv   quotazioni (minimo e massimo), un file per anno
├── averages/<anno>.csv medie quindicinali della borsa, tenute a parte (solo Verona)
├── revisions.csv       valori corretti dalla fonte dopo la prima pubblicazione
├── meta.json           ultimo bollettino, conteggi, data di generazione
└── exchange.json       scheda della borsa: nome, ente, fonte, avvertenze
```

Prima di usarli:

- **Un campo prezzo vuoto non è uno zero.** Il prodotto non è stato quotato in
  quella rilevazione. La riga è presente comunque: anche l'assenza di
  quotazione è un'informazione.
- **Le unità di misura sono diverse.** A Verona l'unità non è un campo della
  fonte: è ricavata dal testo delle categorie (`CEREALI (prezzo base per
  Tonnellata)`). Oltre metà delle rilevazioni non è in euro/tonnellata: non
  sommare né confrontare prodotti con unità diverse.
- **Le ultime settimane possono cambiare.** Le borse a volte correggono un
  bollettino già pubblicato senza cambiarne il numero. La pipeline ricontrolla
  ogni giorno i bollettini recenti, adotta la versione corretta e registra il
  valore precedente in `revisions.csv`.

I dati non vengono corretti dal progetto: dove la fonte contiene un errore, il
valore resta quello pubblicato e viene segnalato. Dettagli in
[DISCLAIMER.md](DISCLAIMER.md).

### Esempio

```python
import pandas as pd
from pathlib import Path

base = Path("dataset/verona")
prezzi = pd.concat(pd.read_csv(f) for f in sorted((base / "prices").glob("*.csv")))
prodotti = pd.read_csv(base / "products.csv")
df = prezzi.merge(prodotti[["code", "name", "unit"]], on="code")
```

## Architettura

```
exchanges/   scaricamento e lettura delle fonti (XML di Verona, PDF di Bologna)
pipeline/    update, rebuild, validate, publish
dataset/     i CSV: la sorgente di verità
site/        sito statico; site/api/ è generato al deploy e non è versionato
```

Non c'è un database: i CSV sono la sorgente e ogni comando li legge e li
riscrive direttamente. Le scritture sono deterministiche, quindi due esecuzioni
sugli stessi dati producono file identici byte per byte.

Dipendenze minime: `requests` per lo scaricamento e `pdftotext`
(`poppler-utils`) per i listini PDF di Bologna. Parsing, validazione e
pubblicazione usano solo la libreria standard.

## Aggiornamento automatico

Un workflow GitHub Actions gira ogni giorno: cerca i bollettini nuovi, ricontrolla
quelli recenti, valida il dataset e committa solo se qualcosa è cambiato. Se il
controllo di qualità trova un errore non pubblica nulla e apre una issue. Un
secondo workflow rigenera e pubblica il sito su GitHub Pages.

## Uso in locale

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m pipeline.update --dry-run    # mostra cosa arriverebbe di nuovo
python -m pipeline.validate            # controllo di qualità
python -m pipeline.publish             # genera i JSON del sito
cd site && python -m http.server 8000  # sito su http://localhost:8000
```

Il [manuale operativo](MANUAL.md) descrive tutte le operazioni: attivazione su un
fork, ricostruzione dall'archivio, gestione dei guasti, aggiunta di una nuova
borsa.

## Contribuire

Segnalazioni e proposte sono benvenute: vedi [CONTRIBUTING.md](CONTRIBUTING.md).

## Licenze

Codice: [MIT](LICENSE). Dati di Verona: [CC BY 4.0](LICENSE-DATA), fonte Camera di
Commercio di Verona. Per i dati di Bologna le condizioni di riuso della fonte non
sono state verificate: vedi [`dataset/bologna/README.md`](dataset/bologna/README.md).

Questa è una ricostruzione non ufficiale: per usi contrattuali, fiscali o legali
fa fede esclusivamente il listino pubblicato dalla Camera di Commercio.
