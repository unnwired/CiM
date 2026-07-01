import {
  chartTimeToMs,
  formatChartAxisLabel,
  isUnixChartTime,
  normalizeChartTimeKey,
} from './chartTime';

describe('chartTime', () => {
  test('unix seconds are not interpreted as milliseconds (1970 bug)', () => {
    const jun2026 = 1781630700;
    expect(isUnixChartTime(jun2026)).toBe(true);
    const ms = chartTimeToMs(jun2026);
    expect(new Date(ms).getUTCFullYear()).toBeGreaterThan(2020);
    expect(formatChartAxisLabel(jun2026)).toMatch(/Jun/);
    expect(formatChartAxisLabel(jun2026)).not.toMatch(/1970/);
  });

  test('daily strings still parse', () => {
    expect(normalizeChartTimeKey('2026-06-16')).toBe('2026-06-16');
    expect(isUnixChartTime('2026-06-16')).toBe(false);
    expect(chartTimeToMs('2026-06-16')).toBe(Date.parse('2026-06-16'));
  });

  test('normalizeChartTimeKey for unix', () => {
    expect(normalizeChartTimeKey(1781630700)).toBe('1781630700');
  });
});
