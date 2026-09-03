import {
  applyPatchToEarningsRow,
  applyPatchToGenericQuoteRow,
  applyPatchToIndexRow,
  applyPatchToMoversRow,
  applyPatchToStockRow,
  attachEarningsMonthRefClose,
  isIntradayLiveTimeframe,
  monthRefCloseFromRow,
  snapshotChangePct,
  snapshotPrice,
} from './patchOverlay';

describe('patchOverlay', () => {
  it('isIntradayLiveTimeframe includes 1D, 1W, 2W', () => {
    expect(isIntradayLiveTimeframe('1D')).toBe(true);
    expect(isIntradayLiveTimeframe('1W')).toBe(true);
    expect(isIntradayLiveTimeframe('2W')).toBe(true);
    expect(isIntradayLiveTimeframe('1M')).toBe(false);
  });

  it('overlays stock row price and change', () => {
    const snap = { price: 101.25, previous_close: 100, change_pct: 1.25 };
    expect(applyPatchToStockRow({ Symbol: 'RELIANCE', Price: 99, 'Change %': 0 }, snap)).toEqual({
      Symbol: 'RELIANCE',
      Price: 101.25,
      'Change %': 1.25,
    });
  });

  it('replaces stale server 0% when live snap has prior close', () => {
    const snap = { price: 98.9, previous_close: 100 };
    expect(applyPatchToStockRow({ Symbol: 'CAPLIPOINT', Price: 100, 'Change %': 0 }, snap)).toEqual({
      Symbol: 'CAPLIPOINT',
      Price: 98.9,
      'Change %': -1.1,
    });
  });

  it('overlays index row', () => {
    const snap = { price: 22500.5, change_pct: -0.42 };
    expect(applyPatchToIndexRow({ symbol: 'NIFTY', last_price: 22400, change_pct: -1 }, snap)).toEqual({
      symbol: 'NIFTY',
      last_price: 22500.5,
      change_pct: -0.42,
    });
  });

  it('overlays movers row', () => {
    const snap = { price: 50.1, change_pct: 2.5 };
    expect(applyPatchToMoversRow({ symbol: 'ABC', price: 48, change_pct: 0 }, snap)).toEqual({
      symbol: 'ABC',
      price: 50.1,
      change_pct: 2.5,
    });
  });

  it('overlays generic/constituent row with both price and last_price', () => {
    const snap = { price: 312.4, previous_close: 300, change_pct: 4.13 };
    expect(applyPatchToGenericQuoteRow({
      symbol: 'TCS',
      last_price: 300,
      price: 300,
      change_pct: 0,
    }, snap)).toEqual({
      symbol: 'TCS',
      last_price: 312.4,
      price: 312.4,
      change_pct: 4.13,
    });
  });

  it('computes change from price and previous close', () => {
    expect(snapshotChangePct({ price: 105, previous_close: 100 })).toBe(5);
    expect(snapshotPrice({ price: 12.3456 })).toBe(12.35);
  });

  it('derives month_ref_close from fetch-time price and 1M %', () => {
    // price 110 after +10% month → ref = 100
    expect(monthRefCloseFromRow({ price: 110, change_1m_pct: 10 })).toBe(100);
    expect(attachEarningsMonthRefClose({ symbol: 'AAA', price: 110, change_1m_pct: 10 })).toEqual({
      symbol: 'AAA',
      price: 110,
      change_1m_pct: 10,
      month_ref_close: 100,
    });
  });

  it('overlays earnings price, 1D %, and derives 1M % from month_ref_close', () => {
    const row = {
      symbol: 'RELIANCE',
      price: 100,
      change_1d_pct: 0.5,
      change_1m_pct: 5,
      month_ref_close: 100,
    };
    const snap = { price: 105, previous_close: 100, change_pct: 5 };
    expect(applyPatchToEarningsRow(row, snap)).toEqual({
      symbol: 'RELIANCE',
      price: 105,
      change_1d_pct: 5,
      change_1m_pct: 5,
      month_ref_close: 100,
    });
  });
});
