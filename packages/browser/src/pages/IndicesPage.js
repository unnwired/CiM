import React, { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'react';
import { applySavedOrder, reorderByGap, insertionGapFromRowHover } from '../utils/listOrder';
import { setListDragImage, DropInsetLine } from '../utils/listDnD';
import axios from 'axios';
import IndexChartContainer from '../components/chart/IndexChartContainer';
import { DrawingMirrorProvider } from '../components/chart/drawing/DrawingMirrorContext';
import { DrawingWorkspaceProvider } from '../components/chart/drawing/DrawingWorkspaceContext';
import { DrawingToolbarConnected, DrawingFloatPaletteConnected } from '../components/chart/drawing/DrawingToolbar';
import DrawingToolsDesignControl from '../components/chart/drawing/DrawingToolsDesignControl';
import EMAControls         from '../components/chart/EMAControls';
import ChartHeaderBar      from '../components/chart/ChartHeaderBar';
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
import InstrumentNotesIcon from '../components/InstrumentNotesIcon';
import IndexStarTag from '../components/IndexStarTag';
import { sortIndicesByStarTier, normalizeStarTags } from '../utils/indexStarTags';
import {
  DEFAULT_CHART_LAYOUT,
  DEFAULT_CHART_TIMEFRAME_1,
  DEFAULT_CHART_TIMEFRAME_2,
  DEFAULT_CHART_TIMEFRAME_3,
  normalizeSavedTimeframe3,
} from '../config/chartViewDefaults';
import { CHART_DATA_UPDATED_EVENT, MARKET_PULSE_REFRESH_EVENT } from '../chartEvents';
import { useChartPrefsContext } from '../chartPrefs/useChartPrefs';
import {
  CHART_PAGE_IDS,
  hydrateIndicatorPanels,
  mergeIndicatorPanelSaveFields,
  pageLayoutToApiPayload,
} from '../chartPrefs/chartPageLayout';
import {
  useWebChartLayoutMount,
  useWebChartLayoutAutoSave,
  saveWebChartLayoutOrServer,
} from '../chartPrefs/useWebChartPageLayout';
import { useIndicatorPanelAutoSave } from '../chartPrefs/useIndicatorPanelAutoSave';
import { usePatchOverlay } from '../intraday/usePatchOverlay';
import { useRegisterFocusedSymbol } from '../intraday/useRegisterFocusedSymbol';
import { symbolsForIndicesPage } from '../intraday/intradayRefreshScopes';
import { isIntradayLiveTimeframe } from '../intraday/patchOverlay';
import { usePageLive } from '../intraday/pageLiveContext';
import { useSyncedPanelHeights, columnCountForChartLayout, multiColumnHeightProps } from '../hooks/useSyncedPanelHeights';
import {
  LIST_ORDER_KEYS,
  persistLayoutOrderFields,
} from '../layout/listOrderPersistence';
import { useIndicesListOrderAutoSave } from '../layout/useIndicesListOrderAutoSave';

const API = '';

const DEFAULT_ORDER  = ['stochrsi', 'macd'];

const LAYOUTS = [
  { key: 'single', label: 'Single',              desc: 'One chart panel'               },
  { key: '2h',     label: '2 — Multi Timeframe', desc: 'Same index, two timeframes'    },
  { key: '3h',     label: '3 — Multi Timeframe', desc: 'Same index, three timeframes'  },
];

export default function IndicesPage({ onOpenConstituents, onContextMenuRequest }) {
  const [indices, setIndices]           = useState([]);
  const [selected, setSelected]         = useState(null);
  const [loading, setLoading]           = useState(true);
  const [search, setSearch]             = useState('');
  const searchInputRef                  = useRef(null);

  const [timeframe,  setTimeframe]  = useState(DEFAULT_CHART_TIMEFRAME_1);
  const [timeframe2, setTimeframe2] = useState(DEFAULT_CHART_TIMEFRAME_2);
  const [timeframe3, setTimeframe3] = useState(DEFAULT_CHART_TIMEFRAME_3);
  const [lastChange, setLastChange] = useState(null);

  const [emas,          setEmas]          = useState(() => getPersistedEmaSet());
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(true));
  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());
  const [panelOrder,    setPanelOrder]    = useState(DEFAULT_ORDER);

  // Crosshair sync across panels
  const [crosshairTime, setCrosshairTime] = useState(null);

  const [indOpen,     setIndOpen]     = useState(false);
  const [viewOpen,    setViewOpen]    = useState(false);
  const [chartLayout, setChartLayout] = useState(DEFAULT_CHART_LAYOUT);
  const [indDropdownRect, setIndDropdownRect] = useState(null);
  const [viewDropdownRect, setViewDropdownRect] = useState(null);
  const indRef                        = useRef(null);
  const viewRef                       = useRef(null);

  const [paneWidth, setPaneWidth]     = useState(240);
  const chartPrefs = useChartPrefsContext();
  const { liveActive, liveTick } = usePageLive('indices');
  const { overlayIndexRows, refreshTick: patchRefreshTick } = usePatchOverlay('indices');
  const displayIndices = useMemo(
    () => overlayIndexRows(indices),
    [indices, overlayIndexRows, patchRefreshTick],
  );
  useRegisterFocusedSymbol('indices', useMemo(
    () => symbolsForIndicesPage(selected),
    [selected],
  ));
  const draggingRef                   = useRef(false);
  const startXRef                     = useRef(0);
  const startWidthRef                 = useRef(0);
  const wrapperRef                    = useRef(null);
  const rowRefs                       = useRef({});
  const { getPanelHeights, heightsRef, handleHeightsChange, applyLayoutHeights, heightsRevision } = useSyncedPanelHeights({
    columnCount: columnCountForChartLayout(chartLayout),
  });
  const eqDragIdxRef                  = useRef(null);
  const equityDropGapRef              = useRef(null);
  const [equityDropGap, setEquityDropGap] = useState(null);
  const [equityDraggingIdx, setEquityDraggingIdx] = useState(null);

  /** User order of equity index symbols (persisted in layout). */
  const [equitySymbolOrder, setEquitySymbolOrder] = useState(null);
  /** User star tags per equity index symbol (persisted in layout). */
  const [indexStarTags, setIndexStarTags] = useState({});

  useEffect(() => {
    function handle(e) {
      if (viewRef.current && !viewRef.current.contains(e.target)) setViewOpen(false);
      if (indRef.current && !indRef.current.contains(e.target)) setIndOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

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

  const loadIndices = useCallback(() => {
    return axios.get(`${API}/api/indices`).then(r => {
      const chartable = (r.data.data || []).filter(i => i.chartable && i.category !== 'commodity');
      setIndices(chartable);
      setSelected(prev => {
        if (!chartable.length) return null;
        if (prev && chartable.some(i => i.symbol === prev.symbol)) {
          return chartable.find(i => i.symbol === prev.symbol);
        }
        return chartable[0];
      });
    });
  }, []);

  useEffect(() => {
    loadIndices()
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [loadIndices]);

  const { layoutHydrated, indicatorsHydrated } = useWebChartLayoutMount(CHART_PAGE_IDS.indices, {
    setChartLayout, setTimeframe, setTimeframe2, setTimeframe3, setPaneWidth,
  }, (data, fromPrefs, globalIndicator) => {
    const savedOrder = data[LIST_ORDER_KEYS.equityIndexSymbolOrder];
    if (Array.isArray(savedOrder) && savedOrder.length) {
      setEquitySymbolOrder(savedOrder);
    }
    const savedTags = data[LIST_ORDER_KEYS.indexStarTags];
    if (savedTags && typeof savedTags === 'object') {
      setIndexStarTags(normalizeStarTags(savedTags));
    }
    hydrateIndicatorPanels(data, fromPrefs, globalIndicator, { applyLayoutHeights, setPanelOrder });
  });

  useIndicesListOrderAutoSave({
    email: chartPrefs?.email,
    ready: layoutHydrated && indicatorsHydrated,
    indexStarTags,
    equitySymbolOrder,
  });

  useWebChartLayoutAutoSave(CHART_PAGE_IDS.indices, {
    chartLayout, timeframe, timeframe2, timeframe3, paneWidth,
  }, layoutHydrated, true, indicatorsHydrated);

  const onHeightsChangePersist = useIndicatorPanelAutoSave({
    handleHeightsChange,
    heightsRef,
    panelOrder,
    ready: layoutHydrated && indicatorsHydrated,
  });

  useEffect(() => {
    function reloadIndices() {
      loadIndices().catch(() => {});
    }
    window.addEventListener(CHART_DATA_UPDATED_EVENT, reloadIndices);
    window.addEventListener(MARKET_PULSE_REFRESH_EVENT, reloadIndices);
    return () => {
      window.removeEventListener(CHART_DATA_UPDATED_EVENT, reloadIndices);
      window.removeEventListener(MARKET_PULSE_REFRESH_EVENT, reloadIndices);
    };
  }, [loadIndices]);

  const handlePanelLastChange = useCallback((pct, lastPrice) => {
    if (pct != null && Number.isFinite(Number(pct))) {
      setLastChange(Math.round(Number(pct) * 100) / 100);
    }
    setIndices(prev => {
      if (!selected?.symbol || pct == null || !Number.isFinite(Number(pct))) return prev;
      const rounded = Math.round(Number(pct) * 100) / 100;
      return prev.map(i => {
        if (i.symbol !== selected.symbol) return i;
        const next = { ...i, change_pct: rounded };
        if (lastPrice != null && Number.isFinite(Number(lastPrice))) {
          next.last_price = Number(lastPrice);
        }
        return next;
      });
    });
  }, [selected?.symbol]);

  const equity = useMemo(() => {
    const raw = displayIndices.filter(i => i.category === 'equity');
    const ordered = applySavedOrder(raw, equitySymbolOrder, i => i.symbol);
    return sortIndicesByStarTier(ordered, indexStarTags, i => i.symbol);
  }, [displayIndices, equitySymbolOrder, indexStarTags]);
  const filteredEquity = useMemo(() => {
    const q = search.trim().toUpperCase();
    if (!q) return equity;
    return equity.filter(i =>
      String(i.symbol || '').toUpperCase().includes(q) ||
      String(i.name || '').toUpperCase().includes(q)
    );
  }, [equity, search]);

  useEffect(() => {
    if (!filteredEquity.length) return;
    if (!selected || !filteredEquity.some(i => i.symbol === selected.symbol)) {
      setSelected(filteredEquity[0]);
      setLastChange(null);
      setCrosshairTime(null);
    }
  }, [filteredEquity, selected]);

  useEffect(() => {
    function handleKey(e) {
      if (!['ArrowUp','ArrowDown'].includes(e.key)) return;
      if (indOpen) return;
      e.preventDefault();
      const idx = filteredEquity.findIndex(i => i.symbol === selected?.symbol);
      if (idx === -1) return;
      const next = e.key === 'ArrowDown'
        ? Math.min(idx + 1, filteredEquity.length - 1)
        : Math.max(idx - 1, 0);
      setSelected(filteredEquity[next]);
      setLastChange(null);
      setCrosshairTime(null);
      rowRefs.current[next]?.scrollIntoView({ block: 'nearest' });
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [filteredEquity, selected, indOpen]);

  useEffect(() => {
    if (!selected?.symbol || filteredEquity.length === 0) return;
    const idx = filteredEquity.findIndex(i => i.symbol === selected.symbol);
    if (idx < 0) return;
    rowRefs.current[idx]?.scrollIntoView({ block: 'nearest' });
  }, [filteredEquity, selected]);

  useEffect(() => {
    function onGlobalPick(e) {
      const d = e?.detail || {};
      if (String(d.targetView || '') !== 'indices') return;
      const symbol = String(d.symbol || '').toUpperCase();
      if (!symbol) return;
      const pick = equity.find(i => String(i.symbol || '').toUpperCase() === symbol);
      if (pick) {
        setSelected(pick);
        setLastChange(null);
        setCrosshairTime(null);
      }
    }
    window.addEventListener('cim-global-search-select', onGlobalPick);
    return () => window.removeEventListener('cim-global-search-select', onGlobalPick);
  }, [equity]);

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

  function onDividerMouseDown(e) {
    e.preventDefault();
    draggingRef.current = true; startXRef.current = e.clientX; startWidthRef.current = paneWidth;
    function onMouseMove(ev) {
      if (!draggingRef.current) return;
      const total = wrapperRef.current?.clientWidth || 1200;
      setPaneWidth(Math.max(160, Math.min(total - 500, startWidthRef.current + ev.clientX - startXRef.current)));
    }
    function onMouseUp() { draggingRef.current = false; window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp); }
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  function handleSaveLayout() {
    const snapshot = { chartLayout, timeframe, timeframe2, timeframe3, paneWidth };
    const normalizedTags = normalizeStarTags(indexStarTags);
    const payload = mergeIndicatorPanelSaveFields({
      ...pageLayoutToApiPayload(CHART_PAGE_IDS.indices, snapshot),
      ...(equitySymbolOrder && equitySymbolOrder.length
        ? { [LIST_ORDER_KEYS.equityIndexSymbolOrder]: equitySymbolOrder }
        : {}),
      [LIST_ORDER_KEYS.indexStarTags]: normalizedTags,
    }, heightsRef.current, panelOrder);
    saveWebChartLayoutOrServer(CHART_PAGE_IDS.indices, chartPrefs, snapshot, payload);
    persistLayoutOrderFields(chartPrefs?.email, {
      [LIST_ORDER_KEYS.indexStarTags]: normalizedTags,
      ...(equitySymbolOrder?.length
        ? { [LIST_ORDER_KEYS.equityIndexSymbolOrder]: equitySymbolOrder }
        : {}),
    });
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

  function persistEquityOrder(symbols) {
    setEquitySymbolOrder(symbols);
    persistLayoutOrderFields(chartPrefs?.email, {
      [LIST_ORDER_KEYS.equityIndexSymbolOrder]: symbols,
    });
  }

  function handleStarTagChange(symbol, tag) {
    setIndexStarTags((prev) => {
      const next = { ...prev };
      if (tag == null) {
        delete next[symbol];
      } else {
        next[symbol] = tag;
      }
      const normalized = normalizeStarTags(next);
      persistLayoutOrderFields(chartPrefs?.email, {
        [LIST_ORDER_KEYS.indexStarTags]: normalized,
      });
      return normalized;
    });
  }

  function clearEquityDnD() {
    eqDragIdxRef.current = null;
    equityDropGapRef.current = null;
    setEquityDropGap(null);
    setEquityDraggingIdx(null);
  }

  function onEquityDragStart(e, idx) {
    eqDragIdxRef.current = idx;
    setEquityDraggingIdx(idx);
    const row = equity[idx];
    if (row) setListDragImage(e.dataTransfer, row.symbol, row.name);
  }

  function onEquityDragOver(e, i) {
    if (eqDragIdxRef.current === null) return;
    e.preventDefault();
    const gap = insertionGapFromRowHover(e.clientY, e.currentTarget, i, equity.length);
    equityDropGapRef.current = gap;
    setEquityDropGap(gap);
  }

  function onEquityDrop(e) {
    e.preventDefault();
    const from = eqDragIdxRef.current;
    const gap = equityDropGapRef.current;
    clearEquityDnD();
    if (from === null || gap === null || gap === undefined) return;
    const orderedSyms = equity.map(i => i.symbol);
    const nextOrder = reorderByGap(orderedSyms, from, gap);
    if (JSON.stringify(nextOrder) === JSON.stringify(orderedSyms)) return;
    persistEquityOrder(nextOrder);
  }

  function onEquityDragEnd() {
    clearEquityDnD();
  }

  // Render a single index chart panel — all panels share crosshairTime
  function renderPanel(sym, name, tf, setTf, onLastChange, cacheKey, hasBorderRight, columnIndex) {
    if (!sym) return null;
    const tfLive = liveActive && isIntradayLiveTimeframe(tf);
    return (
      <div key={cacheKey} style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', minWidth:0, borderRight: hasBorderRight ? '2px solid var(--border)' : 'none' }}>
        <ChartHeaderBar
          symbol={name}
          timeframe={tf}
          onTimeframeChange={newTf => { setTf(newTf); onLastChange(null); setCrosshairTime(null); }}
        />
        <IndexChartContainer
          key={cacheKey}
          symbol={sym}
          timeframe={tf}
          liveToday={tfLive}
          liveRefreshKey={tfLive ? liveTick : null}
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
          drawingScopeId={`indices:${cacheKey}`}
          drawingAutoFocus={false}
        />
      </div>
    );
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', width:'100%', backgroundColor:'var(--bg-primary)', overflow:'hidden' }}>

      {/* ── Top bar ── */}
      <div className="chart-app-toolbar" style={{ height:44, flexShrink:0, backgroundColor:'var(--bg-secondary)', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', padding:'0 12px', gap:8, overflowX:'auto' }}>
        <div style={{ display:'flex', alignItems:'center', gap:6, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, width:220, flexShrink:0 }}>
          <svg width="11" height="11" viewBox="0 0 16 16" fill="var(--text-muted)"><path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z"/></svg>
          <input
            ref={searchInputRef}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search index…"
            style={{ background:'transparent', color:'var(--text-primary)', flex:1, fontSize:12, border:'none', outline:'none' }}
          />
          {search ? <button type="button" onClick={() => setSearch('')} style={{ background:'none', color:'var(--text-muted)', fontSize:14, border:'none', lineHeight:1, cursor:'pointer' }}>×</button> : null}
        </div>

        {selected && (
          <>
            <span style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:13, color:'var(--text-primary)', flexShrink:0 }}>{selected.name}</span>
            {lastChange !== null && (
              <span style={{ fontFamily:'var(--font-mono)', fontSize:11, fontWeight:600, flexShrink:0, color: lastChange>=0?'var(--accent-green)':'var(--accent-red)', backgroundColor: lastChange>=0?'rgba(63,185,80,0.12)':'rgba(248,81,73,0.12)', border:`1px solid ${lastChange>=0?'#3fb95044':'#f8514944'}`, borderRadius:4, padding:'1px 6px' }}>
                {lastChange>=0?'+':''}{lastChange.toFixed(2)}%
              </span>
            )}
            <div style={{ width:1, height:20, backgroundColor:'var(--border)', flexShrink:0 }} />
            <div onClick={() => setVolumeVisible(v=>!v)}
              style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:`1px solid ${volumeVisible?'#388bfd55':'var(--border)'}`, borderRadius:4, padding:'0 8px', height:26, opacity: volumeVisible?1:0.5, cursor:'pointer', flexShrink:0 }}>
              <div style={{ width:8, height:8, backgroundColor:'#388bfd', borderRadius:2 }} />
              <span style={{ fontSize:11, color:'var(--text-secondary)', fontWeight:500 }}>Vol</span>
            </div>
            <EMAControls emas={emas} onChange={setEmas} />
          </>
        )}

        <div style={{ flex:1, minWidth:8 }} />

        <DrawingToolsDesignControl />

        {selected && selected.category === 'equity' && (
          <button onClick={() => onOpenConstituents && onOpenConstituents(selected)}
            style={{ display:'flex', alignItems:'center', gap:4, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, color:'var(--text-secondary)', fontSize:12, flexShrink:0, cursor:'pointer' }}
            onMouseEnter={e => { e.currentTarget.style.borderColor='var(--accent-blue)'; e.currentTarget.style.color='var(--accent-blue)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor='var(--border)'; e.currentTarget.style.color='var(--text-secondary)'; }}
          >Constituents ↗</button>
        )}

        <div ref={indRef} style={{ position:'relative', flexShrink:0 }}>
          <button onClick={() => { setIndOpen(o=>!o); setViewOpen(false); }}
            style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, color:'var(--text-secondary)', fontSize:12, cursor:'pointer' }}>
            Indicators <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity:0.6 }}><path d="M0 0l4 5 4-5z"/></svg>
          </button>
          {indOpen && indDropdownRect && (
            <div style={{ position:'fixed', top:indDropdownRect.top, left:indDropdownRect.left, width:indDropdownRect.width, zIndex:200000, backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6, boxShadow:'0 8px 24px rgba(0,0,0,0.6)', minWidth:160, overflow:'hidden' }}>
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
          <button onClick={() => { setViewOpen(o=>!o); setIndOpen(false); }}
            style={{ display:'flex', alignItems:'center', gap:5, backgroundColor: chartLayout!=='single'?'rgba(56,139,253,0.15)':'var(--bg-tertiary)', border:`1px solid ${chartLayout!=='single'?'var(--accent-blue)':'var(--border)'}`, borderRadius:5, padding:'0 10px', height:28, color: chartLayout!=='single'?'var(--accent-blue)':'var(--text-secondary)', fontSize:12, cursor:'pointer' }}>
            View <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity:0.6 }}><path d="M0 0l4 5 4-5z"/></svg>
          </button>
          {viewOpen && viewDropdownRect && (
            <div style={{ position:'fixed', top:viewDropdownRect.top, left:viewDropdownRect.left, width:viewDropdownRect.width, zIndex:200000, backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6, boxShadow:'0 8px 24px rgba(0,0,0,0.6)', minWidth:230, overflow:'hidden' }}>
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

        <button onClick={handleSaveLayout}
          style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, color:'var(--text-secondary)', fontSize:12, cursor:'pointer', flexShrink:0 }}
          onMouseEnter={e => e.currentTarget.style.borderColor='var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.borderColor='var(--border)'}
        >Save Layout</button>
      </div>

      {/* ── Body ── */}
      <div ref={wrapperRef} style={{ flex:1, display:'flex', overflow:'hidden' }}>
        <div style={{ width:paneWidth, minWidth:160, flexShrink:0, display:'flex', flexDirection:'column', overflowY:'auto', overflowX:'hidden', borderRight:'1px solid var(--border)' }}>
          {filteredEquity.length > 0 && (
            <div style={{ flexShrink:0, borderBottom:'1px solid var(--border)', padding:'4px 0' }}>
              <div style={{ fontSize:10, fontWeight:700, color:'var(--text-muted)', padding:'4px 10px 2px', textTransform:'uppercase', letterSpacing:'0.06em' }}>Equity</div>
              {equityDraggingIdx !== null && equityDropGap === 0 ? <DropInsetLine /> : null}
              {filteredEquity.map((idx, i) => (
                <React.Fragment key={idx.symbol}>
                  <IndexRow
                    index={idx}
                    i={i}
                    selected={selected}
                    onSelect={s => { setSelected(s); setLastChange(null); setCrosshairTime(null); }}
                    rowRefs={rowRefs}
                    onContextMenuRequest={onContextMenuRequest}
                    draggable={equity.length > 1}
                    onDragStartRow={onEquityDragStart}
                    onDragOverRow={onEquityDragOver}
                    onDropRow={onEquityDrop}
                    onDragEndRow={onEquityDragEnd}
                    dragDimmed={equityDraggingIdx === i}
                    starTag={indexStarTags[idx.symbol] ?? null}
                    onStarTagChange={handleStarTagChange}
                  />
                  {equityDraggingIdx !== null && equityDropGap === i + 1 ? <DropInsetLine /> : null}
                </React.Fragment>
              ))}
            </div>
          )}
        </div>

        <div onMouseDown={onDividerMouseDown}
          style={{ width:4, backgroundColor:'var(--border)', cursor:'col-resize', flexShrink:0, transition:'background 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.backgroundColor='var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.backgroundColor='var(--border)'}
        />

        <div style={{ flex:1, overflow:'hidden', display:'flex', minWidth:400 }}>
          {!selected ? (
            <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', color:'var(--text-muted)', fontSize:13 }}>Select an index to view chart</div>
          ) : (
            <DrawingMirrorProvider
              mirrorStorageKey={
                selected && (chartLayout === '2h' || chartLayout === '3h')
                  ? `indices:${selected.symbol}:mirror`
                  : null
              }
              mirrorContextId={`indices-split-${selected?.symbol || 'none'}`}
            >
            <DrawingWorkspaceProvider workspaceId={`indices-${selected.symbol}`}>
            <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minWidth: 400, position: 'relative' }}>
              <DrawingToolbarConnected />
              <DrawingFloatPaletteConnected />
              {renderPanel(selected.symbol, selected.name, timeframe,  tf => { setTimeframe(tf); setLastChange(null); }, handlePanelLastChange, selected.symbol+'-p1-'+timeframe,  chartLayout!=='single', 0)}
              {(chartLayout==='2h'||chartLayout==='3h') && renderPanel(selected.symbol, selected.name, timeframe2, tf => setTimeframe2(tf), ()=>{}, selected.symbol+'-p2-'+timeframe2, chartLayout==='3h', 1)}
              {chartLayout==='3h' && renderPanel(selected.symbol, selected.name, timeframe3, tf => setTimeframe3(tf), ()=>{}, selected.symbol+'-p3-'+timeframe3, false, 2)}
            </div>
            </DrawingWorkspaceProvider>
            </DrawingMirrorProvider>
          )}
        </div>
      </div>
    </div>
  );
}

function IndexRow({ index, i, selected, onSelect, rowRefs, onContextMenuRequest, draggable, onDragStartRow, onDragOverRow, onDropRow, onDragEndRow, dragDimmed, starTag, onStarTagChange }) {
  const isSelected = index.symbol === selected?.symbol;
  const chg        = index.change_pct;
  const chgColor   = chg > 0 ? 'var(--accent-green)' : chg < 0 ? 'var(--accent-red)' : 'var(--text-muted)';
  return (
    <div
      ref={el => rowRefs.current[i] = el}
      onClick={() => onSelect(index)}
      onContextMenu={(e) => {
        e.preventDefault();
        if (onContextMenuRequest) onContextMenuRequest({ x: e.clientX, y: e.clientY, symbol: index.symbol, type: 'index', sourcePage: 'indices' });
      }}
      onDragOver={e => onDragOverRow && onDragOverRow(e, i)}
      onDrop={e => onDropRow && onDropRow(e)}
      style={{ display:'flex', flexDirection:'column', padding:'6px 10px', cursor:'pointer', borderLeft: isSelected?'2px solid var(--accent-blue)':'2px solid transparent', backgroundColor: isSelected?'rgba(56,139,253,0.08)':'transparent', borderBottom:'1px solid var(--border-light)', opacity: dragDimmed ? 0.45 : 1 }}
      onMouseEnter={e => { if (!isSelected) e.currentTarget.style.backgroundColor='var(--bg-hover)'; }}
      onMouseLeave={e => { if (!isSelected) e.currentTarget.style.backgroundColor='transparent'; }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 4, minWidth: 0 }}>
        {draggable ? (
          <span
            title="Drag to reorder"
            draggable
            onDragStart={e => { e.stopPropagation(); onDragStartRow(e, i); }}
            onDragEnd={e => { e.stopPropagation(); if (onDragEndRow) onDragEndRow(); }}
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
              paddingTop: 2,
            }}
          >⋮⋮</span>
        ) : null}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', gap: 6 }}>
            <span style={{ fontSize:11, fontWeight:600, color: isSelected?'var(--accent-blue)':'var(--text-primary)', flex:1, minWidth:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{index.name}</span>
            <span style={{ display:'flex', alignItems:'center', gap: 4, flexShrink:0 }}>
              <span onClick={e => e.stopPropagation()} style={{ display:'inline-flex' }}>
                <IndexStarTag symbol={index.symbol} tag={starTag} onChange={onStarTagChange} />
              </span>
              <span onClick={e => e.stopPropagation()} style={{ display:'inline-flex' }}>
                <InstrumentNotesIcon symbol={index.symbol} instrumentType="index" />
              </span>
              <span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:chgColor, fontWeight:500 }}>{chg!=null?`${chg>0?'+':''}${chg.toFixed(2)}%`:'—'}</span>
            </span>
          </div>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-secondary)' }}>
            {index.last_price!=null?Number(index.last_price).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}):'—'}
          </span>
        </div>
      </div>
    </div>
  );
}