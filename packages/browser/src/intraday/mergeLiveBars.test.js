import { mergeLiveIntoDailyBars, mergeLiveIntoChartBars, sanitizeBarsForDisplay } from './mergeLiveBars';

describe('mergeLiveIntoDailyBars', () => {
  const eodBars = [
    { time: '2026-06-03', open: 770, high: 775, low: 768, close: 772, volume: 1e6 },
    { time: '2026-06-04', open: 772, high: 778, low: 770, close: 776, volume: 1.1e6 },
  ];

  it('rejects zero open/low from snapshot (no 0→price spike)', () => {
    const { bars, dayChangePct } = mergeLiveIntoDailyBars(eodBars, {
      price: 782.3,
      open: 0,
      high: 0,
      low: 0,
      previous_close: 776,
      volume: 500000,
    });
    const last = bars[bars.length - 1];
    expect(last.live).toBe(true);
    expect(last.low).toBeGreaterThan(0);
    expect(last.open).toBeGreaterThan(0);
    expect(last.low).toBeLessThanOrEqual(last.close);
    expect(dayChangePct).toBeCloseTo(((782.3 - 776) / 776) * 100, 1);
  });

  it('shows red intraday candle when session open is above close (RELIANCE)', () => {
    const { bars, dayChangePct } = mergeLiveIntoDailyBars(eodBars, {
      price: 1305,
      open: 1315.3,
      high: 1325,
      low: 1303.6,
      previous_close: 1296.5,
    });
    const last = bars[bars.length - 1];
    expect(last.open).toBeCloseTo(1315.3, 1);
    expect(last.close).toBe(1305);
    expect(last.close).toBeLessThan(last.open);
    expect(dayChangePct).toBeCloseTo(((1305 - 1296.5) / 1296.5) * 100, 1);
  });

  it('does not use previous_close as today open when session open missing', () => {
    const { bars } = mergeLiveIntoDailyBars(eodBars, {
      price: 1305,
      previous_close: 1296.5,
    });
    const last = bars[bars.length - 1];
    expect(last.open).not.toBe(1296.5);
    expect(last.open).toBe(1305);
    expect(last.close).toBe(1305);
  });

  it('returns unchanged bars when price invalid', () => {
    const { bars } = mergeLiveIntoDailyBars(eodBars, { price: 0, previous_close: 776 });
    expect(bars).toEqual(eodBars);
  });

  it('updates last bar close on 1W timeframe', () => {
    const bars = [
      { time: '2026-05-26', open: 1200, high: 1220, low: 1190, close: 1210 },
      { time: '2026-06-02', open: 1210, high: 1280, low: 1205, close: 1270 },
    ];
    const { bars: out } = mergeLiveIntoChartBars(bars, {
      price: 1305,
      open: 1315,
      high: 1325,
      low: 1303,
      previous_close: 1296.5,
    }, '1W');
    const last = out[out.length - 1];
    expect(last.close).toBe(1305);
    expect(last.live).toBe(true);
  });
});

describe('sanitizeBarsForDisplay', () => {
  it('fixes zero open on EOD bar', () => {
    const bars = sanitizeBarsForDisplay([
      { time: '2026-06-03', open: 770, high: 775, low: 768, close: 772 },
      { time: '2026-06-04', open: 0, high: 1310, low: 0, close: 1307 },
    ]);
    const last = bars[1];
    expect(last.open).toBeGreaterThan(0);
    expect(last.low).toBeGreaterThan(0);
    expect(last.low).toBeLessThanOrEqual(last.close);
  });
});
