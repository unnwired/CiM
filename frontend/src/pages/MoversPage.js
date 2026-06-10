import React, { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo } from 'react';
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
  VOLUME_PREFS_UPDATED_EVENT,
  PANELS_PREFS_KEY,
  PANELS_PREFS_UPDATED_EVENT,
  getPersistedEmaSet,
  getPersistedVolumeVisible,
  getPersistedVisiblePanels,
  persistEmaSet,
  persistVolumeVisible,
  persistVisiblePanels,
} from '../config/chartDefaults';
import {
  DEFAULT_CHART_LAYOUT,
  DEFAULT_CHART_TIMEFRAME_1,
  DEFAULT_CHART_TIMEFRAME_2,
  DEFAULT_CHART_TIMEFRAME_3,
  normalizeSavedTimeframe3,
} from '../config/chartViewDefaults';
import { MOVERS_REFRESH_EVENT } from '../chartEvents';
import { formatMarketCap, formatCompactCount, parseMarketCapInput } from '../utils/formatMarketCap';

const LIMIT_OPTIONS = [20, 50, 100, 200, 400];
const PAGE_SIZE_OPTIONS = [10, 20, 25, 50];
const POLL_INTERVAL_KEY = 'cim.movers.pollIntervalSec';
const POLL_INTERVAL_OPTIONS = [
  { value: 0, label: 'None' },
  { value: 15, label: '15 seconds' },
  { value: 30, label: '30 seconds' },
  { value: 60, label: '1 minute' },
  { value: 120, label: '2 minutes' },
];

function getPersistedPollInterval() {
  if (typeof window === 'undefined') return 0;
  try {
    const v = Number(window.localStorage.getItem(POLL_INTERVAL_KEY));
    return POLL_INTERVAL_OPTIONS.some(o => o.value === v) ? v : 0;
  } catch {
    return 0;
  }
}

function persistPollInterval(sec) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(POLL_INTERVAL_KEY, String(sec));
  } catch {
    // ignore
  }
}

const API = '';
const CHART_TOOLBAR_OVERLAY_Z = 200000;

const LAYOUTS = [
  { key: 'single', label: 'Single', desc: 'One chart panel' },
  { key: '2h', label: '2 - Multi Timeframe', desc: 'Same stock, two timeframes' },
  { key: '3h', label: '3 - Multi Timeframe', desc: 'Same stock, three timeframes' },
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

function formatVolume(v) {
  if (v == null || Number.isNaN(Number(v))) return '-';
  return formatCompactCount(v);
}

function filterRowsByMinMcap(rows, minMcapInr) {
  if (minMcapInr == null || !Number.isFinite(minMcapInr)) return rows;
  return rows.filter(r => {
    const m = Number(r.market_cap);
    return Number.isFinite(m) && m >= minMcapInr;
  });
}

const MOVERS_CTRL_H = 28;

const moversFormCardStyle = {
  background: 'var(--bg-secondary)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  padding: 10,
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
};

const moversSectionLabelStyle = {
  fontSize: 10,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 6,
};

const moversInputStyle = {
  width: '100%',
  height: MOVERS_CTRL_H,
  padding: '0 8px',
  borderRadius: 4,
  border: '1px solid var(--border)',
  background: 'var(--bg-tertiary)',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  boxSizing: 'border-box',
};

const moversSelectStyle = {
  ...moversInputStyle,
  fontFamily: 'inherit',
};

const moversCompactInputStyle = {
  ...moversInputStyle,
  width: 44,
  flexShrink: 0,
};

const moversCompactSelectStyle = {
  ...moversSelectStyle,
  width: 'auto',
  minWidth: 44,
  flexShrink: 0,
  paddingRight: 4,
};

function InlineField({ label, children }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-muted)', fontSize: 10, whiteSpace: 'nowrap' }}>
      {label}
      {children}
    </label>
  );
}

function SegmentedBar({ options, value, onChange }) {
  return (
    <div
      role="group"
      style={{
        display: 'flex',
        borderRadius: 5,
        border: '1px solid var(--border)',
        overflow: 'hidden',
        background: 'var(--bg-tertiary)',
      }}
    >
      {options.map((opt, i) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            style={{
              flex: 1,
              minWidth: 0,
              height: MOVERS_CTRL_H,
              padding: '0 4px',
              fontSize: 10,
              fontWeight: active ? 600 : 400,
              color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
              background: active ? 'var(--bg-primary)' : 'transparent',
              border: 'none',
              borderRight: i < options.length - 1 ? '1px solid var(--border)' : 'none',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function pagerBtnStyle(enabled) {
  return {
    padding: '5px 14px',
    borderRadius: 4,
    border: 'none',
    fontSize: 11,
    fontWeight: 600,
    cursor: enabled ? 'pointer' : 'not-allowed',
    backgroundColor: enabled ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
    color: enabled ? '#ffffff' : 'var(--text-muted)',
    opacity: enabled ? 1 : 0.5,
  };
}

export default function MoversPage({ onOpenChart, isActive = false, onContextMenuRequest }) {
  const [mainTab, setMainTab] = useState('day');
  const [daySide, setDaySide] = useState('gainers');
  const [volumeMode, setVolumeMode] = useState('absolute');
  const [limit, setLimit] = useState(50);
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);
  const [minMcap, setMinMcap] = useState('');
  const [appliedMinMcapInr, setAppliedMinMcapInr] = useState(null);
  const [mcapError, setMcapError] = useState('');

  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState('');
  const [liveFetchNote, setLiveFetchNote] = useState('');
  const [liveSessionBanner, setLiveSessionBanner] = useState(null);
  const [pollIntervalSec, setPollIntervalSec] = useState(() => getPersistedPollInterval());
  const [appliedPollIntervalSec, setAppliedPollIntervalSec] = useState(0);
  const [pollCountdown, setPollCountdown] = useState(null);
  const [chartQuoteTick, setChartQuoteTick] = useState(0);
  const [selectedSymbol, setSelectedSymbol] = useState(null);

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

  const [indOpen, setIndOpen] = useState(false);
  const [indicatorMenuRect, setIndicatorMenuRect] = useState(null);
  const indRef = useRef(null);

  const [paneWidth, setPaneWidth] = useState(320);
  const draggingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  const wrapperRef = useRef(null);
  const heightsRef = useRef({});
  const rowsRef = useRef([]);
  const loadingRef = useRef(false);

  const [viewOpen, setViewOpen] = useState(false);
  const [viewMenuRect, setViewMenuRect] = useState(null);
  const viewRef = useRef(null);

  const parsedMinMcap = parseMarketCapInput(minMcap);
  const mcapValid = parsedMinMcap === null || Number.isFinite(parsedMinMcap);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageRows = rows.slice((safePage - 1) * pageSize, safePage * pageSize);
  const volumeColLabel = volumeMode === 'surge' ? 'Vol chg%' : volumeMode === 'rvol' ? 'RVOL 20d' : 'Volume';
  const useLive = appliedPollIntervalSec > 0;
  const selectedRow = useMemo(
    () => rows.find(r => String(r.symbol || '').toUpperCase() === String(selectedSymbol || '').toUpperCase()),
    [rows, selectedSymbol],
  );
  const liveDayChangePct = useLive && selectedRow?.change_pct != null && Number.isFinite(Number(selectedRow.change_pct))
    ? Number(selectedRow.change_pct)
    : null;

  rowsRef.current = rows;

  const configureLivePolling = useCallback(async (sec) => {
    try {
      await axios.post(`${API}/api/movers/live/configure`, { interval_seconds: sec });
    } catch {
      // server may be offline; EOD fallback still works
    }
  }, []);

  const fetchMovers = useCallback(async ({ background = false, minMcapOverride, light = false } = {}) => {
    if (background && loadingRef.current) return;
    if (!background) {
      loadingRef.current = true;
      setLoading(true);
    }
    if (!background) {
      setFetchError('');
      setLiveFetchNote('');
    }
    const params = { limit };
    const mcapVal = minMcapOverride !== undefined ? minMcapOverride : appliedMinMcapInr;
    if (mcapVal != null && Number.isFinite(mcapVal)) {
      params.min_market_cap = mcapVal;
    }
    if (light) params.light = true;
    if (mainTab === 'day') params.side = daySide;
    else params.volume_mode = volumeMode;
    const eodListUrl = mainTab === 'day' ? `${API}/api/movers/day-change` : `${API}/api/movers/volume`;
    const liveListUrl = mainTab === 'day' ? `${API}/api/movers/live/day-change` : `${API}/api/movers/live/volume`;
    const listUrl = useLive ? liveListUrl : eodListUrl;
    const metaUrl = useLive ? `${API}/api/movers/live/meta` : `${API}/api/movers/meta`;
    try {
      let listRes;
      let usedEodFallback = false;
      try {
        listRes = await axios.get(listUrl, { params, timeout: light ? 45000 : 120000 });
      } catch (liveErr) {
        if (!useLive) throw liveErr;
        usedEodFallback = true;
        listRes = await axios.get(eodListUrl, { params });
      }
      let metaData = null;
      try {
        const metaRes = await axios.get(metaUrl);
        metaData = metaRes.data || null;
      } catch {
        if (!useLive) {
          try {
            const metaRes = await axios.get(`${API}/api/movers/meta`);
            metaData = metaRes.data || null;
          } catch {
            // meta optional
          }
        }
      }
      let data = filterRowsByMinMcap(listRes.data?.data || [], mcapVal);
      if (background && rowsRef.current.length > 0) {
        setRows(data);
        if (useLive) {
          setChartQuoteTick(t => t + 1);
          setPollCountdown(appliedPollIntervalSec);
        }
      } else {
        setRows(data);
        setMeta(metaData);
        if (!useLive) {
          setLiveSessionBanner(null);
          setLiveFetchNote('');
        } else if (usedEodFallback) {
          setLiveSessionBanner(null);
          setLiveFetchNote('Live API unavailable — showing EOD data. Restart the backend.');
        } else {
          setLiveFetchNote('');
          setLiveSessionBanner({
            stockCount: data.length,
            nseRefresh: metaData?.live_status?.last_nse_refresh_at || null,
            marketClosed: metaData?.live_status?.market_open === false,
          });
          setPollCountdown(appliedPollIntervalSec);
        }
        if (!background) setPage(1);
      }
      if (data.length > 0) {
        const syms = data.map(r => String(r.symbol || '').toUpperCase());
        setSelectedSymbol(prev => (prev && syms.includes(prev) ? prev : syms[0]));
      } else if (!background) setSelectedSymbol(null);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Failed to load movers';
      if (background && useLive) {
        setLiveFetchNote('Live refresh paused (request failed). Next poll will retry.');
      } else {
        setFetchError(msg);
        setRows([]);
      }
    } finally {
      if (!background) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  }, [mainTab, daySide, volumeMode, limit, appliedMinMcapInr, useLive, appliedPollIntervalSec]);

  function applyFiltersAndFetch() {
    if (minMcap.trim() && !mcapValid) {
      setMcapError('Invalid min market cap (e.g. 50B, 50 billion, 500M)');
      return;
    }
    setMcapError('');
    const mcap = parsedMinMcap != null && Number.isFinite(parsedMinMcap) ? parsedMinMcap : null;
    setAppliedMinMcapInr(mcap);
    setAppliedPollIntervalSec(pollIntervalSec);
    persistPollInterval(pollIntervalSec);
    configureLivePolling(pollIntervalSec);
    if (pollIntervalSec <= 0) {
      setPollCountdown(null);
      setLiveSessionBanner(null);
    }
  }

  useEffect(() => {
    fetchMovers();
  }, [fetchMovers]);

  useEffect(() => {
    if (appliedPollIntervalSec <= 0) return undefined;
    setPollCountdown(appliedPollIntervalSec);
    const tickId = window.setInterval(() => {
      setPollCountdown(prev => {
        if (prev == null || prev <= 1) return appliedPollIntervalSec;
        return prev - 1;
      });
    }, 1000);
    return () => window.clearInterval(tickId);
  }, [appliedPollIntervalSec]);

  useEffect(() => {
    if (!isActive || appliedPollIntervalSec <= 0) return undefined;
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchMovers({ background: true, light: true });
      }
    }, appliedPollIntervalSec * 1000);
    return () => window.clearInterval(id);
  }, [isActive, appliedPollIntervalSec, fetchMovers]);

  useEffect(() => {
    axios.get(`${API}/api/layout`).then(r => {
      if (r.data.moversPaneWidth) setPaneWidth(Number(r.data.moversPaneWidth) || 360);
      if (r.data.moversChartLayout) setChartLayout(String(r.data.moversChartLayout));
      if (r.data.moversTimeframe) setTimeframe(r.data.moversTimeframe);
      if (r.data.moversTimeframe2) setTimeframe2(r.data.moversTimeframe2);
      if (r.data.moversTimeframe3) setTimeframe3(normalizeSavedTimeframe3(r.data.moversTimeframe3));
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

  useEffect(() => {
    function onDocDown(e) {
      if (indRef.current && !indRef.current.contains(e.target)) setIndOpen(false);
      if (viewRef.current && !viewRef.current.contains(e.target)) setViewOpen(false);
    }
    document.addEventListener('mousedown', onDocDown);
    return () => document.removeEventListener('mousedown', onDocDown);
  }, []);

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

  useEffect(() => {
    const h = () => fetchMovers();
    window.addEventListener(MOVERS_REFRESH_EVENT, h);
    return () => window.removeEventListener(MOVERS_REFRESH_EVENT, h);
  }, [fetchMovers]);
  useEffect(() => { if (page !== safePage) setPage(safePage); }, [page, safePage]);

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
      moversPaneWidth: paneWidth,
      moversChartLayout: chartLayout,
      moversTimeframe: timeframe,
      moversTimeframe2: timeframe2,
      moversTimeframe3: timeframe3,
    };
    axios.post(`${API}/api/layout`, payload)
      .then(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Layout saved.' })))
      .catch(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Failed to save layout.' })));
  }

  function renderPanel(sym, tf, setTf, onLastChange, cacheKey, hasBorderRight, dayChgOverride = null, chartLive = false) {
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
          dayChangePctOverride={dayChgOverride}
          liveToday={chartLive}
          liveRefreshKey={chartLive ? chartQuoteTick : null}
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
          drawingScopeId={`movers:${cacheKey}`}
          drawingAutoFocus={false}
        />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', backgroundColor: 'var(--bg-primary)', overflow: 'hidden' }}>
      <div className="chart-app-toolbar" style={{ height: 44, flexShrink: 0, backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 12px', gap: 8, overflowX: 'auto' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13, color: 'var(--text-primary)', flexShrink: 0 }}>
          {selectedSymbol || 'Market Movers'}
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
          <button type="button" onClick={() => onOpenChart && onOpenChart(selectedSymbol)}
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
          <div style={{ borderBottom: '1px solid var(--border)', padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={moversFormCardStyle}>
              <section>
                <div style={moversSectionLabelStyle}>Ranking</div>
                <SegmentedBar
                  options={[
                    { value: 'day', label: 'Day change' },
                    { value: 'volume', label: 'Volume' },
                  ]}
                  value={mainTab}
                  onChange={setMainTab}
                />
                <div style={{ height: 8 }} />
                {mainTab === 'day' ? (
                  <SegmentedBar
                    options={[
                      { value: 'gainers', label: 'Gainers' },
                      { value: 'losers', label: 'Losers' },
                    ]}
                    value={daySide}
                    onChange={setDaySide}
                  />
                ) : (
                  <SegmentedBar
                    options={[
                      { value: 'absolute', label: 'Absolute' },
                      { value: 'surge', label: 'Surge %' },
                      { value: 'rvol', label: 'RVOL 20d' },
                    ]}
                    value={volumeMode}
                    onChange={setVolumeMode}
                  />
                )}
              </section>

              <div style={{ height: 1, backgroundColor: 'var(--border)' }} />

              <section>
                <div style={moversSectionLabelStyle}>Filters</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                  <InlineField label="Min MCap">
                    <input
                      value={minMcap}
                      onChange={e => { setMinMcap(e.target.value); setMcapError(''); }}
                      onKeyDown={e => { if (e.key === 'Enter') applyFiltersAndFetch(); }}
                      placeholder="50B"
                      style={moversCompactInputStyle}
                    />
                  </InlineField>
                  <InlineField label="Top">
                    <select value={limit} onChange={e => setLimit(Number(e.target.value))} style={moversCompactSelectStyle}>
                      {LIMIT_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </InlineField>
                  <InlineField label="Per page">
                    <select
                      value={pageSize}
                      onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
                      style={moversCompactSelectStyle}
                    >
                      {PAGE_SIZE_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </InlineField>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginTop: 8 }}>
                  <InlineField label="Live refresh">
                    <select
                      value={pollIntervalSec}
                      onChange={e => setPollIntervalSec(Number(e.target.value))}
                      style={{ ...moversCompactSelectStyle, minWidth: 72 }}
                    >
                      {POLL_INTERVAL_OPTIONS.map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </InlineField>
                  <button
                    type="button"
                    onClick={applyFiltersAndFetch}
                    disabled={loading || (minMcap.trim() && !mcapValid)}
                    style={{
                      height: MOVERS_CTRL_H,
                      padding: '0 10px',
                      borderRadius: 4,
                      border: '1px solid var(--accent-blue)',
                      background: 'rgba(56,139,253,0.15)',
                      color: 'var(--accent-blue)',
                      fontSize: 11,
                      fontWeight: 600,
                      whiteSpace: 'nowrap',
                      cursor: loading || (minMcap.trim() && !mcapValid) ? 'not-allowed' : 'pointer',
                      opacity: loading || (minMcap.trim() && !mcapValid) ? 0.5 : 1,
                    }}
                  >
                    Apply filters
                  </button>
                </div>
              </section>
            </div>

            {parsedMinMcap != null && Number.isFinite(parsedMinMcap) && mcapValid && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', paddingLeft: 2 }}>
                Min cap: ≥ {formatMarketCap(parsedMinMcap)}
                {appliedMinMcapInr != null && appliedMinMcapInr === parsedMinMcap ? ' · applied' : ' · press Apply filters'}
              </div>
            )}
            {pollIntervalSec !== appliedPollIntervalSec && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)', paddingLeft: 2 }}>
                Live refresh changed — press Apply filters to start
              </div>
            )}
            {(mcapError || fetchError || liveFetchNote) && (
              <div style={{ fontSize: 10, color: (mcapError || fetchError) ? 'var(--accent-red)' : 'var(--text-muted)', paddingLeft: 2 }}>{mcapError || fetchError || liveFetchNote}</div>
            )}
          </div>

          <div
            style={{
              flexShrink: 0,
              padding: '6px 10px',
              fontSize: 10,
              color: 'var(--text-muted)',
              borderBottom: '1px solid var(--border)',
              backgroundColor: 'var(--bg-secondary)',
              lineHeight: 1.4,
            }}
          >
            {loading ? 'Loading…' : `${rows.length} stocks`}
            {useLive && liveSessionBanner ? (
              <>
                {' · '}
                <span style={{ color: 'var(--accent-green)', fontWeight: 700 }}>Live</span>
                {liveSessionBanner.nseRefresh ? ` · NSE ${liveSessionBanner.nseRefresh}` : ''}
                {liveSessionBanner.marketClosed ? ' · market closed' : ''}
              </>
            ) : !useLive && meta?.as_of_date ? (
              ` · EOD ${meta.as_of_date}`
            ) : null}
            {useLive && pollCountdown != null && appliedPollIntervalSec > 0 ? (
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-green)', fontWeight: 600 }}>
                {` · ${pollCountdown}s`}
              </span>
            ) : null}
          </div>

          <div style={{ flex: 1, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-secondary)', zIndex: 1 }}>
                <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                  <th style={{ padding: '6px 8px' }}>#</th>
                  <th style={{ padding: '6px 4px' }}>Symbol</th>
                  <th style={{ padding: '6px 4px', textAlign: 'right' }}>Price</th>
                  <th style={{ padding: '6px 4px', textAlign: 'right' }}>Chg%</th>
                  {mainTab === 'volume' && <th style={{ padding: '6px 4px', textAlign: 'right' }}>{volumeColLabel}</th>}
                  <th style={{ padding: '6px 8px', textAlign: 'right' }}>Mcap</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map(row => {
                  const sym = String(row.symbol || '').toUpperCase();
                  const active = sym === selectedSymbol;
                  const volCell = volumeMode === 'surge'
                    ? formatPct(row.volume_change_pct)
                    : volumeMode === 'rvol'
                      ? (row.rvol_20d != null ? Number(row.rvol_20d).toFixed(2) : '-')
                      : formatVolume(row.volume);
                  const chg = Number(row.change_pct);
                  const chgColor = Number.isFinite(chg) ? (chg >= 0 ? 'var(--accent-green)' : 'var(--accent-red)') : 'var(--text-muted)';
                  return (
                    <tr
                      key={sym}
                      onClick={() => { setSelectedSymbol(sym); setLastCandleChange(null); setCrosshairTime(null); }}
                      onContextMenu={(e) => {
                        e.preventDefault();
                        if (onContextMenuRequest) {
                          onContextMenuRequest({
                            x: e.clientX,
                            y: e.clientY,
                            symbol: sym,
                            type: 'stock',
                            sourcePage: 'movers',
                          });
                        }
                      }}
                      style={{ cursor: 'pointer', background: active ? 'rgba(56,139,253,0.12)' : 'transparent', borderBottom: '1px solid var(--border-light)' }}
                    >
                      <td style={{ padding: '5px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{row.rank}</td>
                      <td style={{ padding: '5px 4px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: active ? 'var(--accent-blue)' : 'var(--text-primary)' }}>{sym}</td>
                      <td style={{ padding: '5px 4px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{formatPrice(row.price)}</td>
                      <td style={{ padding: '5px 4px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: chgColor }}>{formatPct(row.change_pct)}</td>
                      {mainTab === 'volume' && <td style={{ padding: '5px 4px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{volCell}</td>}
                      <td style={{ padding: '5px 8px', textAlign: 'right' }}>{formatMarketCap(row.market_cap)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!loading && pageRows.length === 0 && (
              <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>{useLive
                  ? 'No live movers match these filters. Try lowering min market cap, set Live refresh to None for EOD, or refresh OHLC.'
                  : 'No results. Adjust min market cap or refresh OHLC.'}</div>
            )}
          </div>
          <div style={{ padding: '8px 10px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
            <button type="button" disabled={safePage <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} style={pagerBtnStyle(safePage > 1)}>Prev</button>
            <span style={{ color: 'var(--text-secondary)' }}>Page {safePage} / {totalPages}</span>
            <button type="button" disabled={safePage >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))} style={pagerBtnStyle(safePage < totalPages)}>Next</button>
          </div>
        </div>

        <div onMouseDown={onDividerMouseDown}
          style={{ width: 4, backgroundColor: 'var(--border)', cursor: 'col-resize', flexShrink: 0 }}
        />

        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', minWidth: 400 }}>
          {!selectedSymbol ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              {loading ? 'Loading movers...' : 'Select a symbol from the left panel'}
            </div>
          ) : (
            <DrawingMirrorProvider
              mirrorStorageKey={selectedSymbol && (chartLayout === '2h' || chartLayout === '3h') ? `movers:${selectedSymbol}:mirror` : null}
              mirrorContextId={`movers-split-${selectedSymbol || 'none'}`}
            >
              <DrawingWorkspaceProvider workspaceId={`movers-${selectedSymbol}`}>
                <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minWidth: 400, position: 'relative' }}>
                  <DrawingToolbarConnected />
                  <DrawingFloatPaletteConnected />
                  {renderPanel(selectedSymbol, timeframe, tf => setTimeframe(tf), pct => setLastCandleChange(pct), `${selectedSymbol}-p1-${timeframe}`, chartLayout !== 'single', liveDayChangePct, useLive)}
                  {(chartLayout === '2h' || chartLayout === '3h') && renderPanel(selectedSymbol, timeframe2, tf => setTimeframe2(tf), () => {}, `${selectedSymbol}-p2-${timeframe2}`, chartLayout === '3h', liveDayChangePct, useLive)}
                  {chartLayout === '3h' && renderPanel(selectedSymbol, timeframe3, tf => setTimeframe3(tf), () => {}, `${selectedSymbol}-p3-${timeframe3}`, false, liveDayChangePct, useLive)}
                </div>
              </DrawingWorkspaceProvider>
            </DrawingMirrorProvider>
          )}
        </div>
      </div>
    </div>
  );
}
