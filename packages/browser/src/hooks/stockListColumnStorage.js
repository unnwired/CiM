/** Canonical stock-list column widths shared across Pulse, Portfolio, Watchlist, Constituents, etc. */
export const STOCK_LIST_COL_WIDTHS_STORAGE_KEY = 'cim.stockList.colWidths.v1';

export const DEFAULT_STOCK_COL_WIDTHS = {
  symbol: 90,
  market_cap: 110,
  note: 36,
  price: 85,
  change_1d: 80,
  change_1m: 80,
  change_30d: 80,
  change_1y: 80,
  volume: 100,
  year_high: 88,
  year_low: 88,
  remove: 34,
  rank: 36,
};

const MIN_BY_KEY = {
  note: 28,
  remove: 28,
  rank: 28,
};

export function columnWidthKey(col) {
  return col.widthKey || col.key;
}

export function defaultWidthForColumn(col) {
  const wk = columnWidthKey(col);
  return col.defaultWidth ?? col.width ?? DEFAULT_STOCK_COL_WIDTHS[wk] ?? 80;
}

export function minWidthForColumn(col) {
  const wk = columnWidthKey(col);
  return col.minWidth ?? MIN_BY_KEY[wk] ?? 48;
}

export function readStoredColumnWidths() {
  try {
    const raw = window.localStorage.getItem(STOCK_LIST_COL_WIDTHS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function mergeColumnWidths(columnDefs, stored = readStoredColumnWidths()) {
  const merged = { ...stored };
  for (const col of columnDefs) {
    const wk = columnWidthKey(col);
    if (merged[wk] == null) {
      merged[wk] = defaultWidthForColumn(col);
    }
  }
  return merged;
}

export function writeStoredColumnWidths(widths) {
  window.localStorage.setItem(STOCK_LIST_COL_WIDTHS_STORAGE_KEY, JSON.stringify(widths));
}
