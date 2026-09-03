import {
  CHART_RIGHT_SCALE_MIN_WIDTH,
  computeSeriesLeadOffset,
} from './chartPanelSync';

describe('chartPanelSync', () => {
  test('computeSeriesLeadOffset matches first indicator time', () => {
    const price = [
      { time: '2026-01-01', close: 1 },
      { time: '2026-01-02', close: 2 },
      { time: '2026-01-03', close: 3 },
      { time: '2026-01-06', close: 4 },
    ];
    const ind = [
      { time: '2026-01-03', value: 50 },
      { time: '2026-01-06', value: 55 },
    ];
    expect(computeSeriesLeadOffset(price, ind)).toBe(2);
  });

  test('computeSeriesLeadOffset falls back to length delta', () => {
    const price = [{ time: '2026-01-01' }, { time: '2026-01-02' }, { time: '2026-01-03' }];
    const ind = [{ time: '2099-01-01', value: 1 }];
    expect(computeSeriesLeadOffset(price, ind)).toBe(2);
  });

  test('right scale min width is fixed for pane alignment', () => {
    expect(CHART_RIGHT_SCALE_MIN_WIDTH).toBeGreaterThanOrEqual(72);
  });
});
