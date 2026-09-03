import {
  buildAnchoredCorpMarkers,
  buildBottomCorpMarkers,
  shouldShowCorpMarkers,
} from './corpChartMarkers';

describe('corpChartMarkers', () => {
  it('shows on daily timeframes only', () => {
    expect(shouldShowCorpMarkers('1D')).toBe(true);
    expect(shouldShowCorpMarkers('1W')).toBe(false);
  });

  it('anchors split marker to trading day', () => {
    const anchored = buildAnchoredCorpMarkers(
      [{ date: '2026-08-24', kind: 'split', label: 'S', ratio: 2 }],
      ['2026-08-21', '2026-08-24', '2026-08-25'],
    );
    expect(anchored).toHaveLength(1);
    expect(anchored[0].chart_anchor_date).toBe('2026-08-24');
    expect(anchored[0].label).toBe('S');
  });

  it('builds bottom S and D markers', () => {
    const markers = buildBottomCorpMarkers(
      [
        { date: '2026-08-24', kind: 'split', label: 'S', ratio: 2, color: '#a371f7' },
        { date: '2026-06-05', kind: 'dividend', label: 'D', amount: 2.5, color: '#d29922' },
      ],
      ['2026-06-05', '2026-08-24'],
      (time) => (time === '2026-08-24' ? 120 : 40),
      400,
    );
    expect(markers.map((m) => m.label).sort()).toEqual(['D', 'S']);
  });
});
