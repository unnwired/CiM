import {
  STOCK_LIST_COL_WIDTHS_STORAGE_KEY,
  mergeColumnWidths,
  readStoredColumnWidths,
  writeStoredColumnWidths,
  columnWidthKey,
} from './stockListColumnStorage';

describe('stockListColumnStorage', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('uses canonical width keys across column defs', () => {
    expect(columnWidthKey({ key: 'last_price', widthKey: 'price' })).toBe('price');
    expect(columnWidthKey({ key: 'Symbol' })).toBe('Symbol');
  });

  it('merges defaults with stored widths', () => {
    writeStoredColumnWidths({ symbol: 140, market_cap: 120 });
    const cols = [
      { key: 'symbol', widthKey: 'symbol', width: 90 },
      { key: 'last_price', widthKey: 'price', width: 85 },
    ];
    expect(mergeColumnWidths(cols)).toEqual({ symbol: 140, market_cap: 120, price: 85 });
  });

  it('persists widths for reload', () => {
    writeStoredColumnWidths({ symbol: 150 });
    expect(readStoredColumnWidths()).toEqual({ symbol: 150 });
    expect(window.localStorage.getItem(STOCK_LIST_COL_WIDTHS_STORAGE_KEY)).toContain('"symbol":150');
  });
});
