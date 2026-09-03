import React, { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo } from 'react';
import BasketToolbarButton from '../components/Basket';
import { startBasketSymbolDrag } from '../utils/basketDnD';
import axios from 'axios';
import ChartContainer from '../components/chart/ChartContainer';
import ChartHeaderBar from '../components/chart/ChartHeaderBar';
import EMAControls from '../components/chart/EMAControls';
import ExternalFinancialsLinks from '../components/ExternalFinancialsLinks';
import { DrawingMirrorProvider } from '../components/chart/drawing/DrawingMirrorContext';
import { DrawingWorkspaceProvider } from '../components/chart/drawing/DrawingWorkspaceContext';
import { DrawingToolbarConnected, DrawingFloatPaletteConnected } from '../components/chart/drawing/DrawingToolbar';
import StockListSplitBody from '../components/StockListSplitBody';
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
import { CHART_DATA_UPDATED_EVENT, MOVERS_REFRESH_EVENT, MOVERS_LIVE_PREFETCH_EVENT } from '../chartEvents';
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
import { useRegisterIntradaySymbols } from '../intraday/useRegisterIntradaySymbols';
import { symbolsForChartFocus, symbolsForMovers } from '../intraday/intradayRefreshScopes';
import { isIntradayLiveTimeframe } from '../intraday/patchOverlay';
import { usePageLive } from '../intraday/pageLiveContext';
import { useIntradayPatchOptional } from '../intraday/useIntradayPatch';
import { useSyncedPanelHeights, columnCountForChartLayout, multiColumnHeightProps } from '../hooks/useSyncedPanelHeights';
import { formatMarketCap, formatCompactCount, parseMarketCapInput } from '../utils/formatMarketCap';

const LIMIT_OPTIONS = [20, 50, 100, 200, 400];
const PAGE_SIZE_OPTIONS = [10, 20, 25, 50];
/** How often the Movers table re-ranks from the server cache while LIVE is on. */
const LIVE_LIST_REFRESH_MS = 3000;
/** How often visible movers rows pull LTPC/% from the movers cache while LIVE is on. */
const LIVE_QUOTE_POLL_MS = 1500;

function readFloatingLiveActive() {
  if (typeof window === 'undefined') return false;
  try {
    const st = window.CiMLive && typeof window.CiMLive.getState === 'function'
      ? window.CiMLive.getState()
      : window.CiMLiveState;
    if (!st) return false;
    // Movers list is live only when Market movers mode (or explicit universe) is on.
    if (st.moversUniverse) return true;
    const ctx = st.contexts || {};
    if (ctx.movers) return true;
  } catch {
    // ignore
  }
  return false;
}

const EARNINGS_TODAY_KEY = 'cim.movers.earningsToday';

function readEarningsTodayPref() {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(EARNINGS_TODAY_KEY) === '1';
  } catch {
    return false;
  }
}

function writeEarningsTodayPref(on) {
  try {
    window.localStorage.setItem(EARNINGS_TODAY_KEY, on ? '1' : '0');
  } catch {
    // ignore
  }
  try {
    window.dispatchEvent(new CustomEvent('cim:movers-earnings-today', {
      detail: { enabled: !!on },
    }));
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

export default function MoversPage({ onOpenChart, isActive = false, showcaseWebClient = false, onContextMenuRequest }) {
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
  const [floatingLiveOn, setFloatingLiveOn] = useState(() => readFloatingLiveActive());
  const [earningsToday, setEarningsToday] = useState(() => readEarningsTodayPref());
  const [selectedSymbol, setSelectedSymbol] = useState(null);

  const [timeframe, setTimeframe] = useState(DEFAULT_CHART_TIMEFRAME_1);
  const [timeframe2, setTimeframe2] = useState(DEFAULT_CHART_TIMEFRAME_2);
  const [timeframe3, setTimeframe3] = useState(DEFAULT_CHART_TIMEFRAME_3);
  const [chartLayout, setChartLayout] = useState(DEFAULT_CHART_LAYOUT);
  const [lastCandleChange, setLastCandleChange] = useState(null);
  const [lastCandlePrice, setLastCandlePrice] = useState(null);
  const [crosshairTime, setCrosshairTime] = useState(null);

  const [emas, setEmas] = useState(() => getPersistedEmaSet());
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(true));
  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());
  const [panelOrder, setPanelOrder] = useState(['stochrsi', 'macd']);

  const [indOpen, setIndOpen] = useState(false);
  const [indicatorMenuRect, setIndicatorMenuRect] = useState(null);
  const indRef = useRef(null);

  const [paneWidth, setPaneWidth] = useState(320);
  const chartPrefs = useChartPrefsContext();
  const { liveActive, liveTick } = usePageLive('movers');
  const intraday = useIntradayPatchOptional();
  const rowsRef = useRef([]);
  const loadingRef = useRef(false);
  const inFlightRef = useRef(false);
  const abortRef = useRef(null);
  const useLive = floatingLiveOn;

  const { overlayMoversRows, getSnapshot } = usePatchOverlay('movers');
  const liveRows = useMemo(() => {
    // LIVE API already ranks with movers_live quotes + gainers/losers filter.
    // Client overlay + re-filter fought the server cache (dual quote sources) → row flicker.
    let next = useLive ? [...(rows || [])] : (overlayMoversRows(rows) || []);
    if (mainTab === 'day' && !useLive) {
      const wantLosers = daySide === 'losers';
      next = next.filter((r) => {
        const chg = Number(r?.change_pct);
        if (!Number.isFinite(chg) || chg === 0) return false;
        return wantLosers ? chg < 0 : chg > 0;
      });
      next = [...next].sort((a, b) => {
        const ca = Number(a?.change_pct) || 0;
        const cb = Number(b?.change_pct) || 0;
        return wantLosers ? ca - cb : cb - ca;
      });
    }
    return next;
  }, [rows, overlayMoversRows, mainTab, daySide, useLive]);
  // Chart focus + full movers list (so Refresh prices / live quote poll cover table rows).
  useRegisterFocusedSymbol('movers', useMemo(
    () => symbolsForChartFocus(selectedSymbol),
    [selectedSymbol],
  ));
  useRegisterIntradaySymbols('movers', useMemo(
    () => symbolsForMovers(rows),
    [rows],
  ));
  const draggingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  const wrapperRef = useRef(null);
  const { getPanelHeights, heightsRef, handleHeightsChange, applyLayoutHeights, heightsRevision } = useSyncedPanelHeights({
    columnCount: columnCountForChartLayout(chartLayout),
  });

  const [viewOpen, setViewOpen] = useState(false);
  const [viewMenuRect, setViewMenuRect] = useState(null);
  const viewRef = useRef(null);

  const parsedMinMcap = parseMarketCapInput(minMcap);
  const mcapValid = parsedMinMcap === null || Number.isFinite(parsedMinMcap);
  const totalPages = Math.max(1, Math.ceil(liveRows.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageRows = liveRows.slice((safePage - 1) * pageSize, safePage * pageSize);
  const volumeColLabel = volumeMode === 'surge' ? 'Vol chg%' : volumeMode === 'rvol' ? 'RVOL 20d' : 'Volume';
  // Showcase funnel used to force useLive=false, so Market Movers fell back to EOD
  const selectedRow = useMemo(
    () => liveRows.find(r => String(r.symbol || '').toUpperCase() === String(selectedSymbol || '').toUpperCase()),
    [liveRows, selectedSymbol],
  );
  const focusSnap = selectedSymbol ? getSnapshot(selectedSymbol) : null;
  const symbolLive = !!(selectedSymbol && intraday?.isSymbolLive?.(selectedSymbol));
  // Floating LIVE or page live enables chart overlay; focusSnap alone must not gate loading.
  const chartLiveEnabled = !!(liveActive || useLive || symbolLive);
  const liveDayChangePct = (() => {
    // Prefer the movers row the user sees (post re-rank) over focusSnap so header matches list.
    if (selectedRow?.change_pct != null && Number.isFinite(Number(selectedRow.change_pct))) {
      return Number(selectedRow.change_pct);
    }
    const fromSnap = focusSnap?.change_pct;
    if (fromSnap != null && Number.isFinite(Number(fromSnap))) return Number(fromSnap);
    return null;
  })();
  const headerPrice = (() => {
    const fromSnap = focusSnap?.price;
    if (fromSnap != null && Number.isFinite(Number(fromSnap))) return Number(fromSnap);
    if (lastCandlePrice != null && Number.isFinite(Number(lastCandlePrice))) return Number(lastCandlePrice);
    const rowPx = selectedRow?.price;
    return rowPx != null && Number.isFinite(Number(rowPx)) ? Number(rowPx) : null;
  })();
  const headerChange = (() => {
    if (liveDayChangePct != null) return liveDayChangePct;
    return lastCandleChange;
  })();

  rowsRef.current = rows;

  useEffect(() => {
    const sym = String(selectedSymbol || '').trim().toUpperCase();
    if (!sym || typeof window === 'undefined') return undefined;
    window.dispatchEvent(new CustomEvent('cim:chart-focus-symbol', {
      detail: { symbol: sym, source: 'movers' },
    }));
    if (useLive && intraday?.refreshPatch) {
      intraday.refreshPatch([sym]).catch(() => {});
    }
    return undefined;
  }, [selectedSymbol, useLive, intraday]);

  useEffect(() => {
    const sync = (e) => {
      const detail = e?.detail || {};
      if (detail.enabled === false) {
        setFloatingLiveOn(false);
        return;
      }
      const moversMode = detail.movers === true || detail.context === 'movers' || readFloatingLiveActive();
      setFloatingLiveOn(!!moversMode && detail.enabled !== false);
    };
    window.addEventListener('cim:live-active', sync);
    window.addEventListener('cim:live-feed-toggle', sync);
    setFloatingLiveOn(readFloatingLiveActive());
    return () => {
      window.removeEventListener('cim:live-active', sync);
      window.removeEventListener('cim:live-feed-toggle', sync);
    };
  }, []);

  useEffect(() => {
    const sync = (e) => {
      const next = !!(e?.detail && e.detail.enabled);
      setEarningsToday(next);
    };
    window.addEventListener('cim:movers-earnings-today', sync);
    setEarningsToday(readEarningsTodayPref());
    return () => window.removeEventListener('cim:movers-earnings-today', sync);
  }, []);

  const fetchMovers = useCallback(async ({ background = false, minMcapOverride, light = false, preferLive = false } = {}) => {
    // Background polls must not stack while a prior list request is still running
    // (was measured stacking to ~10GB RSS / multi-minute hangs).
    // Light LIVE polls may abort a prior light request so rankings keep reshuffling.
    if (background && loadingRef.current) {
      return null;
    }
    if (background && inFlightRef.current) {
      if (light) {
        try { abortRef.current?.abort(); } catch (_) { /* ignore */ }
      } else {
        return null;
      }
    }
    if (inFlightRef.current && !background) {
      try { abortRef.current?.abort(); } catch (_) { /* ignore */ }
    }
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
    if (earningsToday) params.earnings_today = true;
    if (mainTab === 'day') params.side = daySide;
    else params.volume_mode = volumeMode;
    const eodListUrl = mainTab === 'day' ? `${API}/api/movers/day-change` : `${API}/api/movers/volume`;
    const liveListUrl = mainTab === 'day' ? `${API}/api/movers/live/day-change` : `${API}/api/movers/live/volume`;
    const wantLive = useLive || preferLive;
    const listUrl = wantLive ? liveListUrl : eodListUrl;
    const metaUrl = wantLive ? `${API}/api/movers/live/meta` : `${API}/api/movers/meta`;
    const ac = typeof AbortController !== 'undefined' ? new AbortController() : null;
    abortRef.current = ac;
    inFlightRef.current = true;
    try {
      let listRes;
      let usedEodFallback = false;
      try {
        listRes = await axios.get(listUrl, { params, timeout: light ? 12000 : 120000, signal: ac?.signal });
      } catch (liveErr) {
        if (axios.isCancel?.(liveErr) || liveErr?.code === 'ERR_CANCELED' || liveErr?.name === 'CanceledError') {
          return null;
        }
        if (!wantLive) throw liveErr;
        // Do not chain a second 120s wait after a live timeout — use a short EOD fallback.
        const wasTimeout = String(liveErr?.code || '') === 'ECONNABORTED'
          || /timeout/i.test(String(liveErr?.message || ''));
        usedEodFallback = true;
        listRes = await axios.get(eodListUrl, {
          params,
          timeout: wasTimeout ? 20000 : 45000,
          signal: ac?.signal,
        });
      }
      let metaData = null;
      try {
        const metaRes = await axios.get(metaUrl, { signal: ac?.signal });
        metaData = metaRes.data || null;
      } catch {
        if (!wantLive) {
          try {
            const metaRes = await axios.get(`${API}/api/movers/meta`, { signal: ac?.signal });
            metaData = metaRes.data || null;
          } catch {
            // meta optional
          }
        }
      }
      let data = filterRowsByMinMcap(listRes.data?.data || [], mcapVal);
      if (background && rowsRef.current.length > 0) {
        setRows(data);
      } else {
        setRows(data);
        setMeta(metaData);
        if (!wantLive) {
          setLiveSessionBanner(null);
          setLiveFetchNote('');
        } else if (usedEodFallback) {
          setLiveSessionBanner(null);
          setLiveFetchNote('Live API unavailable — showing EOD data. Restart the backend.');
        } else {
          setLiveFetchNote('');
          const liveSt = metaData?.live_status || {};
          setLiveSessionBanner({
            stockCount: data.length,
            universeSize: liveSt.universe_size || liveSt.quotes_fresh_count || null,
            marketClosed: liveSt.market_open === false,
            streamConnected: liveSt.universe_connected === true,
          });
        }
        if (!background) setPage(1);
      }
      if (data.length > 0) {
        const syms = data.map(r => String(r.symbol || '').toUpperCase());
        if (!background) {
          setSelectedSymbol(prev => (prev && syms.includes(prev) ? prev : syms[0]));
        }
      } else if (!background) setSelectedSymbol(null);
      return data;
    } catch (e) {
      if (axios.isCancel?.(e) || e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') {
        return null;
      }
      const msg = e.response?.data?.detail || e.message || 'Failed to load movers';
      if (background && wantLive) {
        setLiveFetchNote('Live list refresh paused (request failed). Retrying…');
      } else {
        setFetchError(msg);
        setRows([]);
      }
      return null;
    } finally {
      if (abortRef.current === ac) {
        inFlightRef.current = false;
        abortRef.current = null;
      }
      if (!background) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  }, [mainTab, daySide, volumeMode, limit, appliedMinMcapInr, useLive, earningsToday]);

  function applyFiltersAndFetch() {
    if (minMcap.trim() && !mcapValid) {
      setMcapError('Invalid min market cap (e.g. 50B, 50 billion, 500M)');
      return;
    }
    setMcapError('');
    const mcap = parsedMinMcap != null && Number.isFinite(parsedMinMcap) ? parsedMinMcap : null;
    setAppliedMinMcapInr(mcap);
  }

  useEffect(() => {
    fetchMovers();
  }, [fetchMovers]);

  useEffect(() => {
    if (!isActive || !useLive) return undefined;
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchMovers({ background: true, light: true });
      }
    }, LIVE_LIST_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [isActive, useLive, fetchMovers, earningsToday]);

  // EOD-only: patch table from intraday blob. LIVE movers API is already the table quote source.
  useEffect(() => {
    if (!isActive || useLive || !intraday?.ingestExternalQuotes) return undefined;
    let cancelled = false;
    const pollQuotes = async () => {
      if (document.visibilityState !== 'visible') return;
      const syms = symbolsForMovers(rowsRef.current);
      if (!syms.length) return;
      try {
        const res = await axios.get(`${API}/api/live/quotes`, {
          params: { symbols: syms.join(',') },
          timeout: 8000,
        });
        if (cancelled) return;
        const map = res.data?.symbols || {};
        const n = Object.keys(map).length;
        if (n) intraday.ingestExternalQuotes(map);
      } catch (_) {
        /* ignore transient poll errors */
      }
    };
    pollQuotes();
    const id = window.setInterval(pollQuotes, LIVE_QUOTE_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [isActive, useLive, intraday]);

  const { layoutHydrated, indicatorsHydrated } = useWebChartLayoutMount(CHART_PAGE_IDS.movers, {
    setChartLayout, setTimeframe, setTimeframe2, setTimeframe3, setPaneWidth,
  }, (data, fromPrefs, globalIndicator) => {
    hydrateIndicatorPanels(data, fromPrefs, globalIndicator, { applyLayoutHeights, setPanelOrder });
  });

  useWebChartLayoutAutoSave(CHART_PAGE_IDS.movers, {
    chartLayout, timeframe, timeframe2, timeframe3, paneWidth,
  }, layoutHydrated, true, indicatorsHydrated);

  const onHeightsChangePersist = useIndicatorPanelAutoSave({
    handleHeightsChange,
    heightsRef,
    panelOrder,
    ready: layoutHydrated && indicatorsHydrated,
  });

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
    const onRefresh = (e) => {
      const preferLive = e?.detail?.preferLive ?? showcaseWebClient;
      // Never full-page load on external refresh — that fights chart symbol switches.
      fetchMovers({ preferLive, light: showcaseWebClient, background: true });
    };
    const onPrefetch = async (e) => {
      const resolve = e?.detail?.resolve;
      if (typeof resolve !== 'function') return;
      try {
        const data = await fetchMovers({
          preferLive: true,
          light: showcaseWebClient,
          background: true,
        });
        resolve(symbolsForMovers(data || []));
      } catch {
        resolve([]);
      }
    };
    const onChartDataUpdated = () => {
      fetchMovers({ background: true, preferLive: useLive, light: true });
    };
    window.addEventListener(MOVERS_REFRESH_EVENT, onRefresh);
    window.addEventListener(MOVERS_LIVE_PREFETCH_EVENT, onPrefetch);
    window.addEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
    return () => {
      window.removeEventListener(MOVERS_REFRESH_EVENT, onRefresh);
      window.removeEventListener(MOVERS_LIVE_PREFETCH_EVENT, onPrefetch);
      window.removeEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
    };
  }, [fetchMovers, showcaseWebClient, useLive]);
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
    const snapshot = { chartLayout, timeframe, timeframe2, timeframe3, paneWidth };
    const payload = mergeIndicatorPanelSaveFields(
      pageLayoutToApiPayload(CHART_PAGE_IDS.movers, snapshot),
      heightsRef.current,
      panelOrder,
    );
    saveWebChartLayoutOrServer(CHART_PAGE_IDS.movers, chartPrefs, snapshot, payload);
  }

  function renderPanel(sym, tf, setTf, onLastChange, cacheKey, hasBorderRight, dayChgOverride = null, columnIndex = 0) {
    if (!sym) return null;
    const tfLive = chartLiveEnabled && isIntradayLiveTimeframe(tf);
    return (
      <div key={cacheKey} style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0, borderRight: hasBorderRight ? '2px solid var(--border)' : 'none' }}>
        <ChartHeaderBar
          symbol={sym}
          timeframe={tf}
          onTimeframeChange={newTf => {
            setTf(newTf);
            onLastChange(null, null);
            setCrosshairTime(null);
          }}
        />
        <ChartContainer
          symbol={sym}
          timeframe={tf}
          dayChangePctOverride={dayChgOverride}
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
        {headerPrice != null && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)', flexShrink: 0 }}>
            ₹{headerPrice.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        )}
        {headerChange !== null && Number.isFinite(headerChange) && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, flexShrink: 0,
            color: headerChange >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
            backgroundColor: headerChange >= 0 ? 'rgba(63,185,80,0.12)' : 'rgba(248,81,73,0.12)',
            border: `1px solid ${headerChange >= 0 ? '#3fb95044' : '#f8514944'}`,
            borderRadius: 4, padding: '1px 6px',
          }}>
            {headerChange >= 0 ? '+' : ''}{headerChange.toFixed(2)}%
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

        <BasketToolbarButton />

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

      <StockListSplitBody
        splitRef={wrapperRef}
        footer={(
          <>
            {loading ? 'Loading…' : `${liveRows.length} stocks`}
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
              <button type="button" disabled={safePage <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} style={pagerBtnStyle(safePage > 1)}>Prev</button>
              <span style={{ color: 'var(--text-secondary)' }}>Page {safePage} / {totalPages}</span>
              <button type="button" disabled={safePage >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))} style={pagerBtnStyle(safePage < totalPages)}>Next</button>
            </span>
          </>
        )}
      >
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
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      height: MOVERS_CTRL_H,
                      padding: '0 8px',
                      borderRadius: 4,
                      border: `1px solid ${earningsToday ? 'var(--accent-blue)' : 'var(--border)'}`,
                      background: earningsToday ? 'rgba(56,139,253,0.12)' : 'var(--bg-tertiary)',
                    }}
                    title="Intersect movers with stocks releasing earnings today (IST)"
                  >
                    <span style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: earningsToday ? 'var(--accent-blue)' : 'var(--text-secondary)',
                      whiteSpace: 'nowrap',
                    }}
                    >
                      Earnings today
                    </span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={earningsToday}
                      aria-label="Show only stocks with earnings today"
                      onClick={() => {
                        const next = !earningsToday;
                        setEarningsToday(next);
                        writeEarningsTodayPref(next);
                      }}
                      style={{
                        position: 'relative',
                        width: 36,
                        height: 20,
                        flexShrink: 0,
                        borderRadius: 10,
                        border: '1px solid var(--border)',
                        backgroundColor: earningsToday ? 'var(--accent-blue)' : 'var(--bg-primary)',
                        cursor: 'pointer',
                        padding: 0,
                      }}
                    >
                      <span style={{
                        position: 'absolute',
                        top: 1,
                        left: 1,
                        width: 16,
                        height: 16,
                        borderRadius: '50%',
                        backgroundColor: '#fff',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.35)',
                        transform: earningsToday ? 'translateX(16px)' : 'translateX(0)',
                        transition: 'transform 0.15s ease',
                      }}
                      />
                    </button>
                  </div>
                </div>
              </section>
            </div>

            {parsedMinMcap != null && Number.isFinite(parsedMinMcap) && mcapValid && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', paddingLeft: 2 }}>
                Min cap: ≥ {formatMarketCap(parsedMinMcap)}
                {appliedMinMcapInr != null && appliedMinMcapInr === parsedMinMcap ? ' · applied' : ' · press Apply filters'}
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
            {loading ? 'Loading…' : `${liveRows.length} stocks`}
            {earningsToday ? ' · earnings today' : ''}
            {useLive && liveSessionBanner ? (
              <>
                {' · '}
                <span style={{ color: 'var(--accent-green)', fontWeight: 700 }}>Live</span>
                {liveSessionBanner.streamConnected ? ' · stream' : ' · connecting'}
                {liveSessionBanner.universeSize ? ` · ${liveSessionBanner.universeSize} quoted` : ''}
                {liveSessionBanner.marketClosed ? ' · market closed' : ''}
                {' · turn LIVE off for EOD'}
              </>
            ) : !useLive && meta?.as_of_date ? (
              ` · EOD ${meta.as_of_date}`
            ) : useLive ? (
              ' · Live (floating LIVE on)'
            ) : (
              ' · turn floating LIVE on for tick updates'
            )}
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
                      onClick={() => {
                        setSelectedSymbol(sym);
                        setLastCandleChange(null);
                        setLastCandlePrice(null);
                        setCrosshairTime(null);
                      }}
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
                      <td
                        draggable
                        onDragStart={(e) => {
                          e.stopPropagation();
                          startBasketSymbolDrag(e, sym, 'stock');
                        }}
                        title={`${sym} — drag to Basket`}
                        style={{ padding: '5px 4px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: active ? 'var(--accent-blue)' : 'var(--text-primary)', cursor: 'grab' }}
                      >{sym}</td>
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
              <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>{earningsToday
                  ? 'No movers with earnings releasing today match these filters.'
                  : useLive
                    ? 'No live movers match these filters. Try lowering min market cap, turn LIVE off for EOD, or refresh OHLC.'
                    : 'No results. Adjust min market cap or refresh OHLC.'}</div>
            )}
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
                  {renderPanel(selectedSymbol, timeframe, tf => { setTimeframe(tf); setLastCandleChange(null); setLastCandlePrice(null); }, (pct, price) => { setLastCandleChange(pct); setLastCandlePrice(price ?? null); }, `${selectedSymbol}-p1-${timeframe}`, chartLayout !== 'single', liveDayChangePct, 0)}
                  {(chartLayout === '2h' || chartLayout === '3h') && renderPanel(selectedSymbol, timeframe2, tf => setTimeframe2(tf), (pct, price) => { setLastCandleChange(pct); setLastCandlePrice(price ?? null); }, `${selectedSymbol}-p2-${timeframe2}`, chartLayout === '3h', liveDayChangePct, 1)}
                  {chartLayout === '3h' && renderPanel(selectedSymbol, timeframe3, tf => setTimeframe3(tf), (pct, price) => { setLastCandleChange(pct); setLastCandlePrice(price ?? null); }, `${selectedSymbol}-p3-${timeframe3}`, false, liveDayChangePct, 2)}
                </div>
              </DrawingWorkspaceProvider>
            </DrawingMirrorProvider>
          )}
        </div>
      </StockListSplitBody>
    </div>
  );
}
