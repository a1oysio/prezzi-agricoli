# Borsa Merci di Verona — dataset

Prezzi settimanali dei prodotti agricoli rilevati dalla Camera di Commercio di
Verona. Licenza [CC BY 4.0](../../LICENSE-DATA). Leggi anche il
[DISCLAIMER](../../DISCLAIMER.md).

## File

| File | Contenuto |
|------|-----------|
| `products.csv` | Un prodotto per riga, con unità di misura e gerarchia di categoria |
| `prices/<anno>.csv` | Le quotazioni di quell'anno |
| `meta.json` | Data di generazione, ultimo bollettino, conteggi |

I prezzi sono partizionati per anno perché l'aggiornamento tocchi un solo file:
il diff settimanale in git resta di poche righe invece di riscrivere tutto.

## `prices/<anno>.csv`

| Colonna | Tipo | Note |
|---------|------|------|
| `date` | `YYYY-MM-DD` | Data della rilevazione |
| `code` | intero come stringa | Chiave del prodotto, stabile nel tempo |
| `low` | decimale o vuoto | Prezzo minimo |
| `high` | decimale o vuoto | Prezzo massimo |

**Un campo vuoto non è uno zero.** Significa che il prodotto non è stato quotato
in quella rilevazione. La riga esiste comunque, perché l'assenza di quotazione è
essa stessa un'informazione: distingue "questa settimana nessuno ha scambiato"
da "questo prodotto non esiste più".

L'ordinamento è per data e poi per codice numerico, sempre lo stesso: due
esecuzioni sugli stessi dati producono file identici byte per byte.

## `products.csv`

| Colonna | Note |
|---------|------|
| `code` | Chiave, corrisponde a `code` nei file dei prezzi |
| `name` | Descrizione della borsa, comprese le specifiche tecniche |
| `category_path` | Gerarchia completa, livelli separati da ` > ` |
| `unit` | Vedi sotto |
| `first_date`, `last_date` | Estremi delle rilevazioni |
| `n_observations` | Righe totali, quotazioni vuote comprese |
| `n_quoted` | Righe con almeno un prezzo |

`category_path` è la gerarchia **intera**, non la sola foglia, perché il nome
finale da solo non identifica nulla: `a busto` compare sotto POLLI, ANITRE,
TACCHINI e FARAONE.

## Unità di misura

| Valore | Significato |
|--------|-------------|
| `EUR/t` | Euro per tonnellata |
| `EUR/kg` | Euro per chilogrammo |
| `EUR/L` | Euro per litro |
| `EUR/1000L` | Euro per 1000 litri (latte alla stalla) |
| `EUR/grado-hL` | Euro per grado alcolico su 100 litri |
| `EUR/grado-100kg` | Euro per grado alcolico su 100 kg (mosti concentrati) |
| `EUR/100pz` | Euro per 100 pezzi (uova) |

**L'unità non è nella fonte.** Gli XML della borsa non hanno un campo per la
misura: è scritta in italiano dentro il nome della categoria o del prodotto. Il
progetto la ricava da lì (`exchanges/verona/units.py`). Non sommare né
confrontare prodotti con unità diverse.

## Esempio

```python
import pandas as pd

prezzi = pd.concat(pd.read_csv(f) for f in sorted(Path("prices").glob("*.csv")))
prodotti = pd.read_csv("products.csv")

df = prezzi.merge(prodotti[["code", "name", "unit"]], on="code")
grano = df[df.name.str.contains("Grano Fino")].dropna(subset=["low"])
grano.set_index("date")[["low", "high"]].plot()
```
