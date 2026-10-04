# Avvertenze

## Non è una fonte ufficiale

I CSV di questo repository sono una **ricostruzione automatica** dei listini
delle Borse Merci di Verona e di Bologna. Per qualsiasi uso contrattuale,
fiscale o legale fa fede esclusivamente il listino pubblicato dalla Camera di
Commercio competente.

## Cosa il progetto modifica rispetto alla fonte

I file XML della borsa non contengono un campo per l'unità di misura: è scritta
in italiano nel testo delle categorie (`CEREALI (prezzo base per Tonnellata)`).
Il progetto la ricava da lì. Nei pochi casi in cui non compare da nessuna parte
si usa un elenco di corrispondenze basato sulle categorie sorelle, verificato
sugli ordini di grandezza dei prezzi: vedi `exchanges/verona/units.py`.

Zeri e valori negativi vengono pubblicati come **campi vuoti**, non come prezzi:

- lo zero significa che il prodotto non è stato quotato quella settimana;
- i negativi sono due convenzioni diverse della borsa che finiscono negli stessi
  campi — uno scarto rispetto al massimo, oppure la variazione settimanale.
  Nessuna delle due è un prezzo, e ricostruire l'intento sarebbe indovinare.

Nient'altro viene alterato.

## Errori presenti nella fonte, lasciati come sono

Alcuni valori del listino originale sono palesemente sbagliati. **Non vengono
corretti**: sono ripubblicati com'è e segnalati dal controllo di qualità
(`python -m pipeline.validate`).

| Caso | Cosa succede |
|------|--------------|
| Olive per olio d.o.p. (codici 96-100, 670-671) | Mediana 1,15-1,40 EUR/kg, ma fra il 24/10 e il 15/12 2022 il listino le riporta fra 70 e 140 |
| Codice 672, 2022-03-30 | `480 / 250`, con le settimane vicine a `480 / 490` |
| Alcune categorie | Radice incoerente, per esempio `Lattiero/Caseari > SUINI` |

Il sito segnala da sé, sul grafico, i prodotti con valori che si scostano di
oltre dieci volte dalla mediana storica.

## Quando la fonte si corregge da sola

Capita che la borsa pubblichi l'XML **prima** del bollettino PDF ufficiale, e che
quella prima versione contenga dati incompleti o sbagliati. Nei giorni successivi
l'XML viene riallineato al PDF **mantenendo lo stesso numero di bollettino**: chi
lo avesse scaricato una volta sola non se ne accorgerebbe mai.

Per questo l'aggiornamento non si limita ai numeri nuovi: a ogni esecuzione
riscarica anche gli **ultimi otto bollettini già acquisiti** e li riconfronta con
i CSV. Dove la fonte ha cambiato idea, vince la versione nuova.

Ogni valore sostituito è registrato in
[`dataset/verona/revisions.csv`](dataset/verona/revisions.csv), con il valore
vecchio, quello nuovo, il bollettino e la data in cui la differenza è stata
rilevata. Niente sparisce in silenzio, e il conteggio complessivo è in
`meta.json` come `n_revisions`.

Conseguenza pratica: **un CSV scaricato può cambiare nei giorni seguenti**, anche
per date già pubblicate. Chi tiene una copia locale delle ultime settimane
dovrebbe riscaricarla, o guardare il registro delle rettifiche.

Le rettifiche riguardano solo i valori che la fonte ripubblica. Quelle della
sezione precedente sono un'altra cosa: errori che la borsa non ha mai corretto, e
che restano nel dataset così come sono.

## Continuità delle serie

I codici prodotto della borsa sono stabili: su 840 codici, 794 non cambiano mai
identità e solo 5 prodotti hanno ricevuto un codice nuovo in dieci anni. I 46
casi restanti sono per lo più rifiniture della descrizione (`grano fino
(p.s. 78/79)` → `var. n.3 fino (p.s. 78/80)`), non prodotti diversi.

I vini fanno eccezione per costruzione: ogni annata è una serie a sé e riceve
codici nuovi. "Valpolicella d.o.c. 2025" e "Valpolicella d.o.c. 2024" **non**
vanno concatenati.

## Rispetto della fonte

Il fetcher si identifica con uno `User-Agent` che rimanda a questo repository e
attende un secondo fra una richiesta e l'altra. L'aggiornamento gira una volta al
giorno e fa una quindicina di richieste per esecuzione: sei di sondaggio sui
numeri nuovi, otto di ricontrollo su quelli recenti.

## Bologna: i listini sono PDF

I dati di Bologna non vengono da un file strutturato ma dal **testo dei PDF**
dei listini, estratto con `pdftotext` e interpretato da un parser. Non e' una
trascrizione manuale e non e' infallibile.

* Il parser **controlla se stesso**: ogni listino riporta la differenza fra
  settimana corrente e precedente, e il parser verifica che coincida con quella
  calcolata. Su oltre 130.000 righe complete non torna in 14, e sono
  incoerenze della fonte. Le righe che non riesce a collocare con certezza
  sulla colonna giusta le **scarta**, non le indovina (94 su 241.299).
* **Il codice di un prodotto Bologna segue l'etichetta esatta.** La Camera cambia
  le specifiche ogni anno ("p.s. 78/79" diventa "79/80"): il codice cambia con
  essa. Le serie si uniscono automaticamente solo per i gradi commerciali del
  frumento; per gli altri prodotti la scelta e' agronomica e non viene fatta in
  automatico. Vedi `dataset/bologna/README.md`.
* **Il 2012 e dieci listini successivi non sono leggibili** (caratteri
  codificati male nei PDF di origine). Quasi tutte le loro settimane si
  recuperano dal listino seguente, che ripete la settimana precedente;
  settembre 2014 resta un buco di cinque settimane.
* **Le settimane senza listino nell'archivio** sono ricostruite dalla colonna
  "precedente" del listino successivo; sono distinguibili perche' non hanno una
  riga in `issues.csv` per la propria data.
* Se la colonna "precedente" di un listino non concorda con il listino della
  settimana prima, la fonte si e' corretta: vince il valore piu' recente e il
  vecchio e' in `dataset/bologna/revisions.csv`. Una colonna "precedente"
  **svuotata** dalla Camera non cancella mai un prezzo gia' pubblicato.
* Zeri e valori non numerici ("-", "n.r.", errori di formula come "#VALORE!")
  sono pubblicati come **campi vuoti**, come a Verona.
