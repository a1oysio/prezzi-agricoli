# Borsa Merci di Bologna — dataset

Prezzi settimanali all'ingrosso rilevati il giovedì alla Borsa Merci di Bologna,
letti dai listini PDF pubblicati da [AGER](https://www.agerborsamerci.it/listino-borsa/settimanale-ager/),
che gestisce la borsa per conto della Camera di Commercio. Dal gennaio 2004.

**Licenza.** Le condizioni di riuso di questi listini non sono state verificate:
la CC BY 4.0 di [LICENSE-DATA](../../LICENSE-DATA) vale per Verona, non per
questa cartella. Il riferimento ufficiale resta il listino pubblicato dalla
Camera di Commercio di Bologna. Leggi anche il [DISCLAIMER](../../DISCLAIMER.md).

## File

Lo schema è quello di [Verona](../verona/README.md): stesse colonne, stesso
significato del campo vuoto.

| File | Contenuto |
|------|-----------|
| `products.csv` | Una voce di listino per riga; per Bologna è anche il registro dei codici |
| `prices/<anno>.csv` | Le quotazioni di quell'anno: `date`, `code`, `low`, `high` |
| `revisions.csv` | Valori che la fonte ha corretto dopo la prima acquisizione (compare alla prima rettifica) |
| `meta.json` | Data di generazione, ultimo listino, conteggi |
| `exchange.json` | Scheda della borsa, scritta a mano |

Non c'è `averages/`: delle medie mensili che la borsa pubblica non si acquisisce nulla.

## Che cos'è una voce

I listini di Bologna non hanno codici prodotto. Una voce è identificata da
**dove sta** (`category_path`) e da **come è scritta** (`name`), alla lettera:

```
FRANCO PARTENZA > FRUMENTO TENERO di produzione nazionale 2026
n° 1 - speciali di forza - prot. 13,5% min, p.s. 80 kg/hl min, c.e. 1%
```

Quando la borsa cambia l'annata nel titolo o una caratteristica nel nome, quella
è **un'altra voce**, con un altro codice. Non c'è nessun raggruppamento: dire che
due diciture sono "lo stesso prodotto" sarebbe un giudizio di chi compila il
dataset, non un dato della fonte. La conseguenza è che molte serie durano un
anno; `first_date` e `last_date` in `products.csv` dicono quale.

Il `code` è un numero progressivo assegnato alla prima comparsa della voce. Non
viene dalla fonte e non ha significato, ma è stabile: `pipeline.rebuild` rilegge
`products.csv` e riusa i codici già assegnati.

Dal testo vengono tolti solo i richiami di nota — `(1)`, `(*)` — e i due punti
finali. Nei listini fino al 2016 alcuni nomi sono troncati dal bordo della
colonna (`… c.e.1% max; p`): restano troncati, com'erano stampati.

## Cose da sapere

- **Unità.** Tutti i prezzi sono in euro per tonnellata, come dichiara la riga
  "Prezzi in €/t" di ogni tabella.
- **Resa.** Dal 9 giugno 2016 il primo livello di `category_path` è `FRANCO
  PARTENZA` o `FRANCO ARRIVO`. Prima il listino dichiarava "resa franco arrivo o
  partenza" per tutto il foglio e la distinzione stava nelle note: il percorso
  comincia direttamente dal titolo.
- **Minimo maggiore del massimo.** Per alcune voci le due colonne sono due
  qualità o due provenienze (lo dicono le note del listino), non una forbice.
- **Non quotato.** `n.q.`, il trattino e lo `0,00` con cui il listino riempie le
  celle vuote diventano un campo vuoto. Una voce elencata senza nessuna cella
  non produce righe.
- **Settimane recuperate.** Dei listini del 22 gennaio 2004, 28 maggio 2009, 18
  dicembre 2014 e 22 ottobre 2015 il PDF non è più scaricabile: i loro prezzi
  vengono dalle colonne "settimana precedente" del listino successivo.
- **Cosa manca.** Il 2003 e le settimane fra il 27 novembre e l'11 dicembre 2014.

## Come si controlla la lettura

Ogni listino riporta, accanto ai prezzi della settimana, quelli della precedente.
Confrontando ogni listino con quello prima si verifica che le colonne siano state
lette giuste: su circa 166 mila confronti le differenze sono qualche decina, e
sono correzioni che la borsa ha fatto da una settimana all'altra.
