import { isDualBeatRow, sortItemsByEarningsPriority } from './portfolioEarnings';

describe('isDualBeatRow', () => {
  test('accepts dual beat when both surprises are non-negative', () => {
    expect(isDualBeatRow({
      eps_surprise_pct: 5,
      revenue_surprise_pct: 2,
      eps_actual: 10,
      revenue_actual: 100,
    })).toBe(true);
  });

  test('accepts revenue-only beat when reported EPS exists (GMDC-style)', () => {
    expect(isDualBeatRow({
      eps_surprise_pct: null,
      revenue_surprise_pct: 3.5,
      eps_actual: 1.2,
      revenue_actual: 500,
    })).toBe(true);
  });

  test('rejects revenue-only beat without reported EPS', () => {
    expect(isDualBeatRow({
      eps_surprise_pct: null,
      revenue_surprise_pct: 3.5,
      eps_actual: null,
      revenue_actual: 500,
    })).toBe(false);
  });
});

describe('sortItemsByEarningsPriority', () => {
  const beatBySymbol = new Map([
    ['BEAT_TODAY', { earnings_release_date: '2026-05-25', days_since_report: 0 }],
    ['BEAT_TWO', { earnings_release_date: '2026-05-23', days_since_report: 2 }],
    ['BOTH', { earnings_release_date: '2026-05-25', days_since_report: 0 }],
  ]);
  const upcomingBySymbol = new Map([
    ['UP_SOON', { earnings_release_next_date: '2026-05-25', days_until: 0 }],
    ['UP_LATER', { earnings_release_next_date: '2026-05-27', days_until: 2 }],
    ['BOTH', { earnings_release_next_date: '2026-05-26', days_until: 1 }],
  ]);

  const items = [
    { symbol: 'OTHER_A', type: 'stock' },
    { symbol: 'BEAT_TWO', type: 'stock' },
    { symbol: 'UP_LATER', type: 'stock' },
    { symbol: 'OTHER_B', type: 'stock' },
    { symbol: 'UP_SOON', type: 'stock' },
    { symbol: 'BEAT_TODAY', type: 'stock' },
    { symbol: 'BOTH', type: 'stock' },
    { symbol: 'NIFTY 50', type: 'index' },
  ];

  function sort(dir = 'asc') {
    return sortItemsByEarningsPriority(items, {
      getSymbol: item => item.symbol,
      isEligible: item => item.type !== 'index',
      beatBySymbol,
      upcomingBySymbol,
      dir,
    }).map(item => item.symbol);
  }

  test('sorts upcoming first, then most recent beat rows, then preserves base order for the rest', () => {
    expect(sort('asc')).toEqual([
      'UP_SOON',
      'UP_LATER',
      'BEAT_TODAY',
      'BOTH',
      'BEAT_TWO',
      'OTHER_A',
      'OTHER_B',
      'NIFTY 50',
    ]);
  });

  test('reverses date order inside upcoming and beat buckets only', () => {
    expect(sort('desc')).toEqual([
      'UP_LATER',
      'UP_SOON',
      'BEAT_TWO',
      'BEAT_TODAY',
      'BOTH',
      'OTHER_A',
      'OTHER_B',
      'NIFTY 50',
    ]);
  });
});
