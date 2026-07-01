import {
  cycleStarTag,
  getStarTier,
  sortIndicesByStarTier,
  normalizeStarTags,
  STAR_PRIORITY_ORDER,
} from './indexStarTags';

describe('indexStarTags', () => {
  it('picker and sort priority order is golden → green → blue → red', () => {
    expect(STAR_PRIORITY_ORDER).toEqual(['golden', 'green', 'blue', 'red']);
  });

  it('cycles none → red → green → blue → golden → none', () => {
    expect(cycleStarTag(null)).toBe('red');
    expect(cycleStarTag(undefined)).toBe('red');
    expect(cycleStarTag('red')).toBe('green');
    expect(cycleStarTag('green')).toBe('blue');
    expect(cycleStarTag('blue')).toBe('golden');
    expect(cycleStarTag('golden')).toBe(null);
  });

  it('assigns sort tiers golden first', () => {
    expect(getStarTier('golden')).toBe(0);
    expect(getStarTier('green')).toBe(1);
    expect(getStarTier('blue')).toBe(2);
    expect(getStarTier('red')).toBe(3);
    expect(getStarTier(null)).toBe(4);
    expect(getStarTier('invalid')).toBe(4);
  });

  it('sorts by tier then preserves manual order within tier', () => {
    const items = [
      { symbol: 'A' },
      { symbol: 'B' },
      { symbol: 'C' },
      { symbol: 'D' },
    ];
    const tags = { A: 'red', B: 'golden', C: 'red', D: 'green' };
    const sorted = sortIndicesByStarTier(items, tags, (i) => i.symbol);
    expect(sorted.map((i) => i.symbol)).toEqual(['B', 'D', 'A', 'C']);
  });

  it('normalizes tag map', () => {
    expect(normalizeStarTags({ 'NIFTY 50': 'golden', BAD: 'purple' })).toEqual({
      'NIFTY 50': 'golden',
    });
    expect(normalizeStarTags(null)).toEqual({});
  });
});
