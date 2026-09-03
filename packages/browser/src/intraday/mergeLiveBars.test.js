import { mergeLiveIntoDailyBars } from './mergeLiveBars';

describe('mergeLiveIntoDailyBars session open', () => {
  const yesterday = '2026-07-21';
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
  // Fixed IST instants (wall clock independent).
  const preOpen = new Date('2026-07-22T08:30:00+05:30');
  const afterOpen = new Date('2026-07-22T10:00:00+05:30');

  it('does not paint today open from LTP when session open is missing', () => {
    const bars = [
      { time: yesterday, open: 1280, high: 1295, low: 1275, close: 1290, volume: 1e6 },
    ];
    const { bars: out, dayChangePct } = mergeLiveIntoDailyBars(
      bars,
      {
        price: 1305,
        previous_close: 1290,
        change_pct: 1.16,
        source: 'upstox_stream',
      },
      afterOpen,
    );
    expect(out).toHaveLength(1);
    expect(out[0].time).toBe(yesterday);
    expect(dayChangePct).toBeCloseTo(1.16, 1);
  });

  it('uses session open from snapshot for new today bar', () => {
    const bars = [
      { time: yesterday, open: 1280, high: 1295, low: 1275, close: 1290, volume: 1e6 },
    ];
    const { bars: out } = mergeLiveIntoDailyBars(
      bars,
      {
        price: 1305,
        open: 1285,
        high: 1310,
        low: 1280,
        previous_close: 1290,
        source: 'upstox_session_seed',
      },
      afterOpen,
    );
    const last = out[out.length - 1];
    expect(last.time).toBe(today);
    expect(last.open).toBe(1285);
    expect(last.close).toBe(1305);
    expect(last.live).toBe(true);
  });

  it('does not paint today bar before 09:15 IST even when quote has OHLC', () => {
    const bars = [
      { time: yesterday, open: 1280, high: 1295, low: 1275, close: 1290, volume: 1e6 },
    ];
    const { bars: out, dayChangePct } = mergeLiveIntoDailyBars(
      bars,
      {
        price: 1305,
        open: 1285,
        high: 1310,
        low: 1280,
        volume: 2e6,
        previous_close: 1290,
        source: 'upstox_stream',
      },
      preOpen,
    );
    expect(out).toHaveLength(1);
    expect(out[0].time).toBe(yesterday);
    expect(dayChangePct).toBeNull();
  });
});
