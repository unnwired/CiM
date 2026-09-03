import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import api from '../api/http';
import * as patchStore from './patchStore';
import { mergeLiveIntoChartBars } from './mergeLiveBars';

import { CHART_DATA_UPDATED_EVENT } from '../chartEvents';

const IntradayPatchContext = createContext(null);
const CHUNK_SIZE = 12;
const MAX_SYMBOLS_PER_REFRESH = 200;
const PATCH_REQUEST_TIMEOUT_MS = 45000;
/** List / multi-symbol overlays — keep UI cool under LTPC flood. */
const LIVE_STREAM_RENDER_THROTTLE_MS = 1000;
/** Focus chart symbol — flush on next animation frame (no 1s lag). */
const FOCUS_STREAM_FLUSH_MS = 0;


function finite(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function firstFinite(...values) {
  for (const v of values) {
    const n = finite(v);
    if (n != null) return n;
  }
  return null;
}

function positiveFinite(v) {
  const n = finite(v);
  return n != null && n > 0 ? n : null;
}

function focusSymbolsFromContexts(contexts) {
  const focus = contexts && contexts.focus;
  const symbols = focus && Array.isArray(focus.symbols) ? focus.symbols : [];
  return new Set(
    symbols.map((s) => String(s || '').trim().toUpperCase()).filter(Boolean),
  );
}

/** Prefer engine day candle OHLC when quote open is still missing / stub. */
function enrichSnapFromDayCandle(snap, dayBar) {
  if (!snap || !dayBar || typeof dayBar !== 'object') return snap;
  const open = positiveFinite(dayBar.open);
  const high = positiveFinite(dayBar.high);
  const low = positiveFinite(dayBar.low);
  const close = positiveFinite(dayBar.close);
  const next = { ...snap };
  if (open != null) next.open = open;
  if (high != null) next.high = high;
  if (low != null) next.low = low;
  if (close != null) next.price = close;
  next.candle_1d = dayBar;
  return next;
}
export function mergeRunningSessionOhlc(prevSnap, nextSnap) {
  if (!nextSnap) return prevSnap || null;
  if (!prevSnap) {
    const px = positiveFinite(nextSnap.price);
    if (px == null) return nextSnap;
    const seededOpen = positiveFinite(nextSnap.open);
    const seededHigh = positiveFinite(nextSnap.high);
    const seededLow = positiveFinite(nextSnap.low);
    return {
      ...nextSnap,
      open: seededOpen ?? nextSnap.open,
      high: seededHigh ?? (seededOpen != null ? Math.max(seededOpen, px) : px),
      low: seededLow ?? (seededOpen != null ? Math.min(seededOpen, px) : px),
    };
  }
  const px = positiveFinite(nextSnap.price);
  const prevHigh = positiveFinite(prevSnap.high);
  const prevLow = positiveFinite(prevSnap.low);
  const prevOpen = positiveFinite(prevSnap.open);
  let open = positiveFinite(nextSnap.open) ?? prevOpen;
  let high = positiveFinite(nextSnap.high);
  let low = positiveFinite(nextSnap.low);
  if (px != null) {
    high = Math.max(high ?? px, prevHigh ?? px, px);
    low = Math.min(low ?? px, prevLow ?? px, px);
  } else {
    if (high == null) high = prevHigh;
    if (low == null) low = prevLow;
  }
  return {
    ...prevSnap,
    ...nextSnap,
    open: open ?? nextSnap.open ?? prevSnap.open,
    high: high ?? nextSnap.high ?? prevSnap.high,
    low: low ?? nextSnap.low ?? prevSnap.low,
    previous_close: nextSnap.previous_close ?? prevSnap.previous_close,
    change_pct: nextSnap.change_pct ?? prevSnap.change_pct,
  };
}

export function liveQuoteToSnapshot(symbol, quote) {
  if (!quote || typeof quote !== 'object') return null;
  const ohlc = quote.ohlc && typeof quote.ohlc === 'object' ? quote.ohlc : {};
  const price = firstFinite(
    quote.price,
    quote.last_price,
    quote.ltp,
    quote.last_traded_price,
    quote.close,
    ohlc.close,
  );
  if (price == null || price <= 0) return null;
  const previousClose = firstFinite(
    quote.previous_close,
    quote.prev_close,
    quote.cp,
    quote.close_price,
    quote.day_close,
    ohlc.previous_close,
  );
  const changePct = firstFinite(
    quote.change_pct,
    quote.change_percent,
    quote.percent_change,
    quote.pChange,
    previousClose && previousClose > 0 ? ((price - previousClose) / previousClose) * 100 : null,
  );
  return {
    symbol,
    price,
    previous_close: previousClose,
    open: firstFinite(quote.open, ohlc.open),
    high: firstFinite(quote.high, ohlc.high),
    low: firstFinite(quote.low, ohlc.low),
    volume: firstFinite(quote.volume, quote.day_volume, quote.total_traded_volume, ohlc.volume),
    change_pct: changePct,
    source: quote.source || 'upstox',
    ts: quote.ts || quote.timestamp || quote.last_updated || null,
  };
}

function normalizeLiveContexts(contexts) {
  const out = {};
  if (!contexts || typeof contexts !== 'object') return out;
  Object.entries(contexts).forEach(([context, value]) => {
    const key = String(context || '').trim();
    if (!key) return;
    const rawSymbols = Array.isArray(value?.symbols) ? value.symbols : [];
    out[key] = {
      mode: value?.mode || 'ltpc',
      symbols: rawSymbols.map((s) => String(s || '').trim().toUpperCase()).filter(Boolean),
    };
  });
  return out;
}

function contextMatchesPage(contexts, pageId) {
  const id = String(pageId || '').trim();
  if (!id || !contexts) return false;
  if (contexts[id]) return true;
  // Chart / focus aliases
  if ((id === 'chart' || id === 'focus') && (contexts.focus || contexts.chart)) return true;
  // Portfolio aliases
  if (
    (id === 'portfolio' || id === 'portfolio-dashboard')
    && (contexts.portfolio || contexts['portfolio-dashboard'])
  ) {
    return true;
  }
  // Direct page contexts used by Live Feed Mode
  if (contexts.dashboard && id === 'dashboard') return true;
  if (contexts.pnl && id === 'pnl') return true;
  if (contexts.watchlist && id === 'watchlist') return true;
  if (contexts['market-map'] && id === 'market-map') return true;
  if (contexts['market-pulse'] && id === 'market-pulse') return true;
  if ((contexts.movers || contexts['market-movers']) && id === 'movers') return true;
  if (contexts.indices && id === 'indices') return true;
  if (contexts['potential-swings'] && id === 'potential-swings') return true;
  if (
    (contexts['earnings-beats'] || contexts.earnings)
    && (id === 'earnings-beats' || id === 'earnings')
  ) {
    return true;
  }
  // Index constituents pages: constituents-NIFTY 50, etc.
  if (id.startsWith('constituents-') && contexts[id]) {
    return true;
  }
  // Index chart pages: index-NIFTY 50, etc.
  if (id.startsWith('index-') && contexts[id]) {
    return true;
  }
  return false;
}

export function IntradayPatchProvider({ enabled, userEmail, onApiReady, children }) {
  const [eodTradeDate, setEodTradeDate] = useState(null);
  const [sessionIntradayAllowed, setSessionIntradayAllowed] = useState(false);
  const [patchBlob, setPatchBlob] = useState({});
  const [liveContexts, setLiveContexts] = useState({});
  const [liveStreamActive, setLiveStreamActive] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  const blobRef = useRef({});
  const liveContextsRef = useRef({});
  const liveSymbolsRef = useRef(new Set());
  const liveFlushTimerRef = useRef(null);
  const liveFlushRafRef = useRef(null);
  const publishedAtRef = useRef(null);

  const clearLiveFlush = useCallback(() => {
    if (liveFlushTimerRef.current) {
      window.clearTimeout(liveFlushTimerRef.current);
      liveFlushTimerRef.current = null;
    }
    if (liveFlushRafRef.current != null && typeof window.cancelAnimationFrame === 'function') {
      window.cancelAnimationFrame(liveFlushRafRef.current);
      liveFlushRafRef.current = null;
    }
  }, []);

  const clearPatchState = useCallback(async () => {
    await patchStore.clearAllForUser(userEmail);
    blobRef.current = {};
    setPatchBlob({});
    setRefreshTick((t) => t + 1);
  }, [userEmail]);

  const publishLivePatch = useCallback((nextContexts = null) => {
    setPatchBlob({ ...blobRef.current });
    if (nextContexts) {
      liveContextsRef.current = nextContexts;
      liveSymbolsRef.current = new Set(
        Object.values(nextContexts).flatMap((ctx) => ctx.symbols || []),
      );
      setLiveContexts(nextContexts);
      setLiveStreamActive(Object.keys(nextContexts).length > 0);
    }
    setRefreshTick((t) => t + 1);
  }, []);

  const ingestLiveState = useCallback((state) => {
    if (!enabled || typeof window === 'undefined') return;
    const liveState = state || window.CiMLive?.getState?.() || window.CiMLiveState || {};
    const contexts = normalizeLiveContexts(liveState.contexts || {});
    const quotes = liveState.quotes || {};
    const candleMap = liveState.candles || {};
    const focusSet = focusSymbolsFromContexts(contexts);
    const merged = {};
    let touchedFocus = false;
    Object.entries(quotes).forEach(([rawSymbol, quote]) => {
      const symbol = String(rawSymbol || '').trim().toUpperCase();
      let snap = liveQuoteToSnapshot(symbol, quote);
      if (!snap) return;
      const bundle = candleMap[symbol];
      const dayBar = bundle && (bundle['1D'] || bundle.day || bundle['1d']);
      if (dayBar) snap = enrichSnapFromDayCandle(snap, dayBar);
      merged[symbol] = mergeRunningSessionOhlc(blobRef.current[symbol], snap);
      if (focusSet.has(symbol)) touchedFocus = true;
    });
    // Candle-only updates (quote already merged earlier)
    Object.entries(candleMap).forEach(([rawSymbol, bundle]) => {
      const symbol = String(rawSymbol || '').trim().toUpperCase();
      if (merged[symbol] || !bundle) return;
      const dayBar = bundle['1D'] || bundle.day || bundle['1d'];
      if (!dayBar) return;
      const prev = blobRef.current[symbol];
      if (!prev) return;
      merged[symbol] = mergeRunningSessionOhlc(prev, enrichSnapFromDayCandle({ ...prev }, dayBar));
      if (focusSet.has(symbol)) touchedFocus = true;
    });
    if (Object.keys(merged).length) {
      blobRef.current = { ...blobRef.current, ...merged };
    }
    const delay = touchedFocus ? FOCUS_STREAM_FLUSH_MS : LIVE_STREAM_RENDER_THROTTLE_MS;
    if (!touchedFocus && (liveFlushTimerRef.current || liveFlushRafRef.current != null)) {
      return;
    }
    clearLiveFlush();
    const flush = () => {
      liveFlushTimerRef.current = null;
      liveFlushRafRef.current = null;
      publishLivePatch(contexts);
    };
    if (delay <= 0 && typeof window.requestAnimationFrame === 'function') {
      liveFlushRafRef.current = window.requestAnimationFrame(flush);
      return;
    }
    liveFlushTimerRef.current = window.setTimeout(flush, delay);
  }, [clearLiveFlush, enabled, publishLivePatch]);

  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return undefined;
    let cancelled = false;
    let unsubscribe = null;

    const attach = () => {
      if (cancelled) return;
      const live = window.CiMLive;
      if (!live?.onStoreUpdate) {
        window.setTimeout(attach, 500);
        return;
      }
      unsubscribe = live.onStoreUpdate((snapshot, state) => {
        ingestLiveState(state || window.CiMLiveState || {});
      });
      ingestLiveState(live.getState?.() || window.CiMLiveState || {});
    };

    attach();
    const onSubscriptionChanged = () => {
      ingestLiveState(window.CiMLive?.getState?.() || window.CiMLiveState || {});
    };
    window.addEventListener('cim:live-subscribe', onSubscriptionChanged);
    window.addEventListener('cim:live-unsubscribe', onSubscriptionChanged);
    return () => {
      cancelled = true;
      if (unsubscribe) unsubscribe();
      window.removeEventListener('cim:live-subscribe', onSubscriptionChanged);
      window.removeEventListener('cim:live-unsubscribe', onSubscriptionChanged);
      if (liveFlushTimerRef.current || liveFlushRafRef.current != null) {
        clearLiveFlush();
      }
    };
  }, [clearLiveFlush, enabled, ingestLiveState]);

  const applyServerVersion = useCallback(async (ver, { forceClearPatch = false } = {}) => {
    if (!enabled) return;
    setSessionIntradayAllowed(!!ver.session_intraday_allowed);
    const latest = ver.eod_trade_date ? String(ver.eod_trade_date).slice(0, 10) : null;
    const published = ver.published_at ? String(ver.published_at) : null;
    const eodStale = latest && ver.status === 'complete' && patchStore.isStale(eodTradeDate, latest);
    const publishStale = patchStore.isPublishStale(publishedAtRef.current, published);
    if (forceClearPatch || eodStale || publishStale) {
      await clearPatchState();
    }
    if (published) publishedAtRef.current = published;
    if (latest) setEodTradeDate(latest);
  }, [clearPatchState, eodTradeDate, enabled]);

  const pollVersion = useCallback(async (options = {}) => {
    if (!enabled) return;
    try {
      const res = await api.get('/api/market-data-version');
      await applyServerVersion(res.data || {}, {
        forceClearPatch: !!options.forceClearPatch,
      });
    } catch {
      /* offline / auth blip */
    }
  }, [applyServerVersion, enabled]);

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;

    (async () => {
      try {
        const verRes = await api.get('/api/market-data-version');
        if (cancelled) return;
        const ver = verRes.data || {};
        if (ver.published_at) publishedAtRef.current = String(ver.published_at);
        setSessionIntradayAllowed(!!ver.session_intraday_allowed);
        const latest = ver.eod_trade_date ? String(ver.eod_trade_date).slice(0, 10) : null;
        setEodTradeDate(latest);

        if (latest && userEmail) {
          const saved = await patchStore.loadPatchBlob(userEmail, latest);
          if (!cancelled && saved && Object.keys(saved).length > 0) {
            blobRef.current = { ...saved };
            setPatchBlob({ ...saved });
            setRefreshTick((t) => t + 1);
          }
        }
      } catch {
        /* offline / auth blip */
      }
    })();

    pollVersion();
    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, userEmail]);

  // Invalidate local patch overlay when host admin/scheduler jobs finish.
  useEffect(() => {
    if (!enabled) return undefined;
    const onDataUpdated = (e) => {
      const force = e?.detail?.invalidatePatches !== false;
      pollVersion({ forceClearPatch: force });
    };
    window.addEventListener(CHART_DATA_UPDATED_EVENT, onDataUpdated);
    return () => window.removeEventListener(CHART_DATA_UPDATED_EVENT, onDataUpdated);
  }, [enabled, pollVersion]);

  const refreshPatch = useCallback(async (symbols) => {
    if (!enabled) return { ok: false, error: 'Intraday overlay disabled' };
    const uniq = [];
    const seen = new Set();
    for (const raw of symbols || []) {
      const sym = String(raw || '').trim().toUpperCase();
      if (!sym || seen.has(sym)) continue;
      seen.add(sym);
      uniq.push(sym);
    }
    if (!uniq.length) return { ok: false, error: 'No symbols' };

    let eod = eodTradeDate;
    if (!eod) {
      try {
        const verRes = await api.get('/api/market-data-version');
        eod = verRes.data?.eod_trade_date
          ? String(verRes.data.eod_trade_date).slice(0, 10)
          : istTodayYmd();
      } catch {
        eod = istTodayYmd();
      }
    }

    const capped = uniq.slice(0, MAX_SYMBOLS_PER_REFRESH);
    const merged = {};
    let nseError = null;
    for (let i = 0; i < capped.length; i += CHUNK_SIZE) {
      const chunk = capped.slice(i, i + CHUNK_SIZE);
      const res = await api.get('/api/intraday-patch', {
        params: { symbols: chunk.join(',') },
        timeout: PATCH_REQUEST_TIMEOUT_MS,
      });
      const map = res.data?.symbols || {};
      Object.assign(merged, map);
      if (res.data?.nse_error) nseError = res.data.nse_error;
    }

    const withOhlc = Object.fromEntries(
      Object.entries(merged).map(([sym, snap]) => [
        sym,
        mergeRunningSessionOhlc(blobRef.current[sym], snap),
      ]),
    );
    blobRef.current = { ...blobRef.current, ...withOhlc };
    setPatchBlob({ ...blobRef.current });
    await patchStore.savePatchBlob(userEmail, eod, withOhlc);
    setRefreshTick((t) => t + 1);
    return {
      ok: true,
      count: Object.keys(merged).length,
      nseError,
      truncated: uniq.length > capped.length,
      requested: uniq.length,
    };
  }, [enabled, userEmail, eodTradeDate]);

  const getSymbolSnapshot = useCallback((symbol) => {
    const sym = String(symbol || '').trim().toUpperCase();
    return blobRef.current[sym] || null;
  }, []);

  /** Merge external live quotes (e.g. movers LTPC poll) into the overlay blob and re-render. */
  const ingestExternalQuotes = useCallback((quotesMap) => {
    if (!enabled || !quotesMap || typeof quotesMap !== 'object') return 0;
    const merged = {};
    Object.entries(quotesMap).forEach(([rawSymbol, quote]) => {
      const symbol = String(rawSymbol || '').trim().toUpperCase();
      const snap = liveQuoteToSnapshot(symbol, quote);
      if (!snap) return;
      merged[symbol] = mergeRunningSessionOhlc(blobRef.current[symbol], snap);
    });
    if (!Object.keys(merged).length) return 0;
    blobRef.current = { ...blobRef.current, ...merged };
    publishLivePatch(null);
    return Object.keys(merged).length;
  }, [enabled, publishLivePatch]);


  const applyToChartBars = useCallback((bars, symbol, timeframe) => {
    const snap = getSymbolSnapshot(symbol);
    if (!snap) return { bars, dayChangePct: null };
    return mergeLiveIntoChartBars(bars, snap, timeframe);
  }, [getSymbolSnapshot]);

  const isLiveContextActive = useCallback((pageId) => (
    contextMatchesPage(liveContextsRef.current, pageId)
  ), []);

  const isSymbolLive = useCallback((symbol) => {
    const sym = String(symbol || '').trim().toUpperCase();
    return !!sym && liveSymbolsRef.current.has(sym);
  }, []);

  const value = useMemo(() => ({
    enabled: !!enabled,
    eodTradeDate,
    sessionIntradayAllowed,
    patchBlob,
    liveContexts,
    liveStreamActive,
    refreshTick,
    refreshPatch,
    getSymbolSnapshot,
    ingestExternalQuotes,
    applyToChartBars,
    isLiveContextActive,
    isSymbolLive,
    pollVersion,
  }), [
    enabled,
    eodTradeDate,
    sessionIntradayAllowed,
    patchBlob,
    liveContexts,
    liveStreamActive,
    refreshTick,
    refreshPatch,
    getSymbolSnapshot,
    ingestExternalQuotes,
    applyToChartBars,
    isLiveContextActive,
    isSymbolLive,
    pollVersion,
  ]);

  useEffect(() => {
    if (!onApiReady) return undefined;
    if (!enabled) {
      onApiReady(null);
      return undefined;
    }
    onApiReady(value);
    return () => onApiReady(null);
  }, [enabled, onApiReady, value]);

  return (
    <IntradayPatchContext.Provider value={value}>
      {children}
    </IntradayPatchContext.Provider>
  );
}

function istTodayYmd() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
}

export function useIntradayPatch() {
  return useContext(IntradayPatchContext);
}

export function useIntradayPatchOptional() {
  return useContext(IntradayPatchContext);
}
