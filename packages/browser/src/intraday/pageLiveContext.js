import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { isIntradayLiveTimeframe } from './patchOverlay';

const PageLiveContext = createContext(null);
const PAGE_LIVE_STORAGE_KEY = 'cim.pageLiveId';

function readStoredPageLiveId() {
  try {
    const id = sessionStorage.getItem(PAGE_LIVE_STORAGE_KEY);
    return id ? String(id).trim() : null;
  } catch {
    return null;
  }
}

export function PageLiveProvider({ onApiReady, children }) {
  const [pageLiveId, setPageLiveIdState] = useState(() => readStoredPageLiveId());
  const [liveTick, setLiveTick] = useState(0);

  const setPageLive = useCallback((pageId) => {
    const id = String(pageId || '').trim();
    if (!id) return;
    setPageLiveIdState(id);
    setLiveTick((t) => t + 1);
    try {
      sessionStorage.setItem(PAGE_LIVE_STORAGE_KEY, id);
    } catch {
      /* private browsing */
    }
  }, []);

  const clearPageLive = useCallback(() => {
    setPageLiveIdState(null);
    try {
      sessionStorage.removeItem(PAGE_LIVE_STORAGE_KEY);
    } catch {
      /* private browsing */
    }
  }, []);

  const value = useMemo(
    () => ({ pageLiveId, liveTick, setPageLive, clearPageLive }),
    [pageLiveId, liveTick, setPageLive, clearPageLive],
  );

  useEffect(() => {
    if (!onApiReady) return undefined;
    onApiReady(value);
    return () => onApiReady(null);
  }, [onApiReady, value]);

  return (
    <PageLiveContext.Provider value={value}>
      {children}
    </PageLiveContext.Provider>
  );
}

export function usePageLiveContext() {
  return useContext(PageLiveContext);
}

export function usePageLive(pageId) {
  const ctx = useContext(PageLiveContext);
  const id = String(pageId || '').trim();
  const liveActive = !!ctx && !!id && ctx.pageLiveId === id;
  return {
    liveActive,
    liveTick: ctx?.liveTick ?? 0,
    setPageLive: ctx?.setPageLive,
  };
}

/** Chart props gated on explicit Refresh prices for this page. */
export function usePageLiveChartProps(pageId, symbol, timeframe) {
  const { liveActive, liveTick } = usePageLive(pageId);
  const liveToday = liveActive && !!symbol && isIntradayLiveTimeframe(timeframe);
  return {
    liveToday,
    liveRefreshKey: liveToday ? liveTick : null,
  };
}
