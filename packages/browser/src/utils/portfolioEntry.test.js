import { computePlPct, formatPlPct, plPctColor } from './portfolioEntry';

describe('portfolioEntry', () => {
  test('computePlPct gain and loss', () => {
    expect(computePlPct(110, 100)).toBe(10);
    expect(computePlPct(88, 100)).toBe(-12);
    expect(computePlPct(null, 100)).toBeNull();
    expect(computePlPct(100, 0)).toBeNull();
  });

  test('formatPlPct', () => {
    expect(formatPlPct(10)).toBe('+10.00%');
    expect(formatPlPct(-12)).toBe('-12.00%');
    expect(formatPlPct(null)).toBe('—');
  });

  test('plPctColor', () => {
    expect(plPctColor(5)).toBe('var(--accent-green)');
    expect(plPctColor(-3)).toBe('var(--accent-red)');
    expect(plPctColor(null)).toBe('var(--text-muted)');
  });
});
