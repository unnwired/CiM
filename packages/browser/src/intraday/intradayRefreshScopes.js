/** Per-page symbol lists for Refresh prices — each page registers what it actually displays. */

function dedupeSymbols(symbols) {
  const out = [];
  const seen = new Set();
  for (const raw of symbols || []) {
    const sym = String(raw || '').trim().toUpperCase();
    if (!sym || seen.has(sym)) continue;
    seen.add(sym);
    out.push(sym);
  }
  return out;
}

export function symbolsForChartFocus(symbol) {
  const sym = String(symbol || '').trim().toUpperCase();
  return sym ? [sym] : [];
}

export function symbolsForChartPanels(panels) {
  const syms = [];
  for (const p of panels || []) {
    const sym = p?.symbol;
    if (sym) syms.push(sym);
  }
  return dedupeSymbols(syms);
}

export function symbolsForMarketMap(selected, constituents) {
  const syms = [];
  if (selected?.symbol) syms.push(selected.symbol);
  for (const c of constituents || []) {
    if (c?.symbol) syms.push(c.symbol);
  }
  return dedupeSymbols(syms);
}

export function symbolsForMarketPulse(indices) {
  return dedupeSymbols((indices || []).map((i) => i?.symbol));
}

export function symbolsForMovers(rows) {
  return dedupeSymbols((rows || []).map((r) => r?.symbol));
}

export function symbolsForIndicesPage(selected) {
  const sym = selected?.symbol;
  return sym ? dedupeSymbols([sym]) : [];
}

export function symbolsForConstituents(stocks, chartSymbol) {
  const syms = [];
  if (chartSymbol) syms.push(chartSymbol);
  for (const s of stocks || []) {
    if (s?.symbol) syms.push(s.symbol);
  }
  return dedupeSymbols(syms);
}

/** User-facing toast when Refresh prices has nothing to fetch on this page. */
export const REFRESH_EMPTY_MESSAGE = {
  dashboard: 'Select a stock on the chart, then refresh prices.',
  'portfolio-dashboard': 'Select a stock on the chart, then refresh prices.',
  watchlist: 'Select a watchlist item on the chart, then refresh prices.',
  'potential-swings': 'Select a stock on the chart, then refresh prices.',
  chart: 'Open a chart symbol, then refresh prices.',
  indices: 'Select an index on the chart, then refresh prices.',
  'market-map': 'Select an index and wait for constituents to load, then refresh prices.',
  'market-pulse': 'Wait for indices to load, then refresh prices.',
  movers: 'Wait for movers to load, then refresh prices.',
};

export function refreshEmptyMessage(pageId) {
  const id = String(pageId || '').trim();
  if (REFRESH_EMPTY_MESSAGE[id]) return REFRESH_EMPTY_MESSAGE[id];
  if (id.startsWith('index-')) return 'Open an index chart, then refresh prices.';
  if (id.startsWith('constituents-')) return 'Wait for constituents to load, then refresh prices.';
  return 'Nothing to refresh on this page.';
}
