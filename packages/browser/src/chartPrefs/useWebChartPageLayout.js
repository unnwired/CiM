import { useEffect, useRef, useState } from 'react';
import api from '../api/http';
import {
  hydrateListOrderFields,
  syncListOrdersToServerIfNeeded,
} from '../layout/listOrderPersistence';
import { useChartPrefsContext } from './ChartPrefsProvider';
import { loadChartPrefs, saveChartPrefs } from './chartPrefsStore';
import {
  GLOBAL_LAYOUT_ID,
  apiDataToGlobalChartView,
  apiDataToPagePaneWidth,
  applyGlobalChartView,
  collectLegacyChartViewFromApi,
  collectLegacyChartViewFromPrefs,
  globalChartViewToApiPayload,
  hydrateIndicatorPanels,
  loadWebPageLayout,
  mergeGlobalChartViewSources,
  pagePaneToApiPayload,
  pickGlobalChartViewSnapshot,
  pickIndicatorPanelFields,
  pickPageLayoutSnapshot,
  pickPagePaneSnapshot,
} from './chartPageLayout';

const API = '';

export function useWebChartLayoutMount(pageId, setters, onApiLayoutExtra) {
  const chartPrefs = useChartPrefsContext();
  const [layoutHydrated, setLayoutHydrated] = useState(false);
  const [indicatorsHydrated, setIndicatorsHydrated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLayoutHydrated(false);
    setIndicatorsHydrated(false);

    api.get(`${API}/api/layout`).then((r) => {
      if (cancelled) return;
      const serverData = r.data || {};
      const prefs = (chartPrefs?.enabled && chartPrefs?.email)
        ? loadChartPrefs(chartPrefs.email)
        : null;
      const { orders, usedLocal, needsStarTagsServerSync } = hydrateListOrderFields(
        serverData,
        chartPrefs?.enabled ? chartPrefs?.email : null,
        prefs?.listOrders || {},
      );
      const data = { ...serverData, ...orders };
      if (usedLocal || needsStarTagsServerSync) {
        syncListOrdersToServerIfNeeded(
          chartPrefs?.enabled ? chartPrefs?.email : null,
          orders,
          { usedLocal, needsStarTagsServerSync },
        );
      }
      const globalFromApi = apiDataToGlobalChartView(data);
      const globalFromPrefs = prefs?.layouts?.[GLOBAL_LAYOUT_ID] || {};
      const legacyApi = collectLegacyChartViewFromApi(data);
      const legacyPrefs = collectLegacyChartViewFromPrefs(prefs?.layouts || {});
      const mergedGlobal = mergeGlobalChartViewSources(
        globalFromApi,
        globalFromPrefs,
        legacyApi,
        legacyPrefs,
      );
      applyGlobalChartView(mergedGlobal, setters);

      const paneFromApi = apiDataToPagePaneWidth(pageId, data);
      const paneFromPrefs = prefs?.layouts?.[pageId]?.paneWidth;
      const paneWidth = paneFromPrefs != null ? Number(paneFromPrefs) : paneFromApi;
      if (paneWidth != null && setters.setPaneWidth) {
        setters.setPaneWidth(paneWidth);
      }

      const pagePrefs = prefs?.layouts?.[pageId] || null;
      if (onApiLayoutExtra) onApiLayoutExtra(data, pagePrefs, prefs?.indicatorPanels || null);
      setIndicatorsHydrated(true);
      setLayoutHydrated(true);
    }).catch(() => {
      if (cancelled) return;
      const { orders } = hydrateListOrderFields(
        {},
        chartPrefs?.enabled ? chartPrefs?.email : null,
        chartPrefs?.enabled && chartPrefs?.email
          ? loadChartPrefs(chartPrefs.email).listOrders
          : {},
      );
      const data = { ...orders };
      if (chartPrefs?.enabled && chartPrefs?.email) {
        loadWebPageLayout(chartPrefs.email, pageId, {}, setters);
      }
      if (onApiLayoutExtra && Object.keys(orders).length) {
        onApiLayoutExtra(data, null, null);
      }
      setIndicatorsHydrated(true);
      setLayoutHydrated(true);
    });

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageId, chartPrefs?.enabled, chartPrefs?.email]);

  return { layoutHydrated, indicatorsHydrated };
}

/** Standard indicator-panel restore for multi-chart pages. */
export function useIndicatorPanelHydration(handlers) {
  return (data, fromPrefs, globalIndicator) => {
    hydrateIndicatorPanels(data, fromPrefs, globalIndicator, handlers);
  };
}

export function useWebChartLayoutAutoSave(
  pageId,
  snapshot,
  layoutHydrated = false,
  layoutActive = true,
  indicatorsHydrated = true,
) {
  const chartPrefs = useChartPrefsContext();
  const desktopTimerRef = useRef(null);
  const {
    chartLayout, timeframe, timeframe2, timeframe3, paneWidth,
  } = snapshot;

  useEffect(() => {
    if (!layoutActive || !layoutHydrated || !indicatorsHydrated) return undefined;

    if (chartPrefs?.enabled && chartPrefs?.email) {
      chartPrefs.scheduleLayoutSave(pageId, pickPageLayoutSnapshot({
        chartLayout, timeframe, timeframe2, timeframe3, paneWidth,
      }));
      return undefined;
    }

    if (desktopTimerRef.current) clearTimeout(desktopTimerRef.current);
    desktopTimerRef.current = setTimeout(() => {
      const snap = pickPageLayoutSnapshot({
        chartLayout, timeframe, timeframe2, timeframe3, paneWidth,
      });
      const payload = {
        ...globalChartViewToApiPayload(snap),
        ...pagePaneToApiPayload(pageId, snap),
      };
      if (Object.keys(payload).length > 0) {
        api.post(`${API}/api/layout`, payload).catch(() => {});
      }
    }, 500);

    return () => {
      if (desktopTimerRef.current) clearTimeout(desktopTimerRef.current);
    };
  }, [
    layoutActive, layoutHydrated, indicatorsHydrated, chartPrefs, pageId,
    chartLayout, timeframe, timeframe2, timeframe3, paneWidth,
  ]);
}

export function saveWebChartLayoutOrServer(pageId, chartPrefs, snapshot, serverPayload) {
  const globalSnap = pickGlobalChartViewSnapshot(snapshot);
  const paneSnap = pickPagePaneSnapshot(snapshot);
  const indicatorSnap = pickIndicatorPanelFields(serverPayload || {});

  if (chartPrefs?.enabled && chartPrefs?.email) {
    saveChartPrefs(chartPrefs.email, {
      layouts: {
        [GLOBAL_LAYOUT_ID]: globalSnap,
        [pageId]: paneSnap,
      },
      ...(Object.keys(indicatorSnap).length ? { indicatorPanels: indicatorSnap } : {}),
    });
  }

  const payload = (serverPayload && Object.keys(serverPayload).length > 0)
    ? serverPayload
    : {
      ...globalChartViewToApiPayload(globalSnap),
      ...pagePaneToApiPayload(pageId, paneSnap),
      ...indicatorSnap,
    };

  if (!payload || Object.keys(payload).length === 0) {
    window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Layout saved.' }));
    return Promise.resolve();
  }

  return api.post(`${API}/api/layout`, payload)
    .then(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Layout saved.' })))
    .catch(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Failed to save layout.' })));
}
