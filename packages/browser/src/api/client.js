import api from './http';

export async function fetchStocks({ page = 1, pageSize = 50, sortBy = 'Symbol', sortDir = 'asc', search = '' } = {}) {
  const res = await api.get('/api/stocks', {
    params: { page, pageSize, sortBy, sortDir, search },
  });
  return res.data;
}

export async function searchStocks(q) {
  if (!q || q.trim().length === 0) return { results: [] };
  const res = await api.get('/api/stocks/search', { params: { q } });
  return res.data;
}

export async function searchUniverse(q) {
  if (!q || q.trim().length === 0) return { stocks: [], indices: [] };
  const res = await api.get('/api/unified-search', { params: { q } });
  return res.data;
}

export async function addPortfolioItem(item) {
  const res = await api.post('/api/portfolio/items', item);
  return res.data;
}

export async function removePortfolioItem(symbol, type = 'stock') {
  const res = await api.delete(`/api/portfolio/items/${encodeURIComponent(symbol)}`, { params: { type } });
  return res.data;
}

export async function fetchStockDetail(symbol) {
  const res = await api.get(`/api/stock/${symbol}`);
  return res.data;
}

export async function fetchChartData(symbol, timeframe = '1D', emas = [], barsLimit = 700, liveToday = false) {
  const params = { timeframe };
  if (emas[0]) params.ema1 = emas[0];
  if (emas[1]) params.ema2 = emas[1];
  if (emas[2]) params.ema3 = emas[2];
  if (emas[3]) params.ema4 = emas[3];
  if (barsLimit) params.bars_limit = barsLimit;
  if (liveToday) params.live_today = true;
  const res = await api.get(`/api/chart-data/${symbol}`, { params });
  return res.data;
}

export async function fetchEarningsChartEvents(symbol, refreshLatest = true) {
  const res = await api.get(`/api/earnings-chart-events/${encodeURIComponent(symbol)}`, {
    params: { refresh_latest: refreshLatest },
  });
  return res.data;
}

export async function fetchTimeframes() {
  const res = await api.get('/api/timeframes');
  return res.data;
}

/** `instrumentType`: `stock` | `index` — same ticker can exist as both; notes are scoped per kind. */
export async function getInstrumentNote(symbol, instrumentType = 'stock') {
  const res = await api.get(`/api/instrument-notes/${encodeURIComponent(symbol)}`, {
    params: { type: instrumentType },
  });
  return res.data;
}

export async function putInstrumentNote(symbol, { instrumentType = 'stock', note = '' } = {}) {
  const res = await api.put(`/api/instrument-notes/${encodeURIComponent(symbol)}`, {
    instrument_type: instrumentType,
    note,
  });
  return res.data;
}
