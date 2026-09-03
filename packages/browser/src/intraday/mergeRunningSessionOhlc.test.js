import { liveQuoteToSnapshot, mergeRunningSessionOhlc } from './useIntradayPatch';

describe('mergeRunningSessionOhlc', () => {
  it('does not invent session open from first LTP-only tick', () => {
    const next = mergeRunningSessionOhlc(null, {
      symbol: 'RELIANCE',
      price: 1300,
      previous_close: 1290,
      change_pct: 0.78,
    });
    expect(next.open).toBeUndefined();
    expect(next.high).toBe(1300);
    expect(next.low).toBe(1300);
  });

  it('uses seeded open on first tick when present', () => {
    const next = mergeRunningSessionOhlc(null, {
      symbol: 'RELIANCE',
      price: 1300,
      open: 1285,
      high: 1310,
      low: 1280,
      previous_close: 1290,
    });
    expect(next.open).toBe(1285);
    expect(next.high).toBe(1310);
    expect(next.low).toBe(1280);
  });

  it('expands high/low across LTP ticks when OHLC omitted', () => {
    const a = mergeRunningSessionOhlc(null, { symbol: 'X', price: 100, previous_close: 99 });
    const b = mergeRunningSessionOhlc(a, { symbol: 'X', price: 105, open: 100, previous_close: 99, change_pct: 6.06 });
    const c = mergeRunningSessionOhlc(b, { symbol: 'X', price: 97, previous_close: 99, change_pct: -2.02 });
    expect(c.open).toBe(100);
    expect(c.high).toBe(105);
    expect(c.low).toBe(97);
    expect(c.price).toBe(97);
  });

  it('preserves prior high/low when new tick omits them', () => {
    const prev = { symbol: 'X', price: 102, open: 100, high: 110, low: 98, previous_close: 99 };
    const next = mergeRunningSessionOhlc(prev, { symbol: 'X', price: 103, previous_close: 99, change_pct: 4.04 });
    expect(next.high).toBe(110);
    expect(next.low).toBe(98);
    expect(next.open).toBe(100);
    expect(next.price).toBe(103);
  });
});

describe('liveQuoteToSnapshot', () => {
  it('maps day OHLC from quote fields', () => {
    const snap = liveQuoteToSnapshot('INFY', {
      price: 1501,
      previous_close: 1490,
      open: 1495,
      high: 1510,
      low: 1488,
      change_pct: 0.74,
      source: 'upstox_stream',
    });
    expect(snap).toMatchObject({
      symbol: 'INFY',
      price: 1501,
      open: 1495,
      high: 1510,
      low: 1488,
      previous_close: 1490,
      change_pct: 0.74,
    });
  });
});
