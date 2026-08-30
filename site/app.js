/* Dashboard dei prezzi della Borsa Merci di Verona.
   Sito statico: tutto arriva da api/index.json e api/series/<code>.json. */
'use strict';

const $ = (sel) => document.querySelector(sel);
const fmtNum = (n) => n.toLocaleString('it-IT');
const fmtPrice = (v) => v == null ? '—' : v.toLocaleString('it-IT', { maximumFractionDigits: 2 });

let CATALOG = [];
let META = {};
let chart = null, sLow = null, sHigh = null, sMid = null;
let current = null, currentPoints = [], range = 0;

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

  // Niente candele: la fonte pubblica un minimo e un massimo di rilevazione,
  // non apertura e chiusura. Inventare un OHLC significherebbe inventare dati.
  sHigh = chart.addLineSeries({ color: band, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
  sLow = chart.addLineSeries({ color: band, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
  sMid = chart.addLineSeries({ color: accent, lineWidth: 2, priceLineVisible: false });

  chart.subscribeCrosshairMove((param) => {
    const lo = param.seriesData?.get(sLow)?.value;
    const hi = param.seriesData?.get(sHigh)?.value;
    if (!param.time || (lo == null && hi == null)) { updateLegend(null); return; }
    updateLegend({ time: param.time, low: lo, high: hi });
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

  const line = (pick) => pts
    .map(([d, lo, hi]) => ({ time: d, value: pick(lo, hi) }))
    .filter((p) => p.value != null);

  sLow.setData(line((lo, hi) => lo ?? hi));
  sHigh.setData(line((lo, hi) => hi ?? lo));
  sMid.setData(line((lo, hi) => (lo != null && hi != null) ? (lo + hi) / 2 : (lo ?? hi)));
  chart.timeScale().fitContent();
  updateLegend(null);
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
  const last = currentPoints[currentPoints.length - 1];
  const p = hover || { time: last[0], low: last[1], high: last[2] };
  const span = (p.low != null && p.high != null && p.low !== p.high)
    ? `${fmtPrice(p.low)} – ${fmtPrice(p.high)}`
    : fmtPrice(p.high ?? p.low);
  $('#legend').innerHTML =
    `${fmtTime(p.time)} &nbsp; <b>${span}</b> ${current.unit}` +
    (hover ? '' : ' <i>(ultima rilevazione)</i>');
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
