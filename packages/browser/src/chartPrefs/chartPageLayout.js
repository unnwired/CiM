import api from '../api/http';
import { normalizeSavedTimeframe3 } from '../config/chartViewDefaults';
import { loadChartPrefs, saveChartPrefs } from './chartPrefsStore';
import {
  loadPersistedIndicatorPanelHeights,
  persistIndicatorPanelHeightsLocal,
} from './indicatorPanelHeightsStore';

export const CHART_PAGE_IDS = {
  dashboard: 'dashboard',
  movers: 'movers',
  watchlist: 'watchlist',
  indices: 'indices',
  potentialSwings: 'potentialSwings',
  constituents: 'constituents',
};

/** Shared chart view (layout + timeframes) stored once for all chart pages. */
export const GLOBAL_LAYOUT_ID = 'global';

const PAGE_PREFIX = {
  dashboard: 'dashboard',
  movers: 'movers',
  watchlist: 'watchlist',
  indices: 'indices',
  potentialSwings: 'potentialSwings',
  constituents: 'constituents',
};

const PAGE_IDS = Object.keys(PAGE_PREFIX);

export function pickGlobalChartViewSnapshot(state = {}) {
  const snap = {};
  if (state.chartLayout != null) snap.chartLayout = state.chartLayout;
  if (state.timeframe != null) snap.timeframe = state.timeframe;
  if (state.timeframe2 != null) snap.timeframe2 = state.timeframe2;
  if (state.timeframe3 != null) snap.timeframe3 = state.timeframe3;
  return snap;
}

export function pickPagePaneSnapshot(state = {}) {
  const snap = {};
  if (state.paneWidth != null) snap.paneWidth = state.paneWidth;
  return snap;
}

export function apiDataToGlobalChartView(apiData = {}) {
  if (!apiData) return {};
  const layout = {};
  const chartLayout = apiData.globalChartLayout;
  if (chartLayout) layout.chartLayout = String(chartLayout);
  const tf = apiData.globalTimeframe;
  if (tf) layout.timeframe = tf;
  const tf2 = apiData.globalTimeframe2;
  if (tf2) layout.timeframe2 = tf2;
  const tf3 = apiData.globalTimeframe3;
  if (tf3) layout.timeframe3 = normalizeSavedTimeframe3(tf3);
  return layout;
}

export function apiDataToPagePaneWidth(pageId, apiData = {}) {
  const prefix = PAGE_PREFIX[pageId];
  if (!prefix || !apiData) return null;
  const paneWidth = apiData[`${prefix}PaneWidth`];
  return paneWidth != null ? Number(paneWidth) : null;
}

function pickWinningLegacyChartView(views = []) {
  if (!views.length) return {};
  let chartLayout = null;
  for (const v of views) {
    chartLayout = resolveChartLayoutConflict(chartLayout, v.chartLayout);
  }
  const winner = views.find((v) => v.chartLayout === chartLayout)
    || views.find((v) => v.chartLayout && v.chartLayout !== 'single')
    || views[0];
  const out = {};
  if (chartLayout) out.chartLayout = String(chartLayout);
  if (winner.timeframe) out.timeframe = winner.timeframe;
  if (winner.timeframe2) out.timeframe2 = winner.timeframe2;
  if (winner.timeframe3) out.timeframe3 = normalizeSavedTimeframe3(winner.timeframe3);
  return out;
}

/** Migrate chart view from legacy per-page server fields. */
export function collectLegacyChartViewFromApi(apiData = {}) {
  const views = Object.values(PAGE_PREFIX).map((prefix) => ({
    chartLayout: apiData[`${prefix}ChartLayout`],
    timeframe: apiData[`${prefix}Timeframe`],
    timeframe2: apiData[`${prefix}Timeframe2`],
    timeframe3: apiData[`${prefix}Timeframe3`],
  })).filter((v) => v.chartLayout || v.timeframe || v.timeframe2 || v.timeframe3);
  return pickWinningLegacyChartView(views);
}

/** Migrate chart view from legacy per-page chart prefs. */
export function collectLegacyChartViewFromPrefs(layouts = {}) {
  const views = PAGE_IDS.map((pageId) => {
    if (pageId === GLOBAL_LAYOUT_ID) return null;
    const pref = layouts[pageId];
    if (!pref) return null;
    return {
      chartLayout: pref.chartLayout,
      timeframe: pref.timeframe,
      timeframe2: pref.timeframe2,
      timeframe3: pref.timeframe3,
    };
  }).filter(Boolean).filter((v) => v.chartLayout || v.timeframe || v.timeframe2 || v.timeframe3);
  return pickWinningLegacyChartView(views);
}

/** Merge global chart view from server, prefs, and legacy per-page sources. */
export function mergeGlobalChartViewSources(
  globalFromApi = {},
  globalFromPrefs = {},
  legacyFromApi = {},
  legacyFromPrefs = {},
) {
  let chartLayout = null;
  for (const src of [legacyFromApi, legacyFromPrefs, globalFromPrefs, globalFromApi]) {
    chartLayout = resolveChartLayoutConflict(chartLayout, src?.chartLayout);
  }
  const merged = {};
  if (chartLayout) merged.chartLayout = chartLayout;
  for (const field of ['timeframe', 'timeframe2', 'timeframe3']) {
    for (const src of [globalFromApi, globalFromPrefs, legacyFromApi, legacyFromPrefs]) {
      if (src?.[field] != null) {
        merged[field] = field === 'timeframe3'
          ? normalizeSavedTimeframe3(src[field])
          : src[field];
        break;
      }
    }
  }
  return merged;
}

export function applyGlobalChartView(layout = {}, setters = {}) {
  applyPageLayout(layout, setters);
}

export function globalChartViewToApiPayload(snapshot = {}) {
  const snap = pickGlobalChartViewSnapshot(snapshot);
  const payload = {};
  if (snap.chartLayout != null) payload.globalChartLayout = snap.chartLayout;
  if (snap.timeframe != null) payload.globalTimeframe = snap.timeframe;
  if (snap.timeframe2 != null) payload.globalTimeframe2 = snap.timeframe2;
  if (snap.timeframe3 != null) payload.globalTimeframe3 = snap.timeframe3;
  return payload;
}

export function pagePaneToApiPayload(pageId, snapshot = {}) {
  const prefix = PAGE_PREFIX[pageId];
  if (!prefix) return {};
  const snap = pickPagePaneSnapshot(snapshot);
  const payload = {};
  if (snap.paneWidth != null) payload[`${prefix}PaneWidth`] = snap.paneWidth;
  return payload;
}

/** Read global chart view + per-page pane width from server layout.json. */
export function apiDataToPageLayout(pageId, apiData = {}) {
  const global = mergeGlobalChartViewSources(
    apiDataToGlobalChartView(apiData),
    {},
    collectLegacyChartViewFromApi(apiData),
    {},
  );
  const paneWidth = apiDataToPagePaneWidth(pageId, apiData);
  return { ...global, ...(paneWidth != null ? { paneWidth } : {}) };
}

export function applyPageLayout(layout = {}, setters = {}) {
  if (!layout) return;
  if (layout.chartLayout && setters.setChartLayout) setters.setChartLayout(String(layout.chartLayout));
  if (layout.timeframe && setters.setTimeframe) setters.setTimeframe(layout.timeframe);
  if (layout.timeframe2 && setters.setTimeframe2) setters.setTimeframe2(layout.timeframe2);
  if (layout.timeframe3 && setters.setTimeframe3) {
    setters.setTimeframe3(normalizeSavedTimeframe3(layout.timeframe3));
  }
  if (layout.paneWidth != null && setters.setPaneWidth) {
    setters.setPaneWidth(Number(layout.paneWidth));
  }
}

export function pickPageLayoutSnapshot(state = {}) {
  return {
    ...pickGlobalChartViewSnapshot(state),
    ...pickPagePaneSnapshot(state),
  };
}

export const DEFAULT_PANEL_ORDER = ['stochrsi', 'macd'];

/** Valid saved stack order for StochRSI / MACD sub-panels. */
export function normalizePanelOrder(raw) {
  if (!Array.isArray(raw)) return null;
  const allowed = new Set(['stochrsi', 'macd']);
  const filtered = raw.filter((key) => allowed.has(key));
  if (filtered.length !== 2 || new Set(filtered).size !== 2) return null;
  return filtered;
}

/** Merge indicator panel geometry into a /api/layout POST body. */
export function mergeIndicatorPanelSaveFields(payload = {}, heights = {}, panelOrder) {
  const merged = { ...payload };
  const stoch = Number(heights?.stochrsi);
  const macd = Number(heights?.macd);
  if (Number.isFinite(stoch)) merged.stochrsi = stoch;
  if (Number.isFinite(macd)) merged.macd = macd;
  const order = normalizePanelOrder(panelOrder);
  if (order) merged.panelOrder = order;
  return merged;
}

/** Extract indicator geometry fields for chart prefs + server merge. */
export function pickIndicatorPanelFields(source = {}) {
  const out = {};
  const stoch = Number(source?.stochrsi);
  const macd = Number(source?.macd);
  if (Number.isFinite(stoch)) out.stochrsi = stoch;
  if (Number.isFinite(macd)) out.macd = macd;
  const order = normalizePanelOrder(source?.panelOrder);
  if (order) out.panelOrder = order;
  return out;
}

/** Prefer localStorage + chart prefs over server defaults (server omits unset indicator keys). */
export function resolveIndicatorPanelLayout(apiData = {}, prefsLayout = null, globalIndicator = null) {
  const localHeights = loadPersistedIndicatorPanelHeights();
  const stoch = Number(
    localHeights?.stochrsi
    ?? (apiData && 'stochrsi' in apiData ? apiData.stochrsi : undefined)
    ?? globalIndicator?.stochrsi
    ?? prefsLayout?.stochrsi,
  );
  const macd = Number(
    localHeights?.macd
    ?? (apiData && 'macd' in apiData ? apiData.macd : undefined)
    ?? globalIndicator?.macd
    ?? prefsLayout?.macd,
  );
  const order = normalizePanelOrder(localHeights?.panelOrder)
    ?? normalizePanelOrder(apiData?.panelOrder)
    ?? normalizePanelOrder(globalIndicator?.panelOrder)
    ?? normalizePanelOrder(prefsLayout?.panelOrder);
  const resolved = {};
  if (Number.isFinite(stoch)) resolved.stochrsi = stoch;
  if (Number.isFinite(macd)) resolved.macd = macd;
  if (order) resolved.panelOrder = order;
  return resolved;
}

/** Restore MACD / StochRSI heights and stack order from server + chart prefs. */
export function applyIndicatorPanelLayoutFromApi(
  data,
  handlers = {},
  prefsLayout = null,
  globalIndicator = null,
) {
  const resolved = resolveIndicatorPanelLayout(data, prefsLayout, globalIndicator);
  if (Object.keys(resolved).length === 0) return;
  const heightFields = pickIndicatorPanelFields(resolved);
  const hasHeights = Number.isFinite(heightFields.stochrsi) || Number.isFinite(heightFields.macd);
  if (hasHeights && handlers.applyLayoutHeights) {
    const heightsOnly = {};
    if (Number.isFinite(heightFields.stochrsi)) heightsOnly.stochrsi = heightFields.stochrsi;
    if (Number.isFinite(heightFields.macd)) heightsOnly.macd = heightFields.macd;
    handlers.applyLayoutHeights(heightsOnly);
  }
  if (resolved.panelOrder && handlers.setPanelOrder) {
    handlers.setPanelOrder(resolved.panelOrder);
  }
}

export function hydrateIndicatorPanels(data, fromPrefs, globalIndicator, handlers) {
  applyIndicatorPanelLayoutFromApi(data, handlers, fromPrefs, globalIndicator);
}

/** Persist global StochRSI/MACD heights (+ optional stack order) to chart prefs and server. */
export function persistIndicatorPanelsGlobal({
  email,
  chartPrefsEnabled = false,
  heights,
  panelOrder,
  skipLocal = false,
}) {
  const payload = mergeIndicatorPanelSaveFields({}, heights, panelOrder);
  const indicatorSnap = pickIndicatorPanelFields(payload);
  if (Object.keys(indicatorSnap).length === 0) return;

  if (!skipLocal) {
    persistIndicatorPanelHeightsLocal(heights, panelOrder);
  }

  if (email && chartPrefsEnabled) {
    saveChartPrefs(email, { indicatorPanels: indicatorSnap });
  }

  api.post('/api/layout', indicatorSnap).catch(() => {});
}

/** Prefer a non-default multi-panel layout when sources disagree (guards against stale "single" clobber). */
export function resolveChartLayoutConflict(apiLayout, prefsLayout) {
  const a = apiLayout ? String(apiLayout) : null;
  const p = prefsLayout ? String(prefsLayout) : null;
  if (!a && !p) return null;
  if (a === p) return a;
  if (a && a !== 'single') return a;
  if (p && p !== 'single') return p;
  return a || p;
}

/** Merge server + localStorage; chartLayout uses resolveChartLayoutConflict. */
export function mergePageLayoutSources(fromApi = {}, fromPrefs = {}) {
  const merged = { ...fromApi, ...fromPrefs };
  const resolved = resolveChartLayoutConflict(fromApi?.chartLayout, fromPrefs?.chartLayout);
  if (resolved) merged.chartLayout = resolved;
  else delete merged.chartLayout;
  return merged;
}

export function pageLayoutToApiPayload(pageId, snapshot = {}) {
  return {
    ...globalChartViewToApiPayload(snapshot),
    ...pagePaneToApiPayload(pageId, snapshot),
  };
}

export function loadWebPageLayout(email, pageId, apiData, setters) {
  const prefs = email ? loadChartPrefs(email) : null;
  const globalFromApi = apiDataToGlobalChartView(apiData);
  const globalFromPrefs = prefs?.layouts?.[GLOBAL_LAYOUT_ID] || {};
  const legacyApi = collectLegacyChartViewFromApi(apiData);
  const legacyPrefs = collectLegacyChartViewFromPrefs(prefs?.layouts || {});
  const mergedGlobal = mergeGlobalChartViewSources(
    globalFromApi,
    globalFromPrefs,
    legacyApi,
    legacyPrefs,
  );
  if (Object.keys(mergedGlobal).length > 0) {
    applyGlobalChartView(mergedGlobal, setters);
  }

  const paneFromApi = apiDataToPagePaneWidth(pageId, apiData);
  const paneFromPrefs = prefs?.layouts?.[pageId]?.paneWidth;
  const paneWidth = paneFromPrefs != null ? Number(paneFromPrefs) : paneFromApi;
  if (paneWidth != null && setters.setPaneWidth) {
    setters.setPaneWidth(paneWidth);
  }

  return Object.keys(mergedGlobal).length > 0 || paneWidth != null;
}

export function saveWebPageLayoutNow(email, pageId, snapshot, extraServerFields = null) {
  const globalSnap = pickGlobalChartViewSnapshot(snapshot);
  const paneSnap = pickPagePaneSnapshot(snapshot);
  const indicatorSnap = pickIndicatorPanelFields(extraServerFields || snapshot);

  saveChartPrefs(email, {
    layouts: {
      [GLOBAL_LAYOUT_ID]: globalSnap,
      [pageId]: paneSnap,
    },
    ...(Object.keys(indicatorSnap).length
      ? { indicatorPanels: indicatorSnap }
      : {}),
  });

  const payload = {
    ...globalChartViewToApiPayload(globalSnap),
    ...pagePaneToApiPayload(pageId, paneSnap),
    ...indicatorSnap,
    ...(extraServerFields && typeof extraServerFields === 'object'
      ? Object.fromEntries(
        Object.entries(extraServerFields).filter(([key]) => (
          !['chartLayout', 'timeframe', 'timeframe2', 'timeframe3', 'paneWidth',
            'stochrsi', 'macd', 'panelOrder'].includes(key)
          && !key.endsWith('ChartLayout')
          && !key.endsWith('Timeframe')
          && !key.endsWith('Timeframe2')
          && !key.endsWith('Timeframe3')
          && !key.endsWith('PaneWidth')
        )),
      )
      : {}),
  };
  if (Object.keys(payload).length > 0) {
    api.post('/api/layout', payload).catch(() => {});
  }
}

/** Persist layout to chart prefs (web) or server API (desktop). */
export function persistChartPageLayout({
  email,
  pageId,
  snapshot,
  extraServerFields = null,
  chartPrefsEnabled = false,
}) {
  if (email && chartPrefsEnabled) {
    saveWebPageLayoutNow(email, pageId, snapshot, extraServerFields);
    return;
  }
  const globalSnap = pickGlobalChartViewSnapshot(snapshot);
  const paneSnap = pickPagePaneSnapshot(snapshot);
  const indicatorSnap = pickIndicatorPanelFields(extraServerFields || snapshot);
  const payload = {
    ...globalChartViewToApiPayload(globalSnap),
    ...pagePaneToApiPayload(pageId, paneSnap),
    ...indicatorSnap,
    ...(extraServerFields && typeof extraServerFields === 'object' ? extraServerFields : {}),
  };
  if (Object.keys(payload).length > 0) {
    api.post('/api/layout', payload).catch(() => {});
  }
}
