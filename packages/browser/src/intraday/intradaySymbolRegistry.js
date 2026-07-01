/** Per-page chart focus — Refresh prices fetches only these symbols (not whole tables). */

const pageFocusedSymbols = new Map();

const pageSymbols = new Map();

const VIEW_PAGE_ID = {
  dashboard: 'dashboard',
  portfolio: 'portfolio-dashboard',
  pnl: 'pnl',
  'market-map': 'market-map',
  'market-movers': 'movers',
  'market-pulse': 'market-pulse',
  watchlist: 'watchlist',
  indices: 'indices',
  'potential-swings': 'potential-swings',
  chart: 'chart',
};

export const PAGE_DISPLAY_NAMES = {
  dashboard: 'Dashboard',
  'portfolio-dashboard': 'Portfolio',
  pnl: 'P&L',
  'market-map': 'Market Map',
  movers: 'Market Movers',
  'market-pulse': 'Market Pulse',
  watchlist: 'Watchlist',
  indices: 'Indices',
  'potential-swings': 'Potential Swings',
  chart: 'Chart',
};

export function setPageIntradaySymbols(pageId, symbols) {
  const id = String(pageId || '').trim();
  if (!id) return;
  const set = new Set();
  for (const raw of symbols || []) {
    const sym = String(raw || '').trim().toUpperCase();
    if (sym) set.add(sym);
  }
  if (set.size === 0) pageSymbols.delete(id);
  else pageSymbols.set(id, set);
}

export function clearPageIntradaySymbols(pageId) {
  pageSymbols.delete(String(pageId || '').trim());
}

/** @deprecated Use getSymbolsForPage for Refresh prices. */
export function collectRegisteredIntradaySymbols() {
  const out = new Set();
  pageSymbols.forEach((set) => {
    set.forEach((sym) => out.add(sym));
  });
  return [...out];
}

export function resolvePageId(view, chartTabSymbol = null) {
  const v = String(view || '').trim();
  if (v === 'chart') return 'chart';
  if (v.startsWith('index_')) {
    return `index-${v.slice(6).trim().toUpperCase()}`;
  }
  if (v.startsWith('constituents_')) {
    return `constituents-${v.slice(13).trim().toUpperCase()}`;
  }
  if (VIEW_PAGE_ID[v]) return VIEW_PAGE_ID[v];
  return v;
}

export function getSymbolsForPage(pageId, chartTabSymbol = null) {
  const id = String(pageId || '').trim();
  if (id === 'chart') {
    const sym = String(chartTabSymbol || '').trim().toUpperCase();
    if (sym) return [sym];
    const set = pageSymbols.get('chart');
    return set ? [...set] : [];
  }
  const set = pageSymbols.get(id);
  return set ? [...set] : [];
}

export function setPageFocusedSymbols(pageId, symbols) {
  const id = String(pageId || '').trim();
  if (!id) return;
  const set = new Set();
  for (const raw of symbols || []) {
    const sym = String(raw || '').trim().toUpperCase();
    if (sym) set.add(sym);
  }
  if (set.size === 0) pageFocusedSymbols.delete(id);
  else pageFocusedSymbols.set(id, set);
}

export function clearPageFocusedSymbols(pageId) {
  pageFocusedSymbols.delete(String(pageId || '').trim());
}

/** Symbols to fetch on Refresh prices — chart focus only, never whole screener tables. */
export function getRefreshSymbols(pageId, chartTabSymbol = null) {
  const id = String(pageId || '').trim();
  if (id === 'chart') {
    const sym = String(chartTabSymbol || '').trim().toUpperCase();
    if (sym) return [sym];
    const focused = pageFocusedSymbols.get('chart');
    return focused ? [...focused] : [];
  }
  const focused = pageFocusedSymbols.get(id);
  if (focused && focused.size > 0) return [...focused];
  return [];
}

export function pageDisplayName(pageId) {
  const id = String(pageId || '').trim();
  if (PAGE_DISPLAY_NAMES[id]) return PAGE_DISPLAY_NAMES[id];
  if (id.startsWith('index-')) return `Index ${id.slice(6)}`;
  if (id.startsWith('constituents-')) return `Constituents ${id.slice(13)}`;
  return 'this page';
}
