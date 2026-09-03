import {
  appendFutureWhitespace,
  buildFutureWhitespaceBars,
} from './chartFutureTime';

describe('chartFutureTime', () => {
  test('projects daily bars across weekends', () => {
    const future = buildFutureWhitespaceBars(
      [{ time: '2026-07-17', close: 100 }], // Friday
      '1D',
      3,
    );
    expect(future).toEqual([
      { time: '2026-07-20' },
      { time: '2026-07-21' },
      { time: '2026-07-22' },
    ]);
  });

  test('uses the selected multi-day and weekly cadence', () => {
    expect(buildFutureWhitespaceBars([{ time: '2026-07-16' }], '2D', 2)).toEqual([
      { time: '2026-07-20' },
      { time: '2026-07-22' },
    ]);
    expect(buildFutureWhitespaceBars([{ time: '2026-07-16' }], '2W', 2)).toEqual([
      { time: '2026-07-30' },
      { time: '2026-08-13' },
    ]);
  });

  test('projects monthly bars by calendar month', () => {
    expect(buildFutureWhitespaceBars([{ time: '2026-07-31' }], '1M', 3)).toEqual([
      { time: '2026-08-31' },
      { time: '2026-09-30' },
      { time: '2026-10-31' },
    ]);
  });

  test('projects 4H NSE session slots and skips weekends', () => {
    // Fri 17 Jul 2026 13:15 IST = 07:45 UTC.
    const fridayAfternoon = Date.UTC(2026, 6, 17, 7, 45) / 1000;
    const future = buildFutureWhitespaceBars([{ time: fridayAfternoon }], '4H', 3);
    expect(future).toEqual([
      { time: Date.UTC(2026, 6, 20, 3, 45) / 1000 }, // Mon 09:15 IST
      { time: Date.UTC(2026, 6, 20, 7, 45) / 1000 }, // Mon 13:15 IST
      { time: Date.UTC(2026, 6, 21, 3, 45) / 1000 }, // Tue 09:15 IST
    ]);
  });

  test('projects 30m NSE session slots and skips weekends', () => {
    // Fri 17 Jul 2026 15:15 IST = 09:45 UTC (last session bar).
    const fridayLast = Date.UTC(2026, 6, 17, 9, 45) / 1000;
    const future = buildFutureWhitespaceBars([{ time: fridayLast }], '30m', 2);
    expect(future).toEqual([
      { time: Date.UTC(2026, 6, 20, 3, 45) / 1000 }, // Mon 09:15 IST
      { time: Date.UTC(2026, 6, 20, 4, 15) / 1000 }, // Mon 09:45 IST
    ]);
  });

  test('appends time-only points without altering source data', () => {
    const data = [{ time: '2026-07-16', value: 10 }];
    const future = [{ time: '2026-07-17' }];
    expect(appendFutureWhitespace(data, future)).toEqual([...data, ...future]);
    expect(data).toHaveLength(1);
  });
});
