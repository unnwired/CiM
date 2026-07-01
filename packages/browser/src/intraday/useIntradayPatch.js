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

export function IntradayPatchProvider({ enabled, userEmail, onApiReady, children }) {
  const [eodTradeDate, setEodTradeDate] = useState(null);
  const [sessionIntradayAllowed, setSessionIntradayAllowed] = useState(false);
  const [patchBlob, setPatchBlob] = useState({});
  const [refreshTick, setRefreshTick] = useState(0);
  const blobRef = useRef({});
  const publishedAtRef = useRef(null);

  const clearPatchState = useCallback(async () => {
    await patchStore.clearAllForUser(userEmail);
    blobRef.current = {};
    setPatchBlob({});
    setRefreshTick((t) => t + 1);
  }, [userEmail]);

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

    blobRef.current = { ...blobRef.current, ...merged };
    setPatchBlob({ ...blobRef.current });
    await patchStore.savePatchBlob(userEmail, eod, merged);
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

  const applyToChartBars = useCallback((bars, symbol, timeframe) => {
    const snap = getSymbolSnapshot(symbol);
    if (!snap) return { bars, dayChangePct: null };
    return mergeLiveIntoChartBars(bars, snap, timeframe);
  }, [getSymbolSnapshot]);

  const value = useMemo(() => ({
    enabled: !!enabled,
    eodTradeDate,
    sessionIntradayAllowed,
    patchBlob,
    refreshTick,
    refreshPatch,
    getSymbolSnapshot,
    applyToChartBars,
    pollVersion,
  }), [
    enabled,
    eodTradeDate,
    sessionIntradayAllowed,
    patchBlob,
    refreshTick,
    refreshPatch,
    getSymbolSnapshot,
    applyToChartBars,
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
