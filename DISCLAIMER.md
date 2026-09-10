# Avvertenze

## Non è una fonte ufficiale

I CSV di questo repository sono una **ricostruzione automatica** del listino
della Borsa Merci di Verona. Per qualsiasi uso contrattuale, fiscale o legale
fa fede esclusivamente il listino pubblicato dalla Camera di Commercio di
Verona.

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
