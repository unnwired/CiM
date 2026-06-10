/* eslint-disable react-hooks/exhaustive-deps */
import React, { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'react';
import axios from 'axios';
import ChartContainer        from '../components/chart/ChartContainer';
import ChartHeaderBar        from '../components/chart/ChartHeaderBar';
import EMAFilterBuilder      from '../components/EMAFilterBuilder';
import MACDFilterBuilder     from '../components/MACDFilterBuilder';
import MACDHistChainFilterBuilder from '../components/MACDHistChainFilterBuilder';
import StochRSIFilterBuilder from '../components/StochRSIFilterBuilder';
import PriceFilterBuilder    from '../components/PriceFilterBuilder';
import MarketCapFilterBuilder from '../components/MarketCapFilterBuilder';
import EarningsFilterBuilder from '../components/EarningsFilterBuilder';
import EMAControls           from '../components/chart/EMAControls';
import IndexTopBar           from '../components/chart/IndexTopBar';
import IndexChartContainer   from '../components/chart/IndexChartContainer';
import DrawingToolsDesignControl from '../components/chart/drawing/DrawingToolsDesignControl';
import { DrawingMirrorProvider } from '../components/chart/drawing/DrawingMirrorContext';
import { DrawingWorkspaceProvider } from '../components/chart/drawing/DrawingWorkspaceContext';
import { DrawingToolbarConnected, DrawingFloatPaletteConnected } from '../components/chart/drawing/DrawingToolbar';
import { searchUniverse, addPortfolioItem } from '../api/client';
import { formatMarketCap } from '../utils/formatMarketCap';
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
import { applySavedOrder, reorderByGap, insertionGapFromRowHover, portfolioRowKey } from '../utils/listOrder';
import { setListDragImage, DropInsetLine } from '../utils/listDnD';
import {
  STOCK_LIST_HEADER_HEIGHT,
  STOCK_LIST_ROW_HEIGHT,
  stockListHeaderStripStyle,
  stockListFooterStripStyle,
} from '../components/stockTableChrome';
import InstrumentNotesIcon from '../components/InstrumentNotesIcon';
import ExternalFinancialsLinks from '../components/ExternalFinancialsLinks';
import PortfolioEarningsModal from '../components/PortfolioEarningsModal';
import {
  buildDualBeatEarningsMap,
  buildUpcomingEarningsMap,
  PORTFOLIO_EARNINGS_WINDOW_DAYS,
  DUAL_BEAT_WINDOW_DAYS,
  EARNINGS_PRIORITY_DEFAULT_DIR,
  formatEarningsBadgeDate,
  PORTFOLIO_EARNINGS_BORDER,
  PORTFOLIO_EARNINGS_ROW_BG,
  PORTFOLIO_EARNINGS_ROW_HEIGHT,
  PORTFOLIO_EARNINGS_ROW_HOVER,
  PORTFOLIO_EARNINGS_LABEL_COLOR,
  DUAL_BEAT_ROW_BG,
  DUAL_BEAT_BORDER,
  DUAL_BEAT_ROW_HOVER,
  DUAL_BEAT_LABEL_COLOR,
  resolveEarningsRowHighlight,
  sortItemsByEarningsPriority,
} from '../utils/portfolioEarnings';

const API = '';

/** Above chart canvas / panels so toolbar popovers are never occluded by the chart body (later sibling paint order). */
const CHART_TOOLBAR_OVERLAY_Z = 200000;
/** Dashboard chart toolbar (search, View, Sector, …) must sit above the filter row so dropdowns are not covered. */
const DASHBOARD_CHART_TOOLBAR_Z = 50;
/** Filter row above chart body only; keep below DASHBOARD_CHART_TOOLBAR_Z so top-bar menus win. */
const DASHBOARD_FILTER_BAR_Z = 15;
const STOCKS_PAGE_SIZE = 150;
const FILTERED_FULL_LIST_PAGE_SIZE = 500;
const PREFETCH_BUFFER_ROWS = 20; // Start fetching next page around row 130 of each 150 block

function filtersComparable(filters) {
  return (filters || []).map(({ label, ...rest }) => rest);
}

function enabledFiltersComparable(filters) {
  return filtersComparable((filters || []).filter(f => f?.enabled !== false));
}

function snapshotPresetFilters(filters) {
  return JSON.parse(JSON.stringify(filtersComparable(filters)));
}
const LAYOUTS = [
  { key: 'single', label: 'Single',              desc: 'One chart panel'              },
  { key: '2h',     label: '2 — Multi Timeframe', desc: 'Same stock, two timeframes'   },
  { key: '3h',     label: '3 — Multi Timeframe', desc: 'Same stock, three timeframes' },
];

const FILTER_MENU_ITEMS = [
  { key: 'ema',       label: 'EMA'        },
  { key: 'macd',      label: 'MACD'       },
  { key: 'macd_hist_chain', label: 'MACD Histogram' },
  { key: 'stochrsi',  label: 'StochRSI'   },
  { key: 'price',     label: 'Price'      },
  { key: 'marketcap', label: 'Market Cap' },
  { key: 'earnings',  label: 'Earnings'   },
];

const MONTH_NAMES = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function SectorCountBadge({ n }) {
  if (n <= 0) return null;
  const t = n > 99 ? '99+' : String(n);
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      minWidth: 16, height: 16, padding: '0 4px', borderRadius: 8,
      backgroundColor: 'var(--accent-blue)', color: '#fff', fontSize: 10, fontWeight: 700,
      marginLeft: 5, lineHeight: 1, fontFamily: 'var(--font-mono)',
    }}>{t}</span>
  );
}

function buildFilterLabel(f) {
  if (f.filter_type === 'marketcap') {
    if (f.from_value !== null && f.to_value !== null) {
      return `Mkt Cap ${formatMarketCap(f.from_value)}–${formatMarketCap(f.to_value)}`;
    }
    if (f.from_value !== null) return `Mkt Cap ≥ ${formatMarketCap(f.from_value)}`;
    return `Mkt Cap ≤ ${formatMarketCap(f.to_value)}`;
  }
  if (f.filter_type === 'price') {
    const cond = { above:'>',above_eq:'≥',below:'<',below_eq:'≤',crosses_up:'↑✕',crosses_down:'↓✕',above_pct:`>${f.pct_value}%`,below_pct:`<${f.pct_value}%` }[f.condition] || '>';
    const tgt  = f.target === 'ema'
      ? `EMA ${f.ema_period} (${f.timeframe})`
      : `${f.target.charAt(0).toUpperCase() + f.target.slice(1)} (${f.timeframe})`;
    return `Price ${cond} ${tgt}`;
  }
  if (f.filter_type === 'stochrsi') {
    const srcLabel  = f.source === 'k' ? 'StochRSI %K' : 'StochRSI %D';
    const condLabel = { above:'>',above_eq:'≥',below:'<',below_eq:'≤',crosses_up:'↑✕',crosses_down:'↓✕',above_pct:`>${f.pct_value}%`,below_pct:`<${f.pct_value}%` }[f.condition] || '>';
    const tgtLabel  = f.target === 'value' ? String(f.target_value) : f.target === 'k' ? '%K' : '%D';
    return `${srcLabel} (${f.timeframe}) ${condLabel} ${tgtLabel}`;
  }
  if (f.filter_type === 'macd') {
    const srcLabel  = f.source === 'macd' ? 'MACD Level' : 'MACD Signal';
    const condLabel = { above:'>',above_eq:'≥',below:'<',below_eq:'≤',crosses_up:'↑✕',crosses_down:'↓✕',above_pct:`>${f.pct_value}%`,below_pct:`<${f.pct_value}%` }[f.condition] || '>';
    const tgtLabel  = f.target === 'value' ? String(f.target_value) : f.target === 'macd' ? 'MACD Level' : 'MACD Signal';
    return `${srcLabel} (${f.timeframe}) ${condLabel} ${tgtLabel}`;
  }
  if (f.filter_type === 'macd_hist_chain') {
    const mode = f.chain_mode === 'increasing' ? 'increasing' : 'receding';
    const side = f.histogram_side === 'positive' ? 'pos' : f.histogram_side === 'both' ? 'both' : 'neg';
    const cross = f.allow_cross_zero ? 'cross-zero' : 'same-side';
    return `MACD Histogram (${f.timeframe}) ${mode} ${f.bars_to_compare} bars · stragglers ${f.allowed_stragglers} · ${side} · ${cross}`;
  }
  if (f.filter_type === 'earnings') {
    const parts = ['Earnings'];
    const rw = f.report_window || 'month_range';
    if (rw === 'this_week') parts.push('This week');
    else if (rw === 'prev_week') parts.push('Prev week');
    else {
      const fm = MONTH_NAMES[f.from_month] || f.from_month;
      const tm = MONTH_NAMES[f.to_month] || f.to_month;
      parts.push(`${fm} ${f.from_year} – ${tm} ${f.to_year}`);
    }
    const bounds = [];
    if (f.eps_surprise_min != null && f.eps_surprise_min !== '') bounds.push(`EPS ≥ ${f.eps_surprise_min}%`);
    if (f.eps_surprise_max != null && f.eps_surprise_max !== '') bounds.push(`EPS ≤ ${f.eps_surprise_max}%`);
    if (f.revenue_surprise_min != null && f.revenue_surprise_min !== '') bounds.push(`Rev ≥ ${f.revenue_surprise_min}%`);
    if (f.revenue_surprise_max != null && f.revenue_surprise_max !== '') bounds.push(`Rev ≤ ${f.revenue_surprise_max}%`);
    if (bounds.length) parts.push(bounds.join(', '));
    return parts.join(' · ');
  }
  // EMA
  const cond = { above:'>',above_eq:'≥',below:'<',below_eq:'≤',crosses_up:'↑✕',crosses_down:'↓✕',above_pct:`>${f.pct_value}%`,below_pct:`<${f.pct_value}%` }[f.condition] || '>';
  const tgt  = f.target === 'ema' ? `EMA ${f.target_ema_period} (${f.timeframe})` : f.target.charAt(0).toUpperCase() + f.target.slice(1);
  return `EMA ${f.ema_period} (${f.timeframe}) ${cond} ${tgt}`;
}

export default function DashboardPage({
  pageMode = 'pulse',
  onOpenChart,
  onAddStocksToWatchlist,
  watchlists = [],
  onGoToWatchlist,
  onContextMenuRequest,
}) {
  const [stocks, setStocks]                 = useState([]);
  const [total, setTotal]                   = useState(0);
  const [loading, setLoading]               = useState(true);
  const [loadingMore, setLoadingMore]       = useState(false);
  const [nextPage, setNextPage]             = useState(2);
  const [hasMorePages, setHasMorePages]     = useState(false);
  const [search, setSearch]                 = useState('');
  const [sortBy, setSortBy]                 = useState('Market Cap');
  const [sortDir, setSortDir]               = useState('desc');
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [selectedSymbols, setSelectedSymbols] = useState(new Set());
  const [lastSelectedIndex, setLastSelectedIndex] = useState(null);

  const [timeframe,  setTimeframe]  = useState(DEFAULT_CHART_TIMEFRAME_1);
  const [timeframe2, setTimeframe2] = useState(DEFAULT_CHART_TIMEFRAME_2);
  const [timeframe3, setTimeframe3] = useState(DEFAULT_CHART_TIMEFRAME_3);
  const [lastCandleChange, setLastCandleChange] = useState(null);
  const [lastCandlePrice,  setLastCandlePrice]  = useState(null);

  const [emas,          setEmas]          = useState(() => getPersistedEmaSet());
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(true));
  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());
  const [panelOrder,    setPanelOrder]    = useState(['stochrsi', 'macd']);
  const [crosshairTime, setCrosshairTime] = useState(null);

  const [selectedMarketSectors, setSelectedMarketSectors] = useState([]);
  const [canonicalMarketSectors, setCanonicalMarketSectors] = useState([]);
  const [sectorOpen, setSectorOpen]       = useState(false);
  const sectorRef                     = useRef(null);
  const [selectedKind, setSelectedKind] = useState('stock');
  const [pickOpen, setPickOpen]         = useState(false);
  const [pickStocks, setPickStocks]     = useState([]);
  const [pickIndices, setPickIndices]  = useState([]);
  const searchWrapRef                 = useRef(null);
  const searchInputRef                = useRef(null);
  const pickTimerRef                  = useRef(null);
  /** Fixed viewport coords for toolbar menus (toolbar uses overflow-x:auto, which clips position:absolute children). */
  const [searchDropdownRect, setSearchDropdownRect] = useState(null);
  const [sectorDropdownRect, setSectorDropdownRect] = useState(null);
  const [indicatorMenuRect, setIndicatorMenuRect] = useState(null);
  const [viewMenuRect, setViewMenuRect] = useState(null);

  const [indOpen,     setIndOpen]     = useState(false);
  const [viewOpen,    setViewOpen]    = useState(false);
  const [chartLayout, setChartLayout] = useState(DEFAULT_CHART_LAYOUT);
  const indRef                        = useRef(null);
  const viewRef                       = useRef(null);

  // Filters
  const [activeFilters,        setActiveFilters]        = useState([]);
  const [filterMenuOpen,       setFilterMenuOpen]       = useState(false);
  const [editingIdx,           setEditingIdx]           = useState(null);
  const [emaFilterOpen,        setEmaFilterOpen]        = useState(false);
  const [macdFilterOpen,       setMacdFilterOpen]       = useState(false);
  const [macdHistChainFilterOpen, setMacdHistChainFilterOpen] = useState(false);
  const [stochrsiFilterOpen,   setStochrsiFilterOpen]   = useState(false);
  const [priceFilterOpen,      setPriceFilterOpen]      = useState(false);
  const [marketcapFilterOpen,  setMarketcapFilterOpen]  = useState(false);
  const [earningsFilterOpen,   setEarningsFilterOpen]   = useState(false);

  // Presets
  const [presets,         setPresets]         = useState([]);
  const [presetsOpen,     setPresetsOpen]     = useState(false);
  const [saveNameOpen,    setSaveNameOpen]     = useState(false);
  const [saveNameValue,   setSaveNameValue]    = useState('');
  const [activePresetName, setActivePresetName] = useState(null);
  const [presetFiltersBaseline, setPresetFiltersBaseline] = useState([]);
  const [renamingPresetName, setRenamingPresetName] = useState(null);
  const [renamePresetValue, setRenamePresetValue] = useState('');
  const presetsRef                             = useRef(null);
  const filterMenuRef                          = useRef(null);
  const importFileRef                          = useRef(null);
  const [wlPickOpen, setWlPickOpen]             = useState(false);
  const [wlPickRect, setWlPickRect]           = useState(null);
  const wlPickWrapRef                         = useRef(null);
  const wlBtnWatchlistRef                     = useRef(null);
  const addAllRowRef                          = useRef(null);
  const [addAllMenuOpen, setAddAllMenuOpen]   = useState(false);
  const [addAllMenuRect, setAddAllMenuRect]   = useState(null);
  const [addMenuMode, setAddMenuMode]         = useState('all');

  const presetDirty = useMemo(() => {
    if (!activePresetName || activeFilters.length === 0) return false;
    return JSON.stringify(filtersComparable(activeFilters)) !== JSON.stringify(presetFiltersBaseline);
  }, [activePresetName, activeFilters, presetFiltersBaseline]);

  useEffect(() => {
    if (!activePresetName) setPresetFiltersBaseline([]);
  }, [activePresetName]);

  useEffect(() => {
    if (!presetsOpen) {
      setRenamingPresetName(null);
      setRenamePresetValue('');
    }
  }, [presetsOpen]);

  const [paneWidth, setPaneWidth]   = useState(320);
  const draggingRef                 = useRef(false);
  const startXRef                   = useRef(0);
  const startWidthRef               = useRef(0);
  const wrapperRef                  = useRef(null);
  const currentHeightsRef           = useRef({});
  const rowRefs                     = useRef({});
  const pfDragIdxRef                = useRef(null);
  const pfDropGapRef                = useRef(null);
  const [pfDropGap, setPfDropGap]   = useState(null);
  const [pfDraggingIdx, setPfDraggingIdx] = useState(null);
  const headerScrollRef             = useRef(null);
  const rowsScrollRef               = useRef(null);
  const chipsRailRef                = useRef(null);
  const [chipsScrollEdges, setChipsScrollEdges] = useState({ canScroll: false, atStart: true, atEnd: true });
  const hasActiveUniverseFilters = activeFilters.some(f => f?.enabled !== false) || selectedMarketSectors.length > 0;

  /** Portfolio table: user-defined row order (persisted). */
  const [portfolioUseCustomRowOrder, setPortfolioUseCustomRowOrder] = useState(false);
  const [portfolioRowOrder, setPortfolioRowOrder] = useState(null);
  /** Portfolio-only: upcoming earnings within rolling 30 days (stocks only). */
  const [portfolioEarningsBySymbol, setPortfolioEarningsBySymbol] = useState(() => new Map());
  const [portfolioBeatBySymbol, setPortfolioBeatBySymbol] = useState(() => new Map());
  const [portfolioEarningsModal, setPortfolioEarningsModal] = useState(null);
  const [portfolioEarningsPriorityEnabled, setPortfolioEarningsPriorityEnabled] = useState(true);
  const [portfolioEarningsPriorityDir, setPortfolioEarningsPriorityDir] = useState(EARNINGS_PRIORITY_DEFAULT_DIR);

  const portfolioStockSymbols = useMemo(() => {
    if (pageMode !== 'portfolio') return new Set();
    return new Set(
      stocks
        .filter(s => s.instrumentType !== 'index')
        .map(s => String(s.Symbol || '').trim().toUpperCase())
        .filter(Boolean),
    );
  }, [pageMode, stocks]);

  const portfolioEarningsCount = useMemo(() => {
    if (pageMode !== 'portfolio') return 0;
    let n = 0;
    for (const sym of portfolioEarningsBySymbol.keys()) {
      const highlight = resolveEarningsRowHighlight(
        portfolioBeatBySymbol.get(sym),
        portfolioEarningsBySymbol.get(sym),
      );
      if (highlight.kind === 'upcoming') n += 1;
    }
    return n;
  }, [pageMode, portfolioEarningsBySymbol, portfolioBeatBySymbol]);

  const portfolioBeatCount = useMemo(() => {
    if (pageMode !== 'portfolio') return 0;
    let n = 0;
    for (const sym of portfolioBeatBySymbol.keys()) {
      const highlight = resolveEarningsRowHighlight(
        portfolioBeatBySymbol.get(sym),
        portfolioEarningsBySymbol.get(sym),
      );
      if (highlight.kind === 'beat') n += 1;
    }
    return n;
  }, [pageMode, portfolioEarningsBySymbol, portfolioBeatBySymbol]);

  useEffect(() => {
    if (pageMode !== 'portfolio') return;
    setPortfolioEarningsPriorityEnabled(true);
    setPortfolioEarningsPriorityDir(EARNINGS_PRIORITY_DEFAULT_DIR);
  }, [pageMode]);

  useEffect(() => {
    if (pageMode !== 'portfolio') {
      setPortfolioEarningsBySymbol(new Map());
      setPortfolioBeatBySymbol(new Map());
      setPortfolioEarningsModal(null);
      return undefined;
    }
    if (portfolioStockSymbols.size === 0) {
      setPortfolioEarningsBySymbol(new Map());
      setPortfolioBeatBySymbol(new Map());
      return undefined;
    }
    let cancelled = false;
    (async () => {
      const [upcomingSettled, beatSettled] = await Promise.allSettled([
        axios.get(`${API}/api/earnings-beats`, {
          params: { mode: 'upcoming', period: 'rolling_30_days', limit: 2000 },
        }),
        axios.get(`${API}/api/earnings-beats`, {
          params: {
            mode: 'reported',
            report_window: 'rolling_10_days',
            limit: 2000,
            symbols: [...portfolioStockSymbols].join(','),
          },
        }),
      ]);
      if (cancelled) return;
      if (upcomingSettled.status === 'fulfilled') {
        setPortfolioEarningsBySymbol(
          buildUpcomingEarningsMap(
            upcomingSettled.value.data?.rows || [],
            portfolioStockSymbols,
            PORTFOLIO_EARNINGS_WINDOW_DAYS,
          ),
        );
      } else {
        setPortfolioEarningsBySymbol(new Map());
      }
      if (beatSettled.status === 'fulfilled') {
        setPortfolioBeatBySymbol(
          buildDualBeatEarningsMap(beatSettled.value.data?.rows || [], portfolioStockSymbols),
        );
      } else {
        setPortfolioBeatBySymbol(new Map());
      }
    })();
    return () => { cancelled = true; };
  }, [pageMode, portfolioStockSymbols]);

  const updateChipsScrollEdges = useCallback(() => {
    const el = chipsRailRef.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    const canScroll = scrollWidth > clientWidth + 0.5;
    setChipsScrollEdges({
      canScroll,
      atStart: !canScroll || scrollLeft <= 0.5,
      atEnd: !canScroll || scrollLeft + clientWidth >= scrollWidth - 0.5,
    });
  }, []);

  const scrollChipsBy = useCallback((delta) => {
    chipsRailRef.current?.scrollBy({ left: delta, behavior: 'smooth' });
  }, []);

  useLayoutEffect(() => {
    updateChipsScrollEdges();
  }, [activeFilters, updateChipsScrollEdges]);

  useLayoutEffect(() => {
    const el = chipsRailRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => updateChipsScrollEdges());
    ro.observe(el);
    return () => ro.disconnect();
  }, [updateChipsScrollEdges]);

  useEffect(() => {
    const el = chipsRailRef.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      if (el.scrollWidth <= el.clientWidth) return;
      e.preventDefault();
      // Wheel down (deltaY positive) scrolls right; wheel up scrolls left
      el.scrollLeft += e.deltaY;
      updateChipsScrollEdges();
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [updateChipsScrollEdges]);

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e) {
      if (viewRef.current    && !viewRef.current.contains(e.target))    setViewOpen(false);
      if (indRef.current     && !indRef.current.contains(e.target))     setIndOpen(false);
      if (presetsRef.current && !presetsRef.current.contains(e.target)) setPresetsOpen(false);
      if (filterMenuRef.current && !filterMenuRef.current.contains(e.target)) setFilterMenuOpen(false);
      if (sectorRef.current && !sectorRef.current.contains(e.target)) setSectorOpen(false);
      if (searchWrapRef.current && !searchWrapRef.current.contains(e.target)) setPickOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  // Load layout + presets + sector taxonomy on mount
  useEffect(() => {
    axios.get(`${API}/api/layout`).then(r => {
      if (r.data.dashboardPaneWidth)   setPaneWidth(r.data.dashboardPaneWidth);
      if (r.data.dashboardChartLayout) setChartLayout(r.data.dashboardChartLayout);
      if (r.data.dashboardTimeframe) setTimeframe(r.data.dashboardTimeframe);
      if (r.data.dashboardTimeframe2) setTimeframe2(r.data.dashboardTimeframe2);
      if (r.data.dashboardTimeframe3) setTimeframe3(normalizeSavedTimeframe3(r.data.dashboardTimeframe3));
      if (r.data.portfolioRowOrder && Array.isArray(r.data.portfolioRowOrder)) {
        setPortfolioRowOrder(r.data.portfolioRowOrder);
      }
      if (r.data.portfolioUseCustomRowOrder === false) {
        setPortfolioUseCustomRowOrder(false);
      } else if (r.data.portfolioRowOrder?.length) {
        setPortfolioUseCustomRowOrder(true);
      }
    }).catch(() => {});
    axios.get(`${API}/api/sector-mapping`).then(r => {
      setCanonicalMarketSectors(r.data.canonical_sectors || []);
    }).catch(() => {});
    loadPresets();
  }, []);

  async function loadPresets() {
    try {
      const r = await axios.get(`${API}/api/filter-presets`);
      const list = r.data.presets || [];
      setPresets(list);
      setActivePresetName(prev => (prev && !list.some(p => p.name === prev) ? null : prev));
    } catch {}
  }

  async function savePreset() {
    const name = saveNameValue.trim();
    if (!name) { alert('Please enter a preset name'); return; }
    if (activeFilters.length === 0) { alert('No active filters to save'); return; }
    try {
      await axios.post(`${API}/api/filter-presets`, { name, filters: activeFilters });
      setSaveNameValue('');
      setSaveNameOpen(false);
      if (name === activePresetName) {
        setPresetFiltersBaseline(snapshotPresetFilters(activeFilters));
      }
      loadPresets();
    } catch (e) {
      alert('Failed to save preset: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function updateActivePreset() {
    if (!activePresetName || activeFilters.length === 0) return;
    try {
      await axios.post(`${API}/api/filter-presets`, { name: activePresetName, filters: activeFilters });
      setPresetFiltersBaseline(snapshotPresetFilters(activeFilters));
      loadPresets();
    } catch (e) {
      alert('Failed to update preset: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function loadPreset(preset) {
    setPresetsOpen(false);
    setActivePresetName(preset.name);
    setPresetFiltersBaseline(snapshotPresetFilters(preset.filters));
    const withLabels = preset.filters.map(f => ({ ...f, label: f.label || buildFilterLabel(f) }));
    setActiveFilters(withLabels);
  }

  function cancelRenamePreset() {
    setRenamingPresetName(null);
    setRenamePresetValue('');
  }

  async function renamePreset() {
    const oldNm = renamingPresetName;
    if (!oldNm) return;
    const name = renamePresetValue.trim();
    if (!name || name === oldNm) {
      cancelRenamePreset();
      return;
    }
    try {
      await axios.patch(`${API}/api/filter-presets/${encodeURIComponent(oldNm)}`, { new_name: name });
      cancelRenamePreset();
      if (activePresetName === oldNm) setActivePresetName(name);
      await loadPresets();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  }

  async function deletePreset(name, e) {
    e.stopPropagation();
    try {
      await axios.delete(`${API}/api/filter-presets/${encodeURIComponent(name)}`);
      if (name === activePresetName) setActivePresetName(null);
      if (renamingPresetName === name) cancelRenamePreset();
      loadPresets();
    } catch {}
  }

  function handleExportPresets() {
    if (!presets.length) {
      alert('No presets available to export.');
      return;
    }
    try {
      const payload = {
        version: 1,
        exported_at: new Date().toISOString(),
        presets: presets.map(p => ({ name: p.name, filters: p.filters || [] })),
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      const a = document.createElement('a');
      a.href = url;
      a.download = `nse-pulse-filter-presets-${stamp}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Failed to export presets: ' + (e?.message || 'Unknown error'));
    }
  }

  async function handleImportPresetFile(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const imported = Array.isArray(parsed) ? parsed : (parsed?.presets || []);
      const cleaned = imported
        .filter(p => p && typeof p.name === 'string' && p.name.trim() && Array.isArray(p.filters))
        .map(p => ({ name: p.name.trim(), filters: p.filters }));

      if (!cleaned.length) {
        alert('No valid presets found in this file.');
        return;
      }

      const replaceAll = window.confirm(
        `Import ${cleaned.length} preset(s)?\n\n` +
        'Click OK to REPLACE existing presets.\n' +
        'Click Cancel to MERGE (keep existing + overwrite same names).'
      );

      if (replaceAll) {
        await Promise.all((presets || []).map(p =>
          axios.delete(`${API}/api/filter-presets/${encodeURIComponent(p.name)}`).catch(() => null)
        ));
        setActivePresetName(null);
      }

      for (const p of cleaned) {
        // Backend already does name-based replace.
        // Sequential writes keep server-side file writes simple and deterministic.
        // eslint-disable-next-line no-await-in-loop
        await axios.post(`${API}/api/filter-presets`, { name: p.name, filters: p.filters });
      }

      await loadPresets();
      setPresetsOpen(false);
      alert(`Imported ${cleaned.length} preset(s) successfully.`);
    } catch (err) {
      alert('Failed to import presets: ' + (err.response?.data?.detail || err.message));
    }
  }

  const loadStocks = useCallback(async () => {
    setLoading(true);
    try {
      const listUrl = pageMode === 'portfolio' ? `${API}/api/portfolio/stocks` : `${API}/api/stocks`;
      let loadedRows = [];
      const buildParams = (page, pageSize) => {
        const params = { page, pageSize, sortBy, sortDir };
        if (search) params.search = search;
        const enabledFilters = enabledFiltersComparable(activeFilters);
        if (enabledFilters.length) params.filters = JSON.stringify(enabledFilters);
        if (selectedMarketSectors.length) params.marketSectors = JSON.stringify(selectedMarketSectors);
        return params;
      };

      if (hasActiveUniverseFilters) {
        const first = await axios.get(listUrl, { params: buildParams(1, FILTERED_FULL_LIST_PAGE_SIZE) });
        let merged = first.data.data || [];
        const totalRows = first.data.total || 0;
        const pages = first.data.pages || Math.ceil(totalRows / FILTERED_FULL_LIST_PAGE_SIZE) || 1;
        for (let p = 2; p <= pages; p += 1) {
          const r = await axios.get(listUrl, { params: buildParams(p, FILTERED_FULL_LIST_PAGE_SIZE) });
          merged = merged.concat(r.data.data || []);
        }
        loadedRows = merged;
        setStocks(merged);
        setTotal(totalRows);
        setNextPage(2);
        setHasMorePages(false);
      } else {
        const r = await axios.get(listUrl, { params: buildParams(1, STOCKS_PAGE_SIZE) });
        const data = r.data.data || [];
        loadedRows = data;
        setStocks(data);
        const totalRows = r.data.total || 0;
        setTotal(totalRows);
        setNextPage(2);
        setHasMorePages(data.length < totalRows);
      }
      setSelectedSymbol(prev => {
        if (prev || loadedRows.length === 0) return prev;
        setSelectedSymbols(new Set([loadedRows[0].Symbol]));
        setSelectedKind(loadedRows[0].instrumentType === 'index' ? 'index' : 'stock');
        return loadedRows[0].Symbol;
      });
    } catch {}
    setLoading(false);
  }, [activeFilters, hasActiveUniverseFilters, pageMode, search, selectedMarketSectors, sortBy, sortDir]);

  useEffect(() => { loadStocks(); }, [loadStocks]);

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

  const loadMoreStocks = useCallback(async () => {
    if (hasActiveUniverseFilters) return;
    if (loading || loadingMore || !hasMorePages) return;
    const listUrl = pageMode === 'portfolio' ? `${API}/api/portfolio/stocks` : `${API}/api/stocks`;
    setLoadingMore(true);
    try {
      const params = { page: nextPage, pageSize: STOCKS_PAGE_SIZE, sortBy, sortDir };
      if (search) params.search = search;
      if (activeFilters.length) params.filters = JSON.stringify(filtersComparable(activeFilters));
      if (selectedMarketSectors.length) params.marketSectors = JSON.stringify(selectedMarketSectors);
      const r = await axios.get(listUrl, { params });
      const data = r.data.data || [];
      setStocks(prev => [...prev, ...data]);
      const totalRows = r.data.total || 0;
      setTotal(totalRows);
      const loadedCount = (nextPage - 1) * STOCKS_PAGE_SIZE + data.length;
      setHasMorePages(loadedCount < totalRows && data.length > 0);
      setNextPage(prev => prev + 1);
    } catch {}
    setLoadingMore(false);
  }, [activeFilters, hasActiveUniverseFilters, hasMorePages, loading, loadingMore, nextPage, pageMode, search, selectedMarketSectors, sortBy, sortDir]);

  useEffect(() => {
    const el = rowsScrollRef.current;
    if (!el) return undefined;
    const onScroll = () => {
      if (headerScrollRef.current && headerScrollRef.current.scrollLeft !== el.scrollLeft) {
        headerScrollRef.current.scrollLeft = el.scrollLeft;
      }
      const approxRowH = 32;
      const lastVisibleRow = Math.floor((el.scrollTop + el.clientHeight) / approxRowH);
      if (lastVisibleRow >= stocks.length - PREFETCH_BUFFER_ROWS) {
        loadMoreStocks();
      }
    };
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, [loadMoreStocks, stocks.length]);

  useLayoutEffect(() => {
    const headerEl = headerScrollRef.current;
    const rowsEl = rowsScrollRef.current;
    if (!headerEl || !rowsEl) return;
    headerEl.scrollLeft = rowsEl.scrollLeft;
  }, [stocks.length, paneWidth, pageMode]);

  useLayoutEffect(() => {
    if (!pickOpen || !(pickStocks.length || pickIndices.length)) {
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
      let left = r.left;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      left = Math.min(Math.max(pad, left), maxLeft);
      setSearchDropdownRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [pickOpen, pickStocks.length, pickIndices.length]);

  useLayoutEffect(() => {
    if (!sectorOpen) {
      setSectorDropdownRect(null);
      return;
    }
    const el = sectorRef.current;
    if (!el) {
      setSectorDropdownRect(null);
      return;
    }
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = Math.max(280, r.width);
      let left = r.left;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      left = Math.min(Math.max(pad, left), maxLeft);
      setSectorDropdownRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [sectorOpen]);

  useLayoutEffect(() => {
    if (!indOpen) {
      setIndicatorMenuRect(null);
      return;
    }
    const el = indRef.current;
    if (!el) {
      setIndicatorMenuRect(null);
      return;
    }
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = Math.max(160, r.width);
      let left = r.left;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      left = Math.min(Math.max(pad, left), maxLeft);
      setIndicatorMenuRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [indOpen]);

  useLayoutEffect(() => {
    if (!viewOpen) {
      setViewMenuRect(null);
      return;
    }
    const el = viewRef.current;
    if (!el) {
      setViewMenuRect(null);
      return;
    }
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = 230;
      let left = r.right - width;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      left = Math.min(Math.max(pad, left), maxLeft);
      setViewMenuRect({ top: r.bottom + 4, left, width });
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
    if (!wlPickOpen) {
      setWlPickRect(null);
      return;
    }
    const el = wlBtnWatchlistRef.current;
    if (!el) {
      setWlPickRect(null);
      return;
    }
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = Math.max(200, 220);
      let left = r.left;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      left = Math.min(Math.max(pad, left), maxLeft);
      setWlPickRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [wlPickOpen]);

  useLayoutEffect(() => {
    if (!addAllMenuOpen) {
      setAddAllMenuRect(null);
      return;
    }
    const el = addAllRowRef.current;
    if (!el) {
      setAddAllMenuRect(null);
      return;
    }
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = 220;
      const pad = 8;
      const left = Math.min(r.right + 4, window.innerWidth - width - pad);
      const top  = Math.max(pad, Math.min(r.top, window.innerHeight - pad));
      setAddAllMenuRect({ top, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [addAllMenuOpen, addMenuMode]);

  useEffect(() => {
    if (!addAllMenuOpen) return undefined;
    function handleDoc(e) {
      if (wlPickWrapRef.current?.contains(e.target)) return;
      setAddAllMenuOpen(false);
    }
    document.addEventListener('mousedown', handleDoc);
    return () => document.removeEventListener('mousedown', handleDoc);
  }, [addAllMenuOpen]);

  useEffect(() => {
    if (!wlPickOpen) return undefined;
    function handleDoc(e) {
      if (wlPickWrapRef.current?.contains(e.target)) return;
      setWlPickOpen(null);
    }
    document.addEventListener('mousedown', handleDoc);
    return () => document.removeEventListener('mousedown', handleDoc);
  }, [wlPickOpen]);

  useEffect(() => {
    const onPf = () => { loadStocks(); };
    window.addEventListener('portfolio-updated', onPf);
    window.addEventListener('dashboard-refresh', onPf);
    return () => {
      window.removeEventListener('portfolio-updated', onPf);
      window.removeEventListener('dashboard-refresh', onPf);
    };
  }, [loadStocks]);

  useEffect(() => {
    if (pickTimerRef.current) clearTimeout(pickTimerRef.current);
    const q = search.trim();
    if (q.length < 1) {
      setPickStocks([]); setPickIndices([]); setPickOpen(false);
      return;
    }
    pickTimerRef.current = setTimeout(async () => {
      try {
        const d = await searchUniverse(q);
        setPickStocks(d.stocks || []);
        setPickIndices(d.indices || []);
        setPickOpen(true);
      } catch {
        setPickStocks([]); setPickIndices([]); setPickOpen(false);
      }
    }, 220);
    return () => { if (pickTimerRef.current) clearTimeout(pickTimerRef.current); };
  }, [search]);

  useEffect(() => {
    function onGlobalPick(e) {
      const d = e?.detail || {};
      const targetView = String(d.targetView || '');
      const isMatchingView = (pageMode === 'portfolio' && targetView === 'portfolio')
        || (pageMode !== 'portfolio' && targetView === 'dashboard');
      if (!isMatchingView) return;
      const symbol = String(d.symbol || '').toUpperCase();
      if (!symbol) return;
      const typ = String(d.type || 'stock').toLowerCase();
      setPickOpen(false);
      setSelectedKind(typ === 'index' ? 'index' : 'stock');
      setSelectedSymbol(symbol);
      if (typ !== 'index' && !stocks.some(s => s.Symbol === symbol)) {
        void (async () => {
          try {
            const r = await axios.get(`${API}/api/stock/${encodeURIComponent(symbol)}`);
            const row = r?.data || null;
            if (!row?.Symbol) return;
            setStocks(prev => {
              if (prev.some(s => s.Symbol === row.Symbol)) return prev;
              return [row, ...prev];
            });
          } catch {
            // Keep chart selection even if row materialization fails.
          }
        })();
      }
    }
    window.addEventListener('cim-global-search-select', onGlobalPick);
    return () => window.removeEventListener('cim-global-search-select', onGlobalPick);
  }, [pageMode, stocks]);

  async function handleAddPickToPortfolio(symbol, type) {
    try {
      await addPortfolioItem({ symbol, type });
      window.dispatchEvent(new CustomEvent('portfolio-updated'));
      setSearch('');
      setPickOpen(false);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  }

  const selectedStock = stocks.find(s => s.Symbol === selectedSymbol);
  const baseDisplayStocks = useMemo(() => {
    if (pageMode !== 'portfolio' || !portfolioUseCustomRowOrder || !portfolioRowOrder?.length) return stocks;
    return applySavedOrder(stocks, portfolioRowOrder, portfolioRowKey);
  }, [stocks, pageMode, portfolioUseCustomRowOrder, portfolioRowOrder]);
  const displayStocks = useMemo(() => {
    if (pageMode !== 'portfolio' || !portfolioEarningsPriorityEnabled) return baseDisplayStocks;
    return sortItemsByEarningsPriority(baseDisplayStocks, {
      getSymbol: stock => stock.Symbol,
      isEligible: stock => stock.instrumentType !== 'index',
      beatBySymbol: portfolioBeatBySymbol,
      upcomingBySymbol: portfolioEarningsBySymbol,
      dir: portfolioEarningsPriorityDir,
    });
  }, [
    baseDisplayStocks,
    pageMode,
    portfolioBeatBySymbol,
    portfolioEarningsBySymbol,
    portfolioEarningsPriorityDir,
    portfolioEarningsPriorityEnabled,
  ]);

  useEffect(() => {
    function handleKey(e) {
      if (!['ArrowUp','ArrowDown'].includes(e.key)) return;
      if (indOpen || sectorOpen) return;
      e.preventDefault();
      setSelectedSymbol(sym => {
        const idx  = displayStocks.findIndex(s => s.Symbol === sym);
        if (idx === -1) return sym;
        const next = e.key === 'ArrowDown'
          ? Math.min(idx + 1, displayStocks.length - 1)
          : Math.max(idx - 1, 0);
        setLastCandleChange(null);
        setLastCandlePrice(null);
        rowRefs.current[next]?.scrollIntoView({ block: 'nearest' });
        return displayStocks[next].Symbol;
      });
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [displayStocks, indOpen, sectorOpen]);

  function onDividerMouseDown(e) {
    e.preventDefault();
    draggingRef.current = true; startXRef.current = e.clientX; startWidthRef.current = paneWidth;
    function onMouseMove(ev) {
      if (!draggingRef.current) return;
      const total = wrapperRef.current?.clientWidth || 1200;
      setPaneWidth(Math.max(200, Math.min(total - 500, startWidthRef.current + ev.clientX - startXRef.current)));
    }
    function onMouseUp() { draggingRef.current = false; window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp); }
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  function handleSort(col) {
    if (col === 'note') return;
    if (pageMode === 'portfolio') {
      setPortfolioEarningsPriorityEnabled(false);
      setPortfolioUseCustomRowOrder(false);
      axios.post(`${API}/api/layout`, { portfolioUseCustomRowOrder: false }).catch(() => {});
    }
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortBy(col); setSortDir(col === 'Symbol' ? 'asc' : 'desc'); }
  }

  function handlePortfolioEarningsPriorityControlClick() {
    if (pageMode !== 'portfolio') return;
    if (!portfolioEarningsPriorityEnabled) {
      setPortfolioEarningsPriorityEnabled(true);
      return;
    }
    setPortfolioEarningsPriorityDir(d => (d === 'asc' ? 'desc' : 'asc'));
  }

  function persistPortfolioRowOrder(keys) {
    setPortfolioRowOrder(keys);
    setPortfolioUseCustomRowOrder(true);
    axios.post(`${API}/api/layout`, {
      portfolioRowOrder: keys,
      portfolioUseCustomRowOrder: true,
    }).catch(() => {});
  }

  function clearPortfolioDnD() {
    pfDragIdxRef.current = null;
    pfDropGapRef.current = null;
    setPfDropGap(null);
    setPfDraggingIdx(null);
  }

  function onPortfolioDragStart(e, idx) {
    pfDragIdxRef.current = idx;
    setPfDraggingIdx(idx);
    const stock = displayStocks[idx];
    if (!stock) return;
    const symLabel = stock.instrumentType === 'index' && stock.indexName ? stock.indexName : stock.Symbol;
    setListDragImage(e.dataTransfer, symLabel, stock.Symbol);
  }

  function onPortfolioDragOver(e, idx) {
    if (pageMode !== 'portfolio' || pfDragIdxRef.current === null) return;
    e.preventDefault();
    const gap = insertionGapFromRowHover(e.clientY, e.currentTarget, idx, displayStocks.length);
    pfDropGapRef.current = gap;
    setPfDropGap(gap);
  }

  function onPortfolioDrop(e) {
    e.preventDefault();
    if (pageMode !== 'portfolio') return;
    const from = pfDragIdxRef.current;
    const gap = pfDropGapRef.current;
    clearPortfolioDnD();
    if (from === null || gap === null || gap === undefined) return;
    const keys = displayStocks.map(portfolioRowKey);
    const nextKeys = reorderByGap(keys, from, gap);
    if (JSON.stringify(nextKeys) === JSON.stringify(keys)) return;
    persistPortfolioRowOrder(nextKeys);
  }

  function onPortfolioDragEnd() {
    clearPortfolioDnD();
  }

  function handleSaveLayout() {
    axios.post(`${API}/api/layout`, {
      ...currentHeightsRef.current,
      dashboardPaneWidth:   paneWidth,
      dashboardChartLayout: chartLayout,
      dashboardTimeframe: timeframe,
      dashboardTimeframe2: timeframe2,
      dashboardTimeframe3: timeframe3,
      ...(portfolioRowOrder?.length
        ? { portfolioRowOrder, portfolioUseCustomRowOrder: portfolioUseCustomRowOrder }
        : {}),
    }).then(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Layout saved.' }))).catch(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Failed to save layout.' })));
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

  function openEditFilter(idx) {
    setEditingIdx(idx);
    const f = activeFilters[idx];
    if (f.filter_type === 'macd')      setMacdFilterOpen(true);
    else if (f.filter_type === 'macd_hist_chain') setMacdHistChainFilterOpen(true);
    else if (f.filter_type === 'stochrsi')  setStochrsiFilterOpen(true);
    else if (f.filter_type === 'price')     setPriceFilterOpen(true);
    else if (f.filter_type === 'marketcap') setMarketcapFilterOpen(true);
    else if (f.filter_type === 'earnings') setEarningsFilterOpen(true);
    else setEmaFilterOpen(true);
  }

  function closeFilterBuilders() {
    setEmaFilterOpen(false);
    setMacdFilterOpen(false);
    setMacdHistChainFilterOpen(false);
    setStochrsiFilterOpen(false);
    setPriceFilterOpen(false);
    setMarketcapFilterOpen(false);
    setEarningsFilterOpen(false);
    setEditingIdx(null);
  }

  function applyFilter(filterDef) {
    closeFilterBuilders();
    const label = buildFilterLabel(filterDef);
    const entry = { ...filterDef, label, enabled: true };
    if (editingIdx !== null) {
      setActiveFilters(prev => prev.map((f, i) => i === editingIdx ? { ...entry, enabled: f?.enabled !== false } : f));
    } else {
      setActiveFilters(prev => [...prev, entry]);
    }
  }

  function removeFilter(idx) {
    const nf = activeFilters.filter((_, i) => i !== idx);
    setActiveFilters(nf);
    if (nf.length === 0) setActivePresetName(null);
  }

  function toggleFilterEnabled(idx) {
    setActiveFilters(prev => prev.map((f, i) => (
      i === idx ? { ...f, enabled: f?.enabled === false } : f
    )));
  }

  useEffect(() => {
    if (displayStocks.length === 0) return;
    const inList = displayStocks.some((s) => s.Symbol === selectedSymbol);
    if (!selectedSymbol || !inList) {
      const firstRow = displayStocks[0];
      setSelectedSymbol(firstRow.Symbol);
      setSelectedSymbols(new Set([firstRow.Symbol]));
      setSelectedKind(firstRow.instrumentType === 'index' ? 'index' : 'stock');
      setLastCandleChange(null);
      setLastCandlePrice(null);
    }
  }, [displayStocks, selectedSymbol]);

  useEffect(() => {
    if (!selectedSymbol || displayStocks.length === 0) return;
    const idx = displayStocks.findIndex(s => s.Symbol === selectedSymbol);
    if (idx < 0) return;
    rowRefs.current[idx]?.scrollIntoView({ block: 'nearest' });
  }, [displayStocks, selectedSymbol]);

  function handleRowSelect(stock, idx, e) {
    const symbol = stock.Symbol;
    if (e.shiftKey && lastSelectedIndex !== null) {
      const start = Math.min(lastSelectedIndex, idx);
      const end = Math.max(lastSelectedIndex, idx);
      const rangeSymbols = displayStocks.slice(start, end + 1).map(s => s.Symbol);
      setSelectedSymbols(prev => {
        const next = new Set(prev);
        for (const sym of rangeSymbols) next.add(sym);
        return next;
      });
    } else if (e.ctrlKey || e.metaKey) {
      setSelectedSymbols(prev => {
        const next = new Set(prev);
        if (next.has(symbol)) next.delete(symbol);
        else next.add(symbol);
        return next;
      });
      setLastSelectedIndex(idx);
    } else {
      setSelectedSymbols(new Set([symbol]));
      setLastSelectedIndex(idx);
    }
    setSelectedSymbol(symbol);
    setSelectedKind(stock.instrumentType === 'index' ? 'index' : 'stock');
    setLastCandleChange(null);
    setLastCandlePrice(null);
    setCrosshairTime(null);
  }

  function openPortfolioEarningsModalFromSymbol(stock, e) {
    if (pageMode !== 'portfolio' || stock.instrumentType === 'index') return;
    if (e.shiftKey || e.ctrlKey || e.metaKey) return;
    const sym = stock.Symbol;
    const highlight = resolveEarningsRowHighlight(
      portfolioBeatBySymbol.get(sym),
      portfolioEarningsBySymbol.get(sym),
    );
    if (!highlight.info) return;
    if (highlight.kind === 'beat') {
      setPortfolioEarningsModal({
        symbol: sym,
        variant: 'beat',
        earningsDate: highlight.info.earnings_release_date,
        daysSinceReport: highlight.info.days_since_report,
      });
      return;
    }
    setPortfolioEarningsModal({
      symbol: sym,
      variant: 'upcoming',
      earningsDate: highlight.info.earnings_release_next_date,
      daysUntil: highlight.info.days_until,
    });
  }

  const COLS = [
    { key: 'Symbol',           label: 'Symbol',   width: 90  },
    { key: 'Market Cap',       label: 'Mkt Cap',  width: 110 },
    { key: 'note',             label: '',         width: 36  },
    { key: 'Price',            label: 'Price',    width: 85  },
    { key: 'Change %',         label: '1D Chg %', width: 80  },
    { key: 'Monthly Change %', label: '1M Chg %', width: 80  },
  ];

  function renderPanel(symbol, tf, setTf, onLastChange, cacheKey, hasBorderRight) {
    return (
      <div key={cacheKey} style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', minWidth:0, borderRight: hasBorderRight ? '2px solid var(--border)' : 'none' }}>
        <ChartHeaderBar symbol={symbol} timeframe={tf}
          onTimeframeChange={newTf => { setTf(newTf); onLastChange(null, null); setCrosshairTime(null); }} />
        <ChartContainer key={cacheKey} symbol={symbol} timeframe={tf} emas={emas}
          volumeVisible={volumeVisible} visiblePanels={visiblePanels} panelOrder={panelOrder}
          onTogglePanel={handleTogglePanel} onMovePanel={handleMovePanel}
          onLastChange={onLastChange} onHeightsChange={h => { currentHeightsRef.current = h; }}
          onCrosshairMove={setCrosshairTime} crosshairTime={crosshairTime}
          drawingScopeId={`dash:${cacheKey}`}
          drawingAutoFocus={false} />
      </div>
    );
  }

  function renderIndexPanel(symbol, tf, setTf, onLastChange, cacheKey, hasBorderRight, indexMeta) {
    return (
      <div key={cacheKey} style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', minWidth:0, borderRight: hasBorderRight ? '2px solid var(--border)' : 'none' }}>
        <IndexTopBar
          index={indexMeta}
          timeframe={tf}
          onTimeframeChange={(newTf) => { setTf(newTf); onLastChange(null, null); setCrosshairTime(null); }}
          emas={emas}
          onEmasChange={setEmas}
          volumeVisible={volumeVisible}
          onToggleVolume={() => setVolumeVisible(v => !v)}
          visiblePanels={visiblePanels}
          onTogglePanel={handleTogglePanel}
          lastCandleChange={lastCandleChange}
          onShowConstituents={undefined}
          onSaveLayout={handleSaveLayout}
          onBack={undefined}
        />
        <IndexChartContainer
          symbol={symbol}
          timeframe={tf}
          emas={emas}
          volumeVisible={volumeVisible}
          visiblePanels={visiblePanels}
          panelOrder={panelOrder}
          onTogglePanel={handleTogglePanel}
          onMovePanel={handleMovePanel}
          onLastChange={onLastChange}
          onHeightsChange={h => { currentHeightsRef.current = h; }}
          onCrosshairMove={setCrosshairTime}
          crosshairTime={crosshairTime}
          drawingScopeId={`dash-idx:${cacheKey}`}
          drawingAutoFocus={false}
        />
      </div>
    );
  }

  function FilterChip({ f, idx }) {
    const [hovered, setHovered] = useState(false);
    const enabled = f?.enabled !== false;
    return (
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{ position:'relative', display:'inline-flex', alignItems:'center', paddingTop:8, paddingRight:8, paddingBottom:8, flexShrink:0, overflow:'visible' }}
      >
        <div
          style={{ position:'relative', display:'flex', alignItems:'stretch', border:`1px solid ${enabled ? 'var(--accent-blue)' : 'var(--border)'}`, borderRadius:5, height:24, fontSize:11, fontFamily:'var(--font-mono)', opacity: enabled ? 1 : 0.72, backgroundColor: hovered ? 'rgba(56,139,253,0.10)' : 'var(--bg-secondary)' }}
        >
          <span
            onClick={() => openEditFilter(idx)}
            title={f.label}
            style={{
              cursor:'pointer', userSelect:'none',
              maxWidth:220, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
              display:'inline-flex', alignItems:'center', padding:'0 10px', color: enabled ? 'var(--accent-blue)' : 'var(--text-secondary)',
            }}
          >{f.label}</span>
          <button
            type="button"
            onClick={() => toggleFilterEnabled(idx)}
            title={enabled ? 'Disable filter' : 'Enable filter'}
            style={{
              width:24, border:'none', borderLeft:'1px solid var(--border)', cursor:'pointer',
              backgroundColor:'transparent', color:'var(--text-secondary)',
              display:'inline-flex', alignItems:'center', justifyContent:'center', padding:0, flexShrink:0,
            }}
          >
            <span style={{ width:8, height:8, borderRadius:999, backgroundColor: enabled ? 'var(--accent-blue)' : 'var(--text-muted)', opacity: enabled ? 1 : 0.65 }} />
          </button>
          <button
            type="button"
            onClick={() => removeFilter(idx)}
            title="Remove filter"
            style={{
              position:'absolute', top:0, right:0, width:14, height:14,
              border:'none', backgroundColor:'transparent', color:'var(--accent-blue)',
              cursor:'pointer',
              padding:0, opacity: hovered ? 1 : 0, pointerEvents: hovered ? 'auto' : 'none',
              transform:'translate(50%, -50%)',
            }}
          >
            <svg
              width="8"
              height="8"
              viewBox="0 0 10 10"
              fill="none"
              aria-hidden="true"
              style={{ position:'absolute', left:'50%', top:'50%', transform:'translate(-50%, -50%)', display:'block' }}
            >
              <path d="M2 2L8 8M8 2L2 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', width:'100%', backgroundColor:'var(--bg-primary)', overflow:'hidden' }}>

      {/* ── Top bar (overflow-x:auto clips overflow; dropdowns must use position:fixed + getBoundingClientRect like search/sector/indicators/view) ── */}
      <div className="chart-app-toolbar" style={{ height:48, flexShrink:0, position:'relative', zIndex:DASHBOARD_CHART_TOOLBAR_Z, backgroundColor:'var(--bg-secondary)', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', padding:'0 12px', gap:10, overflowX:'auto' }}>
        <div ref={searchWrapRef} style={{ position:'relative', flexShrink:0 }}>
          <div style={{ display:'flex', alignItems:'center', gap:6, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, width:200, flexShrink:0 }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="var(--text-muted)"><path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z"/></svg>
            <input ref={searchInputRef} value={search} onChange={e => setSearch(e.target.value)} placeholder="Search symbol…" style={{ background:'transparent', color:'var(--text-primary)', flex:1, fontSize:12 }} />
            {search && <button type="button" onClick={() => { setSearch(''); setPickOpen(false); }} style={{ background:'none', color:'var(--text-muted)', fontSize:14 }}>×</button>}
          </div>
        </div>

        {selectedSymbol && (
          <>
            <div style={{ display:'flex', flexDirection:'column', justifyContent:'center', flexShrink:0, minWidth:52 }}>
              <span style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:14, color:'var(--text-primary)', lineHeight:1.1 }}>
                {selectedKind === 'index'
                  ? (selectedStock?.indexName || selectedSymbol)
                  : selectedSymbol}
              </span>
              <span style={{ fontSize:9, color:'var(--text-muted)', maxWidth:160, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', marginTop:2 }} title={selectedStock?.['Market Sector'] || ''}>
                {selectedStock?.['Market Sector'] || '—'}
              </span>
            </div>
            {(lastCandlePrice != null || selectedStock?.Price != null) && (
              <span style={{ fontFamily:'var(--font-mono)', fontSize:13, color:'var(--text-primary)', flexShrink:0 }}>
                ₹{(lastCandlePrice ?? selectedStock?.Price)?.toLocaleString('en-IN', { minimumFractionDigits:2 })}
              </span>
            )}
            {lastCandleChange !== null && (
              <span style={{ fontFamily:'var(--font-mono)', fontSize:11, fontWeight:600, flexShrink:0, color: lastCandleChange>=0?'var(--accent-green)':'var(--accent-red)', backgroundColor: lastCandleChange>=0?'rgba(63,185,80,0.12)':'rgba(248,81,73,0.12)', border:`1px solid ${lastCandleChange>=0?'#3fb95044':'#f8514944'}`, borderRadius:4, padding:'1px 6px' }}>
                {lastCandleChange>=0?'+':''}{lastCandleChange.toFixed(2)}%
              </span>
            )}
            <div style={{ width:1, height:20, backgroundColor:'var(--border)', flexShrink:0 }} />
            <div onClick={() => setVolumeVisible(v=>!v)} style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:`1px solid ${volumeVisible?'#388bfd55':'var(--border)'}`, borderRadius:4, padding:'0 8px', height:28, opacity: volumeVisible?1:0.5, cursor:'pointer', flexShrink:0 }}>
              <div style={{ width:8, height:8, backgroundColor:'#388bfd', borderRadius:2 }} />
              <span style={{ fontSize:11, color:'var(--text-secondary)', fontWeight:500 }}>Vol</span>
            </div>
            <EMAControls emas={emas} onChange={setEmas} />
            {selectedKind === 'stock' && (
              <ExternalFinancialsLinks symbol={selectedSymbol} instrumentType={selectedKind} />
            )}
          </>
        )}

        <div ref={sectorRef} style={{ position:'relative', flexShrink:0 }}>
          <button
            type="button"
            title={selectedMarketSectors.length ? selectedMarketSectors.join(' · ') : 'Filter table & technical scans by market sector'}
            onClick={() => { setSectorOpen(o => !o); setIndOpen(false); setViewOpen(false); }}
            style={{
              display:'flex', alignItems:'center', gap:6, backgroundColor: sectorOpen ? 'var(--bg-active)' : 'var(--bg-tertiary)',
              border:`1px solid ${selectedMarketSectors.length ? 'var(--accent-blue)' : 'var(--border)'}`, borderRadius:5, padding:'0 10px 0 12px', height:28,
              color: selectedMarketSectors.length ? 'var(--accent-blue)' : 'var(--text-secondary)', fontSize:12, fontWeight:600, cursor:'pointer', whiteSpace:'nowrap',
            }}
          >
            <span style={{ fontFamily: 'system-ui, sans-serif' }}>Sector</span>
            <SectorCountBadge n={selectedMarketSectors.length} />
            <svg width="10" height="6" viewBox="0 0 10 6" fill="currentColor" style={{ opacity: 0.65, flexShrink: 0 }}><path d="M0 0l5 6 5-6z" /></svg>
          </button>
          {sectorOpen && sectorDropdownRect && (
            <div style={{
              position:'fixed', top: sectorDropdownRect.top, left: sectorDropdownRect.left, width: sectorDropdownRect.width,
              maxHeight:'min(72vh, 360px)', overflowY:'auto', zIndex: CHART_TOOLBAR_OVERLAY_Z,
              backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6, boxShadow:'0 8px 24px rgba(0,0,0,0.6)', padding:'8px 0',
            }}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:8, padding:'2px 12px 8px' }}>
                <div style={{ fontSize:10, fontWeight:700, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.06em' }}>Market sectors (multi)</div>
                <button type="button" onClick={() => setSelectedMarketSectors([])} style={{ fontSize:11, background:'none', border:'1px solid var(--border)', borderRadius:4, padding:'2px 8px', color:'var(--text-secondary)', cursor:'pointer' }}>Clear</button>
              </div>
              {(canonicalMarketSectors.length ? canonicalMarketSectors : []).map(name => (
                <label key={name} style={{ display:'flex', alignItems:'center', gap:8, padding:'5px 12px', cursor:'pointer', fontSize:12, color:'var(--text-primary)' }}
                  onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                  onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                >
                  <input
                    type="checkbox"
                    checked={selectedMarketSectors.includes(name)}
                    onChange={() => {
                      setSelectedMarketSectors(prev => (
                        prev.includes(name) ? prev.filter(x => x !== name) : [...prev, name]
                      ));
                    }}
                  />
                  <span style={{ flex:1 }}>{name}</span>
                </label>
              ))}
              <div style={{ borderTop:'1px solid var(--border)', marginTop:6, padding:'8px 12px', display:'flex', justifyContent:'flex-start', alignItems:'center', gap:8 }}>
                <span style={{ fontSize:10, color:'var(--text-muted)' }}>⚙ Edit mapping in Data Management</span>
              </div>
            </div>
          )}
        </div>

        <div style={{ flex:1, minWidth:8 }} />

        <DrawingToolsDesignControl />

        {/* Indicators — menu is position:fixed so it is not clipped by toolbar overflow-x:auto */}
        <div ref={indRef} style={{ position:'relative', flexShrink:0 }}>
          <button type="button" onClick={() => { setIndOpen(o=>!o); setViewOpen(false); }}
            style={{ display:'flex', alignItems:'center', gap:5, backgroundColor: indOpen?'var(--bg-active)':'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, color:'var(--text-secondary)', fontSize:12 }}>
            Indicators <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity:0.6 }}><path d="M0 0l4 5 4-5z"/></svg>
          </button>
          {indOpen && indicatorMenuRect && (
            <div style={{
              position:'fixed', top: indicatorMenuRect.top, left: indicatorMenuRect.left, width: indicatorMenuRect.width,
              zIndex: CHART_TOOLBAR_OVERLAY_Z, backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6,
              boxShadow:'0 8px 24px rgba(0,0,0,0.6)', minWidth:160, overflow:'hidden',
            }}>
              {[{ key:'stochrsi', label:'StochRSI' },{ key:'macd', label:'MACD' }].map(ind => {
                const active = visiblePanels[ind.key];
                return (
                  <div key={ind.key} onClick={() => { handleTogglePanel(ind.key); setIndOpen(false); }}
                    style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 14px', cursor:'pointer', fontSize:13, color: active?'var(--text-primary)':'var(--text-secondary)' }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor='var(--bg-hover)'}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor='transparent'}
                  >
                    {ind.label}
                    <div style={{ width:14, height:14, borderRadius:3, border:'1px solid var(--border)', backgroundColor: active?'var(--accent-blue)':'transparent', display:'flex', alignItems:'center', justifyContent:'center' }}>
                      {active && <svg width="9" height="7" viewBox="0 0 9 7" fill="none"><path d="M1 3.5L3.5 6L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* View */}
        <div ref={viewRef} style={{ position:'relative', flexShrink:0 }}>
          <button type="button" onClick={() => { setViewOpen(o=>!o); setIndOpen(false); }}
            style={{ display:'flex', alignItems:'center', gap:5, backgroundColor: chartLayout!=='single'?'rgba(56,139,253,0.15)':'var(--bg-tertiary)', border:`1px solid ${chartLayout!=='single'?'var(--accent-blue)':'var(--border)'}`, borderRadius:5, padding:'0 10px', height:28, color: chartLayout!=='single'?'var(--accent-blue)':'var(--text-secondary)', fontSize:12 }}>
            View <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity:0.6 }}><path d="M0 0l4 5 4-5z"/></svg>
          </button>
          {viewOpen && viewMenuRect && (
            <div style={{
              position:'fixed', top: viewMenuRect.top, left: viewMenuRect.left, width: viewMenuRect.width,
              zIndex: CHART_TOOLBAR_OVERLAY_Z, backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6,
              boxShadow:'0 8px 24px rgba(0,0,0,0.6)', minWidth:230, overflow:'hidden',
            }}>
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

        {selectedSymbol && (
          <button onClick={() => onOpenChart && onOpenChart(selectedSymbol)}
            style={{ display:'flex', alignItems:'center', gap:4, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, color:'var(--text-secondary)', fontSize:12, flexShrink:0, cursor:'pointer' }}
            onMouseEnter={e => { e.currentTarget.style.borderColor='var(--accent-blue)'; e.currentTarget.style.color='var(--accent-blue)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor='var(--border)'; e.currentTarget.style.color='var(--text-secondary)'; }}
          >Open Full Chart ↗</button>
        )}

        <button onClick={handleSaveLayout}
          style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, color:'var(--text-secondary)', fontSize:12, flexShrink:0 }}
          onMouseEnter={e => e.currentTarget.style.borderColor='var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.borderColor='var(--border)'}
        >Save Layout</button>
      </div>

      {/* ── Filter bar: watchlist actions (left) · chips · counts & presets (right) ── */}
      <div style={{
        height:40, flexShrink:0, minWidth:0, width:'100%', boxSizing:'border-box',
        backgroundColor:'var(--bg-secondary)', borderBottom:'1px solid var(--border)',
        display:'flex', alignItems:'center', padding:'0 12px', gap:8,
        position:'relative', zIndex: DASHBOARD_FILTER_BAR_Z,
        overflow:'visible',
      }}>
        {/* Left: Watchlist → Presets → + Filter + watchlist target picker */}
        <div ref={wlPickWrapRef} style={{ display:'flex', alignItems:'center', gap:6, flexShrink:0, flexWrap:'nowrap' }}>
          {onAddStocksToWatchlist && (displayStocks.length > 0 || selectedSymbols.size > 0) && (activeFilters.length > 0 || selectedMarketSectors.length > 0) && (
            <button
              type="button"
              ref={wlBtnWatchlistRef}
              onClick={() => {
                if (!onAddStocksToWatchlist) return;
                setFilterMenuOpen(false);
                setPresetsOpen(false);
                if (!watchlists?.length) {
                  if (window.confirm('You don\'t have any watchlists yet.\n\nOn the Watchlist tab, enter a name under "New watchlist..." and click Create.\n\nOpen the Watchlist tab now?')) {
                    onGoToWatchlist && onGoToWatchlist();
                  }
                  return;
                }
                setAddAllMenuOpen(false);
                setWlPickOpen(o => !o);
              }}
              style={{ display:'flex', alignItems:'center', gap:4, fontSize:11, color:'var(--text-secondary)', background:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, cursor:'pointer', padding:'2px 8px', whiteSpace:'nowrap' }}
            >
              Watchlist <svg width="7" height="4" viewBox="0 0 8 5" fill="currentColor" style={{ opacity:0.6, flexShrink:0 }}><path d="M0 0l4 5 4-5z"/></svg>
            </button>
          )}
          <div ref={presetsRef} style={{ position:'relative', flexShrink:0 }}>
            <input
              ref={importFileRef}
              type="file"
              accept="application/json,.json"
              onChange={handleImportPresetFile}
              style={{ display: 'none' }}
            />
            <button
              type="button"
              onClick={() => { setWlPickOpen(null); setAddAllMenuOpen(false); setPresetsOpen(o => !o); }}
              style={{ display:'flex', alignItems:'center', gap:4, maxWidth:220, backgroundColor: presetsOpen?'var(--bg-active)': activePresetName ? 'rgba(56,139,253,0.08)' : 'var(--bg-tertiary)', border:`1px solid ${activePresetName ? 'var(--accent-blue)' : 'var(--border)'}`, borderRadius:5, padding:'0 10px', height:24, color:'var(--text-secondary)', fontSize:11, cursor:'pointer' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor='var(--accent-blue)'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor= activePresetName ? 'var(--accent-blue)' : 'var(--border)'; }}
            >
              <span style={{ flexShrink:0 }}>Presets</span>
              {activePresetName && (
                <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', fontWeight:600, color:'var(--accent-blue)' }} title={activePresetName}>· {activePresetName}</span>
              )}
              <svg width="7" height="4" viewBox="0 0 8 5" fill="currentColor" style={{ opacity:0.6, flexShrink:0 }}><path d="M0 0l4 5 4-5z"/></svg>
            </button>
            {presetsOpen && (
              <div style={{
                position:'absolute', top:'calc(100% + 4px)', left:0, zIndex: CHART_TOOLBAR_OVERLAY_Z,
                width:280, minWidth:280, maxWidth:'min(480px, calc(100vw - 16px))',
                backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6,
                boxShadow:'0 8px 24px rgba(0,0,0,0.6)', overflow:'hidden', overflowX:'hidden',
              }}>
                <div style={{ padding:'4px 0', maxHeight:'min(70vh, 420px)', overflowY:'auto' }}>
                  {presets.length === 0 ? (
                    <div style={{ padding:'10px 14px', fontSize:11, color:'var(--text-muted)', lineHeight:1.45 }}>
                      No saved presets yet. Use <strong style={{ color:'var(--text-secondary)' }}>Import</strong> below to restore from a backup file.
                    </div>
                  ) : (
                    presets.map(p => {
                      const rowActive = p.name === activePresetName;
                      const isRenaming = renamingPresetName === p.name;
                      return (
                      <div key={p.name}
                        onClick={isRenaming ? undefined : () => loadPreset(p)}
                        style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:8, padding:'8px 14px', cursor: isRenaming ? 'default' : 'pointer', fontSize:12, color:'var(--text-primary)', backgroundColor: rowActive ? 'rgba(56,139,253,0.14)' : 'transparent', borderLeft: rowActive ? '3px solid var(--accent-blue)' : '3px solid transparent' }}
                        onMouseEnter={e => { if (!rowActive && !isRenaming) e.currentTarget.style.backgroundColor='var(--bg-hover)'; }}
                        onMouseLeave={e => { e.currentTarget.style.backgroundColor = rowActive ? 'rgba(56,139,253,0.14)' : 'transparent'; }}
                      >
                        {isRenaming ? (
                          <div style={{ display:'flex', alignItems:'center', gap:6, flex:1, minWidth:0 }}>
                            <input
                              value={renamePresetValue}
                              onChange={e => setRenamePresetValue(e.target.value)}
                              onClick={e => e.stopPropagation()}
                              onKeyDown={e => {
                                e.stopPropagation();
                                if (e.key === 'Enter') renamePreset();
                                if (e.key === 'Escape') cancelRenamePreset();
                              }}
                              autoFocus
                              title={`${p.filters.length} filter${p.filters.length !== 1 ? 's' : ''}`}
                              style={{ flex:1, minWidth:0, height:24, background:'var(--bg-tertiary)', color:'var(--text-primary)', border:'1px solid var(--border)', borderRadius:4, padding:'0 6px', fontSize:12 }}
                            />
                            <button
                              type="button"
                              title="Save rename"
                              onClick={e => { e.stopPropagation(); renamePreset(); }}
                              style={{ display:'flex', alignItems:'center', justifyContent:'center', width:22, height:22, flexShrink:0, border:'1px solid var(--border)', borderRadius:4, background:'var(--bg-tertiary)', cursor:'pointer', padding:0, color:'var(--accent-blue)', fontSize:12 }}
                            >
                              ✓
                            </button>
                            <button
                              type="button"
                              title="Cancel rename"
                              onClick={e => { e.stopPropagation(); cancelRenamePreset(); }}
                              style={{ display:'flex', alignItems:'center', justifyContent:'center', width:22, height:22, flexShrink:0, border:'1px solid var(--border)', borderRadius:4, background:'var(--bg-tertiary)', cursor:'pointer', padding:0, color:'var(--text-muted)', fontSize:13 }}
                            >
                              ×
                            </button>
                          </div>
                        ) : (
                          <>
                            <span
                              title={p.name}
                              style={{
                                flex:1, minWidth:0, marginRight:4,
                                whiteSpace:'normal', wordBreak:'break-word', lineHeight:1.35,
                              }}
                            >{p.name}</span>
                            <div style={{ display:'flex', alignItems:'flex-start', gap:6, flexShrink:0 }}>
                              <span style={{ fontSize:10, color:'var(--text-muted)', whiteSpace:'nowrap', paddingTop:2 }}>{p.filters.length} filter{p.filters.length !== 1 ? 's' : ''}</span>
                              <button
                                type="button"
                                className="cim-row-edit-btn"
                                title="Rename preset"
                                onClick={e => {
                                  e.stopPropagation();
                                  setRenamingPresetName(p.name);
                                  setRenamePresetValue(p.name);
                                }}
                              >
                                <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                                  <path d="M11.013 1.427a1.75 1.75 0 0 1 2.474 0l1.086 1.086a1.75 1.75 0 0 1 0 2.474l-8.61 8.61-3.447 1.148 1.148-3.447 8.61-8.61z" />
                                </svg>
                              </button>
                              <button
                                type="button"
                                title="Delete preset"
                                onClick={e => deletePreset(p.name, e)}
                                style={{ background:'none', border:'none', color:'var(--text-muted)', fontSize:13, cursor:'pointer', padding:0, lineHeight:1, flexShrink:0 }}
                                onMouseEnter={e => { e.currentTarget.style.color='var(--accent-red)'; }}
                                onMouseLeave={e => { e.currentTarget.style.color='var(--text-muted)'; }}
                              >×</button>
                            </div>
                          </>
                        )}
                      </div>
                      );
                    })
                  )}
                </div>
                <div style={{
                  borderTop:'1px solid var(--border)',
                  padding:'8px 10px',
                  display:'flex',
                  alignItems:'center',
                  justifyContent:'space-between',
                  gap:8,
                  backgroundColor:'var(--bg-tertiary)',
                }}>
                  <span style={{ fontSize:10, fontWeight:600, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.04em' }}>Backup</span>
                  <div style={{ display:'flex', gap:6 }}>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); handleExportPresets(); }}
                      disabled={!presets.length}
                      style={{
                        fontSize:11,
                        color: presets.length ? 'var(--text-secondary)' : 'var(--text-muted)',
                        background:'var(--bg-secondary)',
                        border:'1px solid var(--border)',
                        borderRadius:4,
                        cursor: presets.length ? 'pointer' : 'not-allowed',
                        padding:'3px 10px',
                        opacity: presets.length ? 1 : 0.5,
                      }}
                      title={presets.length ? 'Export all presets to a JSON file' : 'No presets to export'}
                    >
                      Export
                    </button>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); importFileRef.current?.click(); }}
                      style={{
                        fontSize:11,
                        color:'var(--text-secondary)',
                        background:'var(--bg-secondary)',
                        border:'1px solid var(--border)',
                        borderRadius:4,
                        cursor:'pointer',
                        padding:'3px 10px',
                      }}
                      title="Import presets from a JSON backup file"
                    >
                      Import
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
          <div ref={filterMenuRef} style={{ position:'relative', flexShrink:0 }}>
            <button
              type="button"
              onClick={() => { setWlPickOpen(null); setAddAllMenuOpen(false); setFilterMenuOpen(o => !o); }}
              style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:24, color:'var(--text-muted)', fontSize:11, cursor:'pointer' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor='var(--accent-blue)'; e.currentTarget.style.color='var(--accent-blue)'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor='var(--border)'; e.currentTarget.style.color='var(--text-muted)'; }}
            >+ Filter</button>
            {filterMenuOpen && (
              <div style={{ position:'fixed', zIndex: CHART_TOOLBAR_OVERLAY_Z, backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6, boxShadow:'0 8px 24px rgba(0,0,0,0.6)', minWidth:160, overflow:'hidden' }}>
                {FILTER_MENU_ITEMS.map(f => (
                  <div key={f.key}
                    onClick={() => {
                      setFilterMenuOpen(false); setEditingIdx(null);
                      if (f.key === 'ema')       setEmaFilterOpen(true);
                      if (f.key === 'macd')      setMacdFilterOpen(true);
                      if (f.key === 'macd_hist_chain') setMacdHistChainFilterOpen(true);
                      if (f.key === 'stochrsi')  setStochrsiFilterOpen(true);
                      if (f.key === 'price')     setPriceFilterOpen(true);
                      if (f.key === 'marketcap') setMarketcapFilterOpen(true);
                      if (f.key === 'earnings') setEarningsFilterOpen(true);
                    }}
                    style={{ padding:'9px 14px', cursor:'pointer', fontSize:13, color:'var(--text-primary)', display:'flex', alignItems:'center' }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor='var(--bg-hover)'}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor='transparent'}
                  >
                    {f.label}
                  </div>
                ))}
              </div>
            )}
          </div>
          {activeFilters.length > 0 && (
            <div style={{ position:'relative', flexShrink:0 }}>
              {!saveNameOpen ? (
                <button
                  type="button"
                  onClick={() => setSaveNameOpen(true)}
                  style={{ display:'flex', alignItems:'center', gap:4, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:24, color:'var(--text-muted)', fontSize:11, cursor:'pointer' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor='var(--accent-green)'; e.currentTarget.style.color='var(--accent-green)'; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor='var(--border)'; e.currentTarget.style.color='var(--text-muted)'; }}
                >
                  ✦ Save
                </button>
              ) : (
                <div style={{ display:'flex', alignItems:'center', gap:4 }}>
                  <input
                    autoFocus
                    value={saveNameValue}
                    onChange={e => setSaveNameValue(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') savePreset(); if (e.key === 'Escape') { setSaveNameOpen(false); setSaveNameValue(''); } }}
                    placeholder="Preset name..."
                    style={{ backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--accent-green)', borderRadius:4, padding:'2px 8px', color:'var(--text-primary)', fontSize:11, width:130, fontFamily:'var(--font-sans)', outline:'none' }}
                  />
                  <button type="button" onClick={savePreset} style={{ backgroundColor:'var(--accent-green)', border:'none', borderRadius:4, padding:'2px 8px', color:'#fff', fontSize:11, cursor:'pointer', fontWeight:600 }}>Save</button>
                  <button type="button" onClick={() => { setSaveNameOpen(false); setSaveNameValue(''); }} style={{ background:'none', border:'none', color:'var(--text-muted)', fontSize:13, cursor:'pointer' }}>×</button>
                </div>
              )}
            </div>
          )}
          {activeFilters.length > 0 && (
            <button
              type="button"
              onClick={() => { setActiveFilters([]); setActivePresetName(null); }}
              style={{ fontSize:11, color:'var(--accent-red)', background:'none', border:'none', cursor:'pointer', padding:'0 4px', whiteSpace:'nowrap' }}
            >
              Clear all
            </button>
          )}
          {wlPickOpen && wlPickRect && watchlists.length > 0 && (
            <div
              style={{
                position:'fixed', top: wlPickRect.top, left: wlPickRect.left, width: wlPickRect.width,
                zIndex: CHART_TOOLBAR_OVERLAY_Z,
                backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6,
                boxShadow:'0 8px 24px rgba(0,0,0,0.6)', overflow:'hidden',
              }}
            >
              <div style={{ fontSize:10, fontWeight:700, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.06em', padding:'8px 12px 4px' }}>Watchlist</div>
              {hasActiveUniverseFilters && (
                <div
                  ref={addAllRowRef}
                  role="menuitem"
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => {
                    setAddMenuMode('all');
                    setAddAllMenuOpen(o => !o || addMenuMode !== 'all');
                  }}
                  style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 12px', cursor:'pointer', fontSize:12, color:'var(--text-secondary)', borderTop:'1px solid var(--border-light)', borderBottom:'1px solid var(--border-light)' }}
                  onMouseEnter={e => { e.currentTarget.style.backgroundColor='var(--bg-hover)'; }}
                  onMouseLeave={e => { e.currentTarget.style.backgroundColor='transparent'; }}
                >
                  <span>Add all to... </span>
                  <span style={{ fontFamily:'var(--font-mono)', opacity:0.8 }}>{'>'}</span>
                </div>
              )}
              {selectedSymbol && (
                <div
                  role="menuitem"
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => {
                    setAddAllMenuOpen(false);
                  }}
                  style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 12px', cursor:'pointer', fontSize:12, color:'var(--text-secondary)', borderBottom:'1px solid var(--border-light)' }}
                  onMouseEnter={e => { e.currentTarget.style.backgroundColor='var(--bg-hover)'; }}
                  onMouseLeave={e => { e.currentTarget.style.backgroundColor='transparent'; }}
                >
                  <span>Add to... </span>
                  <span />
                </div>
              )}
              {selectedSymbol && (
                <div style={{ borderBottom:'1px solid var(--border-light)' }}>
                  {watchlists.map(w => (
                    <div
                      key={`focused-${w.name}`}
                      role="menuitem"
                      onMouseDown={e => e.preventDefault()}
                      onClick={() => {
                        if (!onAddStocksToWatchlist || !selectedSymbol) return;
                        void (async () => {
                          try {
                            await onAddStocksToWatchlist([selectedSymbol], w.name);
                            setWlPickOpen(false);
                          } catch {
                            /* parent already alerted; keep menu open to retry */
                          }
                        })();
                      }}
                      style={{ padding:'8px 22px', cursor:'pointer', fontSize:12, color:'var(--text-primary)' }}
                      onMouseEnter={e => { e.currentTarget.style.backgroundColor='var(--bg-hover)'; }}
                      onMouseLeave={e => { e.currentTarget.style.backgroundColor='transparent'; }}
                    >
                      {w.name}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {addAllMenuOpen && hasActiveUniverseFilters && addMenuMode === 'all' && addAllMenuRect && watchlists.length > 0 && (
            <div
              style={{
                position:'fixed',
                top: addAllMenuRect.top,
                left: addAllMenuRect.left,
                width: addAllMenuRect.width,
                zIndex: CHART_TOOLBAR_OVERLAY_Z,
                backgroundColor:'var(--bg-secondary)',
                border:'1px solid var(--border)',
                borderRadius:6,
                boxShadow:'0 8px 24px rgba(0,0,0,0.6)',
                overflow:'hidden',
              }}
            >
              <div style={{ fontSize:10, fontWeight:700, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.06em', padding:'8px 12px 4px' }}>
                {`Add all to Watchlist (${displayStocks.length})`}
              </div>
              {watchlists.map(w => (
                <div
                  key={w.name}
                  role="menuitem"
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => {
                    if (!onAddStocksToWatchlist) return;
                    const symbols = displayStocks.map(s => s.Symbol);
                    if (!symbols.length) return;
                    void (async () => {
                      try {
                        await onAddStocksToWatchlist(symbols, w.name);
                        setAddAllMenuOpen(false);
                        setWlPickOpen(false);
                      } catch {
                        /* parent already alerted; keep menu open to retry */
                      }
                    })();
                  }}
                  style={{ padding:'9px 14px', cursor:'pointer', fontSize:13, color:'var(--text-primary)' }}
                  onMouseEnter={e => { e.currentTarget.style.backgroundColor='var(--bg-hover)'; }}
                  onMouseLeave={e => { e.currentTarget.style.backgroundColor='transparent'; }}
                >
                  {w.name}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Center: filter chips rail */}
        <div style={{ flex:1, minWidth:0, display:'flex', alignItems:'center', gap:4, flexShrink:1, justifyContent:'flex-start' }}>
          {chipsScrollEdges.canScroll && (
            <button
              type="button"
              aria-label="Scroll filters left"
              disabled={chipsScrollEdges.atStart}
              onClick={() => scrollChipsBy(-140)}
              style={{
                flexShrink:0, width:22, height:24, padding:0, lineHeight:1,
                display:'flex', alignItems:'center', justifyContent:'center',
                backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:4,
                color:'var(--text-secondary)', fontSize:12, fontWeight:700, cursor: chipsScrollEdges.atStart ? 'default' : 'pointer',
                opacity: chipsScrollEdges.atStart ? 0.35 : 1,
              }}
            >{'<'}</button>
          )}
          <div
            ref={chipsRailRef}
            className="dashboard-filter-chips-rail"
            onScroll={updateChipsScrollEdges}
            style={{
              flex: chipsScrollEdges.canScroll ? 1 : '0 1 auto',
              width: chipsScrollEdges.canScroll ? undefined : 'auto',
              minWidth: 0,
              maxWidth: '100%',
              display:'flex', alignItems:'center', gap:6,
              overflowX: chipsScrollEdges.canScroll ? 'auto' : 'visible',
              overflowY:'hidden',
              ...(chipsScrollEdges.canScroll ? { WebkitOverflowScrolling: 'touch' } : {}),
            }}
          >
            {activeFilters.map((f, idx) => <FilterChip key={idx} f={f} idx={idx} />)}
          </div>
          {chipsScrollEdges.canScroll && (
            <button
              type="button"
              aria-label="Scroll filters right"
              disabled={chipsScrollEdges.atEnd}
              onClick={() => scrollChipsBy(140)}
              style={{
                flexShrink:0, width:22, height:24, padding:0, lineHeight:1,
                display:'flex', alignItems:'center', justifyContent:'center',
                backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:4,
                color:'var(--text-secondary)', fontSize:12, fontWeight:700, cursor: chipsScrollEdges.atEnd ? 'default' : 'pointer',
                opacity: chipsScrollEdges.atEnd ? 0.35 : 1,
              }}
            >{'>'}</button>
          )}
        </div>

        {/* Right: total filtered · Update preset */}
        <div style={{ display:'flex', alignItems:'center', gap:6, flexShrink:0, flexWrap:'nowrap' }}>
          {(activeFilters.length > 0 || selectedMarketSectors.length > 0) && (
            <span style={{ fontSize:11, color:'var(--text-muted)', flexShrink:0, whiteSpace:'nowrap' }}>
              Total stocks filtered: {total}
            </span>
          )}
          {activePresetName && presetDirty && activeFilters.length > 0 && (
            <button
              type="button"
              onClick={() => updateActivePreset()}
              style={{ display:'flex', alignItems:'center', gap:4, backgroundColor:'rgba(56,139,253,0.12)', border:'1px solid var(--accent-blue)', borderRadius:5, padding:'0 10px', height:24, color:'var(--accent-blue)', fontSize:11, fontWeight:600, cursor:'pointer', flexShrink:0 }}
            >
              Update preset
            </button>
          )}
        </div>
      </div>

      {/* ── Body ── */}
      <div ref={wrapperRef} style={{ flex:1, display:'flex', overflow:'hidden', position:'relative', zIndex:0 }}>
        <div style={{ width:paneWidth, minWidth:200, flexShrink:0, display:'flex', flexDirection:'column', overflow:'hidden' }}>
          <div
            ref={headerScrollRef}
            style={{ ...stockListHeaderStripStyle, overflowX: 'hidden', overflowY: 'hidden' }}
          >
            {COLS.map(col => {
              const sortable = col.key !== 'note';
              const activeSort = sortable && sortBy === col.key;
              return (
                <div
                  key={col.key}
                  style={{ width:col.width, minWidth:col.width, flexShrink:0, height: STOCK_LIST_HEADER_HEIGHT, display:'flex', alignItems:'center', borderRight:'1px solid var(--border-light)', userSelect:'none' }}
                >
                  {sortable ? (
                    <button
                      type="button"
                      onClick={() => handleSort(col.key)}
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
                      aria-label={`Sort by ${col.label}, currently ${activeSort ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'not sorted'}`}
                    >
                      {col.label}
                      {activeSort && <span style={{ marginLeft:3, fontSize:9 }}>{sortDir==='asc'?'▲':'▼'}</span>}
                    </button>
                  ) : (
                    <span style={{ padding:'0 8px', fontSize:11, fontWeight:600, color:'var(--text-secondary)' }}>{col.label}</span>
                  )}
                </div>
              );
            })}
          </div>
          <div ref={rowsScrollRef} style={{ flex:1, overflowY:'auto', overflowX:'auto' }}>
            {loading ? (
              <div style={{ padding:16, color:'var(--text-muted)', fontSize:12 }}>Loading...</div>
            ) : (
            <>
            {pfDraggingIdx !== null && pfDropGap === 0 ? <DropInsetLine /> : null}
            {displayStocks.map((stock, idx) => {
              const isSel = stock.Symbol === selectedSymbol;
              const isMultiSel = selectedSymbols.has(stock.Symbol);
              const rowKey = `${stock.Symbol}-${stock.instrumentType || 'stock'}`;
              const symLabel = stock.instrumentType === 'index' && stock.indexName ? stock.indexName : stock.Symbol;
              const chg   = stock['Change %']; const chgC = chg>0?'var(--accent-green)':chg<0?'var(--accent-red)':'var(--text-muted)';
              const symC  = chg>0?'var(--accent-green)':chg<0?'var(--accent-red)':'var(--text-primary)';
              const mchg  = stock['Monthly Change %']; const mchgC = mchg>0?'var(--accent-green)':mchg<0?'var(--accent-red)':'var(--text-muted)';
              const pfDrag = pageMode === 'portfolio' && displayStocks.length > 1;
              const beatRaw = pageMode === 'portfolio' && stock.instrumentType !== 'index'
                ? portfolioBeatBySymbol.get(stock.Symbol)
                : null;
              const upcomingRaw = pageMode === 'portfolio' && stock.instrumentType !== 'index'
                ? portfolioEarningsBySymbol.get(stock.Symbol)
                : null;
              const rowHighlight = pageMode === 'portfolio'
                ? resolveEarningsRowHighlight(beatRaw, upcomingRaw)
                : { kind: null, info: null };
              const beatInfo = rowHighlight.kind === 'beat' ? rowHighlight.info : null;
              const upcomingInfo = rowHighlight.kind === 'upcoming' ? rowHighlight.info : null;
              const earningsHighlight = beatInfo || upcomingInfo;
              const isBeatHighlight = !!beatInfo;
              const rowBg = isSel
                ? 'rgba(56,139,253,0.08)'
                : isMultiSel
                  ? 'rgba(56,139,253,0.04)'
                  : isBeatHighlight
                    ? DUAL_BEAT_ROW_BG
                    : upcomingInfo
                      ? PORTFOLIO_EARNINGS_ROW_BG
                      : 'transparent';
              const rowBorderLeft = isSel
                ? '2px solid var(--accent-blue)'
                : isMultiSel
                  ? '2px solid rgba(56,139,253,0.4)'
                  : isBeatHighlight
                    ? `2px solid ${DUAL_BEAT_BORDER}`
                    : upcomingInfo
                      ? `2px solid ${PORTFOLIO_EARNINGS_BORDER}`
                      : '2px solid transparent';
              return (
                <React.Fragment key={rowKey}>
                <div ref={el => rowRefs.current[idx]=el}
                  onClick={(e) => handleRowSelect(stock, idx, e)}
                  onDragOver={pfDrag ? e => onPortfolioDragOver(e, idx) : undefined}
                  onDrop={pfDrag ? onPortfolioDrop : undefined}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    if (onContextMenuRequest) {
                      onContextMenuRequest({
                        x: e.clientX,
                        y: e.clientY,
                        symbol: stock.Symbol,
                        type: stock.instrumentType === 'index' ? 'index' : 'stock',
                        sourcePage: pageMode === 'portfolio' ? 'portfolio' : 'pulse',
                      });
                    }
                  }}
                  style={{ display:'flex', alignItems:'center', height: earningsHighlight ? PORTFOLIO_EARNINGS_ROW_HEIGHT : STOCK_LIST_ROW_HEIGHT, borderBottom:'1px solid var(--border-light)', cursor:'pointer', backgroundColor: rowBg, borderLeft: rowBorderLeft, opacity: pfDraggingIdx === idx ? 0.45 : 1 }}
                  onMouseEnter={e => {
                    if (!isSel && !isMultiSel) {
                      e.currentTarget.style.backgroundColor = isBeatHighlight
                        ? DUAL_BEAT_ROW_HOVER
                        : upcomingInfo
                          ? PORTFOLIO_EARNINGS_ROW_HOVER
                          : 'var(--bg-hover)';
                    }
                  }}
                  onMouseLeave={e => {
                    if (!isSel && !isMultiSel) {
                      e.currentTarget.style.backgroundColor = isBeatHighlight
                        ? DUAL_BEAT_ROW_BG
                        : upcomingInfo
                          ? PORTFOLIO_EARNINGS_ROW_BG
                          : 'transparent';
                    }
                  }}
                >
                  <div style={{ width:COLS[0].width, minWidth:COLS[0].width, flexShrink:0, padding: pfDrag ? '0 4px 0 6px' : '0 8px', display:'flex', alignItems:'center', borderRight:'1px solid var(--border-light)', overflow:'hidden', gap: 4 }}>
                    {pfDrag ? (
                      <span
                        title="Drag to reorder"
                        draggable
                        onDragStart={e => { e.stopPropagation(); onPortfolioDragStart(e, idx); }}
                        onDragEnd={e => { e.stopPropagation(); onPortfolioDragEnd(); }}
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
                        handleRowSelect(stock, idx, e);
                        openPortfolioEarningsModalFromSymbol(stock, e);
                      } : undefined}
                      title={earningsHighlight ? 'Click for quarterly results and company profile' : stock.Symbol}
                    >
                      <span title={stock.Symbol} style={{ fontFamily:'var(--font-mono)', fontWeight:600, fontSize:11, color: symC, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', lineHeight: 1.2 }}>{symLabel}</span>
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
                  <div style={{ width:COLS[1].width, minWidth:COLS[1].width, flexShrink:0, padding:'0 8px', display:'flex', alignItems:'center', borderRight:'1px solid var(--border-light)' }}><span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-secondary)' }}>{formatMarketCap(stock['Market Cap'])}</span></div>
                  <div style={{ width:COLS[2].width, minWidth:COLS[2].width, flexShrink:0, padding:'0 4px', display:'flex', alignItems:'center', justifyContent:'center', borderRight:'1px solid var(--border-light)' }} onClick={e => e.stopPropagation()}><InstrumentNotesIcon symbol={stock.Symbol} instrumentType={stock.instrumentType === 'index' ? 'index' : 'stock'} /></div>
                  <div style={{ width:COLS[3].width, minWidth:COLS[3].width, flexShrink:0, padding:'0 8px', display:'flex', alignItems:'center', borderRight:'1px solid var(--border-light)' }}><span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-primary)' }}>{stock.Price!=null?`₹${stock.Price.toFixed(2)}`:'—'}</span></div>
                  <div style={{ width:COLS[4].width, minWidth:COLS[4].width, flexShrink:0, padding:'0 8px', display:'flex', alignItems:'center', borderRight:'1px solid var(--border-light)' }}><span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:chgC, fontWeight:500 }}>{chg!=null?`${chg>0?'+':''}${chg.toFixed(2)}%`:'—'}</span></div>
                  <div style={{ width:COLS[5].width, minWidth:COLS[5].width, flexShrink:0, padding:'0 8px', display:'flex', alignItems:'center', borderRight:'1px solid var(--border-light)' }}><span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:mchgC, fontWeight:500 }}>{mchg!=null?`${mchg>0?'+':''}${mchg.toFixed(2)}%`:'—'}</span></div>
                </div>
                {pfDraggingIdx !== null && pfDropGap === idx + 1 ? <DropInsetLine /> : null}
                </React.Fragment>
              );
            })}
            {loadingMore && (
              <div style={{ padding: 10, fontSize: 11, color: 'var(--text-muted)', textAlign: 'center' }}>
                Loading more...
              </div>
            )}
            </>
            )}
          </div>
          <div style={stockListFooterStripStyle}>
            {total} {pageMode === 'portfolio' ? 'rows' : 'stocks'}
            {pageMode === 'portfolio' && (
              <button
                type="button"
                onClick={handlePortfolioEarningsPriorityControlClick}
                aria-pressed={portfolioEarningsPriorityEnabled}
                aria-label={`Earnings priority sort ${portfolioEarningsPriorityEnabled ? 'enabled' : 'disabled'}, ${portfolioEarningsPriorityDir === 'asc' ? 'nearest dates first' : 'furthest dates first'}`}
                title={portfolioEarningsPriorityEnabled
                  ? 'Toggle earnings-priority date direction'
                  : 'Re-enable earnings-priority sorting'}
                style={{
                  marginLeft: 8,
                  padding: 0,
                  border: 'none',
                  background: 'none',
                  color: portfolioEarningsPriorityEnabled ? 'var(--accent-blue)' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  font: 'inherit',
                }}
              >
                · Earnings priority {portfolioEarningsPriorityDir === 'asc' ? '▲' : '▼'}
              </button>
            )}
            {pageMode === 'portfolio' && portfolioBeatCount > 0 && (
              <span style={{ marginLeft: 8, color: DUAL_BEAT_LABEL_COLOR }}>
                · {portfolioBeatCount} beat EPS+Rev ({DUAL_BEAT_WINDOW_DAYS}d)
              </span>
            )}
            {pageMode === 'portfolio' && portfolioEarningsCount > 0 && (
              <span style={{ marginLeft: 8, color: PORTFOLIO_EARNINGS_LABEL_COLOR }}>
                · {portfolioEarningsCount} reporting in {PORTFOLIO_EARNINGS_WINDOW_DAYS} days
              </span>
            )}
          </div>
        </div>

        <div onMouseDown={onDividerMouseDown}
          style={{ width:4, backgroundColor:'var(--border)', cursor:'col-resize', flexShrink:0, transition:'background 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.backgroundColor='var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.backgroundColor='var(--border)'}
        />

        <DrawingMirrorProvider
          mirrorStorageKey={
            selectedSymbol && (chartLayout === '2h' || chartLayout === '3h')
              ? `${pageMode}:${selectedKind}:${selectedSymbol}:mirror`
              : null
          }
          mirrorContextId={`${pageMode}-split-${selectedSymbol || 'none'}`}
        >
        <DrawingWorkspaceProvider workspaceId={`${pageMode}-dash-${selectedSymbol || 'none'}`}>
        <div style={{ flex:1, display:'flex', overflow:'hidden', minWidth:400, position:'relative' }}>
          <DrawingToolbarConnected />
          <DrawingFloatPaletteConnected />
          {!selectedSymbol ? (
            <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', color:'var(--text-muted)', fontSize:13 }}>Select a stock to view chart</div>
          ) : selectedKind === 'index' && selectedStock ? (
            <>
              {renderIndexPanel(
                selectedSymbol,
                timeframe,
                tf => { setTimeframe(tf); setLastCandleChange(null); setLastCandlePrice(null); },
                (pct) => { setLastCandleChange(pct); setLastCandlePrice(null); },
                selectedSymbol + '-ip1-' + timeframe,
                chartLayout !== 'single',
                { symbol: selectedStock.Symbol, name: selectedStock.indexName || selectedStock.Symbol, category: selectedStock.indexCategory || 'equity' },
              )}
              {(chartLayout === '2h' || chartLayout === '3h') && renderIndexPanel(
                selectedSymbol,
                timeframe2,
                tf => setTimeframe2(tf),
                (pct) => setLastCandleChange(pct),
                selectedSymbol + '-ip2-' + timeframe2,
                chartLayout === '3h',
                { symbol: selectedStock.Symbol, name: selectedStock.indexName || selectedStock.Symbol, category: selectedStock.indexCategory || 'equity' },
              )}
              {chartLayout === '3h' && renderIndexPanel(
                selectedSymbol,
                timeframe3,
                tf => setTimeframe3(tf),
                (pct) => setLastCandleChange(pct),
                selectedSymbol + '-ip3-' + timeframe3,
                false,
                { symbol: selectedStock.Symbol, name: selectedStock.indexName || selectedStock.Symbol, category: selectedStock.indexCategory || 'equity' },
              )}
            </>
          ) : (
            <>
              {renderPanel(selectedSymbol, timeframe,  tf => { setTimeframe(tf); setLastCandleChange(null); setLastCandlePrice(null); }, (pct,price) => { setLastCandleChange(pct); setLastCandlePrice(price??null); }, selectedSymbol+'-p1-'+timeframe,  chartLayout!=='single')}
              {(chartLayout==='2h'||chartLayout==='3h') && renderPanel(selectedSymbol, timeframe2, tf => setTimeframe2(tf), (pct, price) => { setLastCandleChange(pct); setLastCandlePrice(price ?? null); }, selectedSymbol+'-p2-'+timeframe2, chartLayout==='3h')}
              {chartLayout==='3h' && renderPanel(selectedSymbol, timeframe3, tf => setTimeframe3(tf), (pct, price) => { setLastCandleChange(pct); setLastCandlePrice(price ?? null); }, selectedSymbol+'-p3-'+timeframe3, false)}
            </>
          )}
        </div>
        </DrawingWorkspaceProvider>
        </DrawingMirrorProvider>
      </div>

      {/* Filter modals */}
      {emaFilterOpen       && <EMAFilterBuilder       onApply={applyFilter} onCancel={closeFilterBuilders} initialValues={editingIdx!==null?activeFilters[editingIdx]:null} />}
      {macdFilterOpen      && <MACDFilterBuilder      onApply={applyFilter} onCancel={closeFilterBuilders} initialValues={editingIdx!==null?activeFilters[editingIdx]:null} />}
      {macdHistChainFilterOpen && <MACDHistChainFilterBuilder onApply={applyFilter} onCancel={closeFilterBuilders} initialValues={editingIdx!==null?activeFilters[editingIdx]:null} />}
      {stochrsiFilterOpen  && <StochRSIFilterBuilder  onApply={applyFilter} onCancel={closeFilterBuilders} initialValues={editingIdx!==null?activeFilters[editingIdx]:null} />}
      {priceFilterOpen     && <PriceFilterBuilder     onApply={applyFilter} onCancel={closeFilterBuilders} initialValues={editingIdx!==null?activeFilters[editingIdx]:null} />}
      {marketcapFilterOpen && <MarketCapFilterBuilder onApply={applyFilter} onCancel={closeFilterBuilders} initialValues={editingIdx!==null?activeFilters[editingIdx]:null} />}
      {earningsFilterOpen && <EarningsFilterBuilder onApply={applyFilter} onCancel={closeFilterBuilders} initialValues={editingIdx!==null?activeFilters[editingIdx]:null} />}

      {pageMode === 'portfolio' && portfolioEarningsModal && (
        <PortfolioEarningsModal
          symbol={portfolioEarningsModal.symbol}
          variant={portfolioEarningsModal.variant}
          earningsDate={portfolioEarningsModal.earningsDate}
          daysUntil={portfolioEarningsModal.daysUntil}
          daysSinceReport={portfolioEarningsModal.daysSinceReport}
          onClose={() => setPortfolioEarningsModal(null)}
          onOpenChart={onOpenChart}
        />
      )}
    </div>
  );
}