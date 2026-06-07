import {
  buildAnchoredEarningsEvents,
  buildEarningsEventLookup,
  buildBottomEarningsMarkers,
  getEarningsMarkerColor,
  getEarningsModalVariant,
  getEarningsStatusLabel,
  normalizeEarningsComparisonStatus,
  resolveEarningsAnchorDate,
  shouldShowEarningsMarkers,
} from './earningsChartMarkers';

describe('earningsChartMarkers', () => {
  test('limits markers to day-based 1D through 7D timeframes', () => {
    expect(shouldShowEarningsMarkers('1D')).toBe(true);
    expect(shouldShowEarningsMarkers('7D')).toBe(true);
    expect(shouldShowEarningsMarkers('1W')).toBe(false);
    expect(shouldShowEarningsMarkers('1M')).toBe(false);
  });

  test('normalizes outcome kinds and keeps the latest event per date', () => {
    const lookup = buildEarningsEventLookup([
      { earnings_release_date: '2026-05-20', outcome_kind: 'beat', comparison_status: 'provisional' },
      { earnings_release_date: '2026-05-21', outcome_kind: 'unknown', comparison_status: 'wat' },
    ]);
    expect(lookup.get('2026-05-20')?.outcome_kind).toBe('beat');
    expect(lookup.get('2026-05-21')?.outcome_kind).toBe('miss');
    expect(lookup.get('2026-05-20')?.comparison_status).toBe('provisional');
    expect(lookup.get('2026-05-21')?.comparison_status).toBe('unverified');
  });

  test('anchors weekend earnings events to the previous trading bar', () => {
    expect(resolveEarningsAnchorDate('2026-05-16', ['2026-05-15', '2026-05-18'])).toBe('2026-05-15');
    expect(buildAnchoredEarningsEvents(
      [{ earnings_release_date: '2026-05-16', outcome_kind: 'beat' }],
      ['2026-05-15', '2026-05-18'],
    )).toEqual([
      expect.objectContaining({
        earnings_release_date: '2026-05-16',
        chart_anchor_date: '2026-05-15',
      }),
    ]);
  });

  test('builds visible bottom markers only for loaded bar dates', () => {
    const markers = buildBottomEarningsMarkers(
      [
        {
          earnings_release_date: '2026-05-19',
          chart_anchor_date: '2026-05-19',
          outcome_kind: 'miss',
          comparison_status: 'verified',
        },
        {
          earnings_release_date: '2026-05-20',
          chart_anchor_date: '2026-05-20',
          outcome_kind: 'beat',
          comparison_status: 'provisional',
        },
      ],
      ['2026-05-20', '2026-05-21'],
      (date) => (date === '2026-05-20' ? 42 : null),
      200,
    );

    expect(markers).toEqual([
      expect.objectContaining({
        id: 'earnings:2026-05-20:2026-05-20',
        x: 42,
        date: '2026-05-20',
        color: getEarningsMarkerColor('beat'),
        event: expect.objectContaining({
          earnings_release_date: '2026-05-20',
          chart_anchor_date: '2026-05-20',
          comparison_status: 'provisional',
        }),
      }),
    ]);
  });

  test('uses the previous trading bar for marker coordinates', () => {
    const markers = buildBottomEarningsMarkers(
      [
        {
          earnings_release_date: '2026-05-16',
          chart_anchor_date: '2026-05-15',
          outcome_kind: 'beat',
          comparison_status: 'verified',
        },
      ],
      ['2026-05-15', '2026-05-18'],
      (date) => (date === '2026-05-15' ? 36 : null),
      200,
    );

    expect(markers).toEqual([
      expect.objectContaining({
        id: 'earnings:2026-05-16:2026-05-15',
        x: 36,
        date: '2026-05-15',
        event: expect.objectContaining({
          earnings_release_date: '2026-05-16',
          chart_anchor_date: '2026-05-15',
        }),
      }),
    ]);
  });

  test('maps marker outcome to modal variant', () => {
    expect(getEarningsModalVariant('beat')).toBe('beat');
    expect(getEarningsModalVariant('miss')).toBe('reported_miss');
  });

  test('normalizes comparison status labels', () => {
    expect(normalizeEarningsComparisonStatus('provisional')).toBe('provisional');
    expect(normalizeEarningsComparisonStatus('discrepancy')).toBe('discrepancy');
    expect(normalizeEarningsComparisonStatus('other')).toBe('unverified');
    expect(getEarningsStatusLabel('provisional')).toBe('Provisional');
    expect(getEarningsStatusLabel('discrepancy')).toBe('Mismatch');
  });
});
