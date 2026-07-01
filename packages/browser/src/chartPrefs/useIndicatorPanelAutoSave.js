import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../api/http';
import { normalizePanelHeights } from '../hooks/useSyncedPanelHeights';
import { loadChartPrefs } from './chartPrefsStore';
import { persistIndicatorPanelHeightsLocal } from './indicatorPanelHeightsStore';
import {
  persistIndicatorPanelsGlobal,
  resolveIndicatorPanelLayout,
} from './chartPageLayout';
import { useChartPrefsContext } from './useChartPrefs';

const API = '';

/**
 * Auto-save of global indicator panel heights after user resize / reorder.
 * Writes localStorage immediately; debounces server + chart-prefs sync.
 */
export function useIndicatorPanelAutoSave({
  handleHeightsChange,
  heightsRef,
  panelOrder,
  ready = true,
}) {
  const chartPrefs = useChartPrefsContext();
  const timerRef = useRef(null);
  const skipPersistRef = useRef(true);
  const pendingServerRef = useRef(null);

  const flushServerPersist = useCallback(() => {
    const pending = pendingServerRef.current;
    if (!pending) return;
    pendingServerRef.current = null;
    persistIndicatorPanelsGlobal({
      email: chartPrefs?.email,
      chartPrefsEnabled: !!(chartPrefs?.enabled && chartPrefs?.email),
      heights: pending.heights,
      panelOrder: pending.panelOrder,
      skipLocal: true,
    });
  }, [chartPrefs?.email, chartPrefs?.enabled]);

  useEffect(() => {
    if (!ready) {
      skipPersistRef.current = true;
      return undefined;
    }
    const t = window.setTimeout(() => {
      skipPersistRef.current = false;
    }, 0);
    return () => window.clearTimeout(t);
  }, [ready]);

  const schedulePersist = useCallback((heights) => {
    if (!ready || skipPersistRef.current) return;
    const normalized = normalizePanelHeights(heights);
    persistIndicatorPanelHeightsLocal(normalized, panelOrder);
    pendingServerRef.current = { heights: normalized, panelOrder };
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      flushServerPersist();
    }, 500);
  }, [ready, panelOrder, flushServerPersist]);

  const onHeightsChange = useCallback((h, columnIndex = 0) => {
    handleHeightsChange(h, columnIndex);
    schedulePersist(h);
  }, [handleHeightsChange, schedulePersist]);

  useEffect(() => {
    if (!ready || skipPersistRef.current) return undefined;
    const h = heightsRef?.current;
    if (!h) return undefined;
    schedulePersist(h);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- persist when stack order changes
  }, [panelOrder, ready]);

  useEffect(() => () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    flushServerPersist();
  }, [flushServerPersist]);

  return onHeightsChange;
}

/** Load global indicator heights for standalone chart tabs (stock / index). */
export function useIndicatorPanelsBootstrap({ applyLayoutHeights, setPanelOrder }) {
  const chartPrefs = useChartPrefsContext();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setReady(false);

    api.get(`${API}/api/layout`).then((r) => {
      if (cancelled) return;
      const data = r.data || {};
      const prefs = (chartPrefs?.enabled && chartPrefs?.email)
        ? loadChartPrefs(chartPrefs.email)
        : null;
      const resolved = resolveIndicatorPanelLayout(data, null, prefs?.indicatorPanels);
      if (Object.keys(resolved).length > 0) {
        applyLayoutHeights(resolved);
        if (resolved.panelOrder && setPanelOrder) {
          setPanelOrder(resolved.panelOrder);
        }
      }
      setReady(true);
    }).catch(() => {
      if (!cancelled) {
        const resolved = resolveIndicatorPanelLayout({}, null, null);
        if (Object.keys(resolved).length > 0) {
          applyLayoutHeights(resolved);
          if (resolved.panelOrder && setPanelOrder) {
            setPanelOrder(resolved.panelOrder);
          }
        }
        setReady(true);
      }
    });

    return () => { cancelled = true; };
  }, [applyLayoutHeights, setPanelOrder, chartPrefs?.enabled, chartPrefs?.email]);

  return ready;
}
