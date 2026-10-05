# Borsa Merci di Bologna — dataset

Prezzi settimanali all'ingrosso rilevati dalla Camera di Commercio di Bologna
(cereali, farine, mangimi, semi oleosi, riso, foraggi, sementi, ortofrutta, vini
e mosti, uve). Licenza [CC BY 4.0](../../LICENSE-DATA). Leggi anche il
[DISCLAIMER](../../DISCLAIMER.md).

La fonte sono i **listini PDF** pubblicati sul sito della Camera, non un XML come
a Verona. Il testo dei PDF si estrae con `pdftotext -layout` (pacchetto
`poppler-utils`), poi un parser lo trasforma negli stessi CSV di Verona.

**Copertura:** 651 listini dal 3 gennaio 2013 all'1 ottobre 2026, più le
settimane recuperate dalle colonne "precedente" (dal 27 dicembre 2012).
3.352 prodotti, 240.178 rilevazioni.

## File

| File | Contenuto |
|------|-----------|
| `products.csv` | Un prodotto per riga, con unità di misura e percorso di sezione |
| `prices/<anno>.csv` | Le quotazioni di quell'anno |
| `revisions.csv` | I valori che la fonte ha corretto dopo la prima pubblicazione |
| `series.csv` | Quali codici sono la stessa serie nel tempo (vedi sotto) |
| `series_overrides.csv` | Correzioni a mano a `series.csv` (opzionale, versionato) |
| `issues.csv` | Un listino per riga: data, numero, file di provenienza |
| `skipped.csv` | I listini che non si sono potuti leggere, e perché |
| `meta.json` | Data di generazione, ultimo listino, conteggi |

`prices/<anno>.csv`, `products.csv` e `revisions.csv` hanno lo stesso schema di
[Verona](../verona/README.md#pricesannocsv): leggi quelle note per il
significato di `low`, `high` e del campo vuoto (**vuoto non è zero**: il
prodotto non era quotato).

## Codice e serie: la differenza più importante rispetto a Verona

La fonte **non ha codici prodotto** e la Camera **cambia le specifiche ogni
anno**. Il frumento tenero n. 1 è pubblicato come
`n° 1 - speciali di forza - p.s. 78/79 kg/hl, c.e. 1%, prot. 13%` in un anno,
`... p.s. 79/80 ... prot. 14%` nell'altro, `... prot. 13,5%, p.s. 80 kg/hl min.`
dopo ancora. Per un agronomo è la stessa serie; per un programma sono tre
etichette. Per questo ci sono due livelli:

**`code`** (in `products.csv` e `prices/`) identifica l'etichetta **esatta**,
a meno delle spaziature. Se la specifica cambia, il codice cambia. È fedele alla
fonte: non fonde mai due cose per errore.

**`series`** (in `series.csv`) dice quali codici sono la stessa serie nel tempo.
È assegnata **solo per i gradi commerciali del frumento** (tenero n. 1–5; duro
fino, buono mercantile, mercantile, sotto mercantile, separati per area nord e
centro), dove cambiano soltanto i parametri numerici: 154 codici in 16 serie.

Per tutto il resto la serie è il codice stesso. Non si fondono automaticamente
orzo, mais, soia, semola, farine, foraggi e gli altri: lì le classi spostano i
confini (`p.s. 58/60` diventa `62/64`), e decidere se la classe di ieri è quella
di oggi è un giudizio agronomico. Per deciderlo a mano si aggiunge una riga a
`series_overrides.csv` (`code,series`) e si rigenera con `pipeline.bologna
rebuild`.

`pipeline.validate` controlla che due codici della stessa serie non abbiano mai
prezzi *diversi* nella stessa settimana: se succede, la fusione è sbagliata.

```python
import pandas as pd

prodotti = pd.read_csv("products.csv", dtype={"code": str})
serie = pd.read_csv("series.csv", dtype={"code": str})
prezzi = pd.concat(pd.read_csv(f, dtype={"code": str}) for f in sorted(Path("prices").glob("*.csv")))

df = prezzi.merge(serie, on="code")
tenero1 = df[df.series.str.endswith("n. 1 - speciali di forza")].dropna(subset=["low"])
tenero1.groupby("date")[["low", "high"]].first().plot()
```

## Cosa si toglie dalle etichette

Il testo dei prodotti è quello del listino, con queste sole pulizie, che servono
perché una stessa voce non diventi un prodotto nuovo a ogni settimana:

* i richiami di nota (`(1)`, `(*)`) e l'asterisco dei prezzi provvisori (`157,00*`);
* l'anno di raccolto nei titoli di sezione (`produzione nazionale 2026`): la
  data della quotazione dice già l'annata;
* il marcatore `(1ª quotazione)` della prima settimana stagionale di un prodotto;
* il periodo nell'etichetta degli asparagi (`- dal 2 all'8 maggio`).

## Unità di misura

La fonte dichiara nel testo che i prezzi sono in **EUR/t, salvo diversa
indicazione**. Le sezioni che escono dal default lo dicono nel proprio titolo.

| Valore | Significato | Prodotti |
|--------|-------------|---------:|
| `EUR/t` | Euro per tonnellata | 1.119 |
| `EUR/kg` | Euro per chilogrammo (ortofrutta, formaggi) | 1.874 |
| `EUR/q` | Euro per quintale (uve da vino) | 140 |
| `EUR/grado-hL` | Euro per grado alcolico su 100 litri (vini sfusi) | 75 |
| `EUR/L` | Euro per litro (vini in contenitori) | 51 |
| `unknown` | La fonte non lo dichiara, o ne dà due ("€ al kg/litro") | 93 |

`unknown` sono i mosti e i vini sfusi "pronti per il consumo": preferiamo un
buco dichiarato a un'unità indovinata. **Non sommare né confrontare prodotti con
unità diverse.**

## Come sono ricavate le rilevazioni

Ogni listino riporta **due settimane**: quella corrente e la precedente, con la
differenza stampata. Ne discende quanto segue.

* **Settimane senza listino.** Se il PDF di una settimana manca o è illeggibile,
  i prezzi si recuperano dalla colonna "precedente" del listino dopo. Sono 8.060
  rilevazioni.
* **Rettifiche.** Se la colonna "precedente" di un listino e il listino della
  settimana prima non concordano, la fonte si è corretta: vince il valore più
  recente e il vecchio finisce in `revisions.csv` (263 casi). Non sono errori
  del parser: sono prezzi pubblicati due volte con valori diversi.
* **Una colonna "precedente" vuota non cancella nulla.** A volte la Camera
  svuota quella colonna senza aver ritirato niente (il n. 36 del 2019 la mostra a
  trattini per tutti i vini che il n. 35 aveva quotato). Un valore preso dalla
  colonna "precedente" può riempire un buco o cambiarne un altro, mai
  sostituire un prezzo con un vuoto. Sono 161 casi, ignorati.
* **Controllo aritmetico.** `corrente − precedente` deve coincidere con la
  differenza stampata. Su 132.694 righe complete non torna in 17: sono
  incoerenze della fonte (es. `93/125` che la differenza dà `0/5`), lasciate
  così come sono.

## Limiti noti

* **Il 2012 non c'è** (50 listini) e **10 listini successivi non sono leggibili**:
  i loro PDF hanno i caratteri codificati male e non contengono testo
  recuperabile senza OCR. Sono elencati in `skipped.csv`. Quasi tutte le loro
  settimane si recuperano dal listino seguente; **settembre 2014 no**, perché
  cinque listini consecutivi (n. 34–38) sono illeggibili e il buco resta (35
  giorni).
* **Il grano duro finisce il 26 marzo 2026.** Da allora il listino di Bologna
  scrive che le quotazioni del frumento duro sono "sospese a seguito
  dell'insediamento della Commissione Unica Nazionale Grano duro" (CUN); i
  prezzi si pubblicano a parte e non sono in questo dataset. Le serie del duro
  hanno quindi un'ultima data, non un buco.
* **Sezioni escluse** perché hanno una struttura diversa: suini e carni
  (un solo prezzo con tre decimali, rilevati dalla Borsa di Modena), carcasse
  bovine, prodotti petroliferi.
* **95 righe non collocate** su 240.178 (tabelle dall'impaginazione irregolare);
  il parser le segnala e le salta, non le indovina. Una riga con celle vuote che
  non può essere collocata con certezza sulla sua colonna è sempre scartata.
* **Le etichette portano il rumore del PDF** (note a pie di tabella, "max" a capo,
  qualche titolo che cambia da un anno all'altro): se una serie si interrompe
  senza motivo, cerca lo stesso prodotto con un'etichetta leggermente diversa.

## Aggiornare e ricostruire

```bash
python -m pipeline.bologna update      # listini nuovi, ricontrolla l'ultimo
python -m pipeline.bologna download    # scarica l'archivio in data/bologna (non versionato)
python -m pipeline.bologna rebuild     # ricostruisce tutto dai PDF scaricati
python -m pipeline.validate --exchange bologna
```

`update` è fatto per **fermarsi**: se un listino nuovo ha testo regolare ma non
si riconosce (impaginazione cambiata), non pubblica niente e fa fallire il
workflow. Un listino con i caratteri corrotti, invece, si registra in
`skipped.csv` e si va avanti.
