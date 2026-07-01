import {
  symbolsForChartFocus,
  symbolsForConstituents,
  symbolsForIndicesPage,
  symbolsForMarketMap,
  symbolsForMarketPulse,
  symbolsForMovers,
  refreshEmptyMessage,
} from './intradayRefreshScopes';

describe('intradayRefreshScopes', () => {
  it('symbolsForMarketMap includes index and constituents deduped', () => {
    const syms = symbolsForMarketMap(
      { symbol: '^NSEI' },
      [{ symbol: 'RELIANCE' }, { symbol: 'HDFCBANK' }, { symbol: 'RELIANCE' }],
    );
    expect(syms).toEqual(['^NSEI', 'RELIANCE', 'HDFCBANK']);
  });

  it('symbolsForMarketMap returns index only when constituents empty', () => {
    expect(symbolsForMarketMap({ symbol: '^NSEI' }, [])).toEqual(['^NSEI']);
    expect(symbolsForMarketMap(null, null)).toEqual([]);
  });

  it('symbolsForMovers maps row symbols', () => {
    const rows = Array.from({ length: 50 }, (_, i) => ({ symbol: `SYM${i}` }));
    expect(symbolsForMovers(rows)).toHaveLength(50);
    expect(symbolsForMovers(rows)[0]).toBe('SYM0');
  });

  it('symbolsForIndicesPage returns single selected index', () => {
    expect(symbolsForIndicesPage({ symbol: '^NSEBANK' })).toEqual(['^NSEBANK']);
    expect(symbolsForIndicesPage(null)).toEqual([]);
  });

  it('symbolsForMarketPulse returns all index symbols', () => {
    const indices = [{ symbol: '^NSEI' }, { symbol: '^NSEBANK' }, { symbol: '^CNXIT' }];
    expect(symbolsForMarketPulse(indices)).toEqual(['^NSEI', '^NSEBANK', '^CNXIT']);
  });

  it('symbolsForConstituents includes table stocks and chart symbol', () => {
    const syms = symbolsForConstituents(
      [{ symbol: 'RELIANCE' }, { symbol: 'TCS' }],
      'RELIANCE',
    );
    expect(syms).toEqual(['RELIANCE', 'TCS']);
  });

  it('symbolsForChartFocus returns single symbol', () => {
    expect(symbolsForChartFocus('reliance')).toEqual(['RELIANCE']);
    expect(symbolsForChartFocus('')).toEqual([]);
  });

  it('refreshEmptyMessage is page-specific', () => {
    expect(refreshEmptyMessage('market-map')).toMatch(/constituents/i);
    expect(refreshEmptyMessage('movers')).toMatch(/movers/i);
    expect(refreshEmptyMessage('dashboard')).toMatch(/chart/i);
  });
});
