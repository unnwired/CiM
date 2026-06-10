import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import axios from 'axios';
import ChartContainer from '../components/chart/ChartContainer';
import ChartHeaderBar from '../components/chart/ChartHeaderBar';
import EMAControls from '../components/chart/EMAControls';
import DrawingToolsDesignControl from '../components/chart/drawing/DrawingToolsDesignControl';
import ExternalFinancialsLinks from '../components/ExternalFinancialsLinks';
import { DrawingMirrorProvider } from '../components/chart/drawing/DrawingMirrorContext';
import { DrawingWorkspaceProvider } from '../components/chart/drawing/DrawingWorkspaceContext';
import { DrawingToolbarConnected, DrawingFloatPaletteConnected } from '../components/chart/drawing/DrawingToolbar';
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
  DEFAULT_CHART_LAYOUT,
  DEFAULT_CHART_TIMEFRAME_1,
  DEFAULT_CHART_TIMEFRAME_2,
  DEFAULT_CHART_TIMEFRAME_3,
  normalizeSavedTimeframe3,
} from '../config/chartViewDefaults';

const API = '';
const CHART_TOOLBAR_OVERLAY_Z = 200000;

const LAYOUTS = [
  { key: 'single', label: 'Single', desc: 'One chart panel' },
  { key: '2h', label: '2 - Multi Timeframe', desc: 'Same stock, two timeframes' },
  { key: '3h', label: '3 - Multi Timeframe', desc: 'Same stock, three timeframes' },
];

const SCREENER_GROUPS = [
  {
    key: 'swing-macd-stoch',
    label: 'Swing - MACD + StochRSI',
    items: [
      {
        key: 'swing_2w_default',
        label: '2W Potential Swing',
        desc: 'Receding negative MACD hist + near crossover + StochRSI K > D (snapshot 2W)',
        payload: {
          screener_key: 'swing_2w_default',
          timeframe: '2W',
          epsilon: 0.35,
          min_hist_improve: 0,
          stoch_min_spread: 0,
          limit: 300,
        },
      },
      {
        key: 'swing_2w_tight',
        label: '2W Tight Setup',
        desc: 'Closer to crossover, stronger momentum, higher K-D spread',
        payload: {
          screener_key: 'swing_2w_tight',
          timeframe: '2W',
          epsilon: 0.2,
          min_hist_improve: 0.02,
          stoch_min_spread: 1.0,
          limit: 300,
        },
      },
      {
        key: 'swing_2w_early',
        label: '2W Early Build',
        desc: 'Earlier reversals before tight crossover',
        payload: {
          screener_key: 'swing_2w_early',
          timeframe: '2W',
          epsilon: 0.6,
          min_hist_improve: 0.01,
          stoch_min_spread: 0,
          limit: 300,
        },
      },
    ],
  },
];

function formatPrice(v) {
  if (v == null || Number.isNaN(Number(v))) return '-';
  return Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPct(v) {
  if (v == null || Number.isNaN(Number(v))) return '-';
  const n = Number(v);
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function fmtSmall(v, d = 3) {
  if (v == null || Number.isNaN(Number(v))) return '-';
  return Number(v).toFixed(d);
}

function parseMaybeFloat(raw) {
  const s = String(raw || '').trim();
  if (!s) return null;
  const n = Number(s);
  if (!Number.isFinite(n)) return NaN;
  return n;
}

function parseMarketCapInput(raw) {
  const s0 = String(raw || '').trim();
  if (!s0) return null;
  const s = s0.toUpperCase().replace(/,/g, '');
  const m = s.match(/^([0-9]*\.?[0-9]+)\s*([MBT])?$/);
  if (!m) return NaN;
  const base = Number(m[1]);
  if (!Number.isFinite(base)) return NaN;
  const unit = m[2] || 'M';
  const factor = unit === 'T' ? 1e12 : unit === 'B' ? 1e9 : 1e6;
  return base * factor;
}

export default function PotentialSwingsPage({
  onOpenChart,
  onAddStocksToWatchlist,
  watchlists = [],
  onGoToWatchlist,
}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [activePreset, setActivePreset] = useState(SCREENER_GROUPS[0].items[0].key);
  const [scanMeta, setScanMeta] = useState(null);
  const [scanError, setScanError] = useState('');
  const [librarySearch, setLibrarySearch] = useState('');
  const [screenerDrawerOpen, setScreenerDrawerOpen] = useState(false);

  const [symbolQuery, setSymbolQuery] = useState('');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [minMcap, setMinMcap] = useState('');
  const [maxMcap, setMaxMcap] = useState('');
  const [maxCrossDistance, setMaxCrossDistance] = useState('');
  const [minStochSpread, setMinStochSpread] = useState('');
  const [filterError, setFilterError] = useState('');

  const [timeframe, setTimeframe] = useState(DEFAULT_CHART_TIMEFRAME_1);
  const [timeframe2, setTimeframe2] = useState(DEFAULT_CHART_TIMEFRAME_2);
  const [timeframe3, setTimeframe3] = useState(DEFAULT_CHART_TIMEFRAME_3);
  const [chartLayout, setChartLayout] = useState(DEFAULT_CHART_LAYOUT);
  const [lastCandleChange, setLastCandleChange] = useState(null);
  const [crosshairTime, setCrosshairTime] = useState(null);

  const [emas, setEmas] = useState(() => getPersistedEmaSet());
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(true));
  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());
  const [panelOrder, setPanelOrder] = useState(['stochrsi', 'macd']);

  const [paneWidth, setPaneWidth] = useState(320);
  const draggingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  const wrapperRef = useRef(null);
  const heightsRef = useRef({});

  const [indOpen, setIndOpen] = useState(false);
  const [viewOpen, setViewOpen] = useState(false);
  const [indicatorMenuRect, setIndicatorMenuRect] = useState(null);
  const [viewMenuRect, setViewMenuRect] = useState(null);
  const indRef = useRef(null);
  const viewRef = useRef(null);
  const [wlPickOpen, setWlPickOpen] = useState(false);
  const [wlPickRect, setWlPickRect] = useState(null);
  const wlPickWrapRef = useRef(null);
  const wlBtnWatchlistRef = useRef(null);
  const screenerDrawerRef = useRef(null);
  const screenerToggleRef = useRef(null);
  const addAllRowRef = useRef(null);
  const [addAllMenuOpen, setAddAllMenuOpen] = useState(false);
  const [addAllMenuRect, setAddAllMenuRect] = useState(null);

  const normalizedQuery = String(symbolQuery || '').trim().toUpperCase();
  const normalizedLibrarySearch = String(librarySearch || '').trim().toLowerCase();
  const parsedMinPrice = parseMaybeFloat(minPrice);
  const parsedMaxPrice = parseMaybeFloat(maxPrice);
  const parsedMinMcap = parseMarketCapInput(minMcap);
  const parsedMaxMcap = parseMarketCapInput(maxMcap);
  const parsedMaxCrossDistance = parseMaybeFloat(maxCrossDistance);
  const parsedMinStochSpread = parseMaybeFloat(minStochSpread);

  const filterInputsValid = (
    (parsedMinPrice === null || Number.isFinite(parsedMinPrice))
    && (parsedMaxPrice === null || Number.isFinite(parsedMaxPrice))
    && (parsedMinMcap === null || Number.isFinite(parsedMinMcap))
    && (parsedMaxMcap === null || Number.isFinite(parsedMaxMcap))
    && (parsedMaxCrossDistance === null || Number.isFinite(parsedMaxCrossDistance))
    && (parsedMinStochSpread === null || Number.isFinite(parsedMinStochSpread))
  );

  const filteredRows = rows.filter(row => {
    if (normalizedQuery && !String(row.symbol || '').toUpperCase().includes(normalizedQuery)) return false;

    const price = row.price == null ? null : Number(row.price);
    if (parsedMinPrice !== null && Number.isFinite(parsedMinPrice)) {
      if (price == null || !Number.isFinite(price) || price < parsedMinPrice) return false;
    }
    if (parsedMaxPrice !== null && Number.isFinite(parsedMaxPrice)) {
      if (price == null || !Number.isFinite(price) || price > parsedMaxPrice) return false;
    }

    const mcap = row.market_cap == null ? null : Number(row.market_cap);
    if (parsedMinMcap !== null && Number.isFinite(parsedMinMcap)) {
      if (mcap == null || !Number.isFinite(mcap) || mcap < parsedMinMcap) return false;
    }
    if (parsedMaxMcap !== null && Number.isFinite(parsedMaxMcap)) {
      if (mcap == null || !Number.isFinite(mcap) || mcap > parsedMaxMcap) return false;
    }

    const crossRaw = row.near_cross_distance;
    const crossDist = crossRaw == null ? null : Number(crossRaw);
    if (parsedMaxCrossDistance !== null && Number.isFinite(parsedMaxCrossDistance)) {
      if (crossDist == null || !Number.isFinite(crossDist) || crossDist > parsedMaxCrossDistance) return false;
    }

    const stochSpread = (row.stoch_k == null || row.stoch_d == null) ? null : (Number(row.stoch_k) - Number(row.stoch_d));
    if (parsedMinStochSpread !== null && Number.isFinite(parsedMinStochSpread)) {
      if (stochSpread == null || !Number.isFinite(stochSpread) || stochSpread < parsedMinStochSpread) return false;
    }

    return true;
  });
  const refinedSymbols = filteredRows.map(r => String(r.symbol || '').trim().toUpperCase()).filter(Boolean);
  const visibleScreenerGroups = SCREENER_GROUPS
    .map(group => ({
      ...group,
      items: group.items.filter(item => {
        if (!normalizedLibrarySearch) return true;
        return (
          String(item.label || '').toLowerCase().includes(normalizedLibrarySearch)
          || String(item.desc || '').toLowerCase().includes(normalizedLibrarySearch)
          || String(item.key || '').toLowerCase().includes(normalizedLibrarySearch)
        );
      }),
    }))
    .filter(group => group.items.length > 0);
  const visibleScreenerCount = visibleScreenerGroups.reduce((acc, group) => acc + group.items.length, 0);
  const activePresetMeta = SCREENER_GROUPS
    .flatMap(group => group.items)
    .find(item => item.key === activePreset) || null;
  const activePresetLabel = activePresetMeta?.label || 'Select screener';

  useEffect(() => {
    axios.get(`${API}/api/layout`).then(r => {
      if (r.data.potentialSwingsPaneWidth) setPaneWidth(Number(r.data.potentialSwingsPaneWidth) || 320);
      if (r.data.potentialSwingsChartLayout) setChartLayout(String(r.data.potentialSwingsChartLayout));
      if (r.data.potentialSwingsTimeframe) setTimeframe(r.data.potentialSwingsTimeframe);
      if (r.data.potentialSwingsTimeframe2) setTimeframe2(r.data.potentialSwingsTimeframe2);
      if (r.data.potentialSwingsTimeframe3) setTimeframe3(normalizeSavedTimeframe3(r.data.potentialSwingsTimeframe3));
    }).catch(() => {});
  }, []);

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

  useLayoutEffect(() => {
    if (!indOpen) {
      setIndicatorMenuRect(null);
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
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = 230;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      const left = Math.min(Math.max(pad, r.right - width), maxLeft);
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
      const width = 220;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      const left = Math.min(Math.max(pad, r.left), maxLeft);
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
      const top = Math.max(pad, Math.min(r.top, window.innerHeight - pad));
      setAddAllMenuRect({ top, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [addAllMenuOpen]);

  useEffect(() => {
    function onDocDown(e) {
      if (indRef.current && !indRef.current.contains(e.target)) setIndOpen(false);
      if (viewRef.current && !viewRef.current.contains(e.target)) setViewOpen(false);
    }
    document.addEventListener('mousedown', onDocDown);
    return () => document.removeEventListener('mousedown', onDocDown);
  }, []);

  useEffect(() => {
    if (!wlPickOpen) return undefined;
    function handleDoc(e) {
      if (wlPickWrapRef.current?.contains(e.target)) return;
      setWlPickOpen(false);
      setAddAllMenuOpen(false);
    }
    document.addEventListener('mousedown', handleDoc);
    return () => document.removeEventListener('mousedown', handleDoc);
  }, [wlPickOpen]);

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
    if (!screenerDrawerOpen) return undefined;
    function handleDoc(e) {
      if (screenerDrawerRef.current?.contains(e.target)) return;
      if (screenerToggleRef.current?.contains(e.target)) return;
      setScreenerDrawerOpen(false);
    }
    function handleEsc(e) {
      if (e.key === 'Escape') setScreenerDrawerOpen(false);
    }
    document.addEventListener('mousedown', handleDoc);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleDoc);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [screenerDrawerOpen]);

  function handleTogglePanel(key) {
    setVisiblePanels(prev => ({ ...prev, [key]: !prev[key] }));
  }

  function handleMovePanel(key, dir) {
    setPanelOrder(prev => {
      const idx = prev.indexOf(key);
      if (idx === -1) return prev;
      const swap = dir === 'up' ? idx - 1 : idx + 1;
      if (swap < 0 || swap >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[swap]] = [next[swap], next[idx]];
      return next;
    });
  }

  async function runPreset(preset) {
    setLoading(true);
    setScanError('');
    setActivePreset(preset.key);
    try {
      const r = await axios.post(`${API}/api/scans/potential-swings`, { ...preset.payload });
      const list = Array.isArray(r.data?.symbols) ? r.data.symbols : [];
      setRows(list);
      setScanMeta(r.data || null);
      setSelectedSymbol(prev => (prev && list.some(x => x.symbol === prev) ? prev : (list[0]?.symbol || null)));
      setLastCandleChange(null);
      setCrosshairTime(null);
    } catch {
      setRows([]);
      setScanMeta(null);
      setSelectedSymbol(null);
      setScanError('Scan failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    runPreset(SCREENER_GROUPS[0].items[0]);
  }, []);

  useEffect(() => {
    if (filterInputsValid) {
      setFilterError('');
      return;
    }
    setFilterError('Invalid refine filter value. Market Cap accepts M/B/T, for example 250M, 1.2B, 0.8T.');
  }, [filterInputsValid]);

  useEffect(() => {
    if (!selectedSymbol) return;
    if (filteredRows.some(r => r.symbol === selectedSymbol)) return;
    setSelectedSymbol(filteredRows[0]?.symbol || null);
    setLastCandleChange(null);
    setCrosshairTime(null);
  }, [filteredRows, selectedSymbol]);

  useEffect(() => {
    if (selectedSymbol || !filteredRows.length) return;
    setSelectedSymbol(filteredRows[0].symbol);
  }, [filteredRows, selectedSymbol]);

  function clearRefineFilters() {
    setSymbolQuery('');
    setMinPrice('');
    setMaxPrice('');
    setMinMcap('');
    setMaxMcap('');
    setMaxCrossDistance('');
    setMinStochSpread('');
    setFilterError('');
  }

  async function addSelectedToWatchlist(name) {
    if (!onAddStocksToWatchlist || !selectedSymbol) return;
    try {
      await onAddStocksToWatchlist([selectedSymbol], name);
      setWlPickOpen(false);
      setAddAllMenuOpen(false);
    } catch {
      // parent surfaces error; keep menu open for retry
    }
  }

  async function addAllToWatchlist(name) {
    if (!onAddStocksToWatchlist || !refinedSymbols.length) return;
    try {
      await onAddStocksToWatchlist(refinedSymbols, name);
      setWlPickOpen(false);
      setAddAllMenuOpen(false);
    } catch {
      // parent surfaces error; keep menu open for retry
    }
  }

  function onDividerMouseDown(e) {
    e.preventDefault();
    draggingRef.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = paneWidth;
    function onMouseMove(ev) {
      if (!draggingRef.current) return;
      const total = wrapperRef.current?.clientWidth || 1200;
      setPaneWidth(Math.max(240, Math.min(total - 500, startWidthRef.current + ev.clientX - startXRef.current)));
    }
    function onMouseUp() {
      draggingRef.current = false;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    }
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  function handleSaveLayout() {
    const payload = {
      ...heightsRef.current,
      potentialSwingsPaneWidth: paneWidth,
      potentialSwingsChartLayout: chartLayout,
      potentialSwingsTimeframe: timeframe,
      potentialSwingsTimeframe2: timeframe2,
      potentialSwingsTimeframe3: timeframe3,
    };
    axios.post(`${API}/api/layout`, payload)
      .then(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Layout saved.' })))
      .catch(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Failed to save layout.' })));
  }

  function renderPanel(sym, tf, setTf, onLastChange, cacheKey, hasBorderRight) {
    if (!sym) return null;
    return (
      <div key={cacheKey} style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0, borderRight: hasBorderRight ? '2px solid var(--border)' : 'none' }}>
        <ChartHeaderBar
          symbol={sym}
          timeframe={tf}
          onTimeframeChange={newTf => {
            setTf(newTf);
            onLastChange(null);
            setCrosshairTime(null);
          }}
        />
        <ChartContainer
          symbol={sym}
          timeframe={tf}
          emas={emas}
          volumeVisible={volumeVisible}
          visiblePanels={visiblePanels}
          panelOrder={panelOrder}
          onTogglePanel={handleTogglePanel}
          onMovePanel={handleMovePanel}
          onLastChange={onLastChange}
          onHeightsChange={h => { heightsRef.current = h; }}
          onCrosshairMove={setCrosshairTime}
          crosshairTime={crosshairTime}
          drawingScopeId={`potential-swings:${cacheKey}`}
          drawingAutoFocus={false}
        />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', backgroundColor: 'var(--bg-primary)', overflow: 'hidden' }}>
      <div className="chart-app-toolbar" style={{ height: 44, flexShrink: 0, backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 12px', gap: 8, overflowX: 'auto' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13, color: 'var(--text-primary)', flexShrink: 0 }}>
          {selectedSymbol || 'Potential Swings'}
        </span>
        {lastCandleChange !== null && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, flexShrink: 0,
            color: lastCandleChange >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
            backgroundColor: lastCandleChange >= 0 ? 'rgba(63,185,80,0.12)' : 'rgba(248,81,73,0.12)',
            border: `1px solid ${lastCandleChange >= 0 ? '#3fb95044' : '#f8514944'}`,
            borderRadius: 4, padding: '1px 6px',
          }}>
            {lastCandleChange >= 0 ? '+' : ''}{lastCandleChange.toFixed(2)}%
          </span>
        )}
        <div style={{ width: 1, height: 20, backgroundColor: 'var(--border)', flexShrink: 0 }} />
        <div onClick={() => setVolumeVisible(v => !v)}
          style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: 'var(--bg-tertiary)', border: `1px solid ${volumeVisible ? '#388bfd55' : 'var(--border)'}`, borderRadius: 4, padding: '0 8px', height: 26, opacity: volumeVisible ? 1 : 0.5, cursor: 'pointer', flexShrink: 0 }}>
          <div style={{ width: 8, height: 8, backgroundColor: '#388bfd', borderRadius: 2 }} />
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 500 }}>Vol</span>
        </div>
        <EMAControls emas={emas} onChange={setEmas} />
        <ExternalFinancialsLinks symbol={selectedSymbol} />

        <div style={{ flex: 1, minWidth: 8 }} />

        <DrawingToolsDesignControl />

        <div ref={indRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button type="button" onClick={() => { setIndOpen(o => !o); setViewOpen(false); }}
            style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: indOpen ? 'var(--bg-active)' : 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12 }}>
            Indicators <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6 }}><path d="M0 0l4 5 4-5z" /></svg>
          </button>
          {indOpen && indicatorMenuRect && (
            <div style={{ position: 'fixed', top: indicatorMenuRect.top, left: indicatorMenuRect.left, width: indicatorMenuRect.width, zIndex: CHART_TOOLBAR_OVERLAY_Z, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.6)', minWidth: 160, overflow: 'hidden' }}>
              {[{ key: 'stochrsi', label: 'StochRSI' }, { key: 'macd', label: 'MACD' }].map(ind => {
                const active = visiblePanels[ind.key];
                return (
                  <div key={ind.key} onClick={() => { handleTogglePanel(ind.key); setIndOpen(false); }}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 14px', cursor: 'pointer', fontSize: 13, color: active ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                    {ind.label}
                    <div style={{ width: 14, height: 14, borderRadius: 3, border: '1px solid var(--border)', backgroundColor: active ? 'var(--accent-blue)' : 'transparent' }} />
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div ref={viewRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button type="button" onClick={() => { setViewOpen(o => !o); setIndOpen(false); }}
            style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: chartLayout !== 'single' ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)', border: `1px solid ${chartLayout !== 'single' ? 'var(--accent-blue)' : 'var(--border)'}`, borderRadius: 5, padding: '0 10px', height: 28, color: chartLayout !== 'single' ? 'var(--accent-blue)' : 'var(--text-secondary)', fontSize: 12 }}>
            View <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6 }}><path d="M0 0l4 5 4-5z" /></svg>
          </button>
          {viewOpen && viewMenuRect && (
            <div style={{ position: 'fixed', top: viewMenuRect.top, left: viewMenuRect.left, width: viewMenuRect.width, zIndex: CHART_TOOLBAR_OVERLAY_Z, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.6)', minWidth: 230, overflow: 'hidden' }}>
              <div style={{ padding: '6px 0' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '4px 14px 6px' }}>Layout</div>
                {LAYOUTS.map(l => (
                  <div key={l.key} onClick={() => { setChartLayout(l.key); setViewOpen(false); }}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 14px', cursor: 'pointer', backgroundColor: chartLayout === l.key ? 'rgba(56,139,253,0.10)' : 'transparent', color: chartLayout === l.key ? 'var(--accent-blue)' : 'var(--text-secondary)', fontSize: 13 }}>
                    <div>
                      <div style={{ fontWeight: chartLayout === l.key ? 600 : 400 }}>{l.label}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>{l.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {selectedSymbol && (
          <button onClick={() => onOpenChart && onOpenChart(selectedSymbol)}
            style={{ display: 'flex', alignItems: 'center', gap: 4, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12, flexShrink: 0, cursor: 'pointer' }}>
            Open Full Chart ↗
          </button>
        )}

        <button onClick={handleSaveLayout}
          style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12, flexShrink: 0 }}>
          Save Layout
        </button>
      </div>

      <div ref={wrapperRef} style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ width: paneWidth, minWidth: 240, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRight: '1px solid var(--border)', position: 'relative' }}>
          <div ref={wlPickWrapRef} style={{ borderBottom: '1px solid var(--border)', padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {onAddStocksToWatchlist && rows.length > 0 && (
                <button
                  type="button"
                  ref={wlBtnWatchlistRef}
                  onClick={() => {
                    if (!watchlists?.length) {
                      if (window.confirm('You don\'t have any watchlists yet.\n\nOn the Watchlist tab, enter a name under "New watchlist..." and click Create.\n\nOpen the Watchlist tab now?')) {
                        onGoToWatchlist && onGoToWatchlist();
                      }
                      return;
                    }
                    setAddAllMenuOpen(false);
                    setWlPickOpen(o => !o);
                  }}
                  style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-secondary)', background: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, cursor: 'pointer', padding: '4px 8px', whiteSpace: 'nowrap', flexShrink: 0 }}
                >
                  Watchlist <svg width="7" height="4" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6, flexShrink: 0 }}><path d="M0 0l4 5 4-5z" /></svg>
                </button>
              )}
              <input
                value={librarySearch}
                onChange={e => setLibrarySearch(e.target.value)}
                onFocus={() => setScreenerDrawerOpen(true)}
                placeholder="Find screener..."
                style={{ flex: 1, minWidth: 0, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 4, height: 26, padding: '0 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
              />
              <button
                type="button"
                ref={screenerToggleRef}
                onClick={() => setScreenerDrawerOpen(open => !open)}
                style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: screenerDrawerOpen ? 'var(--accent-blue)' : 'var(--text-secondary)', background: screenerDrawerOpen ? 'rgba(56,139,253,0.12)' : 'var(--bg-tertiary)', border: `1px solid ${screenerDrawerOpen ? 'var(--accent-blue)' : 'var(--border)'}`, borderRadius: 5, cursor: 'pointer', padding: '4px 8px', whiteSpace: 'nowrap', flexShrink: 0 }}
                title={`Active screener: ${activePresetLabel}`}
              >
                <span style={{ color: 'var(--text-muted)' }}>S:</span>
                <span style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {activePresetLabel}
                </span>
              </button>
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{loading ? 'Scanning...' : `Matched: ${scanMeta?.count || 0}`}</span>
              <span>{scanMeta?.timeframe || '2W'}</span>
            </div>
            {scanError ? (
              <div style={{ fontSize: 10, color: 'var(--accent-red)', lineHeight: 1.35 }}>{scanError}</div>
            ) : null}
            {wlPickOpen && wlPickRect && watchlists.length > 0 && (
              <div
                style={{
                  position: 'fixed',
                  top: wlPickRect.top,
                  left: wlPickRect.left,
                  width: wlPickRect.width,
                  zIndex: CHART_TOOLBAR_OVERLAY_Z,
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
                  overflow: 'hidden',
                }}
              >
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '8px 12px 4px' }}>Watchlist</div>
                {refinedSymbols.length > 0 && (
                  <div
                    ref={addAllRowRef}
                    role="menuitem"
                    onMouseDown={e => e.preventDefault()}
                    onClick={() => setAddAllMenuOpen(o => !o)}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)', borderTop: '1px solid var(--border-light)', borderBottom: '1px solid var(--border-light)' }}
                  >
                    <span>Add all to... </span>
                    <span style={{ fontFamily: 'var(--font-mono)', opacity: 0.8 }}>{'>'}</span>
                  </div>
                )}
                {selectedSymbol && (
                  <div style={{ borderBottom: '1px solid var(--border-light)' }}>
                    <div style={{ padding: '7px 12px 5px', fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Add selected ({selectedSymbol})
                    </div>
                    {watchlists.map(w => (
                      <div
                        key={`selected-${w.name}`}
                        role="menuitem"
                        onMouseDown={e => e.preventDefault()}
                        onClick={() => { void addSelectedToWatchlist(w.name); }}
                        style={{ padding: '8px 22px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)' }}
                        onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                        onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                      >
                        {w.name}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {addAllMenuOpen && wlPickOpen && addAllMenuRect && refinedSymbols.length > 0 && watchlists.length > 0 && (
              <div
                style={{
                  position: 'fixed',
                  top: addAllMenuRect.top,
                  left: addAllMenuRect.left,
                  width: addAllMenuRect.width,
                  zIndex: CHART_TOOLBAR_OVERLAY_Z,
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
                  overflow: 'hidden',
                }}
              >
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '8px 12px 4px' }}>
                  {`Add all to Watchlist (${refinedSymbols.length})`}
                </div>
                {watchlists.map(w => (
                  <div
                    key={`all-${w.name}`}
                    role="menuitem"
                    onMouseDown={e => e.preventDefault()}
                    onClick={() => { void addAllToWatchlist(w.name); }}
                    style={{ padding: '9px 14px', cursor: 'pointer', fontSize: 13, color: 'var(--text-primary)' }}
                    onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                    onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                  >
                    {w.name}
                  </div>
                ))}
              </div>
            )}
          </div>

          {screenerDrawerOpen && (
            <>
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  zIndex: 30,
                  backgroundColor: 'rgba(0,0,0,0.28)',
                }}
              />
              <div
                ref={screenerDrawerRef}
                style={{
                  position: 'absolute',
                  top: 8,
                  left: 8,
                  right: 8,
                  maxHeight: '50%',
                  zIndex: 31,
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  boxShadow: '0 10px 26px rgba(0,0,0,0.48)',
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                    Screeners ({visibleScreenerCount})
                  </div>
                  <button
                    type="button"
                    onClick={() => setScreenerDrawerOpen(false)}
                    style={{ height: 22, minWidth: 22, borderRadius: 4, border: '1px solid var(--border)', backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12 }}
                  >
                    x
                  </button>
                </div>
                <div style={{ padding: 8, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {visibleScreenerGroups.map(group => (
                    <div key={group.key} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
                        {group.label}
                      </div>
                      {group.items.map(p => (
                        <button key={p.key} onClick={() => { runPreset(p); setScreenerDrawerOpen(false); }}
                          style={{
                            textAlign: 'left',
                            padding: '7px 9px',
                            borderRadius: 5,
                            border: `1px solid ${activePreset === p.key ? 'var(--accent-blue)' : 'var(--border)'}`,
                            backgroundColor: activePreset === p.key ? 'rgba(56,139,253,0.12)' : 'var(--bg-tertiary)',
                            color: activePreset === p.key ? 'var(--accent-blue)' : 'var(--text-secondary)',
                            cursor: 'pointer',
                          }}>
                          <div style={{ fontSize: 12, fontWeight: 600 }}>{p.label}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{p.desc}</div>
                        </button>
                      ))}
                    </div>
                  ))}
                  {visibleScreenerGroups.length === 0 ? (
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '4px 2px' }}>
                      No screener matches your search.
                    </div>
                  ) : null}
                </div>
              </div>
            </>
          )}

          <div style={{ borderBottom: '1px solid var(--border)', padding: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            <input
              value={symbolQuery}
              onChange={e => setSymbolQuery(e.target.value)}
              placeholder="Symbol"
              style={{ gridColumn: '1 / span 2', backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 4, height: 26, padding: '0 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
            />
            <input
              value={minPrice}
              onChange={e => setMinPrice(e.target.value)}
              placeholder="Min Price"
              style={{ backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 4, height: 26, padding: '0 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
            />
            <input
              value={maxPrice}
              onChange={e => setMaxPrice(e.target.value)}
              placeholder="Max Price"
              style={{ backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 4, height: 26, padding: '0 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
            />
            <input
              value={minMcap}
              onChange={e => setMinMcap(e.target.value)}
              placeholder="Min MCap (M/B/T)"
              style={{ backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 4, height: 26, padding: '0 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
            />
            <input
              value={maxMcap}
              onChange={e => setMaxMcap(e.target.value)}
              placeholder="Max MCap (M/B/T)"
              style={{ backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 4, height: 26, padding: '0 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
            />
            <input
              value={maxCrossDistance}
              onChange={e => setMaxCrossDistance(e.target.value)}
              placeholder="Max hist distance"
              style={{ backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 4, height: 26, padding: '0 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
            />
            <input
              value={minStochSpread}
              onChange={e => setMinStochSpread(e.target.value)}
              placeholder="Min K-D spread"
              style={{ backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 4, height: 26, padding: '0 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
            />
            <div style={{ gridColumn: '1 / span 2', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                Refined: {filterInputsValid ? filteredRows.length : 0} / {rows.length}
              </div>
              <button
                type="button"
                onClick={clearRefineFilters}
                style={{ height: 24, padding: '0 8px', borderRadius: 4, border: '1px solid var(--border)', backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)', fontSize: 10, cursor: 'pointer' }}
              >
                Clear
              </button>
            </div>
            {filterError ? (
              <div style={{ gridColumn: '1 / span 2', fontSize: 10, color: 'var(--accent-red)', lineHeight: 1.35 }}>
                {filterError}
              </div>
            ) : null}
          </div>

          <div style={{ flex: 1, overflowY: 'auto' }}>
            {(filterInputsValid ? filteredRows : []).map(row => {
              const sel = row.symbol === selectedSymbol;
              const chg = Number(row.change_pct);
              const chgColor = Number.isFinite(chg) ? (chg >= 0 ? 'var(--accent-green)' : 'var(--accent-red)') : 'var(--text-muted)';
              return (
                <div key={row.symbol}
                  onClick={() => {
                    setSelectedSymbol(row.symbol);
                    setLastCandleChange(null);
                    setCrosshairTime(null);
                  }}
                  style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-light)', borderLeft: sel ? '2px solid var(--accent-blue)' : '2px solid transparent', backgroundColor: sel ? 'rgba(56,139,253,0.08)' : 'transparent', cursor: 'pointer' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: sel ? 'var(--accent-blue)' : 'var(--text-primary)', fontWeight: 600 }}>{row.symbol}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: chgColor }}>{formatPct(row.change_pct)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    <span>Price {formatPrice(row.price)}</span>
                    <span>dist {fmtSmall(row.near_cross_distance, 3)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2, fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    <span>Hist {fmtSmall(row.hist_prev, 3)} → {fmtSmall(row.hist_curr, 3)}</span>
                    <span>K/D {fmtSmall(row.stoch_k, 1)}/{fmtSmall(row.stoch_d, 1)}</span>
                  </div>
                </div>
              );
            })}
            {!loading && filterInputsValid && filteredRows.length === 0 ? (
              <div style={{ padding: '12px 10px', fontSize: 11, color: 'var(--text-muted)' }}>
                No symbols match the current refine filters.
              </div>
            ) : null}
          </div>
        </div>

        <div onMouseDown={onDividerMouseDown}
          style={{ width: 4, backgroundColor: 'var(--border)', cursor: 'col-resize', flexShrink: 0 }}
        />

        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', minWidth: 400 }}>
          {!selectedSymbol ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              {loading ? 'Scanning potential swings...' : 'Select a symbol from the left panel'}
            </div>
          ) : (
            <DrawingMirrorProvider
              mirrorStorageKey={selectedSymbol && (chartLayout === '2h' || chartLayout === '3h') ? `potential-swings:${selectedSymbol}:mirror` : null}
              mirrorContextId={`potential-swings-split-${selectedSymbol || 'none'}`}
            >
              <DrawingWorkspaceProvider workspaceId={`potential-swings-${selectedSymbol}`}>
                <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minWidth: 400, position: 'relative' }}>
                  <DrawingToolbarConnected />
                  <DrawingFloatPaletteConnected />
                  {renderPanel(selectedSymbol, timeframe, tf => setTimeframe(tf), pct => setLastCandleChange(pct), `${selectedSymbol}-p1-${timeframe}`, chartLayout !== 'single')}
                  {(chartLayout === '2h' || chartLayout === '3h') && renderPanel(selectedSymbol, timeframe2, tf => setTimeframe2(tf), () => {}, `${selectedSymbol}-p2-${timeframe2}`, chartLayout === '3h')}
                  {chartLayout === '3h' && renderPanel(selectedSymbol, timeframe3, tf => setTimeframe3(tf), () => {}, `${selectedSymbol}-p3-${timeframe3}`, false)}
                </div>
              </DrawingWorkspaceProvider>
            </DrawingMirrorProvider>
          )}
        </div>
      </div>
    </div>
  );
}
