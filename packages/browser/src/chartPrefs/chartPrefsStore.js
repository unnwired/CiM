import {
  DEFAULT_EMAS,
  DEFAULT_PANELS,
  EMA_PREFS_KEY,
  EMA_PREFS_UPDATED_EVENT,
  PANELS_PREFS_KEY,
  PANELS_PREFS_UPDATED_EVENT,
  VOLUME_PREFS_KEY,
  VOLUME_PREFS_UPDATED_EVENT,
  getPersistedEmaSet,
  getPersistedVisiblePanels,
  getPersistedVolumeVisible,
  normalizeEmaSet,
  normalizeVisiblePanels,
  persistEmaSet,
  persistVisiblePanels,
  persistVolumeVisible,
} from '../config/chartDefaults';

const PREFS_KEY_PREFIX = 'cim.chart.prefs.v1::';

function emailSafe(email) {
  return String(email || '').trim().toLowerCase().replace(/[^a-z0-9@._-]/g, '_');
}

function storageKey(email) {
  const safe = emailSafe(email);
  return safe ? `${PREFS_KEY_PREFIX}${safe}` : null;
}

export function hasStoredChartPrefs(email) {
  if (typeof window === 'undefined') return false;
  const key = storageKey(email);
  if (!key) return false;
  try {
    return !!window.localStorage.getItem(key);
  } catch {
    return false;
  }
}

export function defaultChartPrefsBlob() {
  return {
    emas: normalizeEmaSet(DEFAULT_EMAS),
    visiblePanels: normalizeVisiblePanels(DEFAULT_PANELS),
    volumeVisible: getPersistedVolumeVisible(false),
    layouts: {},
    listOrders: {},
    savedAt: new Date().toISOString(),
  };
}

export function loadChartPrefs(email) {
  if (typeof window === 'undefined') return defaultChartPrefsBlob();
  const key = storageKey(email);
  if (!key) return defaultChartPrefsBlob();
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return defaultChartPrefsBlob();
    const parsed = JSON.parse(raw);
    return {
      emas: parsed.emas ? normalizeEmaSet(parsed.emas) : normalizeEmaSet(DEFAULT_EMAS),
      visiblePanels: parsed.visiblePanels
        ? normalizeVisiblePanels(parsed.visiblePanels)
        : normalizeVisiblePanels(DEFAULT_PANELS),
      volumeVisible: typeof parsed.volumeVisible === 'boolean'
        ? parsed.volumeVisible
        : getPersistedVolumeVisible(false),
      layouts: parsed.layouts && typeof parsed.layouts === 'object' ? parsed.layouts : {},
      indicatorPanels: parsed.indicatorPanels && typeof parsed.indicatorPanels === 'object'
        ? parsed.indicatorPanels
        : null,
      listOrders: parsed.listOrders && typeof parsed.listOrders === 'object'
        ? parsed.listOrders
        : {},
      savedAt: parsed.savedAt || null,
    };
  } catch {
    return defaultChartPrefsBlob();
  }
}

export function saveChartPrefs(email, partial = {}) {
  if (typeof window === 'undefined') return loadChartPrefs(email);
  const key = storageKey(email);
  if (!key) return defaultChartPrefsBlob();
  const current = loadChartPrefs(email);
  const next = {
    emas: partial.emas != null ? normalizeEmaSet(partial.emas) : current.emas,
    visiblePanels: partial.visiblePanels != null
      ? normalizeVisiblePanels(partial.visiblePanels)
      : current.visiblePanels,
    volumeVisible: partial.volumeVisible != null ? !!partial.volumeVisible : current.volumeVisible,
    layouts: { ...current.layouts },
    indicatorPanels: partial.indicatorPanels != null
      ? { ...(current.indicatorPanels || {}), ...(partial.indicatorPanels || {}) }
      : current.indicatorPanels,
    listOrders: partial.listOrders != null
      ? { ...(current.listOrders || {}), ...(partial.listOrders || {}) }
      : current.listOrders,
    savedAt: new Date().toISOString(),
  };
  if (partial.layouts && typeof partial.layouts === 'object') {
    Object.keys(partial.layouts).forEach((pageId) => {
      next.layouts[pageId] = {
        ...(current.layouts?.[pageId] || {}),
        ...(partial.layouts[pageId] || {}),
      };
    });
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(next));
  } catch {
    // Ignore quota / private mode failures.
  }
  return next;
}

export function clearChartPrefs(email) {
  if (typeof window === 'undefined') return;
  const key = storageKey(email);
  if (!key) return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export function resetChartPrefsToDefaults(email) {
  clearChartPrefs(email);
  const defaults = defaultChartPrefsBlob();
  saveChartPrefs(email, defaults);
  applyChartPrefsToLegacyKeys(defaults);
  return defaults;
}

export function migrateLegacyToEmailPrefs(email) {
  const key = storageKey(email);
  if (!key || typeof window === 'undefined') return;
  try {
    if (window.localStorage.getItem(key)) return;
  } catch {
    return;
  }
  const legacyEmas = window.localStorage.getItem(EMA_PREFS_KEY);
  const legacyPanels = window.localStorage.getItem(PANELS_PREFS_KEY);
  const legacyVolume = window.localStorage.getItem(VOLUME_PREFS_KEY);
  if (!legacyEmas && !legacyPanels && legacyVolume == null) return;
  const blob = defaultChartPrefsBlob();
  if (legacyEmas) {
    try { blob.emas = normalizeEmaSet(JSON.parse(legacyEmas)); } catch { /* keep default */ }
  }
  if (legacyPanels) {
    try { blob.visiblePanels = normalizeVisiblePanels(JSON.parse(legacyPanels)); } catch { /* keep default */ }
  }
  if (legacyVolume != null) blob.volumeVisible = legacyVolume === 'true';
  saveChartPrefs(email, blob);
}

export function applyChartPrefsToLegacyKeys(prefs) {
  if (!prefs || typeof window === 'undefined') return;
  if (prefs.emas) persistEmaSet(prefs.emas);
  if (prefs.visiblePanels) persistVisiblePanels(prefs.visiblePanels);
  if (typeof prefs.volumeVisible === 'boolean') persistVolumeVisible(prefs.volumeVisible);
}

export function snapshotGlobalChartPrefsFromLegacy() {
  return {
    emas: getPersistedEmaSet(),
    visiblePanels: getPersistedVisiblePanels(),
    volumeVisible: getPersistedVolumeVisible(false),
  };
}

export function formatChartPrefsSummary(prefs) {
  const emasOn = (prefs?.emas || []).filter((e) => e.visible).map((e) => e.period).join(', ') || 'none';
  const panels = [];
  if (prefs?.visiblePanels?.macd) panels.push('MACD');
  if (prefs?.visiblePanels?.stochrsi) panels.push('StochRSI');
  const layoutPages = Object.keys(prefs?.layouts || {}).filter(
    (k) => prefs.layouts[k] && Object.keys(prefs.layouts[k]).length > 0,
  );
  return {
    emasOn,
    panels: panels.length ? panels.join(', ') : 'none',
    volume: prefs?.volumeVisible ? 'On' : 'Off',
    layoutPages: layoutPages.length ? layoutPages.join(', ') : 'defaults',
    savedAt: prefs?.savedAt || null,
  };
}

export {
  EMA_PREFS_UPDATED_EVENT,
  PANELS_PREFS_UPDATED_EVENT,
  VOLUME_PREFS_UPDATED_EVENT,
};
