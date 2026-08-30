# Manuale operativo

Come mettere in funzione l'aggiornamento automatico e il sito, e cosa fare
quando qualcosa non torna.

---

## 1. Attivazione su GitHub (una volta sola)

### 1.0 In che ordine

**Prima il push, poi le impostazioni.** Su un repository vuoto meta' interfaccia
non e' disponibile: `Settings` → `Pages` spesso non mostra nemmeno il selettore
della sorgente finche' non esiste un branch, e la scheda `Actions` mostra il
catalogo dei template invece dei workflow — non sceglierne nessuno, i due
workflow sono gia' in `.github/workflows/` e GitHub li trova da solo al push.

```bash
# 1. repository vuoto: niente README, licenza o .gitignore generati da GitHub.
#    Li abbiamo gia', e un commit iniziale loro costringerebbe a un merge.
gh repo create prezzi-agricoli --public

# 2. il codice
git init -b main            # il branch DEVE chiamarsi main: i workflow lo citano
git add .
git commit -m "Dataset e pipeline della Borsa Merci di Verona"
git remote add origin git@github.com:<utente>/prezzi-agricoli.git
git push -u origin main

# 3. le impostazioni: paragrafi 1.1 - 1.4
# 4. rilancia il workflow fallito: paragrafo 1.5
```

Il primo push fa partire `pages.yml` da solo — al primo commit `site/`,
`dataset/` e `pipeline/` sono tutti percorsi nuovi — e quel primo tentativo
**fallisce**, perche' Pages non e' ancora configurato. E' atteso: si rilancia a
mano dopo il paragrafo 1.1.

Link diretti, per non cercarli nei menu:

| Impostazione | Indirizzo |
|---|---|
| Permessi | `/settings/actions` |
| Pages | `/settings/pages` |
| Secret | `/settings/secrets/actions` |
| Etichetta | `/labels` |

Il **cron** comincia a contare solo quando il workflow e' sul branch di default:
prima, per GitHub, non esiste. La prima esecuzione automatica sara' quindi il
giorno seguente.

### 1.1 Abilita GitHub Pages

`Settings` → `Pages` → **Source: GitHub Actions**.

Non scegliere "Deploy from a branch": i JSON del sito non sono versionati, li
genera il workflow a ogni deploy. Versionare sia i CSV sia i JSON significherebbe
committare due volte gli stessi dati.

### 1.2 Dai al workflow il permesso di committare

`Settings` → `Actions` → `General` → `Workflow permissions` →
**Read and write permissions**.

### 1.3 Crea l'etichetta per le segnalazioni

```bash
gh label create pipeline --color B60205 --description "Guasti dell'aggiornamento automatico"
```

Senza questa etichetta il passo che apre la issue in caso di guasto fallisce a
sua volta, e il guasto resta muto.

### 1.4 Token per tenere vivo il cron — consigliato

GitHub **disattiva i workflow schedulati dopo 60 giorni** senza attività nel
repository, e i commit fatti con il token predefinito non sempre contano come
attività. Un repository che aggiorna solo dati rischia quindi di spegnersi da
solo dopo due mesi.

Rimedio: un token personale a scadenza lunga.

1. `Settings` → `Developer settings` → `Personal access tokens` →
   `Fine-grained tokens` → `Generate new token`
2. Repository: solo questo. Permessi: **Contents: Read and write**
3. Copia il token
4. Nel repository: `Settings` → `Secrets and variables` → `Actions` →
   `New repository secret`, nome **`DATA_PAT`**

Il workflow lo usa se c'è e ricade sul token predefinito se manca:

```yaml
token: ${{ secrets.DATA_PAT || secrets.GITHUB_TOKEN }}
```

Il token ha un secondo effetto utile: un push fatto con `GITHUB_TOKEN` non
innesca altri workflow, quindi senza `DATA_PAT` il sito si aggiorna tramite il
trigger `workflow_run` invece che direttamente sul push.

### 1.5 Prima esecuzione

`Actions` → `Aggiorna i dati` → `Run workflow`.

Verifica poi che `Pubblica il sito` sia partito e che
`https://<utente>.github.io/prezzi-agricoli/` risponda.

Se il dataset e' gia' aggiornato, questa prima esecuzione trovera' **zero
bollettini nuovi** e non committera' nulla: e' il comportamento corretto, non un
guasto. Per vedere l'automazione lavorare davvero occorre attendere il
bollettino successivo; nel frattempo il log del passo di sondaggio mostra quali
numeri ha provato.

---

## 2. Cosa succede da solo

```
ogni giorno alle 18:00 UTC
        │
        ├─ pipeline.update    sonda i bollettini successivi all'ultimo noto,
        │                     scarica quelli che esistono, li unisce ai CSV
        │
        ├─ pipeline.validate  ┬─ errori → NIENTE commit, apre una issue
        │                     └─ solo avvisi → prosegue
        │
        ├─ git commit         solo se dataset/ è cambiato davvero
        │
        └─ Pubblica il sito   rigenera i JSON dai CSV e fa il deploy su Pages
```

Il sondaggio si ferma dopo **6 numeri consecutivi mancanti**: la borsa salta
qualche numero (bollettini mensili, settimane di chiusura), quindi il primo 404
non significa "non c'è altro".

Sei richieste al giorno, una al secondo, con uno `User-Agent` che rimanda al
repository.

### Perché tutti i giorni

La borsa pubblica due o tre bollettini a settimana, in giorni non fissi. Sondare
ogni giorno rende l'orario irrilevante: se un giorno il cron di GitHub slitta o
salta — succede, il cron di Actions è "best effort" — l'indomani si recupera da
solo. L'operazione è idempotente: se non c'è niente di nuovo non committa nulla.

---

## 3. Operazioni manuali

Con il virtualenv attivo (`source .venv/bin/activate`).

### Aggiornare adesso, senza aspettare il cron

Da GitHub: `Actions` → `Aggiorna i dati` → `Run workflow`.

In locale:

```bash
python -m pipeline.update
python -m pipeline.validate
git add dataset && git commit -m "dati: aggiornamento manuale"
```

### Vedere cosa arriverebbe, senza scrivere niente

```bash
python -m pipeline.update --dry-run
```

### Ripartire da un bollettino preciso

Se il sondaggio si è fermato troppo presto, per esempio perché la borsa ha
saltato più di sei numeri di fila:

```bash
python -m pipeline.update --from 1450
```

Da GitHub lo stesso parametro è il campo `from` di `Run workflow`.

### Conservare gli XML scaricati

Di norma i file grezzi vengono buttati dopo il parsing: pesano una cinquantina di
MB e non sono versionati. Per tenerne un archivio locale:

```bash
python -m pipeline.update --staging data/verona
```

### Ricostruire tutto dall'archivio XML

Serve dopo aver toccato il parser o le regole sulle unità di misura: rilegge
tutti i bollettini e riscrive i CSV da zero.

```bash
python -m pipeline.rebuild          # da data/verona
python -m pipeline.validate
```

Richiede l'archivio completo. Se non ce l'hai, ricostruiscilo — ci vuole una
mezz'ora, una richiesta al secondo:

```bash
python -m pipeline.update --from 1 --staging data/verona
```

L'operazione è deterministica: due esecuzioni sugli stessi file danno CSV
identici byte per byte. E `rebuild` e `update` producono lo stesso risultato,
perché scrivono entrambi attraverso `pipeline/csvstore.py`.

### Rigenerare i JSON del sito

```bash
python -m pipeline.publish
```

Normalmente non serve: lo fa il workflow a ogni deploy. Utile per provare il sito
in locale:

```bash
python -m pipeline.publish
cd site && python -m http.server 8000
```

---

## 4. Il sito

`https://<utente>.github.io/prezzi-agricoli/` — catalogo con ricerca, filtri per
comparto e unità, grafico per prodotto con banda minimo-massimo, statistiche,
download della singola serie in CSV.

È **statico**: HTML, CSS e JavaScript, senza alcun server. GitHub Pages non
esegue codice. I dati arrivano da `site/api/`, generato dai CSV al momento del
deploy:

| File | Contenuto |
|------|-----------|
| `site/api/index.json` | catalogo completo, ~150 KB |
| `site/api/series/<code>.json` | una serie, scaricata solo quando si apre |

Scaricare i 4 MB dell'intero dataset per disegnare un grafico sarebbe
inaccettabile: da qui la divisione.

I grafici non sono candele. La fonte pubblica un minimo e un massimo di
rilevazione, non apertura e chiusura: costruire un OHLC significherebbe inventare
due valori su quattro.

---

## 5. Quando qualcosa non va

### Il workflow ha aperto una issue

Il dataset **non** è stato toccato: i CSV pubblicati restano quelli dell'ultima
esecuzione riuscita. Riproduci in locale:

```bash
python -m pipeline.update --dry-run
python -m pipeline.validate
```

### La validazione fallisce

Il gate distingue due cose:

| | Significato | Effetto |
|---|---|---|
| **Errore** | La nostra pipeline si è rotta | Blocca la pubblicazione |
| **Avviso** | La fonte ha pubblicato qualcosa di strano | Si segnala e si prosegue |

Sono errori: CSV malformato, data illeggibile, codice assente dal catalogo,
coppia (data, codice) duplicata, unità sconosciuta, prezzo negativo o nullo,
numero di righe che diminuisce.

Sono avvisi: minimo maggiore del massimo, valori oltre dieci volte la mediana
storica, prodotti mai quotati.

Un'**unità sconosciuta** è quasi sempre una categoria nuova con una dicitura mai
vista: aggiungi il pattern in `exchanges/verona/units.py`, poi `rebuild`.

Un **calo del numero di righe** significa che il parser ha smesso di riconoscere
qualcosa. Non forzare il commit: capisci prima cosa è cambiato nella fonte.

### Il cron ha smesso di partire

Quasi certamente i 60 giorni di inattività (§ 1.4). In `Actions` il workflow
appare disabilitato, con un pulsante per riattivarlo. Configura `DATA_PAT`
perché non succeda più.

### Il sito non si aggiorna

Controlla che `Pubblica il sito` sia partito. È innescato dal push su `dataset/`
e, in assenza di `DATA_PAT`, dal trigger `workflow_run` al termine di
`Aggiorna i dati`. Si può sempre lanciare a mano da `Actions`.

---

## 6. Rapporto con agx-scraper

Il parser di Verona nasce in [agx-scraper](https://github.com/a1oysio/agx-scraper),
dove vive anche una dashboard Flask locale per ispezionare i dati e provare borse
nuove. Qui ne esiste una copia, perché la pipeline non può funzionare senza.

Quattro file sono **copie identiche**, e un `diff` basta a vedere se hanno preso
strade diverse:

```
exchanges/verona/parser.py
exchanges/verona/processors.py
exchanges/verona/units.py
exchanges/verona/fetcher.py     ← tranne lo User-Agent, che indica questo repo
```

Due file differiscono per costruzione:

- `exchanges/__init__.py` — qui contiene solo i dataclass `PriceRecord` e
  `FileMetadata`, senza la classe base degli adapter né il registro, che servono
  soltanto all'app Flask;
- `exchanges/verona/__init__.py` — qui è vuoto, là contiene l'adapter.

**Questo repository è quello autorevole** per il parser di Verona. Le correzioni
si fanno qui e semmai si riportano in agx-scraper, non il contrario.

---

## 7. Aggiungere un'altra borsa

`exchanges/verona/` è il modello: un modulo con `fetcher.py` (scaricamento) e
`parser.py`, che espone `parse_xml_file(path) -> (FileMetadata, [PriceRecord])`.

Perché una seconda borsa arrivi fino ai CSV serve:

1. il nuovo modulo in `exchanges/<nome>/`, che restituisca `PriceRecord` con
   `category_path` e `units` **corretti** — mai un'unità fissa: è stato l'errore
   più costoso di questo progetto, il 58% dei dati era sbagliato;
2. rendere `pipeline/paths.py` multi-borsa: oggi ha una sola coppia
   `EXCHANGE_CODE` / `EXCHANGE_SLUG`;
3. estendere `pipeline/update.py`, che oggi chiama direttamente il fetcher di
   Verona;
4. estendere il sito, che oggi legge un solo `index.json`.

Un parser PDF per Bologna esiste già in agx-scraper, ma non ha la stessa
maturità: i suoi dati non sono in questo dataset.
