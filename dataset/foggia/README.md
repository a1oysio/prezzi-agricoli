# Borsa Merci di Foggia — dataset

Prezzi settimanali all'ingrosso rilevati il mercoledì dalla Borsa Merci di
Foggia, letti dai listini PDF pubblicati dalla
[Camera di Commercio di Foggia](https://www.fg.camcom.gov.it/servizi/storico-dei-listini-settimanali).
Dal 23 giugno 2021.

**Condizioni d'uso.** I listini sono pubblici; questa cartella li riporta in CSV.
Chiunque può usare questi dati citando come fonte la Borsa Merci di Foggia
(Camera di Commercio di Foggia). Il riferimento ufficiale resta il listino
pubblicato dalla Camera. Leggi anche il [DISCLAIMER](../../DISCLAIMER.md).

## File

Lo schema è quello di [Bologna](../bologna/README.md): stesse colonne, stesso
significato del campo vuoto, codici assegnati dal progetto.

| File | Contenuto |
|------|-----------|
| `products.csv` | Una voce di listino per riga; è anche il registro dei codici |
| `prices/<anno>.csv` | Le quotazioni di quell'anno: `date`, `code`, `low`, `high` |
| `revisions.csv` | Valori che la fonte ha corretto dopo la prima acquisizione (compare alla prima rettifica) |
| `meta.json` | Data di generazione, ultimo listino, conteggi |
| `datapackage.json` | Descrittore Frictionless: file, colonne, tipi |
| `exchange.json` | Scheda della borsa, scritta a mano |

## Che cos'è una voce

Come a Bologna, i listini non hanno codici prodotto: una voce è la coppia
**comparto** (`category_path`, per esempio `GRANO DURO` o `CRUSCAMI DI FRUMENTO >
di GRANO DURO`) e **nome** (`name`), scritti come li scrive il listino. Quando
la borsa cambia una caratteristica tra parentesi, come il peso specifico o le
proteine (succede quasi ogni anno con il nuovo raccolto), nasce una voce nuova
e la vecchia si ferma. Il `code` è un numero progressivo assegnato alla prima
comparsa, stabile fra una ricostruzione e l'altra.

## Cose da sapere

- **Unità.** Tutti i prezzi sono in euro per tonnellata, I.V.A. esclusa.
- **Non quotato.** `NQ`, il trattino e lo `0,00` diventano un campo vuoto. Il
  grano tenero e il granoturco sono quasi sempre non quotati. Una voce elencata
  senza nessuna cella non produce righe.
- **Commissione Unica Nazionale.** In fondo al listino la Camera riporta i
  prezzi della CUN del grano duro (Sud Italia, quattro qualità). Sono un'altra
  fonte, con altre date, e qui non ci sono. Il grano duro convenzionale (fino,
  buono mercantile, mercantile) la borsa di Foggia l'ha quotato fino al 25 marzo
  2026; da allora resta solo il biologico.
- **Prima del 23 giugno 2021.** La pagina della Camera elenca anche i listini
  dal 2018 al 16 giugno 2021. Erano un altro documento: il listino generale
  della Camera, dieci pagine con vini, olio, bestiame e prodotti petroliferi.
  Non sono letti: servirebbe un parser a parte.
- **Prodotti olivicoli.** Dall'ottobre 2024 la Camera pubblica anche un listino
  dei prodotti olivicoli, separato. Non è ancora acquisito.
- **Testo dei PDF.** In alcuni listini del 2021 fra una parola e l'altra c'è un
  carattere invisibile invece dello spazio, e `pdftotext` a volte perde le
  legature ("spezza" per "spezzati"). Il parser lo corregge, così che la stessa
  voce non risulti un'altra.

## Come si controlla la lettura

Ogni listino riporta, accanto ai prezzi della settimana, quelli della riunione
precedente. Confrontandoli con il listino prima si verifica che le colonne siano
lette giuste: su 7.241 confronti c'è una sola differenza (listino del 14
settembre 2022, grano duro biologico), un ritocco della borsa da una settimana
all'altra.
I test in `tests/test_parsers.py` rileggono due listini e controllano che
diano esattamente le righe del dataset.
