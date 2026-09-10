/* Dashboard dei prezzi della Borsa Merci di Verona.
   Sito statico: tutto arriva da api/index.json e api/series/<code>.json. */
'use strict';

const $ = (sel) => document.querySelector(sel);
const fmtNum = (n) => n.toLocaleString('it-IT');
const fmtPrice = (v) => v == null ? '—' : v.toLocaleString('it-IT', { maximumFractionDigits: 2 });

let CATALOG = [];
let META = {};
let chart = null, sLow = null, sHigh = null, sMid = null, sBox = null;
let lastPriceLine = null, lastPriceOwner = null;
let current = null, currentPoints = [], range = 0;
// '' = una barra per rilevazione; 'W' | 'M' | 'Y' = raggruppate per periodo.
let bucket = '', view = 'line';
// I periodi disegnati adesso, e l'indice per data: il crosshair restituisce una
// data, non l'oggetto, e cercarla nell'array a ogni movimento del mouse sarebbe
// una scansione lineare per pixel.
let currentBuckets = [], bucketIndex = new Map();

/* ---------- avvio ---------- */

async function boot() {
  const res = await fetch('api/index.json');
  const data = await res.json();
  META = data.meta || {};
  // Senza quotazioni non c'è nulla da disegnare: restano nei CSV, non in elenco.
  CATALOG = (data.products || []).filter((p) => p.n > 0);

  renderStats();
  fillSelect('#group', CATALOG.map((p) => p.group));
  fillSelect('#unit', CATALOG.map((p) => p.unit));
  renderList();

  ['#q', '#group', '#unit'].forEach((sel) =>
    $(sel).addEventListener('input', renderList));

  document.querySelectorAll('[data-range]').forEach((b) =>
    b.addEventListener('click', () => {
      range = Number(b.dataset.range);
      document.querySelectorAll('[data-range]').forEach((o) =>
        o.setAttribute('aria-pressed', String(o === b)));
      applyRange();
    }));

  $('#bucket').addEventListener('change', (e) => { bucket = e.target.value; applyRange(); });
  $('#view').addEventListener('change', (e) => { view = e.target.value; applyRange(); });

  $('#csv').addEventListener('click', downloadCsv);
  $('#back').addEventListener('click', showList);

  // Su telefono il riquadro cambia misura anche senza un resize della finestra
  // (rotazione, barra dell'indirizzo che si ritrae, passaggio elenco/scheda).
  const box = $('#chart');
  if (window.ResizeObserver) {
    new ResizeObserver(() => resizeChart()).observe(box);
  } else {
    window.addEventListener('resize', resizeChart);
  }
  window.addEventListener('orientationchange', () => setTimeout(resizeChart, 250));

  const code = new URLSearchParams(location.search).get('p');
  if (code && CATALOG.some((p) => p.code === code)) select(code);
}

function resizeChart() {
  const el = $('#chart');
  // A larghezza zero il riquadro è nascosto: ridimensionare romperebbe la scala.
  if (!chart || !el.clientWidth) return;
  chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
  chart.timeScale().fitContent();
}

// Su schermo stretto elenco e scheda sono due viste alternate (vedi style.css).
function showList() {
  document.body.classList.remove('detail-open');
  const url = new URL(location);
  url.searchParams.delete('p');
  history.replaceState(null, '', url);
  window.scrollTo(0, 0);
}

function renderStats() {
  const rows = [
    ['Prodotti', fmtNum(META.n_products || 0)],
    ['Quotazioni', fmtNum(META.n_quoted || 0)],
    ['Rilevazioni', fmtNum(META.n_observations || 0)],
    ['Dal', META.first_date || '—'],
    ['Al', META.last_date || '—'],
    ['Bollettino', META.last_issue_number != null ? `n. ${META.last_issue_number}` : '—'],
    ['Aggiornato', (META.generated_at || '').slice(0, 10) || '—'],
  ];
  $('#stats').innerHTML = rows
    .map(([k, v]) => `<div class="stat"><div class="v">${v}</div><div class="k">${k}</div></div>`)
    .join('');
}

function fillSelect(sel, values) {
  const el = $(sel);
  [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'it'))
    .forEach((v) => {
      const o = document.createElement('option');
      o.value = v; o.textContent = v;
      el.appendChild(o);
    });
}

/* ---------- elenco ---------- */

function renderList() {
  const q = $('#q').value.trim().toLowerCase();
  const group = $('#group').value;
  const unit = $('#unit').value;

  const rows = CATALOG.filter((p) =>
    (!group || p.group === group) &&
    (!unit || p.unit === unit) &&
    (!q || p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)));

  $('#count').textContent =
    `${fmtNum(rows.length)} prodotti su ${fmtNum(CATALOG.length)}`;

  $('#list').innerHTML = rows.map((p) => `
    <div class="item" role="option" data-code="${p.code}"
         aria-selected="${current && current.code === p.code}">
      <div class="n">${escapeHtml(p.name)}<span class="badge">${p.unit}</span></div>
      <div class="m">${escapeHtml(p.category || p.group)} · ${fmtNum(p.n)} quotazioni · fino al ${p.last}</div>
    </div>`).join('');

  $('#list').querySelectorAll('.item').forEach((el) =>
    el.addEventListener('click', () => select(el.dataset.code)));
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* ---------- dettaglio ---------- */

async function select(code) {
  const meta = CATALOG.find((p) => p.code === code);
  if (!meta) return;
  current = meta;

  const url = new URL(location);
  url.searchParams.set('p', code);
  history.replaceState(null, '', url);

  $('#empty').hidden = true;
  $('#detail').hidden = false;
  // Prima di creare il grafico: su telefono <main> è nascosto finché non c'è
  // questa classe, e un riquadro nascosto ha larghezza zero.
  document.body.classList.add('detail-open');
  window.scrollTo(0, 0);
  $('#title').textContent = meta.name;
  $('#crumb').textContent = `${meta.path} · codice ${meta.code} · ${meta.unit}`;
  renderList();

  const res = await fetch(`api/series/${code}.json`);
  const data = await res.json();
  currentPoints = data.points;

  ensureChart();
  applyRange();
  renderFacts();
}

function ensureChart() {
  if (chart) return;
  const el = $('#chart');
  const css = getComputedStyle(document.body);
  const text = css.getPropertyValue('--muted').trim();
  const border = css.getPropertyValue('--border').trim();
  const accent = css.getPropertyValue('--accent').trim();
  const band = css.getPropertyValue('--band').trim();

  chart = LightweightCharts.createChart(el, {
    width: el.clientWidth,
    height: el.clientHeight,
    layout: { background: { color: 'transparent' }, textColor: text, fontSize: 11 },
    grid: { vertLines: { color: border }, horzLines: { color: border } },
    rightPriceScale: { borderColor: border },
    timeScale: { borderColor: border, fixLeftEdge: true, fixRightEdge: true },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    // Il trascinamento verticale col dito resta alla pagina, non al grafico:
    // altrimenti su telefono lo scorrimento si blocca sopra il riquadro.
    handleScroll: { vertTouchDrag: false },
    localization: {
      locale: 'it-IT',
      priceFormatter: (v) => v.toLocaleString('it-IT', { maximumFractionDigits: 2 }),
    },
  });

  // Vista a linea: due sottili per gli estremi e una spessa per la media in
  // mezzo. Le due sottili non hanno etichetta sull'asse dei prezzi, sono il
  // contorno della banda e non valori da leggere uno per uno.
  sHigh = chart.addLineSeries({ color: band, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
  sLow = chart.addLineSeries({ color: band, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
  // Il tratteggio sull'ultima quotazione lo disegna setLastPriceLine: deve
  // restare lo stesso valore in tutt'e due le viste, e il price line automatico
  // della libreria segue la serie, che nella vista a rettangoli e' un'altra.
  sMid = chart.addLineSeries({
    color: accent, lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
  });

  // Vista a rettangoli. La serie e' di tipo candlestick perche' e' l'unica che
  // disegna un corpo fra due prezzi, ma non sono candele: la fonte pubblica un
  // minimo e un massimo, non apertura e chiusura, e inventarli sarebbe inventare
  // dati. Apertura e chiusura valgono quindi quanto minimo e massimo -- il corpo
  // copre l'escursione e niente altro -- con gli stoppini spenti e un colore
  // solo, perche' il verde/rosso indicherebbe una direzione che non esiste.
  sBox = chart.addCandlestickSeries({
    upColor: band, downColor: band,
    borderUpColor: accent, borderDownColor: accent,
    wickVisible: false, borderVisible: true,
    priceLineVisible: false, lastValueVisible: false,
  });

  chart.subscribeCrosshairMove((param) => {
    if (!param.time) { updateLegend(null); return; }
    updateLegend(bucketIndex.get(fmtTime(param.time)) || null);
  });
}

// Il tratteggio orizzontale sull'ultima quotazione: dice a colpo d'occhio dove
// sta oggi il prezzo rispetto a tutto lo storico che gli sta a sinistra.
function setLastPriceLine(series, value, color) {
  if (lastPriceOwner && lastPriceLine) lastPriceOwner.removePriceLine(lastPriceLine);
  lastPriceLine = lastPriceOwner = null;
  if (value == null) return;
  lastPriceOwner = series;
  lastPriceLine = series.createPriceLine({
    price: value, color, lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true, title: '',
  });
}

function applyRange() {
  if (!chart || !currentPoints.length) return;
  let pts = currentPoints;
  if (range) {
    const cut = new Date(currentPoints[currentPoints.length - 1][0]);
    cut.setFullYear(cut.getFullYear() - range);
    const iso = cut.toISOString().slice(0, 10);
    pts = currentPoints.filter((p) => p[0] >= iso);
  }
  if (!pts.length) pts = currentPoints;

  currentBuckets = aggregate(pts, bucket);
  bucketIndex = new Map(currentBuckets.map((b) => [b.time, b]));

  const boxed = view === 'box';
  const pad = rightPad(currentBuckets);
  const line = (pick) => currentBuckets.map((b) => ({ time: b.time, value: pick(b) }));

  // La serie inattiva si svuota invece di nascondersi: una serie nascosta pesa
  // comunque sulla scala dei prezzi, e la banda min-max allargherebbe l'asse
  // anche nella vista a rettangoli, dove non si vede.
  sLow.setData(boxed ? [] : line((b) => b.low));
  sHigh.setData(boxed ? [] : line((b) => b.high));
  sMid.setData(boxed ? [] : line((b) => b.mid).concat(pad));
  sBox.setData(boxed
    ? currentBuckets.map((b) => (
        { time: b.time, open: b.low, high: b.high, low: b.low, close: b.high }
      )).concat(pad)
    : []);

  const last = currentBuckets[currentBuckets.length - 1];
  setLastPriceLine(boxed ? sBox : sMid, last ? last.mid : null,
                   getComputedStyle(document.body).getPropertyValue('--accent').trim());

  chart.timeScale().fitContent();
  updateLegend(null);
}

const MESI = ['gen', 'feb', 'mar', 'apr', 'mag', 'giu',
              'lug', 'ago', 'set', 'ott', 'nov', 'dic'];

// La data che rappresenta il periodo, piu' l'etichetta da mostrare in legenda.
// Il periodo e' identificato dal suo primo giorno: e' quello che l'asse dei
// tempi puo' ordinare, mentre "agosto 2026" non lo e'.
function periodOf(iso, mode) {
  if (mode === 'Y') return { time: `${iso.slice(0, 4)}-01-01`, label: iso.slice(0, 4) };
  if (mode === 'M') {
    const [y, m] = iso.split('-');
    return { time: `${y}-${m}-01`, label: `${MESI[Number(m) - 1]} ${y}` };
  }
  // Settimana ISO, cioe' quella che comincia di lunedi'. La borsa rileva quasi
  // sempre di lunedi', ma non sempre, e due bollettini nella stessa settimana
  // devono cadere nello stesso periodo.
  const t = new Date(`${iso}T00:00:00Z`);
  t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7));
  const monday = t.toISOString().slice(0, 10);
  return { time: monday, label: `sett. del ${monday}` };
}

// Da rilevazioni a periodi. Minimo e massimo sono gli estremi toccati nel
// periodo; la linea e' la media delle rilevazioni, non il centro della banda:
// un mese con tre settimane a 200 e una a 300 vale 225, non 250.
function aggregate(pts, mode) {
  const midOf = (lo, hi) => (lo != null && hi != null) ? (lo + hi) / 2 : (lo ?? hi);

  if (!mode) {
    return pts.map(([d, lo, hi]) => (
      { time: d, label: d, low: lo ?? hi, high: hi ?? lo, mid: midOf(lo, hi), n: 1 }
    ));
  }

  const acc = new Map();
  for (const [d, lo, hi] of pts) {
    const { time, label } = periodOf(d, mode);
    let b = acc.get(time);
    if (!b) { b = { time, label, low: Infinity, high: -Infinity, sum: 0, n: 0 }; acc.set(time, b); }
    b.low = Math.min(b.low, lo ?? hi);
    b.high = Math.max(b.high, hi ?? lo);
    b.sum += midOf(lo, hi);
    b.n += 1;
  }
  return [...acc.values()]
    .map(({ time, label, low, high, sum, n }) => ({ time, label, low, high, mid: sum / n, n }))
    .sort((a, b) => a.time < b.time ? -1 : 1);
}

// Un po' d'aria fra l'ultima quotazione e l'asse dei prezzi: appiccicata al
// bordo, l'ultima quotazione e' proprio quella che si legge peggio.
//
// Lo spazio si ottiene con punti whitespace -- date senza valore -- e non con
// `rightOffset`, che con `fixRightEdge: true` viene azzerato dalla libreria
// (maxRightOffset vale 0 quando il bordo destro e' fissato).  Cosi' il grafico
// resta ancorato come prima e in piu' l'asse dei tempi mostra le settimane
// entranti, dove il prossimo bollettino andra' a cadere.
//
// La quantita' e' in proporzione ai punti, non fissa: `fitContent` distribuisce
// la larghezza sul numero di barre, quindi il 4% dei punti da' sempre lo stesso
// margine in pixel, che si guardino dieci anni o un anno.
function rightPad(items) {
  if (!items.length) return [];
  const day = 86400000;
  const at = (iso) => new Date(`${iso}T00:00:00Z`).getTime();
  const last = at(items[items.length - 1].time);
  // Passo fra due periodi: di norma sette giorni, ma la borsa salta settimane e
  // raggruppando per mese o per anno il passo e' tutt'altro.
  const step = items.length > 1 ? Math.max(day, last - at(items[items.length - 2].time)) : 7 * day;
  const n = Math.max(1, Math.round(items.length * 0.04));
  return Array.from({ length: n }, (_, i) => (
    { time: new Date(last + (i + 1) * step).toISOString().slice(0, 10) }
  ));
}

// Con le date in formato 'YYYY-MM-DD' la libreria restituisce un BusinessDay
// ({year, month, day}), non la stringa che le abbiamo passato.
function fmtTime(t) {
  if (t && typeof t === 'object') {
    return `${t.year}-${String(t.month).padStart(2, '0')}-${String(t.day).padStart(2, '0')}`;
  }
  return String(t);
}

function updateLegend(hover) {
  if (!current) return;
  const b = hover || currentBuckets[currentBuckets.length - 1];
  if (!b) return;
  const span = (b.low != null && b.high != null && b.low !== b.high)
    ? `${fmtPrice(b.low)} – ${fmtPrice(b.high)}`
    : fmtPrice(b.high ?? b.low);
  const quante = b.n > 1 ? ` <i>(${b.n} rilevazioni)</i>` : '';
  const coda = hover ? '' : (bucket ? ' <i>(ultimo periodo)</i>' : ' <i>(ultima rilevazione)</i>');
  $('#legend').innerHTML =
    `${b.label} &nbsp; <b>${span}</b> ${current.unit}${quante}${coda}`;
}

function renderFacts() {
  const vals = currentPoints
    .map(([, lo, hi]) => (lo != null && hi != null) ? (lo + hi) / 2 : (lo ?? hi))
    .filter((v) => v != null)
    .sort((a, b) => a - b);
  const median = vals.length ? vals[Math.floor(vals.length / 2)] : null;

  $('#facts').innerHTML = [
    ['Quotazioni', fmtNum(current.n)],
    ['Periodo', `${current.first} → ${current.last}`],
    ['Minimo storico', `${fmtPrice(vals[0])} ${current.unit}`],
    ['Mediana', `${fmtPrice(median)} ${current.unit}`],
    ['Massimo storico', `${fmtPrice(vals[vals.length - 1])} ${current.unit}`],
  ].map(([k, v]) => `<div><span>${k}</span>${v}</div>`).join('');

  // Lo stacco dalla mediana segnala quasi sempre un errore di scala della fonte
  // (es. le olive d.o.p. pubblicate a ~100x fra ottobre e dicembre 2022).
  const odd = median ? vals.filter((v) => v > median * 10 || v < median / 10).length : 0;
  const note = $('#note');
  note.hidden = odd === 0;
  if (odd) {
    note.textContent =
      `${odd} quotazioni si scostano di oltre 10 volte dalla mediana storica. ` +
      `Sono quasi certamente errori di scala nel listino pubblicato dalla Camera ` +
      `di Commercio: i dati sono ripubblicati come sono, senza correzioni.`;
  }
}

function downloadCsv() {
  const rows = [['date', 'low', 'high', 'unit']]
    .concat(currentPoints.map(([d, lo, hi]) => [d, lo ?? '', hi ?? '', current.unit]));
  const blob = new Blob([rows.map((r) => r.join(',')).join('\n')],
                        { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `verona-${current.code}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

boot();
