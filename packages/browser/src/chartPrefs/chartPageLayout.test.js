import {
  applyIndicatorPanelLayoutFromApi,
  collectLegacyChartViewFromApi,
  collectLegacyChartViewFromPrefs,
  globalChartViewToApiPayload,
  mergeGlobalChartViewSources,
  mergeIndicatorPanelSaveFields,
  normalizePanelOrder,
  pageLayoutToApiPayload,
  resolveChartLayoutConflict,
  resolveIndicatorPanelLayout,
} from './chartPageLayout';

describe('normalizePanelOrder', () => {
  it('accepts valid permutations', () => {
    expect(normalizePanelOrder(['stochrsi', 'macd'])).toEqual(['stochrsi', 'macd']);
    expect(normalizePanelOrder(['macd', 'stochrsi'])).toEqual(['macd', 'stochrsi']);
  });

  it('rejects invalid values', () => {
    expect(normalizePanelOrder(['stochrsi'])).toBeNull();
    expect(normalizePanelOrder(null)).toBeNull();
  });
});

describe('mergeIndicatorPanelSaveFields', () => {
  it('includes heights and panel order', () => {
    expect(mergeIndicatorPanelSaveFields({ foo: 1 }, { stochrsi: 180, macd: 140 }, ['macd', 'stochrsi'])).toEqual({
      foo: 1,
      stochrsi: 180,
      macd: 140,
      panelOrder: ['macd', 'stochrsi'],
    });
  });
});

describe('resolveIndicatorPanelLayout', () => {
  beforeEach(() => {
    window.localStorage.removeItem('cim.chart.indicatorHeights');
    window.localStorage.removeItem('cim.chart.indicatorHeights.distribution');
  });

  it('prefers localStorage over server defaults', () => {
    window.localStorage.setItem('cim.chart.indicatorHeights', JSON.stringify({
      stochrsi: 210,
      macd: 170,
    }));
    expect(resolveIndicatorPanelLayout(
      { stochrsi: 130, macd: 130 },
      null,
      null,
    )).toEqual({ stochrsi: 210, macd: 170 });
  });

  it('uses explicit server values when localStorage is empty', () => {
    expect(resolveIndicatorPanelLayout(
      { stochrsi: 200, macd: 150 },
      { stochrsi: 130, macd: 130 },
      { stochrsi: 100, macd: 100 },
    )).toEqual({ stochrsi: 200, macd: 150 });
  });

  it('falls back to chart prefs when server lacks indicator fields', () => {
    expect(resolveIndicatorPanelLayout(
      { watchlistChartLayout: 'single' },
      { stochrsi: 190, macd: 160, panelOrder: ['macd', 'stochrsi'] },
      null,
    )).toEqual({
      stochrsi: 190,
      macd: 160,
      panelOrder: ['macd', 'stochrsi'],
    });
  });
});

describe('applyIndicatorPanelLayoutFromApi', () => {
  it('restores heights and stack order', () => {
    const heights = jest.fn();
    const setPanelOrder = jest.fn();
    applyIndicatorPanelLayoutFromApi(
      { stochrsi: 200, macd: 150, panelOrder: ['macd', 'stochrsi'] },
      { applyLayoutHeights: heights, setPanelOrder },
    );
    expect(heights).toHaveBeenCalledWith({
      stochrsi: 200,
      macd: 150,
    });
    expect(setPanelOrder).toHaveBeenCalledWith(['macd', 'stochrsi']);
  });
});

describe('global chart layout', () => {
  it('prefers non-single layout when merging legacy per-page API fields', () => {
    const legacy = collectLegacyChartViewFromApi({
      dashboardChartLayout: 'single',
      moversChartLayout: '3h',
      moversTimeframe: '1D',
      moversTimeframe2: '1W',
      moversTimeframe3: '2W',
    });
    expect(legacy.chartLayout).toBe('3h');
    expect(legacy.timeframe).toBe('1D');
  });

  it('merges global server fields over legacy per-page fields', () => {
    const merged = mergeGlobalChartViewSources(
      { chartLayout: '3s', timeframe: '1D', timeframe2: '1W', timeframe3: '2W' },
      {},
      { chartLayout: 'single', timeframe: '1W' },
      {},
    );
    expect(merged.chartLayout).toBe('3s');
    expect(merged.timeframe).toBe('1D');
  });

  it('writes global API keys and per-page pane width', () => {
    expect(pageLayoutToApiPayload('watchlist', {
      chartLayout: '3h',
      timeframe: '1D',
      timeframe2: '1W',
      timeframe3: '2W',
      paneWidth: 420,
    })).toEqual({
      globalChartLayout: '3h',
      globalTimeframe: '1D',
      globalTimeframe2: '1W',
      globalTimeframe3: '2W',
      watchlistPaneWidth: 420,
    });
  });

  it('collects legacy chart prefs from per-page entries', () => {
    const legacy = collectLegacyChartViewFromPrefs({
      dashboard: { chartLayout: 'single' },
      indices: { chartLayout: '3s', timeframe: '1D' },
    });
    expect(legacy.chartLayout).toBe('3s');
    expect(legacy.timeframe).toBe('1D');
  });

  it('resolveChartLayoutConflict prefers multi-panel over single', () => {
    expect(resolveChartLayoutConflict('single', '3h')).toBe('3h');
    expect(resolveChartLayoutConflict('3h', 'single')).toBe('3h');
  });

  it('globalChartViewToApiPayload omits pane width', () => {
    expect(globalChartViewToApiPayload({
      chartLayout: '3h',
      paneWidth: 300,
    })).toEqual({ globalChartLayout: '3h' });
  });
});
