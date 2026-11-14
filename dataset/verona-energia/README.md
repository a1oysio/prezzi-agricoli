# Prodotti petroliferi di Verona — dataset

Prezzi dei prodotti petroliferi rilevati ogni quindici giorni (il 15 e a fine
mese) dalla Camera di Commercio di Verona, letti dagli XML del
[portale prezzi](https://www.portaleprezziverona.it/camcom-verona/it/prodotti-petroliferi).
Dal gennaio 2016.

Licenza [CC BY 4.0](../../LICENSE-DATA), fonte Camera di Commercio di Verona.
Ricostruzione non ufficiale: leggi il [DISCLAIMER](../../DISCLAIMER.md).

## File

| File | Contenuto |
|------|-----------|
| `products.csv` | Un prodotto per riga: categoria, fascia di consegna, unità. Stesse colonne di [Verona](../verona/README.md) |
| `prices/<anno>.csv` | Le rilevazioni di quell'anno (schema sotto) |
| `revisions.csv` | Valori che la fonte ha corretto dopo la prima acquisizione (compare alla prima rettifica) |
| `meta.json` | Data di generazione, ultima rilevazione, conteggi |
| `exchange.json` | Scheda della fonte, scritta a mano |

## `prices/<anno>.csv`

Lo schema **non** è quello delle borse merci: non c'è un minimo e un massimo, ma
i quattro valori che la fonte pubblica per ogni prodotto.

| Colonna | Significato |
|---|---|
| `date` | Data della rilevazione (15 o fine mese) |
| `code` | Codice del prodotto della fonte, stabile dal 2016 (583–614) |
| `price` | Prezzo netto, senza accisa né IVA |
| `price_with_excise` | Prezzo con accisa, senza IVA |
| `vat_rate` | Aliquota IVA in percentuale (10 o 22) |
| `consumer_price` | Prezzo al consumo, accisa e IVA incluse |

## Cose da sapere

- **Accisa.** Cambia per decreto: un salto in `price_with_excise` che non c'è in
  `price` è fiscale, non di mercato.
- **Fasce.** Il `name` di gasolio e olio combustibile è la fascia di consegna
  (`fino a 2.000`, `oltre 20.000`…), in litri o chili per consegna.
- **Unità.** `EUR/L` per gasolio e GPL sfuso, `EUR/kg` per l'olio combustibile,
  `EUR/m3` per il GPL a contatore. Il GPL in bombole è `EUR/bombola`: la fonte
  scrive "kg", ma il valore è il prezzo della bombola da 10 o 15 kg.
- **Prodotti scomparsi.** Una categoria senza prodotti non produce righe: l'olio
  combustibile BTZ 0,3% ha una sola rilevazione (15 gennaio 2016), il BTZ 1%
  nove, l'ultima del 30 maggio 2023.
- **Una data ricostruita.** La rilevazione n. 849 ha il titolo "DEL 15 SETTEMBRE"
  senza anno: è il 15 settembre 2021, fra le rilevazioni del 30 agosto e del 30
  settembre 2021.

```python
import pandas as pd
from pathlib import Path

prezzi = pd.concat(pd.read_csv(f) for f in sorted(Path("prices").glob("*.csv")))
prodotti = pd.read_csv("products.csv")
agricolo = prezzi.merge(prodotti, on="code").query("category_path.str.startswith('c)')")
```
