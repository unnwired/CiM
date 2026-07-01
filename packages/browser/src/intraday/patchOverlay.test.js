import {
  applyPatchToIndexRow,
  applyPatchToMoversRow,
  applyPatchToStockRow,
  isIntradayLiveTimeframe,
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

  it('computes change from price and previous close', () => {
    expect(snapshotChangePct({ price: 105, previous_close: 100 })).toBe(5);
    expect(snapshotPrice({ price: 12.3456 })).toBe(12.35);
  });
});
