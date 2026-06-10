/* eslint-disable react-hooks/exhaustive-deps */
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { applySavedOrder, reorderByGap, insertionGapFromRowHover, wlItemKey } from '../utils/listOrder';
import { setListDragImage, DropInsetLine } from '../utils/listDnD';
import {
  STOCK_LIST_HEADER_HEIGHT,
  STOCK_LIST_ROW_HEIGHT,
  stockListHeaderStripStyle,
  stockListFooterStripStyle,
} from '../components/stockTableChrome';
import InstrumentNotesIcon from '../components/InstrumentNotesIcon';
import ExternalFinancialsLinks from '../components/ExternalFinancialsLinks';
import ChartContainer from '../components/chart/ChartContainer';
import IndexChartContainer from '../components/chart/IndexChartContainer';
import { DrawingMirrorProvider } from '../components/chart/drawing/DrawingMirrorContext';
import { DrawingWorkspaceProvider } from '../components/chart/drawing/DrawingWorkspaceContext';
import { DrawingToolbarConnected, DrawingFloatPaletteConnected } from '../components/chart/drawing/DrawingToolbar';
import DrawingToolsDesignControl from '../components/chart/drawing/DrawingToolsDesignControl';
import EMAControls from '../components/chart/EMAControls';
import ChartHeaderBar from '../components/chart/ChartHeaderBar';
import {
  DEFAULT_CHART_LAYOUT,
  DEFAULT_CHART_TIMEFRAME_1,
  DEFAULT_CHART_TIMEFRAME_2,
  DEFAULT_CHART_TIMEFRAME_3,
  normalizeSavedTimeframe3,
} from '../config/chartViewDefaults';
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
import { formatMarketCap } from '../utils/formatMarketCap';
import { CHART_DATA_UPDATED_EVENT } from '../chartEvents';
import PortfolioEarningsModal from '../components/PortfolioEarningsModal';
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
  WATCHLIST_EARNINGS_WINDOW_DAYS,
  DUAL_BEAT_WINDOW_DAYS,
  DUAL_BEAT_ROW_BG,
  DUAL_BEAT_BORDER,
  DUAL_BEAT_ROW_HOVER,
  DUAL_BEAT_LABEL_COLOR,
  resolveEarningsRowHighlight,
  sortItemsByEarningsPriority,
} from '../utils/portfolioEarnings';

const API = '';

const LAYOUTS = [
  { key: 'single', label: 'Single', desc: 'One chart panel' },
  { key: '2h', label: '2 - Multi Timeframe', desc: 'Two side-by-side panels' },
  { key: '3h', label: '3 - Multi Timeframe', desc: 'Three side-by-side panels' },
];
const INDICATOR_OPTIONS = [
  { key: 'stochrsi', label: 'StochRSI' },
  { key: 'macd', label: 'MACD' },
];
/** Same column widths & labels as Pulse / Portfolio (`DashboardPage` COLS) + remove column. */
const WL_COLS = [
  { key: 'symbol', label: 'Symbol', width: 90, sortKey: 'symbol' },
  { key: 'mcap', label: 'Mkt Cap', width: 110, sortKey: 'mcap' },
  { key: 'note', label: '', width: 36, sortKey: null },
  { key: 'price', label: 'Price', width: 85, sortKey: 'price' },
  { key: 'd1', label: '1D Chg %', width: 80, sortKey: 'd1' },
  { key: 'm1', label: '1M Chg %', width: 80, sortKey: 'm1' },
  { key: 'act', label: '', width: 34, sortKey: null },
];

function wlRowMetrics(it, stocksMap, indicesMap) {
  const data = it.type === 'index' ? indicesMap[it.symbol] : stocksMap[it.symbol];
  return {
    mcap: it.type === 'index' ? null : data?.['Market Cap'],
    price: it.type === 'index' ? data?.last_price : data?.Price,
    d1: it.type === 'index' ? data?.change_pct : data?.['Change %'],
    m1: it.type === 'index' ? data?.change_30d : data?.['Monthly Change %'],
  };
}

function valForWlSort(it, sortKey, stocksMap, indicesMap) {
  if (sortKey === 'symbol') return String(it.symbol || '').toUpperCase();
  const m = wlRowMetrics(it, stocksMap, indicesMap);
  if (sortKey === 'mcap') return m.mcap != null && m.mcap !== '' ? Number(m.mcap) : null;
  if (sortKey === 'price') return m.price != null ? Number(m.price) : null;
  if (sortKey === 'd1') return m.d1 != null ? Number(m.d1) : null;
  if (sortKey === 'm1') return m.m1 != null ? Number(m.m1) : null;
  return null;
}

function sortWatchlistItems(items, sortKey, sortDir, stocksMap, indicesMap) {
  const decorated = items.map((it, index) => ({
    it,
    index,
    v: valForWlSort(it, sortKey, stocksMap, indicesMap),
  }));
  decorated.sort((a, b) => {
    const as = a.v;
    const bs = b.v;
    if (as == null && bs == null) return a.index - b.index;
    if (as == null) return 1;
    if (bs == null) return -1;
    let cmp;
    if (typeof as === 'string' && typeof bs === 'string') cmp = as.localeCompare(bs);
    else cmp = Number(as) - Number(bs);
    if (cmp !== 0) return sortDir === 'asc' ? cmp : -cmp;
    return a.index - b.index;
  });
  return decorated.map(d => d.it);
}

export default function WatchlistPage({
  onOpenChart,
  onOpenConstituents,
  watchlists,
  onWatchlistsChange,
  appActiveWatchlistName,
  onAppActiveWatchlistNameChange,
  appSelectedItem,
  onAppSelectedItemChange,
  onContextMenuRequest,
}) {
  const [stocksMap, setStocksMap] = useState({});
  const [indicesMap, setIndicesMap] = useState({});
  const [search, setSearch] = useState('');
  const [searchActiveIndex, setSearchActiveIndex] = useState(0);
  const [newWatchlistName, setNewWatchlistName] = useState('');
  const [renamingWatchlistName, setRenamingWatchlistName] = useState(null);
  const [renameName, setRenameName] = useState('');
  const [timeframe, setTimeframe] = useState(DEFAULT_CHART_TIMEFRAME_1);
  const [emas, setEmas] = useState(() => getPersistedEmaSet());
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(true));
  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());
  const [panelOrder, setPanelOrder] = useState(['stochrsi', 'macd']);
  const [timeframe2, setTimeframe2] = useState(DEFAULT_CHART_TIMEFRAME_2);
  const [timeframe3, setTimeframe3] = useState(DEFAULT_CHART_TIMEFRAME_3);
  const [chartLayout, setChartLayout] = useState(DEFAULT_CHART_LAYOUT);
  const [viewOpen, setViewOpen] = useState(false);
  const [indOpen, setIndOpen] = useState(false);
  const [crosshairTime, setCrosshairTime] = useState(null);
  const [lastChange, setLastChange] = useState(null);
  const [lastPrice, setLastPrice] = useState(null);
  const [paneWidth, setPaneWidth] = useState(420);
  const [panelHeights, setPanelHeights] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('watchlist.panelHeights') || '{"stochrsi":130,"macd":130}');
    } catch {
      return { stochrsi: 130, macd: 130 };
    }
  });
  const draggingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  const paneRef = useRef(null);
  const wrapperRef = useRef(null);
  const viewRef = useRef(null);
  const indRef = useRef(null);
  const headerScrollRef = useRef(null);
  const rowsScrollRef = useRef(null);
  const watchlistReorderRef = useRef(null);
  const watchlistImportRef = useRef(null);
  const searchWrapRef = useRef(null);
  const searchInputRef = useRef(null);
  const currentHeightsRef = useRef({});
  const [searchDropdownRect, setSearchDropdownRect] = useState(null);
  const [viewDropdownRect, setViewDropdownRect] = useState(null);
  const [indDropdownRect, setIndDropdownRect] = useState(null);
  const [watchlistSortMode, setWatchlistSortMode] = useState('manual'); // manual | az | za
  const [watchlistReorderOpen, setWatchlistReorderOpen] = useState(false);
  const [watchlistReorderRect, setWatchlistReorderRect] = useState(null);

  /** Keyed by watchlist name → ordered item keys (`type:SYMBOL`). Persisted in layout. */
  const [watchlistItemOrder, setWatchlistItemOrder] = useState({});
  const [watchlistDraggingIdx, setWatchlistDraggingIdx] = useState(null);
  const [watchlistDropGap, setWatchlistDropGap] = useState(null);
  const watchlistDragIdxRef = useRef(null);
  const watchlistDropGapRef = useRef(null);
  const wlDragIdxRef = useRef(null);
  const wlDropGapRef = useRef(null);
  const [wlDropGap, setWlDropGap] = useState(null);
  const [wlDraggingIdx, setWlDraggingIdx] = useState(null);
  const wlRowRefs = useRef({});

  /** Align with Pulse default: Market Cap descending. Dragging rows switches to custom order until a column header is clicked. */
  const [wlSortKey, setWlSortKey] = useState('mcap');
  const [wlSortDir, setWlSortDir] = useState('desc');
  /** 'sort' = column sort active (header highlight); 'manual' = saved drag order only (no highlight). */
  const [wlOrderMode, setWlOrderMode] = useState('sort');
  /** Upcoming earnings within rolling window (watchlist stocks only). */
  const [wlEarningsBySymbol, setWlEarningsBySymbol] = useState(() => new Map());
  const [wlBeatBySymbol, setWlBeatBySymbol] = useState(() => new Map());
  const [wlEarningsModal, setWlEarningsModal] = useState(null);
  const [wlEarningsPriorityEnabled, setWlEarningsPriorityEnabled] = useState(true);
  const [wlEarningsPriorityDir, setWlEarningsPriorityDir] = useState(EARNINGS_PRIORITY_DEFAULT_DIR);

  const activeWatchlist = useMemo(
    () => watchlists.find(w => w.name === appActiveWatchlistName) || watchlists[0] || null,
    [watchlists, appActiveWatchlistName]
  );
  const displayWatchlists = useMemo(() => {
    const arr = [...watchlists];
    if (watchlistSortMode === 'az') {
      arr.sort((a, b) => String(a?.name || '').localeCompare(String(b?.name || '')));
    } else if (watchlistSortMode === 'za') {
      arr.sort((a, b) => String(b?.name || '').localeCompare(String(a?.name || '')));
    }
    return arr;
  }, [watchlists, watchlistSortMode]);
  const watchlistNames = useMemo(() => watchlists.map(w => w.name), [watchlists]);
  const orderedWatchlistItems = useMemo(() => {
    const items = activeWatchlist?.items || [];
    const name = activeWatchlist?.name;
    if (!name) return items;
    const saved = watchlistItemOrder[name];
    return applySavedOrder(items, saved, wlItemKey);
  }, [activeWatchlist, watchlistItemOrder]);

  useEffect(() => {
    setWlOrderMode('sort');
    setWlSortKey('mcap');
    setWlSortDir('desc');
    setWlEarningsPriorityEnabled(true);
    setWlEarningsPriorityDir(EARNINGS_PRIORITY_DEFAULT_DIR);
  }, [activeWatchlist?.name]);

  const baseDisplayWlItems = useMemo(() => {
    if (wlOrderMode === 'manual') return orderedWatchlistItems;
    return sortWatchlistItems(orderedWatchlistItems, wlSortKey, wlSortDir, stocksMap, indicesMap);
  }, [orderedWatchlistItems, wlOrderMode, wlSortKey, wlSortDir, stocksMap, indicesMap]);
  const displayWlItems = useMemo(() => {
    if (!wlEarningsPriorityEnabled) return baseDisplayWlItems;
    return sortItemsByEarningsPriority(baseDisplayWlItems, {
      getSymbol: it => it.symbol,
      isEligible: it => it.type !== 'index',
      beatBySymbol: wlBeatBySymbol,
      upcomingBySymbol: wlEarningsBySymbol,
      dir: wlEarningsPriorityDir,
    });
  }, [
    baseDisplayWlItems,
    wlBeatBySymbol,
    wlEarningsBySymbol,
    wlEarningsPriorityDir,
    wlEarningsPriorityEnabled,
  ]);

  const watchlistStockSymbols = useMemo(() => new Set(
    (activeWatchlist?.items || [])
      .filter(it => it.type !== 'index')
      .map(it => String(it.symbol || '').trim().toUpperCase())
      .filter(Boolean),
  ), [activeWatchlist?.items]);

  const wlEarningsCount = useMemo(() => {
    let n = 0;
    for (const sym of wlEarningsBySymbol.keys()) {
      const highlight = resolveEarningsRowHighlight(
        wlBeatBySymbol.get(sym),
        wlEarningsBySymbol.get(sym),
      );
      if (highlight.kind === 'upcoming') n += 1;
    }
    return n;
  }, [wlEarningsBySymbol, wlBeatBySymbol]);
  const wlBeatCount = useMemo(() => {
    let n = 0;
    for (const sym of wlBeatBySymbol.keys()) {
      const highlight = resolveEarningsRowHighlight(
        wlBeatBySymbol.get(sym),
        wlEarningsBySymbol.get(sym),
      );
      if (highlight.kind === 'beat') n += 1;
    }
    return n;
  }, [wlBeatBySymbol, wlEarningsBySymbol]);

  useEffect(() => {
    if (watchlistStockSymbols.size === 0) {
      setWlEarningsBySymbol(new Map());
      setWlBeatBySymbol(new Map());
      return undefined;
    }
    let cancelled = false;
    (async () => {
      const [upcomingSettled, beatSettled] = await Promise.allSettled([
        axios.get(`${API}/api/earnings-beats`, {
          params: { mode: 'upcoming', period: 'rolling_20_days', limit: 2000 },
        }),
        axios.get(`${API}/api/earnings-beats`, {
          params: {
            mode: 'reported',
            report_window: 'rolling_10_days',
            limit: 2000,
            symbols: [...watchlistStockSymbols].join(','),
          },
        }),
      ]);
      if (cancelled) return;
      if (upcomingSettled.status === 'fulfilled') {
        setWlEarningsBySymbol(
          buildUpcomingEarningsMap(
            upcomingSettled.value.data?.rows || [],
            watchlistStockSymbols,
            WATCHLIST_EARNINGS_WINDOW_DAYS,
          ),
        );
      } else {
        setWlEarningsBySymbol(new Map());
      }
      if (beatSettled.status === 'fulfilled') {
        setWlBeatBySymbol(
          buildDualBeatEarningsMap(beatSettled.value.data?.rows || [], watchlistStockSymbols),
        );
      } else {
        setWlBeatBySymbol(new Map());
      }
    })();
    return () => { cancelled = true; };
  }, [watchlistStockSymbols]);

  useEffect(() => {
    const onWlUpdated = () => {
      setWlEarningsModal(null);
    };
    window.addEventListener('watchlists-updated', onWlUpdated);
    return () => window.removeEventListener('watchlists-updated', onWlUpdated);
  }, []);

  function openWlEarningsModalFromSymbol(it) {
    if (it.type === 'index') return;
    const sym = String(it.symbol || '').trim().toUpperCase();
    const highlight = resolveEarningsRowHighlight(
      wlBeatBySymbol.get(sym),
      wlEarningsBySymbol.get(sym),
    );
    if (!highlight.info) return;
    if (highlight.kind === 'beat') {
      setWlEarningsModal({
        symbol: sym,
        variant: 'beat',
        earningsDate: highlight.info.earnings_release_date,
        daysSinceReport: highlight.info.days_since_report,
      });
      return;
    }
    setWlEarningsModal({
      symbol: sym,
      variant: 'upcoming',
      earningsDate: highlight.info.earnings_release_next_date,
      daysUntil: highlight.info.days_until,
    });
  }

  const selectedItem = useMemo(() => {
    if (!displayWlItems.length) return null;
    const normalizedType = String(appSelectedItem?.type || '').toLowerCase();
    const normalizedSymbol = String(appSelectedItem?.symbol || '').toUpperCase();
    const exact = displayWlItems.find(
      it => String(it.type).toLowerCase() === normalizedType && String(it.symbol).toUpperCase() === normalizedSymbol
    );
    return exact || displayWlItems[0];
  }, [displayWlItems, appSelectedItem]);

  useEffect(() => {
    if (activeWatchlist && activeWatchlist.name !== appActiveWatchlistName) {
      onAppActiveWatchlistNameChange(activeWatchlist.name);
    }
  }, [activeWatchlist, appActiveWatchlistName, onAppActiveWatchlistNameChange]);

  useEffect(() => {
    axios.get(`${API}/api/layout`).then(r => {
      if (r.data.watchlistPaneWidth) setPaneWidth(r.data.watchlistPaneWidth);
      if (r.data.watchlistChartLayout) setChartLayout(r.data.watchlistChartLayout);
      if (r.data.watchlistTimeframe) setTimeframe(r.data.watchlistTimeframe);
      if (r.data.watchlistTimeframe2) setTimeframe2(r.data.watchlistTimeframe2);
      if (r.data.watchlistTimeframe3) setTimeframe3(normalizeSavedTimeframe3(r.data.watchlistTimeframe3));
      if (r.data.watchlistItemOrder && typeof r.data.watchlistItemOrder === 'object') {
        setWatchlistItemOrder(r.data.watchlistItemOrder);
      }
      setPanelHeights({
        stochrsi: Number(r.data.stochrsi || panelHeights.stochrsi || 130),
        macd: Number(r.data.macd || panelHeights.macd || 130),
      });
    }).catch(() => {});
  }, []);

  useEffect(() => {
    localStorage.setItem('watchlist.panelHeights', JSON.stringify(panelHeights));
  }, [panelHeights]);

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

  useEffect(() => {
    function handle(e) {
      if (viewRef.current && !viewRef.current.contains(e.target)) setViewOpen(false);
      if (indRef.current && !indRef.current.contains(e.target)) setIndOpen(false);
      if (watchlistReorderRef.current && !watchlistReorderRef.current.contains(e.target)) setWatchlistReorderOpen(false);
      if (searchWrapRef.current && !searchWrapRef.current.contains(e.target)) setSearch('');
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  useLayoutEffect(() => {
    const q = search.trim().toUpperCase();
    if (!q) {
      setSearchDropdownRect(null);
      return;
    }
    const hasResults =
      Object.keys(stocksMap).some(sym => sym.includes(q)) ||
      Object.values(indicesMap).some(i => (i.symbol || '').toUpperCase().includes(q) || (i.name || '').toUpperCase().includes(q));
    if (!hasResults) {
      setSearchDropdownRect(null);
      return;
    }
    const el = searchWrapRef.current;
    if (!el) {
      setSearchDropdownRect(null);
      return;
    }
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = Math.max(320, r.width);
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      const left = Math.min(Math.max(pad, r.left), maxLeft);
      setSearchDropdownRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [search, stocksMap, indicesMap]);

  useLayoutEffect(() => {
    if (!watchlistReorderOpen) {
      setWatchlistReorderRect(null);
      return;
    }
    const el = watchlistReorderRef.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = 280;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      const left = Math.min(Math.max(pad, r.left), maxLeft);
      setWatchlistReorderRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [watchlistReorderOpen, watchlists]);

  useEffect(() => {
    if (!watchlistReorderOpen) {
      setRenamingWatchlistName(null);
      setRenameName('');
    }
  }, [watchlistReorderOpen]);

  useLayoutEffect(() => {
    if (!viewOpen) {
      setViewDropdownRect(null);
      return;
    }
    const el = viewRef.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = 230;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      const left = Math.min(Math.max(pad, r.right - width), maxLeft);
      setViewDropdownRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [viewOpen]);

  useLayoutEffect(() => {
    if (!indOpen) {
      setIndDropdownRect(null);
      return;
    }
    const el = indRef.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = 170;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      const left = Math.min(Math.max(pad, r.left), maxLeft);
      setIndDropdownRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [indOpen]);

  useEffect(() => {
    loadDataMaps();
    function reload() {
      onWatchlistsChange && onWatchlistsChange();
      loadDataMaps();
    }
    window.addEventListener('watchlists-updated', reload);
    window.addEventListener('dashboard-refresh', reload);
    window.addEventListener(CHART_DATA_UPDATED_EVENT, reload);
    return () => {
      window.removeEventListener('watchlists-updated', reload);
      window.removeEventListener('dashboard-refresh', reload);
      window.removeEventListener(CHART_DATA_UPDATED_EVENT, reload);
    };
  }, []);

  useLayoutEffect(() => {
    const headerEl = headerScrollRef.current;
    const rowsEl = rowsScrollRef.current;
    if (!headerEl || !rowsEl) return undefined;
    const syncHeader = () => {
      if (headerEl.scrollLeft !== rowsEl.scrollLeft) {
        headerEl.scrollLeft = rowsEl.scrollLeft;
      }
    };
    syncHeader();
    rowsEl.addEventListener('scroll', syncHeader);
    return () => rowsEl.removeEventListener('scroll', syncHeader);
  }, [paneWidth, activeWatchlist?.name, watchlists.length]);

  useEffect(() => {
    if (!selectedItem) return;
    const normApp = `${String(appSelectedItem?.type || '').toLowerCase()}:${String(appSelectedItem?.symbol || '').toUpperCase()}`;
    const normSel = `${String(selectedItem.type).toLowerCase()}:${String(selectedItem.symbol).toUpperCase()}`;
    if (normApp !== normSel) {
      onAppSelectedItemChange(selectedItem);
      setLastChange(null);
      setLastPrice(null);
    }
  }, [selectedItem, appSelectedItem, onAppSelectedItemChange]);

  useEffect(() => {
    if (!selectedItem || !displayWlItems.length) return;
    const key = `${String(selectedItem.type || '').toLowerCase()}:${String(selectedItem.symbol || '').toUpperCase()}`;
    wlRowRefs.current[key]?.scrollIntoView({ block: 'nearest' });
  }, [displayWlItems, selectedItem]);

  async function loadDataMaps() {
    try {
      let all = [];
      let p = 1;
      while (true) {
        const r = await axios.get(`${API}/api/stocks`, { params: { page: p, pageSize: 500, sortBy: 'Market Cap', sortDir: 'desc' } });
        const rows = r.data?.data || [];
        all = all.concat(rows);
        if (all.length >= (r.data?.total || 0) || rows.length === 0) break;
        p += 1;
      }
      const sm = {};
      for (const s of all) sm[s.Symbol] = s;
      setStocksMap(sm);
    } catch {}
    try {
      const r = await axios.get(`${API}/api/indices`);
      const im = {};
      for (const i of r.data?.data || []) im[i.symbol] = i;
      setIndicesMap(im);
    } catch {}
  }

  async function createWatchlist() {
    const name = newWatchlistName.trim();
    if (!name) return;
    try {
      await axios.post(`${API}/api/watchlists`, { name });
      setNewWatchlistName('');
      await onWatchlistsChange();
      onAppActiveWatchlistNameChange(name);
      window.dispatchEvent(new CustomEvent('watchlists-updated'));
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  }

  function cancelRenameWatchlist() {
    setRenamingWatchlistName(null);
    setRenameName('');
  }

  async function renameWatchlist() {
    const oldNm = renamingWatchlistName || activeWatchlist?.name;
    if (!oldNm) return;
    const name = renameName.trim();
    if (!name || name === oldNm) {
      cancelRenameWatchlist();
      return;
    }
    try {
      await axios.patch(`${API}/api/watchlists/${encodeURIComponent(oldNm)}`, { new_name: name });
      cancelRenameWatchlist();
      setWatchlistItemOrder(prev => {
        const next = { ...prev };
        const ord = next[oldNm];
        if (ord) {
          next[name] = ord;
          delete next[oldNm];
        }
        axios.post(`${API}/api/layout`, { watchlistItemOrder: next }).catch(() => {});
        return next;
      });
      await onWatchlistsChange();
      if (
        String(appActiveWatchlistName || '').toLowerCase() === String(oldNm).toLowerCase()
      ) {
        onAppActiveWatchlistNameChange(name);
      }
      window.dispatchEvent(new CustomEvent('watchlists-updated'));
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  }

  function handleExportWatchlists() {
    if (!watchlists.length) {
      alert('No watchlists available to export.');
      return;
    }
    try {
      const names = new Set(watchlists.map(w => w.name));
      const order = {};
      for (const [listName, keys] of Object.entries(watchlistItemOrder)) {
        if (names.has(listName) && Array.isArray(keys) && keys.length) {
          order[listName] = keys;
        }
      }
      const payload = {
        version: 1,
        exported_at: new Date().toISOString(),
        watchlists: watchlists.map(w => ({
          name: w.name,
          items: (w.items || []).map(it => ({
            symbol: String(it.symbol || '').toUpperCase(),
            type: String(it.type || 'stock').toLowerCase() === 'index' ? 'index' : 'stock',
          })),
        })),
        watchlist_item_order: order,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      const a = document.createElement('a');
      a.href = url;
      a.download = `cim-watchlists-${stamp}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Failed to export watchlists: ${e?.message || 'Unknown error'}`);
    }
  }

  async function handleImportWatchlistFile(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const imported = Array.isArray(parsed) ? parsed : (parsed?.watchlists || []);
      const cleaned = imported
        .filter(w => w && typeof w.name === 'string' && w.name.trim())
        .map(w => ({
          name: w.name.trim(),
          items: Array.isArray(w.items)
            ? w.items
              .filter(it => it && typeof it.symbol === 'string' && String(it.symbol).trim())
              .map(it => ({
                symbol: String(it.symbol).trim().toUpperCase(),
                type: String(it.type || 'stock').toLowerCase() === 'index' ? 'index' : 'stock',
              }))
            : [],
        }));
      if (!cleaned.length) {
        alert('No valid watchlists found in this file.');
        return;
      }
      const importedOrder = (
        parsed && typeof parsed === 'object' && !Array.isArray(parsed) && parsed.watchlist_item_order
      ) ? parsed.watchlist_item_order : {};
      const replaceAll = window.confirm(
        `Import ${cleaned.length} watchlist(s)?\n\n` +
        'Click OK to REPLACE all existing watchlists.\n' +
        'Click Cancel to MERGE (keep lists not in the file; overwrite lists with the same name).'
      );
      const r = await axios.post(`${API}/api/watchlists/import`, {
        mode: replaceAll ? 'replace' : 'merge',
        watchlists: cleaned,
        watchlist_item_order: importedOrder,
      });
      const data = r.data || {};
      if (data.watchlist_item_order && typeof data.watchlist_item_order === 'object') {
        setWatchlistItemOrder(data.watchlist_item_order);
      }
      await onWatchlistsChange();
      const nextLists = data.watchlists || [];
      const activeStillExists = nextLists.some(
        w => w.name === appActiveWatchlistName || w.name?.toLowerCase() === String(appActiveWatchlistName || '').toLowerCase(),
      );
      if (!activeStillExists && nextLists[0]?.name) {
        onAppActiveWatchlistNameChange(nextLists[0].name);
      }
      window.dispatchEvent(new CustomEvent('watchlists-updated'));
      window.dispatchEvent(new CustomEvent('cim-toast', {
        detail: `Imported ${cleaned.length} watchlist(s) successfully.`,
      }));
    } catch (err) {
      alert(`Failed to import watchlists: ${err.response?.data?.detail || err.message}`);
    }
  }

  async function deleteWatchlist(listName) {
    const target = String(listName || activeWatchlist?.name || '').trim();
    if (!target) return;
    if (!window.confirm(`Delete watchlist "${target}"?`)) return;
    const wasActive = String(appActiveWatchlistName || '').toLowerCase() === target.toLowerCase();
    const remaining = watchlists.filter(w => w.name.toLowerCase() !== target.toLowerCase());
    await axios.delete(`${API}/api/watchlists/${encodeURIComponent(target)}`);
    if (String(renamingWatchlistName || '').toLowerCase() === target.toLowerCase()) {
      cancelRenameWatchlist();
    }
    setWatchlistItemOrder(prev => {
      if (!prev[target]) return prev;
      const next = { ...prev };
      delete next[target];
      axios.post(`${API}/api/layout`, { watchlistItemOrder: next }).catch(() => {});
      return next;
    });
    await onWatchlistsChange();
    if (wasActive) {
      onAppActiveWatchlistNameChange(remaining[0]?.name || '');
    }
    window.dispatchEvent(new CustomEvent('watchlists-updated'));
  }

  async function persistWatchlistNamesOrder(names) {
    const cleaned = (names || []).map(n => String(n || '').trim()).filter(Boolean);
    if (!cleaned.length) return;
    await axios.post(`${API}/api/watchlists/reorder`, { ordered_names: cleaned });
    window.dispatchEvent(new CustomEvent('watchlists-updated'));
  }

  async function addItemToActive(item) {
    if (!activeWatchlist) return;
    await axios.post(`${API}/api/watchlists/${encodeURIComponent(activeWatchlist.name)}/items`, item);
    await onWatchlistsChange();
    window.dispatchEvent(new CustomEvent('watchlists-updated'));
  }

  async function removeItemFromActive(item) {
    if (!activeWatchlist) return;
    await axios.delete(`${API}/api/watchlists/${encodeURIComponent(activeWatchlist.name)}/items/${encodeURIComponent(item.symbol)}`, {
      params: { type: item.type },
    });
    await onWatchlistsChange();
    window.dispatchEvent(new CustomEvent('watchlists-updated'));
  }

  function onDividerMouseDown(e) {
    e.preventDefault();
    draggingRef.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = paneWidth;
    function onMouseMove(ev) {
      if (!draggingRef.current) return;
      const total = wrapperRef.current?.clientWidth || 1200;
      setPaneWidth(Math.max(280, Math.min(total - 500, startWidthRef.current + ev.clientX - startXRef.current)));
    }
    function onMouseUp() {
      draggingRef.current = false;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    }
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  function persistWatchlistItemOrder(nextMap) {
    setWlOrderMode('manual');
    setWatchlistItemOrder(nextMap);
    axios.post(`${API}/api/layout`, { watchlistItemOrder: nextMap }).catch(() => {});
  }

  function handleWlSort(sortKey) {
    if (!sortKey) return;
    setWlEarningsPriorityEnabled(false);
    setWlOrderMode('sort');
    if (wlSortKey === sortKey) setWlSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setWlSortKey(sortKey);
      setWlSortDir(sortKey === 'symbol' ? 'asc' : 'desc');
    }
  }

  function handleWlEarningsPriorityControlClick() {
    if (!wlEarningsPriorityEnabled) {
      setWlEarningsPriorityEnabled(true);
      return;
    }
    setWlEarningsPriorityDir(d => (d === 'asc' ? 'desc' : 'asc'));
  }

  function handleSaveLayout() {
    axios.post(`${API}/api/layout`, {
      ...currentHeightsRef.current,
      watchlistPaneWidth: paneWidth,
      watchlistChartLayout: chartLayout,
      watchlistTimeframe: timeframe,
      watchlistTimeframe2: timeframe2,
      watchlistTimeframe3: timeframe3,
      watchlistItemOrder,
    }).then(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Layout saved.' }))).catch(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Failed to save layout.' })));
  }

  function clearWlDnD() {
    wlDragIdxRef.current = null;
    wlDropGapRef.current = null;
    setWlDropGap(null);
    setWlDraggingIdx(null);
  }

  function onWlDragStart(e, wi) {
    wlDragIdxRef.current = wi;
    setWlDraggingIdx(wi);
    const it = displayWlItems[wi];
    if (!it) return;
    const sub = it.type === 'index'
      ? (indicesMap[it.symbol]?.name || 'Index')
      : 'Stock';
    setListDragImage(e.dataTransfer, it.symbol, sub);
  }

  function onWlDragOver(e, wi) {
    if (wlDragIdxRef.current === null) return;
    e.preventDefault();
    const gap = insertionGapFromRowHover(e.clientY, e.currentTarget, wi, displayWlItems.length);
    wlDropGapRef.current = gap;
    setWlDropGap(gap);
  }

  function onWlDrop(e) {
    e.preventDefault();
    const from = wlDragIdxRef.current;
    const gap = wlDropGapRef.current;
    clearWlDnD();
    if (!activeWatchlist?.name || from === null || gap === null || gap === undefined) return;
    const keys = displayWlItems.map(wlItemKey);
    const nextKeys = reorderByGap(keys, from, gap);
    if (JSON.stringify(nextKeys) === JSON.stringify(keys)) return;
    persistWatchlistItemOrder({
      ...watchlistItemOrder,
      [activeWatchlist.name]: nextKeys,
    });
  }

  function onWlDragEnd() {
    clearWlDnD();
  }

  function clearWatchlistDnD() {
    watchlistDragIdxRef.current = null;
    watchlistDropGapRef.current = null;
    setWatchlistDraggingIdx(null);
    setWatchlistDropGap(null);
  }

  function onWatchlistDragStart(e, wi) {
    watchlistDragIdxRef.current = wi;
    setWatchlistDraggingIdx(wi);
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', String(wi));
    }
    const name = watchlistNames[wi] || 'Watchlist';
    setListDragImage(e.dataTransfer, name, 'Watchlist');
  }

  function onWatchlistDragOver(e, wi) {
    if (watchlistDragIdxRef.current === null) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const gap = insertionGapFromRowHover(e.clientY, e.currentTarget, wi, watchlistNames.length);
    watchlistDropGapRef.current = gap;
    setWatchlistDropGap(gap);
  }

  async function onWatchlistDrop(e) {
    e.preventDefault();
    const from = watchlistDragIdxRef.current;
    const gap = watchlistDropGapRef.current;
    clearWatchlistDnD();
    if (from === null || gap === null || gap === undefined) return;
    const next = reorderByGap(watchlistNames, from, gap);
    if (JSON.stringify(next) === JSON.stringify(watchlistNames)) return;
    await persistWatchlistNamesOrder(next);
  }

  function onWatchlistDragEnd() {
    clearWatchlistDnD();
  }


  const searchResults = useMemo(() => {
    const q = search.trim().toUpperCase();
    if (!q) return [];
    const stockMatches = Object.keys(stocksMap).filter(sym => sym.includes(q)).slice(0, 10).map(sym => ({ symbol: sym, type: 'stock' }));
    const indexMatches = Object.values(indicesMap)
      .filter(i => (i.symbol || '').toUpperCase().includes(q) || (i.name || '').toUpperCase().includes(q))
      .slice(0, 10)
      .map(i => ({ symbol: i.symbol, type: 'index', name: i.name }));
    return [...stockMatches, ...indexMatches];
  }, [search, stocksMap, indicesMap]);

  useEffect(() => {
    if (!searchResults.length) {
      setSearchActiveIndex(0);
      return;
    }
    setSearchActiveIndex(prev => Math.max(0, Math.min(prev, searchResults.length - 1)));
  }, [searchResults.length]);

  function applySearchSelection(payload) {
    onAppSelectedItemChange(payload);
    setLastChange(null);
    setLastPrice(null);
    setCrosshairTime(null);
    setSearch('');
  }

  useEffect(() => {
    function onGlobalPick(e) {
      const d = e?.detail || {};
      if (String(d.targetView || '') !== 'watchlist') return;
      const symbol = String(d.symbol || '').toUpperCase();
      if (!symbol) return;
      const typ = String(d.type || 'stock').toLowerCase();
      const payload = { symbol, type: typ === 'index' ? 'index' : 'stock' };
      setSearchActiveIndex(0);
      const exact = displayWlItems.find(
        it => String(it.symbol || '').toUpperCase() === symbol
          && String(it.type || '').toLowerCase() === payload.type
      );
      if (exact) {
        onAppSelectedItemChange(exact);
        setLastChange(null);
        setLastPrice(null);
        setCrosshairTime(null);
      }
    }
    window.addEventListener('cim-global-search-select', onGlobalPick);
    return () => window.removeEventListener('cim-global-search-select', onGlobalPick);
  }, [displayWlItems, onAppSelectedItemChange]);

  const activeItemData = useMemo(() => {
    if (!selectedItem) return null;
    return selectedItem.type === 'index' ? indicesMap[selectedItem.symbol] : stocksMap[selectedItem.symbol];
  }, [selectedItem, indicesMap, stocksMap]);

  function actionBtnStyle() {
    return {
      display: 'flex',
      alignItems: 'center',
      gap: 4,
      backgroundColor: 'var(--bg-tertiary)',
      border: '1px solid var(--border)',
      borderRadius: 5,
      padding: '0 10px',
      height: 28,
      color: 'var(--text-secondary)',
      fontSize: 12,
      cursor: 'pointer',
      flexShrink: 0,
    };
  }

  function renderPanel(item, tf, setTf, onLast, cacheKey, hasBorderRight) {
    if (!item) return null;
    const common = {
      key: cacheKey,
      style: {
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        borderRight: hasBorderRight ? '2px solid var(--border)' : 'none',
      },
    };
    return (
      <div {...common}>
        <ChartHeaderBar symbol={item.symbol} timeframe={tf} onTimeframeChange={setTf} />
        {item.type === 'stock' ? (
          <ChartContainer
            symbol={item.symbol}
            timeframe={tf}
            liveToday={String(tf || '').toUpperCase() === '1D'}
            emas={emas}
            volumeVisible={volumeVisible}
            visiblePanels={visiblePanels}
            panelOrder={panelOrder}
            onTogglePanel={(k) => setVisiblePanels(prev => ({ ...prev, [k]: !prev[k] }))}
            onMovePanel={(key, direction) => {
              setPanelOrder(prev => {
                const idx = prev.indexOf(key);
                const swap = direction === 'up' ? idx - 1 : idx + 1;
                if (idx < 0 || swap < 0 || swap >= prev.length) return prev;
                const next = [...prev];
                [next[idx], next[swap]] = [next[swap], next[idx]];
                return next;
              });
            }}
            onLastChange={(pct, price) => { onLast(pct, price); }}
            onHeightsChange={h => {
              currentHeightsRef.current = h;
              setPanelHeights(prev => ({
                stochrsi: Number(h?.stochrsi || prev.stochrsi || 130),
                macd: Number(h?.macd || prev.macd || 130),
              }));
            }}
            panelHeights={panelHeights}
            onCrosshairMove={setCrosshairTime}
            crosshairTime={crosshairTime}
            drawingScopeId={`wl:${item.type}:${cacheKey}`}
            drawingAutoFocus={false}
          />
        ) : (
          <IndexChartContainer
            symbol={item.symbol}
            timeframe={tf}
            emas={emas}
            volumeVisible={volumeVisible}
            visiblePanels={visiblePanels}
            panelOrder={panelOrder}
            onTogglePanel={(k) => setVisiblePanels(prev => ({ ...prev, [k]: !prev[k] }))}
            onMovePanel={(key, direction) => {
              setPanelOrder(prev => {
                const idx = prev.indexOf(key);
                const swap = direction === 'up' ? idx - 1 : idx + 1;
                if (idx < 0 || swap < 0 || swap >= prev.length) return prev;
                const next = [...prev];
                [next[idx], next[swap]] = [next[swap], next[idx]];
                return next;
              });
            }}
            onLastChange={(pct, price) => { onLast(pct, price); }}
            onHeightsChange={h => {
              currentHeightsRef.current = h;
              setPanelHeights(prev => ({
                stochrsi: Number(h?.stochrsi || prev.stochrsi || 130),
                macd: Number(h?.macd || prev.macd || 130),
              }));
            }}
            panelHeights={panelHeights}
            onCrosshairMove={setCrosshairTime}
            crosshairTime={crosshairTime}
            drawingScopeId={`wl:${item.type}:${cacheKey}`}
            drawingAutoFocus={false}
          />
        )}
      </div>
    );
  }

  const selectedSectorLabel = selectedItem?.type === 'stock'
    ? (activeItemData?.['Market Sector'] || '—')
    : (activeItemData?.category || 'Index');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', overflow: 'hidden', fontSize: 12 }}>
      <div className="chart-app-toolbar" style={{ height: 48, borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-secondary)', display: 'flex', alignItems: 'center', padding: '0 12px', gap: 8, overflowX: 'auto', fontSize: 12 }}>
        <div ref={searchWrapRef} style={{ position: 'relative', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, width: 200, flexShrink: 0 }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="var(--text-muted)"><path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z" /></svg>
            <input
              ref={searchInputRef}
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search symbol…"
              style={{ background: 'transparent', color: 'var(--text-primary)', flex: 1, fontSize: 12, border: 'none', outline: 'none', minWidth: 0 }}
            />
            {search ? (
              <button type="button" onClick={() => setSearch('')} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 14, lineHeight: 1, padding: 0, border: 'none', cursor: 'pointer' }}>×</button>
            ) : null}
          </div>
          {searchResults.length > 0 && searchDropdownRect && (
            <div style={{ position: 'fixed', top: searchDropdownRect.top, left: searchDropdownRect.left, width: searchDropdownRect.width, zIndex: 200000, maxHeight: 240, overflowY: 'auto', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.35)' }}>
              {searchResults.map((r, idx) => {
                const payload = { symbol: r.symbol, type: r.type };
                const rowKey = wlItemKey(payload);
                const alreadyIn = orderedWatchlistItems.some(it => wlItemKey(it) === rowKey);
                const canAdd = !!activeWatchlist && !alreadyIn;
                const isActive = idx === searchActiveIndex;
                return (
                  <div
                    key={`${r.type}:${r.symbol}`}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '8px 10px',
                      borderBottom: '1px solid var(--border-light)',
                      fontSize: 12,
                      backgroundColor: isActive ? 'rgba(56,139,253,0.12)' : 'transparent',
                    }}
                  >
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => {
                        setSearchActiveIndex(idx);
                        applySearchSelection(payload);
                      }}
                      onKeyDown={e => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSearchActiveIndex(idx);
                          applySearchSelection(payload);
                        }
                      }}
                      style={{ flex: 1, minWidth: 0, cursor: 'pointer', textAlign: 'left' }}
                    >
                      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontSize: 12 }}>{r.symbol}</span>
                      <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-muted)' }}>{r.type === 'index' ? (r.name || 'Index') : 'Stock'}</span>
                    </div>
                    <button
                      type="button"
                      disabled={!canAdd}
                      title={
                        !activeWatchlist
                          ? 'Create or select a watchlist first'
                          : alreadyIn
                            ? 'Already in this watchlist'
                            : `Add ${r.symbol} to ${activeWatchlist.name}`
                      }
                      onClick={e => {
                        e.stopPropagation();
                        if (!canAdd) return;
                        addItemToActive(payload);
                        setSearch('');
                      }}
                      style={{
                        flexShrink: 0,
                        alignSelf: 'center',
                        whiteSpace: 'nowrap',
                        fontSize: 11,
                        fontWeight: 600,
                        padding: '4px 10px',
                        borderRadius: 5,
                        border: `1px solid ${canAdd ? 'var(--accent-blue)' : 'var(--border)'}`,
                        backgroundColor: canAdd ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)',
                        color: canAdd ? 'var(--accent-blue)' : 'var(--text-muted)',
                        cursor: canAdd ? 'pointer' : 'not-allowed',
                        opacity: canAdd ? 1 : 0.85,
                      }}
                    >
                      {alreadyIn ? 'In watchlist' : 'Add to Watchlist'}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {activeItemData && (
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', flexShrink: 0, minWidth: 64 }}>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 700, fontSize: 14, lineHeight: 1.1 }}>{selectedItem?.symbol}</span>
            <span style={{ fontSize: 9, color: 'var(--text-muted)', maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 2 }} title={selectedSectorLabel}>
              {selectedSectorLabel}
            </span>
          </div>
        )}
        {activeItemData && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)', flexShrink: 0 }}>
            ₹{Number(lastPrice ?? activeItemData?.Price ?? activeItemData?.last_price ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        )}
        {lastChange !== null && (
          <span style={{ color: lastChange >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, backgroundColor: lastChange >= 0 ? 'rgba(63,185,80,0.12)' : 'rgba(248,81,73,0.12)', border: `1px solid ${lastChange >= 0 ? '#3fb95044' : '#f8514944'}`, borderRadius: 4, padding: '1px 6px' }}>
            {lastChange >= 0 ? '+' : ''}{lastChange.toFixed(2)}%
          </span>
        )}
        <div style={{ width: 1, height: 20, backgroundColor: 'var(--border)', flexShrink: 0 }} />

        <div
          onClick={() => setVolumeVisible(v => !v)}
          style={{
            display:'flex',
            alignItems:'center',
            gap:5,
            backgroundColor:'var(--bg-tertiary)',
            border:`1px solid ${volumeVisible ? '#388bfd55' : 'var(--border)'}`,
            borderRadius:4,
            padding:'0 8px',
            height:26,
            opacity: volumeVisible ? 1 : 0.5,
            cursor:'pointer',
            flexShrink:0,
          }}
        >
          <div style={{ width:8, height:8, backgroundColor:'#388bfd', borderRadius:2 }} />
          <span style={{ fontSize:11, color:'var(--text-secondary)', fontWeight:500 }}>Vol</span>
        </div>
        <EMAControls emas={emas} onChange={setEmas} />
        {selectedItem?.type === 'stock' && (
          <ExternalFinancialsLinks symbol={selectedItem.symbol} height={26} />
        )}

        <div style={{ flex: 1, minWidth: 8 }} />

        <DrawingToolsDesignControl />

        <div ref={indRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button onClick={() => { setIndOpen(o => !o); setViewOpen(false); }} style={{ ...actionBtnStyle(), backgroundColor: indOpen ? 'var(--bg-active)' : 'var(--bg-tertiary)' }}>
            Indicators <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6 }}><path d="M0 0l4 5 4-5z" /></svg>
          </button>
          {indOpen && indDropdownRect && (
            <div style={{ position: 'fixed', top: indDropdownRect.top, left: indDropdownRect.left, width: indDropdownRect.width, zIndex: 200000, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.6)', overflow: 'hidden' }}>
              {INDICATOR_OPTIONS.map(ind => {
                const active = visiblePanels[ind.key];
                return (
                  <div key={ind.key} onClick={() => { setVisiblePanels(prev => ({ ...prev, [ind.key]: !prev[ind.key] })); setIndOpen(false); }}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 14px', cursor: 'pointer', fontSize: 13, color: active ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--bg-hover)'}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}>
                    {ind.label}
                    <div style={{ width: 14, height: 14, borderRadius: 3, border: '1px solid var(--border)', backgroundColor: active ? 'var(--accent-blue)' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {active && <svg width="9" height="7" viewBox="0 0 9 7" fill="none"><path d="M1 3.5L3.5 6L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        {selectedItem?.type === 'stock' && (
          <button onClick={() => onOpenChart && onOpenChart(selectedItem.symbol)} style={actionBtnStyle()}>Open Full Chart ↗</button>
        )}
        {selectedItem?.type === 'index' && (
          <button onClick={() => onOpenConstituents && onOpenConstituents(indicesMap[selectedItem.symbol])} style={actionBtnStyle()}>Constituents ↗</button>
        )}
        <div ref={viewRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button onClick={() => { setViewOpen(v => !v); setIndOpen(false); }} style={{ ...actionBtnStyle(), color: chartLayout !== 'single' ? 'var(--accent-blue)' : 'var(--text-secondary)' }}>View</button>
          {viewOpen && viewDropdownRect && (
            <div style={{ position: 'fixed', top: viewDropdownRect.top, left: viewDropdownRect.left, width: viewDropdownRect.width, zIndex: 200000, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, minWidth: 230, overflow: 'hidden' }}>
              <div style={{ padding: '6px 0' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '4px 14px 6px' }}>Layout</div>
                {LAYOUTS.map(l => (
                  <div key={l.key} onClick={() => { setChartLayout(l.key); setViewOpen(false); }}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 14px', cursor: 'pointer', backgroundColor: chartLayout === l.key ? 'rgba(56,139,253,0.10)' : 'transparent', color: chartLayout === l.key ? 'var(--accent-blue)' : 'var(--text-secondary)', fontSize: 13 }}>
                    <div>
                      <div style={{ fontWeight: chartLayout === l.key ? 600 : 400 }}>{l.label}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>{l.desc}</div>
                    </div>
                    {chartLayout === l.key && <span style={{ fontSize: 11 }}>✓</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <button onClick={handleSaveLayout} style={actionBtnStyle()}>Save Layout</button>
      </div>

      <div className="chart-app-toolbar" style={{ height: 40, borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-secondary)', display: 'flex', alignItems: 'center', padding: '0 12px', gap: 8, overflowX: 'auto', fontSize: 12 }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          <button
            type="button"
            onClick={() => setWatchlistSortMode('manual')}
            style={{ ...actionBtnStyle(), borderColor: watchlistSortMode === 'manual' ? 'var(--accent-blue)' : 'var(--border)', color: watchlistSortMode === 'manual' ? 'var(--accent-blue)' : 'var(--text-secondary)' }}
            title="Manual watchlist order"
          >
            Manual
          </button>
          <button
            type="button"
            onClick={() => setWatchlistSortMode('az')}
            style={{ ...actionBtnStyle(), borderColor: watchlistSortMode === 'az' ? 'var(--accent-blue)' : 'var(--border)', color: watchlistSortMode === 'az' ? 'var(--accent-blue)' : 'var(--text-secondary)' }}
            title="Sort watchlists A to Z"
          >
            A-Z
          </button>
          <button
            type="button"
            onClick={() => setWatchlistSortMode('za')}
            style={{ ...actionBtnStyle(), borderColor: watchlistSortMode === 'za' ? 'var(--accent-blue)' : 'var(--border)', color: watchlistSortMode === 'za' ? 'var(--accent-blue)' : 'var(--text-secondary)' }}
            title="Sort watchlists Z to A"
          >
            Z-A
          </button>
        </div>
        <div ref={watchlistReorderRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button
            type="button"
            onClick={() => setWatchlistReorderOpen(v => !v)}
            style={{ ...actionBtnStyle(), minWidth: 220, justifyContent: 'space-between' }}
            title="Select watchlist"
          >
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {activeWatchlist?.name || 'Create a watchlist below…'}
            </span>
            <span style={{ opacity: 0.7 }}>▾</span>
          </button>
          {watchlistReorderOpen && watchlistReorderRect && (
            <div style={{ position: 'fixed', top: watchlistReorderRect.top, left: watchlistReorderRect.left, width: watchlistReorderRect.width, zIndex: 200000, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.35)', overflow: 'hidden' }}>
              <div style={{ maxHeight: 220, overflowY: 'auto', padding: '6px 0' }}>
                {displayWatchlists.length === 0 ? (
                  <div style={{ padding: '8px 10px', fontSize: 12, color: 'var(--text-muted)' }}>Create a watchlist below…</div>
                ) : (
                  <>
                    {watchlistDraggingIdx !== null && watchlistDropGap === 0 ? <DropInsetLine /> : null}
                    {displayWatchlists.map((w, wi) => {
                      const isActive = activeWatchlist?.name === w.name;
                      const canDrag = watchlistSortMode === 'manual' && watchlists.length > 1 && renamingWatchlistName !== w.name;
                      const isRenaming = renamingWatchlistName === w.name;
                      return (
                        <React.Fragment key={w.name}>
                          <div
                            draggable={canDrag}
                            onDragStart={canDrag ? e => onWatchlistDragStart(e, wi) : undefined}
                            onDragEnd={canDrag ? onWatchlistDragEnd : undefined}
                            onDragOver={canDrag ? e => onWatchlistDragOver(e, wi) : undefined}
                            onDrop={canDrag ? onWatchlistDrop : undefined}
                            onClick={isRenaming ? undefined : () => {
                              onAppActiveWatchlistNameChange(w.name);
                              setWatchlistReorderOpen(false);
                            }}
                            style={{
                              minHeight: 30,
                              display: 'flex',
                              alignItems: 'center',
                              gap: 6,
                              padding: '0 8px 0 10px',
                              cursor: isRenaming ? 'default' : (canDrag ? 'grab' : 'pointer'),
                              color: isActive ? 'var(--accent-blue)' : 'var(--text-primary)',
                              backgroundColor: isActive ? 'rgba(56,139,253,0.10)' : 'transparent',
                              opacity: watchlistDraggingIdx === wi ? 0.45 : 1,
                            }}
                          >
                            {isRenaming ? (
                              <>
                                <input
                                  value={renameName}
                                  onChange={e => setRenameName(e.target.value)}
                                  onClick={e => e.stopPropagation()}
                                  onKeyDown={e => {
                                    e.stopPropagation();
                                    if (e.key === 'Enter') renameWatchlist();
                                    if (e.key === 'Escape') cancelRenameWatchlist();
                                  }}
                                  autoFocus
                                  style={{ flex: 1, minWidth: 0, height: 24, background: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: 4, padding: '0 6px', fontSize: 12 }}
                                />
                                <button
                                  type="button"
                                  title="Save rename"
                                  onClick={e => { e.stopPropagation(); renameWatchlist(); }}
                                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, flexShrink: 0, border: '1px solid var(--border)', borderRadius: 4, background: 'var(--bg-tertiary)', cursor: 'pointer', padding: 0, color: 'var(--accent-blue)', fontSize: 12 }}
                                >
                                  ✓
                                </button>
                                <button
                                  type="button"
                                  title="Cancel rename"
                                  onClick={e => { e.stopPropagation(); cancelRenameWatchlist(); }}
                                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, flexShrink: 0, border: '1px solid var(--border)', borderRadius: 4, background: 'var(--bg-tertiary)', cursor: 'pointer', padding: 0, color: 'var(--text-muted)', fontSize: 13 }}
                                >
                                  ×
                                </button>
                              </>
                            ) : (
                              <>
                                {canDrag ? <span style={{ width: 12, color: 'var(--text-muted)', fontSize: 10, letterSpacing: '-0.12em', flexShrink: 0 }}>⋮⋮</span> : null}
                                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w.name}</span>
                                <button
                                  type="button"
                                  className="cim-row-edit-btn"
                                  title="Rename watchlist"
                                  onClick={e => {
                                    e.stopPropagation();
                                    setRenamingWatchlistName(w.name);
                                    setRenameName(w.name);
                                  }}
                                >
                                  <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                                    <path d="M11.013 1.427a1.75 1.75 0 0 1 2.474 0l1.086 1.086a1.75 1.75 0 0 1 0 2.474l-8.61 8.61-3.447 1.148 1.148-3.447 8.61-8.61z" />
                                  </svg>
                                </button>
                                <button
                                  type="button"
                                  title="Delete watchlist"
                                  onClick={e => { e.stopPropagation(); deleteWatchlist(w.name); }}
                                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 14, cursor: 'pointer', padding: 0, lineHeight: 1, flexShrink: 0, width: 18 }}
                                  onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent-red)'; }}
                                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; }}
                                >
                                  ×
                                </button>
                              </>
                            )}
                          </div>
                          {watchlistDraggingIdx !== null && watchlistDropGap === wi + 1 ? <DropInsetLine /> : null}
                        </React.Fragment>
                      );
                    })}
                  </>
                )}
              </div>
              <div style={{
                borderTop: '1px solid var(--border)',
                padding: '8px 10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                backgroundColor: 'var(--bg-tertiary)',
              }}>
                <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Backup</span>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    type="button"
                    onClick={e => { e.stopPropagation(); handleExportWatchlists(); }}
                    disabled={!watchlists.length}
                    style={{
                      fontSize: 11,
                      color: watchlists.length ? 'var(--text-secondary)' : 'var(--text-muted)',
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                      cursor: watchlists.length ? 'pointer' : 'not-allowed',
                      padding: '3px 10px',
                      opacity: watchlists.length ? 1 : 0.5,
                    }}
                    title={watchlists.length ? 'Export all watchlists to a JSON file' : 'No watchlists to export'}
                  >
                    Export
                  </button>
                  <button
                    type="button"
                    onClick={e => { e.stopPropagation(); watchlistImportRef.current?.click(); }}
                    style={{
                      fontSize: 11,
                      color: 'var(--text-secondary)',
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                      cursor: 'pointer',
                      padding: '3px 10px',
                    }}
                    title="Import watchlists from a JSON backup file"
                  >
                    Import
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
        <input
          value={newWatchlistName}
          onChange={e => setNewWatchlistName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && createWatchlist()}
          placeholder="New watchlist..."
          style={{ height: 28, width: 180, background: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: 4, padding: '0 8px', flexShrink: 0, fontSize: 12 }}
        />
        <button onClick={createWatchlist} style={actionBtnStyle()}>Create</button>
        <input
          ref={watchlistImportRef}
          type="file"
          accept="application/json,.json"
          style={{ display: 'none' }}
          onChange={handleImportWatchlistFile}
        />
      </div>
      <div ref={wrapperRef} style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
        <div ref={paneRef} style={{ width: paneWidth, minWidth: 300, borderRight: '1px solid var(--border)', flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div
            ref={headerScrollRef}
            style={{ ...stockListHeaderStripStyle, overflowX: 'hidden', overflowY: 'hidden' }}
          >
            {WL_COLS.map(col => {
              const sortable = !!col.sortKey;
              const activeSort = sortable && wlOrderMode === 'sort' && wlSortKey === col.sortKey;
              return (
                <div
                  key={col.key}
                  style={{
                    width: col.width,
                    minWidth: col.width,
                    flexShrink: 0,
                    height: STOCK_LIST_HEADER_HEIGHT,
                    display: 'flex',
                    alignItems: 'center',
                    borderRight: '1px solid var(--border-light)',
                    userSelect: 'none',
                  }}
                >
                  {sortable ? (
                    <button
                      type="button"
                      onClick={() => handleWlSort(col.sortKey)}
                      style={{
                        width: '100%',
                        height: '100%',
                        padding: '0 8px',
                        display: 'flex',
                        alignItems: 'center',
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: 11,
                        fontWeight: 600,
                        color: activeSort ? 'var(--accent-blue)' : 'var(--text-secondary)',
                        fontFamily: 'inherit',
                        textAlign: 'left',
                      }}
                      aria-label={`Sort by ${col.label}, currently ${activeSort ? (wlSortDir === 'asc' ? 'ascending' : 'descending') : 'not sorted'}`}
                    >
                      {col.label}
                      {activeSort && (
                        <span style={{ marginLeft: 3, fontSize: 9 }}>{wlSortDir === 'asc' ? '▲' : '▼'}</span>
                      )}
                    </button>
                  ) : (
                    <span style={{ padding: '0 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>{col.label}</span>
                  )}
                </div>
              );
            })}
          </div>
          <div ref={rowsScrollRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'auto' }}>
          {wlDraggingIdx !== null && wlDropGap === 0 ? <DropInsetLine /> : null}
          {displayWlItems.map((it, wi) => {
            const data = it.type === 'index' ? indicesMap[it.symbol] : stocksMap[it.symbol];
            const oneDay = it.type === 'index' ? data?.change_pct : data?.['Change %'];
            const oneMonth = it.type === 'index' ? data?.change_30d : data?.['Monthly Change %'];
            const price = it.type === 'index' ? data?.last_price : data?.Price;
            const mcap = it.type === 'index' ? null : data?.['Market Cap'];
            const symColor = oneDay > 0 ? 'var(--accent-green)' : oneDay < 0 ? 'var(--accent-red)' : 'var(--text-primary)';
            const isSelected = selectedItem?.symbol === it.symbol && selectedItem?.type === it.type;
            const canDrag = displayWlItems.length > 1;
            const symKey = String(it.symbol || '').trim().toUpperCase();
            const beatRaw = it.type !== 'index' ? wlBeatBySymbol.get(symKey) : null;
            const upcomingRaw = it.type !== 'index' ? wlEarningsBySymbol.get(symKey) : null;
            const rowHighlight = it.type !== 'index'
              ? resolveEarningsRowHighlight(beatRaw, upcomingRaw)
              : { kind: null, info: null };
            const beatInfo = rowHighlight.kind === 'beat' ? rowHighlight.info : null;
            const upcomingInfo = rowHighlight.kind === 'upcoming' ? rowHighlight.info : null;
            const earningsHighlight = beatInfo || upcomingInfo;
            const isBeatHighlight = !!beatInfo;
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
              <React.Fragment key={`${it.type}:${it.symbol}`}>
              <div
                ref={el => { wlRowRefs.current[`${String(it.type || '').toLowerCase()}:${String(it.symbol || '').toUpperCase()}`] = el; }}
                onClick={() => { onAppSelectedItemChange(it); setLastChange(null); setLastPrice(null); setCrosshairTime(null); }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  if (onContextMenuRequest && activeWatchlist?.name) {
                    onContextMenuRequest({
                      x: e.clientX,
                      y: e.clientY,
                      symbol: it.symbol,
                      type: it.type,
                      sourcePage: 'watchlist',
                      watchlistName: activeWatchlist.name,
                    });
                  }
                }}
                onDragOver={canDrag ? e => onWlDragOver(e, wi) : undefined}
                onDrop={canDrag ? onWlDrop : undefined}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  borderBottom: '1px solid var(--border-light)',
                  height: earningsHighlight ? PORTFOLIO_EARNINGS_ROW_HEIGHT : STOCK_LIST_ROW_HEIGHT,
                  cursor: 'pointer',
                  backgroundColor: rowBg,
                  borderLeft: rowBorderLeft,
                  opacity: wlDraggingIdx === wi ? 0.45 : 1,
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
                <div style={{ width: WL_COLS[0].width, minWidth: WL_COLS[0].width, flexShrink: 0, padding: canDrag ? '0 4px 0 6px' : '0 8px', borderRight: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', overflow: 'hidden', gap: 4 }}>
                  {canDrag ? (
                    <span
                      title="Drag to reorder"
                      draggable
                      onDragStart={e => { e.stopPropagation(); onWlDragStart(e, wi); }}
                      onDragEnd={e => { e.stopPropagation(); onWlDragEnd(); }}
                      onClick={e => e.stopPropagation()}
                      style={{
                        flexShrink: 0,
                        width: 14,
                        cursor: 'grab',
                        color: 'var(--text-muted)',
                        fontSize: 10,
                        lineHeight: 1,
                        userSelect: 'none',
                        letterSpacing: '-0.12em',
                      }}
                    >⋮⋮</span>
                  ) : null}
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
                      onAppSelectedItemChange(it);
                      setLastChange(null);
                      setLastPrice(null);
                      setCrosshairTime(null);
                      openWlEarningsModalFromSymbol(it);
                    } : undefined}
                    title={earningsHighlight ? 'Click for quarterly results and company profile' : it.symbol}
                  >
                    <span style={{ fontFamily: 'var(--font-mono)', color: symColor, fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', lineHeight: 1.2 }}>{it.symbol}</span>
                    {isBeatHighlight ? (
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 600,
                          fontFamily: 'var(--font-mono)',
                          color: DUAL_BEAT_LABEL_COLOR,
                          lineHeight: 1.15,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        Beat EPS+Rev
                      </span>
                    ) : upcomingInfo ? (
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 600,
                          fontFamily: 'var(--font-mono)',
                          color: PORTFOLIO_EARNINGS_LABEL_COLOR,
                          lineHeight: 1.15,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        E {formatEarningsBadgeDate(upcomingInfo.earnings_release_next_date)}
                      </span>
                    ) : null}
                  </div>
                </div>
                <div style={{ width: WL_COLS[1].width, minWidth: WL_COLS[1].width, flexShrink: 0, padding: '0 8px', display: 'flex', alignItems: 'center', borderRight: '1px solid var(--border-light)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{formatMarketCap(mcap)}</span>
                </div>
                <div style={{ width: WL_COLS[2].width, minWidth: WL_COLS[2].width, flexShrink: 0, padding: '0 4px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRight: '1px solid var(--border-light)' }} onClick={e => e.stopPropagation()}>
                  <InstrumentNotesIcon symbol={it.symbol} instrumentType={it.type === 'index' ? 'index' : 'stock'} />
                </div>
                <div style={{ width: WL_COLS[3].width, minWidth: WL_COLS[3].width, flexShrink: 0, padding: '0 8px', display: 'flex', alignItems: 'center', borderRight: '1px solid var(--border-light)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)' }}>{price != null ? `₹${Number(price).toFixed(2)}` : '—'}</span>
                </div>
                <div style={{ width: WL_COLS[4].width, minWidth: WL_COLS[4].width, flexShrink: 0, padding: '0 8px', display: 'flex', alignItems: 'center', borderRight: '1px solid var(--border-light)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500, color: oneDay > 0 ? 'var(--accent-green)' : oneDay < 0 ? 'var(--accent-red)' : 'var(--text-muted)' }}>{oneDay != null ? `${oneDay > 0 ? '+' : ''}${Number(oneDay).toFixed(2)}%` : '—'}</span>
                </div>
                <div style={{ width: WL_COLS[5].width, minWidth: WL_COLS[5].width, flexShrink: 0, padding: '0 8px', display: 'flex', alignItems: 'center', borderRight: '1px solid var(--border-light)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500, color: oneMonth > 0 ? 'var(--accent-green)' : oneMonth < 0 ? 'var(--accent-red)' : 'var(--text-muted)' }}>{oneMonth != null ? `${oneMonth > 0 ? '+' : ''}${Number(oneMonth).toFixed(2)}%` : '—'}</span>
                </div>
                <div style={{ width: WL_COLS[6].width, minWidth: WL_COLS[6].width, flexShrink: 0, padding: '0 8px' }}>
                  <button type="button" onClick={(e) => { e.stopPropagation(); removeItemFromActive(it); }} style={{ background: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
                </div>
              </div>
              {wlDraggingIdx !== null && wlDropGap === wi + 1 ? <DropInsetLine /> : null}
              </React.Fragment>
            );
          })}
          </div>
          <div style={stockListFooterStripStyle}>
            {displayWlItems.length} {displayWlItems.length === 1 ? 'symbol' : 'symbols'}
            <button
              type="button"
              onClick={handleWlEarningsPriorityControlClick}
              aria-pressed={wlEarningsPriorityEnabled}
              aria-label={`Earnings priority sort ${wlEarningsPriorityEnabled ? 'enabled' : 'disabled'}, ${wlEarningsPriorityDir === 'asc' ? 'nearest dates first' : 'furthest dates first'}`}
              title={wlEarningsPriorityEnabled
                ? 'Toggle earnings-priority date direction'
                : 'Re-enable earnings-priority sorting'}
              style={{
                marginLeft: 8,
                padding: 0,
                border: 'none',
                background: 'none',
                color: wlEarningsPriorityEnabled ? 'var(--accent-blue)' : 'var(--text-secondary)',
                cursor: 'pointer',
                font: 'inherit',
              }}
            >
              · Earnings priority {wlEarningsPriorityDir === 'asc' ? '▲' : '▼'}
            </button>
            {wlBeatCount > 0 && (
              <span style={{ marginLeft: 8, color: DUAL_BEAT_LABEL_COLOR }}>
                · {wlBeatCount} beat EPS+Rev ({DUAL_BEAT_WINDOW_DAYS}d)
              </span>
            )}
            {wlEarningsCount > 0 && (
              <span style={{ marginLeft: 8, color: PORTFOLIO_EARNINGS_LABEL_COLOR }}>
                · {wlEarningsCount} reporting in {WATCHLIST_EARNINGS_WINDOW_DAYS} days
              </span>
            )}
          </div>
        </div>
        <div
          onMouseDown={onDividerMouseDown}
          style={{ width: 4, backgroundColor: 'var(--border)', cursor: 'col-resize', flexShrink: 0, transition: 'background 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.backgroundColor = 'var(--border)'}
        />
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {!selectedItem ? (
            <div style={{ margin: 'auto', color: 'var(--text-muted)' }}>Select an item in the watchlist</div>
          ) : (
            <DrawingMirrorProvider
              mirrorStorageKey={
                selectedItem && (chartLayout === '2h' || chartLayout === '3h')
                  ? `wl:${selectedItem.type}:${selectedItem.symbol}:mirror`
                  : null
              }
              mirrorContextId={`wl-split-${selectedItem?.type || 'x'}-${selectedItem?.symbol || 'none'}`}
            >
            <DrawingWorkspaceProvider workspaceId={`wl-${activeWatchlist?.name || 'list'}-${selectedItem.symbol}`}>
            <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden', position: 'relative' }}>
              <DrawingToolbarConnected />
              <DrawingFloatPaletteConnected />
              {renderPanel(selectedItem, timeframe, setTimeframe, (pct, price) => { setLastChange(pct); setLastPrice(price); }, `${selectedItem.symbol}-p1-${timeframe}`, chartLayout !== 'single')}
              {(chartLayout === '2h' || chartLayout === '3h') && renderPanel(selectedItem, timeframe2, setTimeframe2, () => {}, `${selectedItem.symbol}-p2-${timeframe2}`, chartLayout === '3h')}
              {chartLayout === '3h' && renderPanel(selectedItem, timeframe3, setTimeframe3, () => {}, `${selectedItem.symbol}-p3-${timeframe3}`, false)}
            </div>
            </DrawingWorkspaceProvider>
            </DrawingMirrorProvider>
          )}
        </div>
      </div>

      {wlEarningsModal && (
        <PortfolioEarningsModal
          symbol={wlEarningsModal.symbol}
          variant={wlEarningsModal.variant}
          earningsDate={wlEarningsModal.earningsDate}
          daysUntil={wlEarningsModal.daysUntil}
          daysSinceReport={wlEarningsModal.daysSinceReport}
          onClose={() => setWlEarningsModal(null)}
          onOpenChart={onOpenChart}
        />
      )}
    </div>
  );
}
