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
  'earnings-beats': 'earnings-beats',
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
  'earnings-beats': 'Earnings',
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

/**
 * Map the active App view to the Live Feed scope (no Mode dropdown).
 * context = CiMLive subscription key; pageId = symbol-registry / pageLive id.
 */
export function livePageContextFromView(view, { chartSymbol } = {}) {
  const v = String(view || '').trim();
  const chartSym = String(chartSymbol || '').trim().toUpperCase();

  if (v === 'chart') {
    return {
      context: 'focus',
      pageId: 'chart',
      label: chartSym ? `Chart · ${chartSym}` : 'Chart',
      list: false,
    };
  }
  if (v === 'dashboard') {
    return { context: 'dashboard', pageId: 'dashboard', label: 'NSE', list: true };
  }
  if (v === 'portfolio') {
    return { context: 'portfolio', pageId: 'portfolio-dashboard', label: 'Portfolio', list: true };
  }
  if (v === 'pnl') {
    return { context: 'pnl', pageId: 'pnl', label: 'P&L', list: true };
  }
  if (v === 'indices') {
    return { context: 'indices', pageId: 'indices', label: 'Indices', list: false };
  }
  if (v === 'watchlist') {
    return { context: 'watchlist', pageId: 'watchlist', label: 'Watchlist', list: true };
  }
  if (v === 'market-map') {
    return { context: 'market-map', pageId: 'market-map', label: 'Market Map', list: true };
  }
  if (v === 'market-pulse') {
    return { context: 'market-pulse', pageId: 'market-pulse', label: 'Market Pulse', list: true };
  }
  if (v === 'market-movers') {
    return { context: 'movers', pageId: 'movers', label: 'Market Movers', list: false, movers: true };
  }
  if (v === 'potential-swings') {
    return {
      context: 'potential-swings',
      pageId: 'potential-swings',
      label: 'Potential Swings',
      list: false,
    };
  }
  if (v === 'earnings-beats') {
    return {
      context: 'earnings-beats',
      pageId: 'earnings-beats',
      label: 'Earnings',
      list: true,
    };
  }
  if (v.startsWith('index_')) {
    const sym = v.slice(6);
    const pageId = `index-${sym}`;
    return {
      context: pageId,
      pageId,
      label: sym ? `Index · ${sym}` : 'Index',
      list: false,
    };
  }
  if (v.startsWith('constituents_')) {
    const sym = v.slice(13);
    const pageId = `constituents-${sym}`;
    return {
      context: pageId,
      pageId,
      label: sym ? `Constituents · ${sym}` : 'Constituents',
      list: true,
    };
  }
  return {
    context: 'focus',
    pageId: 'chart',
    label: 'Focused symbol',
    list: false,
  };
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

/** Live Feed Mode — same left-to-right order as visible nav tabs; Earnings / Potential Swings excluded. */
export const LIVE_FEED_MODE_OPTIONS = [
  { value: 'dashboard', label: 'NSE', pageId: 'dashboard' },
  { value: 'indices', label: 'Indices', pageId: 'indices' },
  { value: 'market-map', label: 'Market Map', pageId: 'market-map' },
  { value: 'market-pulse', label: 'Market Pulse', pageId: 'market-pulse' },
  { value: 'movers', label: 'Market Movers', pageId: 'movers' },
  { value: 'watchlist', label: 'Watchlist', pageId: 'watchlist' },
  { value: 'portfolio', label: 'Portfolio', pageId: 'portfolio-dashboard' },
  { value: 'pnl', label: 'P&L', pageId: 'pnl' },
  { value: 'focus', label: 'Focused symbol', pageId: 'chart' },
];

function publishPageSymbolsApi() {
  if (typeof window === 'undefined') return;
  window.CiMPageSymbols = {
    getRefreshSymbols,
    getSymbolsForPage,
    pageDisplayName,
    livePageContextFromView,
    LIVE_FEED_MODE_OPTIONS,
  };
}

publishPageSymbolsApi();

