/* eslint-disable react-hooks/exhaustive-deps */
import React, { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'react';
import BasketToolbarButton from '../components/Basket';
import axios from 'axios';
import { APP_DATA_REFRESH_EVENT } from '../chartEvents';
import ChartContainer from '../components/chart/ChartContainer';
import { DrawingWorkspaceProvider } from '../components/chart/drawing/DrawingWorkspaceContext';
import { DrawingToolbarConnected, DrawingFloatPaletteConnected } from '../components/chart/drawing/DrawingToolbar';
import EMAControls    from '../components/chart/EMAControls';
import ChartHeaderBar from '../components/chart/ChartHeaderBar';
import {
  EMA_PREFS_UPDATED_EVENT,
  PANELS_PREFS_KEY,
  PANELS_PREFS_UPDATED_EVENT,
  VOLUME_PREFS_UPDATED_EVENT,
  getPersistedEmaSet,
  getPersistedVisiblePanels,
  getPersistedVolumeVisible,
  persistEmaSet,
  persistVisiblePanels,
  persistVolumeVisible,
} from '../config/chartDefaults';
import {
  STOCK_LIST_ROW_HEIGHT,
  stockListHeaderStripStyle,
  stockListGridTrackStyle,
  stockListRowSelectShadow,
} from '../components/stockTableChrome';
import StockListSplitBody from '../components/StockListSplitBody';
import StockListColumnHeader from '../components/StockListColumnHeader';
import StockListGridCell from '../components/StockListGridCell';
import { useStockListColumnWidths } from '../hooks/useStockListColumnWidths';
import { columnWidthKey } from '../hooks/stockListColumnStorage';
import ExternalFinancialsLinks from '../components/ExternalFinancialsLinks';
import PortfolioEarningsModal from '../components/PortfolioEarningsModal';
import EarningsPlusInlineMark from '../components/EarningsPlusInlineMark';
import { formatMarketCap } from '../utils/formatMarketCap';
import {
  buildDualBeatEarningsMap,
  buildUpcomingEarningsMap,
  EARNINGS_PRIORITY_DEFAULT_DIR,
  formatEarningsBadgeDate,
  PORTFOLIO_EARNINGS_BORDER,
  PORTFOLIO_EARNINGS_ROW_BG,
  PORTFOLIO_EARNINGS_ROW_HEIGHT,
  PORTFOLIO_EARNINGS_ROW_HOVER,
  PORTFOLIO_EARNINGS_LABEL_COLOR,
  PORTFOLIO_EARNINGS_WINDOW_DAYS,
  DUAL_BEAT_ROW_BG,
  DUAL_BEAT_BORDER,
  DUAL_BEAT_ROW_HOVER,
  DUAL_BEAT_LABEL_COLOR,
  resolveEarningsRowHighlight,
  sortItemsByEarningsPriority,
} from '../utils/portfolioEarnings';
import {
  DEFAULT_CHART_LAYOUT,
  DEFAULT_CHART_TIMEFRAME_1,
  DEFAULT_CHART_TIMEFRAME_2,
  DEFAULT_CHART_TIMEFRAME_3,
  normalizeSavedTimeframe3,
} from '../config/chartViewDefaults';
import { CHART_PAGE_IDS, hydrateIndicatorPanels } from '../chartPrefs/chartPageLayout';
import {
  useWebChartLayoutMount,
  useWebChartLayoutAutoSave,
} from '../chartPrefs/useWebChartPageLayout';
import { useIndicatorPanelAutoSave } from '../chartPrefs/useIndicatorPanelAutoSave';
import { usePatchOverlay } from '../intraday/usePatchOverlay';
import { useRegisterFocusedSymbol } from '../intraday/useRegisterFocusedSymbol';
import { useRegisterIntradaySymbols } from '../intraday/useRegisterIntradaySymbols';
import { symbolsForConstituents } from '../intraday/intradayRefreshScopes';
import { isIntradayLiveTimeframe } from '../intraday/patchOverlay';
import { usePageLive } from '../intraday/pageLiveContext';
import { isTypingContext } from '../utils/isTypingTarget';
import { useSyncedPanelHeights, columnCountForChartLayout, multiColumnHeightProps } from '../hooks/useSyncedPanelHeights';

const API = '';

const LAYOUTS = [
  { key: 'single', label: 'Single',              desc: 'One chart panel'              },
  { key: '2h',     label: '2 — Multi Timeframe', desc: 'Same stock, two timeframes'   },
  { key: '3h',     label: '3 — Multi Timeframe', desc: 'Same stock, three timeframes' },
];

/** Grid aligned with Pulse / Portfolio stock table. */
const COLS = [
  { key: 'symbol', widthKey: 'symbol', label: 'Symbol', width: 90 },
  { key: 'market_cap', widthKey: 'market_cap', label: 'Mkt Cap', width: 110 },
  { key: 'last_price', widthKey: 'price', label: 'Price', width: 85 },
  { key: 'change_pct', widthKey: 'change_1d', label: '1D Chg %', width: 80 },
  { key: 'change_30d', widthKey: 'change_1m', label: '1M Chg %', width: 80 },
];

function ChangeCell({ value }) {
  if (value === null || value === undefined) return <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>;
  const n     = parseFloat(value);
  const color = n > 0 ? 'var(--accent-green)' : n < 0 ? 'var(--accent-red)' : 'var(--text-secondary)';
  return (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color, fontWeight: 500 }}>
      {n > 0 ? '+' : ''}{n.toFixed(2)}%
    </span>
  );
}

function CellValue({ col, value }) {
  if (value === null || value === undefined) return <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>;
  if (col === 'market_cap') return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{formatMarketCap(value)}</span>;
  if (col === 'last_price') return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)' }}>₹{Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>;
  if (['change_pct', 'change_30d'].includes(col)) return <ChangeCell value={value} />;
  return <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{value}</span>;
}

export default function ConstituentsPage({ index, onOpenChart, onBack, onContextMenuRequest }) {
  const [stocks, setStocks]           = useState([]);
  const intradayPageId = `constituents-${index?.symbol || 'index'}`;
  const { liveActive, liveTick } = usePageLive(intradayPageId);
  const { overlayGenericRow, refreshTick: patchRefreshTick, getSnapshot } = usePatchOverlay(intradayPageId);
  const liveStocks = useMemo(
    () => stocks.map((s) => overlayGenericRow(s)),
    [stocks, overlayGenericRow, patchRefreshTick],
  );
  const [loading, setLoading]         = useState(true);
  const [sortBy, setSortBy]           = useState('market_cap');
  const [sortDir, setSortDir]         = useState('desc');
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [search, setSearch]           = useState('');
  const [chartSymbol, setChartSymbol] = useState(null);
  const [paneWidth, setPaneWidth]     = useState(640);
  const [earningsBySymbol, setEarningsBySymbol] = useState(() => new Map());
  const [beatBySymbol, setBeatBySymbol] = useState(() => new Map());
  /** Earnings+ qualified symbols (gold E+ beside symbol name). */
  const [plusSymbols, setPlusSymbols] = useState(() => new Set());
  const [earningsModal, setEarningsModal] = useState(null);
  const [earningsPriorityEnabled, setEarningsPriorityEnabled] = useState(true);
  const [earningsPriorityDir, setEarningsPriorityDir] = useState(EARNINGS_PRIORITY_DEFAULT_DIR);
  const [emas, setEmas]               = useState(() => getPersistedEmaSet());
  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());
  const [panelOrder, setPanelOrder]   = useState(['stochrsi', 'macd']);
  const [lastCandleChange, setLastCandleChange] = useState(null);
  const [lastCandlePrice, setLastCandlePrice] = useState(null);
  const [timeframe,  setTimeframe]    = useState(DEFAULT_CHART_TIMEFRAME_1);
  const [timeframe2, setTimeframe2]   = useState(DEFAULT_CHART_TIMEFRAME_2);
  const [timeframe3, setTimeframe3]   = useState(DEFAULT_CHART_TIMEFRAME_3);
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(true));
  const [viewOpen, setViewOpen]       = useState(false);
  const [chartLayout, setChartLayout] = useState(DEFAULT_CHART_LAYOUT);
  const [crosshairTime, setCrosshairTime] = useState(null);
  const viewRef                       = useRef(null);
  const rowRefs                       = useRef({});
  const wrapperRef                    = useRef(null);
  const headerScrollRef               = useRef(null);
  const rowsScrollRef                 = useRef(null);
  const { startResize: startColResize, resizingKey: colResizingKey, gridTemplateColumns } = useStockListColumnWidths(COLS);
  const draggingRef                   = useRef(false);
  const startXRef                     = useRef(0);
  const startWidthRef                 = useRef(0);
  const { getPanelHeights, heightsRef, handleHeightsChange, applyLayoutHeights, heightsRevision } = useSyncedPanelHeights({
    columnCount: columnCountForChartLayout(chartLayout),
  });

  useRegisterFocusedSymbol(intradayPageId, useMemo(
    () => (chartSymbol ? [chartSymbol] : []),
    [chartSymbol, intradayPageId],
  ));
  useRegisterIntradaySymbols(intradayPageId, useMemo(
    () => symbolsForConstituents(stocks, chartSymbol),
    [stocks, chartSymbol, intradayPageId],
  ));

  const { layoutHydrated, indicatorsHydrated } = useWebChartLayoutMount(CHART_PAGE_IDS.constituents, {
    setChartLayout, setTimeframe, setTimeframe2, setTimeframe3, setPaneWidth,
  }, (data, fromPrefs, globalIndicator) => {
    hydrateIndicatorPanels(data, fromPrefs, globalIndicator, { applyLayoutHeights, setPanelOrder });
  });

  useWebChartLayoutAutoSave(CHART_PAGE_IDS.constituents, {
    chartLayout, timeframe, timeframe2, timeframe3, paneWidth,
  }, layoutHydrated, true, indicatorsHydrated);

  const onHeightsChangePersist = useIndicatorPanelAutoSave({
    handleHeightsChange,
    heightsRef,
    panelOrder,
    ready: layoutHydrated && indicatorsHydrated,
  });

  useEffect(() => {
    function handle(e) {
      if (viewRef.current && !viewRef.current.contains(e.target)) setViewOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  const loadConstituents = useCallback(() => {
    if (!index?.symbol) return;
    setLoading(true);
    axios.get(`${API}/api/index-constituents/${encodeURIComponent(index.symbol)}`)
      .then(r => { setStocks(r.data.data || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [index?.symbol]);

  useEffect(() => {
    loadConstituents();
  }, [loadConstituents]);

  useEffect(() => {
    const onRefresh = () => { loadConstituents(); };
    window.addEventListener(APP_DATA_REFRESH_EVENT, onRefresh);
    return () => window.removeEventListener(APP_DATA_REFRESH_EVENT, onRefresh);
  }, [loadConstituents]);

  useEffect(() => {
    setEarningsPriorityEnabled(true);
    setEarningsPriorityDir(EARNINGS_PRIORITY_DEFAULT_DIR);
    setEarningsModal(null);
  }, [index?.symbol]);

  useEffect(() => {
    if (liveStocks.length === 0 || chartSymbol !== null) return;
    const firstSorted = [...liveStocks].sort((a, b) => {
      const av = a[sortBy], bv = b[sortBy];
      if (av == null) return 1; if (bv == null) return -1;
      return sortDir === 'asc'
        ? (typeof av === 'string' ? av.localeCompare(bv) : av - bv)
        : (typeof av === 'string' ? bv.localeCompare(av) : bv - av);
    });
    if (firstSorted.length > 0) { setChartSymbol(firstSorted[0].symbol); setSelectedIdx(0); }
  }, [liveStocks]);

  const constituentSymbolsKey = useMemo(() => (
    liveStocks
      .map((s) => String(s.symbol || '').trim().toUpperCase())
      .filter(Boolean)
      .sort()
      .join(',')
  ), [liveStocks]);

  const constituentSymbols = useMemo(
    () => new Set(constituentSymbolsKey ? constituentSymbolsKey.split(',') : []),
    [constituentSymbolsKey],
  );

  useEffect(() => {
    if (!constituentSymbolsKey) {
      setEarningsBySymbol(new Map());
      setBeatBySymbol(new Map());
      setPlusSymbols(new Set());
      return undefined;
    }
    let cancelled = false;
    const ac = typeof AbortController !== 'undefined' ? new AbortController() : null;
    (async () => {
      const [upcomingSettled, beatSettled, plusSettled] = await Promise.allSettled([
        axios.get(`${API}/api/earnings-beats`, {
          params: { mode: 'upcoming', period: 'rolling_30_days', limit: 2000 },
          signal: ac?.signal,
        }),
        axios.get(`${API}/api/earnings-beats`, {
          params: {
            mode: 'reported',
            report_window: 'rolling_10_days',
            limit: 2000,
            symbols: constituentSymbolsKey,
          },
          signal: ac?.signal,
        }),
        axios.get(`${API}/api/earnings-plus-flags`, {
          params: { symbols: constituentSymbolsKey },
          signal: ac?.signal,
        }),
      ]);
      if (cancelled) return;
      if (upcomingSettled.status === 'fulfilled') {
        setEarningsBySymbol(
          buildUpcomingEarningsMap(
            upcomingSettled.value.data?.rows || [],
            constituentSymbols,
            PORTFOLIO_EARNINGS_WINDOW_DAYS,
          ),
        );
      } else {
        setEarningsBySymbol(new Map());
      }
      if (beatSettled.status === 'fulfilled') {
        setBeatBySymbol(
          buildDualBeatEarningsMap(beatSettled.value.data?.rows || [], constituentSymbols),
        );
      } else {
        setBeatBySymbol(new Map());
      }
      if (plusSettled.status === 'fulfilled') {
        setPlusSymbols(new Set(plusSettled.value.data?.qualified || []));
      } else {
        setPlusSymbols(new Set());
      }
    })();
    return () => {
      cancelled = true;
      try { ac?.abort(); } catch (_) {}
    };
  }, [constituentSymbolsKey, constituentSymbols]);

  const baseSorted = useMemo(() => [...liveStocks]
    .filter(s => !search || s.symbol.includes(search.toUpperCase()) || (s.company_name||'').toUpperCase().includes(search.toUpperCase()))
    .sort((a, b) => {
      const av = a[sortBy], bv = b[sortBy];
      if (av == null) return 1; if (bv == null) return -1;
      return sortDir === 'asc'
        ? (typeof av === 'string' ? av.localeCompare(bv) : av - bv)
        : (typeof av === 'string' ? bv.localeCompare(av) : bv - av);
    }), [liveStocks, search, sortBy, sortDir]);

  const sorted = useMemo(() => {
    if (!earningsPriorityEnabled) return baseSorted;
    return sortItemsByEarningsPriority(baseSorted, {
      getSymbol: s => s.symbol,
      beatBySymbol,
      upcomingBySymbol: earningsBySymbol,
      dir: earningsPriorityDir,
    });
  }, [baseSorted, earningsPriorityEnabled, beatBySymbol, earningsBySymbol, earningsPriorityDir]);

  const earningsCount = useMemo(() => {
    let n = 0;
    for (const sym of earningsBySymbol.keys()) {
      const highlight = resolveEarningsRowHighlight(
        beatBySymbol.get(sym),
        earningsBySymbol.get(sym),
      );
      if (highlight.kind === 'upcoming') n += 1;
    }
    return n;
  }, [earningsBySymbol, beatBySymbol]);

  useEffect(() => {
    function handleKey(e) {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      if (isTypingContext(e)) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIdx(prev => {
          const next = Math.min(prev + 1, sorted.length - 1);
          rowRefs.current[next]?.scrollIntoView({ block: 'nearest' });
          setChartSymbol(sorted[next]?.symbol || null);
          setCrosshairTime(null);
          return next;
        });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIdx(prev => {
          const next = Math.max(prev - 1, 0);
          rowRefs.current[next]?.scrollIntoView({ block: 'nearest' });
          setChartSymbol(sorted[next]?.symbol || null);
          setCrosshairTime(null);
          return next;
        });
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [sorted]);

  useEffect(() => {
    setSelectedIdx(0);
  }, [sortBy, sortDir, search, earningsPriorityEnabled, earningsPriorityDir]);

  useEffect(() => {
    persistEmaSet(emas);
  }, [emas]);

  useEffect(() => {
    persistVolumeVisible(volumeVisible);
  }, [volumeVisible]);

  useEffect(() => {
    persistVisiblePanels(visiblePanels);
  }, [visiblePanels]);

  useEffect(() => {
    function onEmaPrefs(e) {
      if (!e?.detail) return;
      setEmas(prev => (JSON.stringify(prev) === JSON.stringify(e.detail) ? prev : e.detail));
    }
    function onVolumePrefs(e) {
      if (typeof e?.detail !== 'boolean') return;
      setVolumeVisible(prev => (prev === e.detail ? prev : e.detail));
    }
    function onPanelsPrefs(e) {
      if (!e?.detail) return;
      setVisiblePanels(prev => (JSON.stringify(prev) === JSON.stringify(e.detail) ? prev : e.detail));
    }
    function onStorage(e) {
      if (e.key === 'cim.chart.ema') setEmas(getPersistedEmaSet());
      if (e.key === 'cim.chart.volumeVisible') setVolumeVisible(getPersistedVolumeVisible(true));
      if (e.key === PANELS_PREFS_KEY) setVisiblePanels(getPersistedVisiblePanels());
    }
    window.addEventListener(EMA_PREFS_UPDATED_EVENT, onEmaPrefs);
    window.addEventListener(VOLUME_PREFS_UPDATED_EVENT, onVolumePrefs);
    window.addEventListener(PANELS_PREFS_UPDATED_EVENT, onPanelsPrefs);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(EMA_PREFS_UPDATED_EVENT, onEmaPrefs);
      window.removeEventListener(VOLUME_PREFS_UPDATED_EVENT, onVolumePrefs);
      window.removeEventListener(PANELS_PREFS_UPDATED_EVENT, onPanelsPrefs);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  function handleSort(col) {
    setEarningsPriorityEnabled(false);
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortBy(col); setSortDir(col === 'symbol' ? 'asc' : 'desc'); }
  }

  function handleEarningsPriorityControlClick() {
    if (!earningsPriorityEnabled) {
      setEarningsPriorityEnabled(true);
      return;
    }
    setEarningsPriorityDir(d => (d === 'asc' ? 'desc' : 'asc'));
  }

  function openEarningsModalFromSymbol(stock) {
    const sym = String(stock?.symbol || '').trim().toUpperCase();
    if (!sym) return;
    const highlight = resolveEarningsRowHighlight(
      beatBySymbol.get(sym),
      earningsBySymbol.get(sym),
    );
    if (!highlight.info) return;
    if (highlight.kind === 'beat') {
      setEarningsModal({
        symbol: sym,
        variant: 'beat',
        earningsDate: highlight.info.earnings_release_date,
        daysSinceReport: highlight.info.days_since_report,
      });
      return;
    }
    setEarningsModal({
      symbol: sym,
      variant: 'upcoming',
      earningsDate: highlight.info.earnings_release_next_date,
      daysUntil: highlight.info.days_until,
    });
  }

  useEffect(() => {
    const el = rowsScrollRef.current;
    if (!el) return undefined;
    const onScroll = () => {
      if (headerScrollRef.current && headerScrollRef.current.scrollLeft !== el.scrollLeft) {
        headerScrollRef.current.scrollLeft = el.scrollLeft;
      }
    };
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, [sorted.length]);

  useLayoutEffect(() => {
    const headerEl = headerScrollRef.current;
    const rowsEl = rowsScrollRef.current;
    if (!headerEl || !rowsEl) return;
    headerEl.scrollLeft = rowsEl.scrollLeft;
  }, [sorted.length, paneWidth, gridTemplateColumns]);

  function handleRowClick(stock, idx) {
    setSelectedIdx(idx);
    setChartSymbol(stock.symbol);
    setLastCandleChange(null);
    setLastCandlePrice(null);
    setCrosshairTime(null);
  }

  function onDividerMouseDown(e) {
    e.preventDefault();
    draggingRef.current = true; startXRef.current = e.clientX; startWidthRef.current = paneWidth;
    function onMouseMove(ev) {
      if (!draggingRef.current) return;
      const total = wrapperRef.current?.clientWidth || 1200;
      setPaneWidth(Math.max(300, Math.min(total - 400, startWidthRef.current + ev.clientX - startXRef.current)));
    }
    function onMouseUp() { draggingRef.current = false; window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp); }
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  function handleTogglePanel(key) { setVisiblePanels(p => ({ ...p, [key]: !p[key] })); }
  function handleMovePanel(key, dir) {
    setPanelOrder(prev => {
      const idx = prev.indexOf(key); if (idx === -1) return prev;
      const si = dir === 'up' ? idx - 1 : idx + 1;
      if (si < 0 || si >= prev.length) return prev;
      const next = [...prev]; [next[idx], next[si]] = [next[si], next[idx]]; return next;
    });
  }

  const selectedStock = sorted[selectedIdx] || null;
  const focusSnap = chartSymbol ? getSnapshot(chartSymbol) : null;
  const headerPrice = (() => {
    const fromSnap = focusSnap?.price;
    if (fromSnap != null && Number.isFinite(Number(fromSnap))) return Number(fromSnap);
    if (lastCandlePrice != null && Number.isFinite(Number(lastCandlePrice))) return Number(lastCandlePrice);
    const rowPx = selectedStock?.last_price ?? selectedStock?.price;
    return rowPx != null && Number.isFinite(Number(rowPx)) ? Number(rowPx) : null;
  })();
  const headerChange = (() => {
    const fromSnap = focusSnap?.change_pct;
    if (fromSnap != null && Number.isFinite(Number(fromSnap))) return Number(fromSnap);
    return lastCandleChange;
  })();

  // Render a single chart panel — all panels share crosshairTime
  function renderPanel(symbol, tf, setTf, onLastChange, cacheKey, hasBorderRight, columnIndex) {
    if (!symbol) return null;
    const tfLive = liveActive && isIntradayLiveTimeframe(tf);
    return (
      <div key={cacheKey} style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', minWidth:0, borderRight: hasBorderRight ? '2px solid var(--border)' : 'none' }}>
        <ChartHeaderBar
          symbol={symbol}
          timeframe={tf}
          onTimeframeChange={newTf => { setTf(newTf); onLastChange(null); setCrosshairTime(null); }}
        />
        <ChartContainer
          key={cacheKey}
          symbol={symbol}
          timeframe={tf}
          emas={emas}
          volumeVisible={volumeVisible}
          visiblePanels={visiblePanels}
          panelOrder={panelOrder}
          onTogglePanel={handleTogglePanel}
          onMovePanel={handleMovePanel}
          onLastChange={onLastChange}
          onHeightsChange={h => onHeightsChangePersist(h, columnIndex)}
          {...multiColumnHeightProps({ chartLayout, columnIndex, getPanelHeights, heightsRevision })}
          onCrosshairMove={setCrosshairTime}
          crosshairTime={crosshairTime}
          liveToday={tfLive}
          liveRefreshKey={tfLive ? liveTick : null}
          drawingScopeId={`constituents:${cacheKey}`}
          drawingAutoFocus={false}
        />
      </div>
    );
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', width:'100%', backgroundColor:'var(--bg-primary)', overflow:'hidden', fontSize: 12 }}>

      {/* ── Header ── */}
      <div className="chart-app-toolbar" style={{ height:52, backgroundColor:'var(--bg-secondary)', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', padding:'0 16px', gap:10, flexShrink:0, overflowX:'auto', fontSize: 12 }}>

        <button onClick={onBack}
          style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, color:'var(--text-secondary)', fontSize:12, flexShrink:0 }}
          onMouseEnter={e => e.currentTarget.style.borderColor='var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.borderColor='var(--border)'}
        >← {index.name}</button>

        <div style={{ width:1, height:20, backgroundColor:'var(--border)' }} />
        <span style={{ fontSize:14, fontWeight:600, color:'var(--text-primary)', flexShrink:0 }}>Constituents</span>
        <span style={{ fontSize:12, color:'var(--text-muted)', flexShrink:0 }}>{stocks.length} stocks</span>

        {selectedStock && (
          <>
            <div style={{ width:1, height:20, backgroundColor:'var(--border)' }} />
            <span style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:14, color:'var(--accent-blue)', flexShrink:0 }}>{selectedStock.symbol}</span>
            {headerPrice != null && (
              <span style={{ fontFamily:'var(--font-mono)', fontSize:13, color:'var(--text-primary)', flexShrink:0 }}>
                ₹{headerPrice.toLocaleString('en-IN', { minimumFractionDigits:2 })}
              </span>
            )}
            {headerChange !== null && Number.isFinite(headerChange) && (
              <span style={{ fontFamily:'var(--font-mono)', fontSize:11, fontWeight:600, color: headerChange>=0?'var(--accent-green)':'var(--accent-red)', backgroundColor: headerChange>=0?'rgba(63,185,80,0.12)':'rgba(248,81,73,0.12)', border:`1px solid ${headerChange>=0?'#3fb95044':'#f8514944'}`, borderRadius:4, padding:'1px 6px', flexShrink:0 }}>
                {headerChange>=0?'+':''}{headerChange.toFixed(2)}%
              </span>
            )}
          </>
        )}

        <div style={{ width:1, height:20, backgroundColor:'var(--border)', flexShrink:0 }} />

        {/* Volume */}
        <div onClick={() => setVolumeVisible(v=>!v)}
          style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:`1px solid ${volumeVisible?'#388bfd55':'var(--border)'}`, borderRadius:4, padding:'0 8px', height:26, opacity: volumeVisible?1:0.5, cursor:'pointer', flexShrink:0 }}>
          <div style={{ width:8, height:8, backgroundColor:'#388bfd', borderRadius:2 }} />
          <span style={{ fontSize:11, color:'var(--text-secondary)', fontWeight:500 }}>Vol</span>
        </div>

        <EMAControls emas={emas} onChange={setEmas} />
        {chartSymbol && <ExternalFinancialsLinks symbol={chartSymbol} />}

        <div style={{ flex:1 }} />

        <BasketToolbarButton />

        {/* View dropdown */}
        <div ref={viewRef} style={{ position:'relative', flexShrink:0 }}>
          <button onClick={() => setViewOpen(o=>!o)}
            style={{ display:'flex', alignItems:'center', gap:5, backgroundColor: chartLayout!=='single'?'rgba(56,139,253,0.15)':'var(--bg-tertiary)', border:`1px solid ${chartLayout!=='single'?'var(--accent-blue)':'var(--border)'}`, borderRadius:5, padding:'0 10px', height:28, color: chartLayout!=='single'?'var(--accent-blue)':'var(--text-secondary)', fontSize:12, cursor:'pointer' }}>
            View <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity:0.6 }}><path d="M0 0l4 5 4-5z"/></svg>
          </button>
          {viewOpen && (
            <div style={{ position:'fixed', zIndex:9999, right:120, backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6, boxShadow:'0 8px 24px rgba(0,0,0,0.6)', minWidth:230, overflow:'hidden' }}>
              <div style={{ padding:'6px 0' }}>
                <div style={{ fontSize:10, fontWeight:700, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.06em', padding:'4px 14px 6px' }}>Layout</div>
                {LAYOUTS.map(l => (
                  <div key={l.key} onClick={() => { setChartLayout(l.key); setViewOpen(false); }}
                    style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'8px 14px', cursor:'pointer', backgroundColor: chartLayout===l.key?'rgba(56,139,253,0.10)':'transparent', color: chartLayout===l.key?'var(--accent-blue)':'var(--text-secondary)', fontSize:13 }}
                    onMouseEnter={e => { if (chartLayout!==l.key) e.currentTarget.style.backgroundColor='var(--bg-hover)'; }}
                    onMouseLeave={e => { if (chartLayout!==l.key) e.currentTarget.style.backgroundColor='transparent'; }}
                  >
                    <div>
                      <div style={{ fontWeight: chartLayout===l.key?600:400 }}>{l.label}</div>
                      <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:1 }}>{l.desc}</div>
                    </div>
                    {chartLayout===l.key && <span style={{ fontSize:11 }}>✓</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {chartSymbol && (
          <button onClick={() => onOpenChart(chartSymbol)}
            style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--accent-blue)', border:'none', borderRadius:5, padding:'0 12px', height:28, color:'#fff', fontSize:12, fontWeight:600, cursor:'pointer', flexShrink:0 }}
            onMouseEnter={e => e.currentTarget.style.opacity='0.85'}
            onMouseLeave={e => e.currentTarget.style.opacity='1'}
          >Open Full Chart ↗</button>
        )}

        {/* Search */}
        <div style={{ display:'flex', alignItems:'center', gap:6, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, width:160, flexShrink:0 }}>
          <svg width="11" height="11" viewBox="0 0 16 16" fill="var(--text-muted)"><path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z"/></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter..." style={{ background:'transparent', color:'var(--text-primary)', flex:1, fontSize:12 }} />
          {search && <button onClick={() => setSearch('')} style={{ background:'none', color:'var(--text-muted)', fontSize:14 }}>×</button>}
        </div>
      </div>

      {/* ── Body ── */}
      <StockListSplitBody
        splitRef={wrapperRef}
        footer={(
          <>
            {sorted.length} stocks
            <button
              type="button"
              onClick={handleEarningsPriorityControlClick}
              aria-pressed={earningsPriorityEnabled}
              aria-label={`Earnings priority sort ${earningsPriorityEnabled ? 'enabled' : 'disabled'}, ${earningsPriorityDir === 'asc' ? 'nearest dates first' : 'furthest dates first'}`}
              title={earningsPriorityEnabled
                ? 'Toggle earnings-priority date direction'
                : 'Re-enable earnings-priority sorting'}
              style={{
                marginLeft: 8,
                padding: 0,
                border: 'none',
                background: 'none',
                color: earningsPriorityEnabled ? 'var(--accent-blue)' : 'var(--text-secondary)',
                cursor: 'pointer',
                font: 'inherit',
              }}
            >
              · Earnings priority {earningsPriorityDir === 'asc' ? '▲' : '▼'}
            </button>
            {earningsCount > 0 && (
              <span style={{ marginLeft: 8, color: PORTFOLIO_EARNINGS_LABEL_COLOR }}>
                · {earningsCount} reporting in {PORTFOLIO_EARNINGS_WINDOW_DAYS} days
              </span>
            )}
          </>
        )}
      >
        {/* Table */}
        <div style={{ width:paneWidth, minWidth:300, flexShrink:0, display:'flex', flexDirection:'column', overflow:'hidden' }}>
          <div ref={headerScrollRef} style={{ ...stockListHeaderStripStyle, overflowX: 'hidden', overflowY: 'hidden' }}>
            <div style={stockListGridTrackStyle(gridTemplateColumns)}>
            {COLS.map((col, colIdx) => {
              const sortable = true;
              const activeSort = sortable && sortBy === col.key;
              const wk = columnWidthKey(col);
              return (
                <StockListColumnHeader
                  key={col.key}
                  colKey={col.key}
                  isLast={colIdx === COLS.length - 1}
                  widthKey={wk}
                  resizingKey={colResizingKey}
                  onResizeStart={(e) => startColResize(col, e)}
                  sortable={sortable}
                  onClick={sortable ? () => handleSort(col.key) : undefined}
                >
                  <span style={{ color: activeSort ? 'var(--accent-blue)' : 'var(--text-secondary)' }}>
                    {col.label}
                    {activeSort && <span style={{ marginLeft: 3, fontSize: 9 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>}
                  </span>
                </StockListColumnHeader>
              );
            })}
            </div>
          </div>
          <div ref={rowsScrollRef} style={{ flex: 1, overflowY: 'auto', overflowX: 'auto' }}>
            {loading ? (
              <div style={{ padding:16, color:'var(--text-muted)', fontSize:12 }}>Loading...</div>
            ) : sorted.map((stock, idx) => {
              const isSelected = idx === selectedIdx;
              const symKey = String(stock.symbol || '').trim().toUpperCase();
              const rowHighlight = resolveEarningsRowHighlight(
                beatBySymbol.get(symKey),
                earningsBySymbol.get(symKey),
              );
              const beatInfo = rowHighlight.kind === 'beat' ? rowHighlight.info : null;
              const upcomingInfo = rowHighlight.kind === 'upcoming' ? rowHighlight.info : null;
              const earningsHighlight = beatInfo || upcomingInfo;
              const isBeatHighlight = !!beatInfo;
              const hasPlusBadge = plusSymbols.has(String(stock.symbol || '').trim().toUpperCase());
              const rowBg = isSelected
                ? 'rgba(56,139,253,0.08)'
                : isBeatHighlight
                  ? DUAL_BEAT_ROW_BG
                  : upcomingInfo
                    ? PORTFOLIO_EARNINGS_ROW_BG
                    : 'transparent';
              const rowBorderLeft = isSelected
                ? '2px solid var(--accent-blue)'
                : isBeatHighlight
                  ? `2px solid ${DUAL_BEAT_BORDER}`
                  : upcomingInfo
                    ? `2px solid ${PORTFOLIO_EARNINGS_BORDER}`
                    : '2px solid transparent';
              return (
                <div key={stock.symbol} ref={el => rowRefs.current[idx]=el}
                  onClick={() => handleRowClick(stock, idx)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    if (onContextMenuRequest) onContextMenuRequest({ x: e.clientX, y: e.clientY, symbol: stock.symbol, type: 'stock', sourcePage: 'constituents' });
                  }}
                  style={{
                    ...stockListGridTrackStyle(gridTemplateColumns),
                    height: earningsHighlight ? PORTFOLIO_EARNINGS_ROW_HEIGHT : STOCK_LIST_ROW_HEIGHT,
                    borderBottom:'1px solid var(--border-light)',
                    cursor:'pointer',
                    backgroundColor: rowBg,
                    ...stockListRowSelectShadow(rowBorderLeft),
                  }}
                  onMouseEnter={e => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = isBeatHighlight
                        ? DUAL_BEAT_ROW_HOVER
                        : upcomingInfo
                          ? PORTFOLIO_EARNINGS_ROW_HOVER
                          : 'var(--bg-hover)';
                    }
                  }}
                  onMouseLeave={e => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = isBeatHighlight
                        ? DUAL_BEAT_ROW_BG
                        : upcomingInfo
                          ? PORTFOLIO_EARNINGS_ROW_BG
                          : 'transparent';
                    }
                  }}
                >
                  {COLS.map((col, colIdx) => (
                    <StockListGridCell key={col.key} colKey={col.key} isLast={colIdx === COLS.length - 1}>
                      {col.key === 'symbol' ? (
                        <div
                          style={{
                            minWidth: 0,
                            flex: 1,
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'center',
                            gap: earningsHighlight ? 1 : 0,
                            cursor: earningsHighlight ? 'pointer' : undefined,
                          }}
                          onClick={earningsHighlight ? (e) => {
                            e.stopPropagation();
                            handleRowClick(stock, idx);
                            openEarningsModalFromSymbol(stock);
                          } : undefined}
                          title={earningsHighlight ? 'Click for quarterly results and company profile' : stock.symbol}
                        >
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
                            <span style={{
                              fontFamily: 'var(--font-mono)',
                              fontWeight: 600,
                              fontSize: 11,
                              color: stock.change_pct > 0 ? 'var(--accent-green)' : stock.change_pct < 0 ? 'var(--accent-red)' : 'var(--text-primary)',
                              whiteSpace: 'nowrap',
                              textOverflow: 'ellipsis',
                              overflow: 'hidden',
                              lineHeight: 1.2,
                            }}>
                              {stock.symbol}
                            </span>
                            {hasPlusBadge ? <EarningsPlusInlineMark /> : null}
                          </span>
                          {isBeatHighlight ? (
                            <span style={{
                              fontSize: 9,
                              fontWeight: 600,
                              fontFamily: 'var(--font-mono)',
                              color: DUAL_BEAT_LABEL_COLOR,
                              lineHeight: 1.15,
                              whiteSpace: 'nowrap',
                            }}>
                              Beat EPS+Rev
                            </span>
                          ) : upcomingInfo ? (
                            <span style={{
                              fontSize: 9,
                              fontWeight: 600,
                              fontFamily: 'var(--font-mono)',
                              color: PORTFOLIO_EARNINGS_LABEL_COLOR,
                              lineHeight: 1.15,
                              whiteSpace: 'nowrap',
                            }}>
                              E {formatEarningsBadgeDate(upcomingInfo.earnings_release_next_date)}
                            </span>
                          ) : null}
                        </div>
                      ) : (
                        <CellValue col={col.key} value={stock[col.key]} />
                      )}
                    </StockListGridCell>
                  ))}
                </div>
              );
            })}
          </div>
        </div>

        {/* Resize divider */}
        <div onMouseDown={onDividerMouseDown}
          style={{ width:4, backgroundColor:'var(--border)', cursor:'col-resize', flexShrink:0, transition:'background 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.backgroundColor='var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.backgroundColor='var(--border)'}
        />

        {/* Chart panels */}
        <DrawingWorkspaceProvider workspaceId={`constituents-${index?.symbol || 'idx'}`}>
        <div style={{ flex:1, display:'flex', overflow:'hidden', minWidth:400, position:'relative' }}>
          <DrawingToolbarConnected />
          <DrawingFloatPaletteConnected />
          {!chartSymbol ? (
            <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column', gap:8, color:'var(--text-muted)', fontSize:13 }}>
              <div style={{ fontSize:24, opacity:0.3 }}>📈</div>
              <div>Click a stock to view its chart</div>
              <div style={{ fontSize:11 }}>Use ↑↓ arrow keys to navigate</div>
            </div>
          ) : (
            <>
              {renderPanel(chartSymbol, timeframe,  tf => { setTimeframe(tf); setLastCandleChange(null); setLastCandlePrice(null); }, (pct, price) => { setLastCandleChange(pct); setLastCandlePrice(price ?? null); }, chartSymbol+'-p1-'+timeframe,  chartLayout!=='single', 0)}
              {(chartLayout==='2h'||chartLayout==='3h') && renderPanel(chartSymbol, timeframe2, tf => setTimeframe2(tf), ()=>{}, chartSymbol+'-p2-'+timeframe2, chartLayout==='3h', 1)}
              {chartLayout==='3h' && renderPanel(chartSymbol, timeframe3, tf => setTimeframe3(tf), ()=>{}, chartSymbol+'-p3-'+timeframe3, false, 2)}
            </>
          )}
        </div>
        </DrawingWorkspaceProvider>
      </StockListSplitBody>

      {earningsModal && (
        <PortfolioEarningsModal
          symbol={earningsModal.symbol}
          variant={earningsModal.variant}
          earningsDate={earningsModal.earningsDate}
          daysUntil={earningsModal.daysUntil}
          daysSinceReport={earningsModal.daysSinceReport}
          onClose={() => setEarningsModal(null)}
          onOpenChart={onOpenChart}
        />
      )}
    </div>
  );
}