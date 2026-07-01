import {
  sortMarketMapConstituents,
  summarizeConstituentChanges,
} from './marketMapConstituents';

describe('marketMapConstituents', () => {
  const rows = [
    { symbol: 'AAA', change_pct: -2.5 },
    { symbol: 'BBB', change_pct: 3.1 },
    { symbol: 'CCC', change_pct: 0.5 },
    { symbol: 'DDD', change_pct: 1.2 },
  ];

  it('sortMarketMapConstituents orders major by change_pct desc', () => {
    const sorted = sortMarketMapConstituents(rows, 'major', false);
    expect(sorted.map((r) => r.symbol)).toEqual(['BBB', 'DDD', 'CCC', 'AAA']);
  });

  it('sortMarketMapConstituents alpha asc/desc', () => {
    expect(sortMarketMapConstituents(rows, 'alpha', false).map((r) => r.symbol)).toEqual(['AAA', 'BBB', 'CCC', 'DDD']);
    expect(sortMarketMapConstituents(rows, 'alpha', true).map((r) => r.symbol)).toEqual(['DDD', 'CCC', 'BBB', 'AAA']);
  });

  it('summarizeConstituentChanges counts adv/decl', () => {
    const s = summarizeConstituentChanges(rows);
    expect(s.advances).toBe(3);
    expect(s.declines).toBe(1);
    expect(s.pct_positive).toBe(75);
  });
});
