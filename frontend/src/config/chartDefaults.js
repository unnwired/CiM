import { isDistributionProfile } from './exportProfile';

const EMA_PREFS_KEY = isDistributionProfile
  ? 'flowx.chart.ema.distribution'
  : 'flowx.chart.ema';
const VOLUME_PREFS_KEY = isDistributionProfile
  ? 'flowx.chart.volumeVisible.distribution'
  : 'flowx.chart.volumeVisible';
/** Distribution builds use a separate key so dev localStorage on 127.0.0.1 does not leave indicators on. */
export const PANELS_PREFS_KEY = isDistributionProfile
  ? 'flowx.chart.visiblePanels.distribution'
  : 'flowx.chart.visiblePanels';
export const EMA_PREFS_UPDATED_EVENT = 'flowx:ema-prefs-updated';
export const VOLUME_PREFS_UPDATED_EVENT = 'flowx:volume-prefs-updated';
export const PANELS_PREFS_UPDATED_EVENT = 'flowx:panels-prefs-updated';
const DIST_EMA_DEFAULTS_VERSION_KEY = 'flowx.chart.ema.distribution.version';
const DIST_EMA_DEFAULTS_VERSION = 'v2-ema-100-200';
const DIST_PANELS_DEFAULTS_VERSION_KEY = 'flowx.chart.panels.distribution.version';
const DIST_PANELS_DEFAULTS_VERSION = 'v2-all-off';
const DIST_VOLUME_DEFAULTS_VERSION_KEY = 'flowx.chart.volume.distribution.version';
const DIST_VOLUME_DEFAULTS_VERSION = 'v1-off';

export const EMA_PERIODS = [21, 50, 100, 200];
export const EMA_COLOR_BY_PERIOD = {
  21: '#f6c90e',
  50: '#26a69a',
  100: '#ef5350',
  200: '#ab47bc',
};

const STANDARD_EMAS = [
  { period: 21, visible: true, color: EMA_COLOR_BY_PERIOD[21] },
  { period: 50, visible: true, color: EMA_COLOR_BY_PERIOD[50] },
  { period: 100, visible: true, color: EMA_COLOR_BY_PERIOD[100] },
  { period: 200, visible: true, color: EMA_COLOR_BY_PERIOD[200] },
];

const DISTRIBUTION_EMAS = [
  { period: 21, visible: false, color: EMA_COLOR_BY_PERIOD[21] },
  { period: 50, visible: false, color: EMA_COLOR_BY_PERIOD[50] },
  { period: 100, visible: true, color: EMA_COLOR_BY_PERIOD[100] },
  { period: 200, visible: true, color: EMA_COLOR_BY_PERIOD[200] },
];

const STANDARD_PANELS = { stochrsi: true, macd: true };
const DISTRIBUTION_PANELS = { stochrsi: false, macd: false };

export const DEFAULT_EMAS = isDistributionProfile ? DISTRIBUTION_EMAS : STANDARD_EMAS;
export const DEFAULT_PANELS = isDistributionProfile ? DISTRIBUTION_PANELS : STANDARD_PANELS;

function coerceBool(value, fallback) {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const v = value.trim().toLowerCase();
    if (v === 'true') return true;
    if (v === 'false') return false;
  }
  if (typeof value === 'number') {
    if (value === 1) return true;
    if (value === 0) return false;
  }
  return fallback;
}

export function normalizeEmaSet(source = []) {
  const base = isDistributionProfile ? DISTRIBUTION_EMAS : STANDARD_EMAS;
  const baseByPeriod = new Map(base.map((e) => [Number(e.period), !!e.visible]));
  const byPeriod = new Map((source || []).map((e) => [Number(e.period), e]));
  return EMA_PERIODS.map((period) => {
    const existing = byPeriod.get(period);
    return {
      period,
      visible: coerceBool(existing?.visible, baseByPeriod.get(period) ?? true),
      color: existing?.color || EMA_COLOR_BY_PERIOD[period],
    };
  });
}

export function getPersistedEmaSet() {
  if (typeof window === 'undefined') return normalizeEmaSet(DEFAULT_EMAS);
  try {
    if (isDistributionProfile) {
      const migrated = window.localStorage.getItem(DIST_EMA_DEFAULTS_VERSION_KEY);
      if (migrated !== DIST_EMA_DEFAULTS_VERSION) {
        const normalizedDefault = normalizeEmaSet(DEFAULT_EMAS);
        window.localStorage.setItem(EMA_PREFS_KEY, JSON.stringify(normalizedDefault));
        window.localStorage.setItem(DIST_EMA_DEFAULTS_VERSION_KEY, DIST_EMA_DEFAULTS_VERSION);
        return normalizedDefault;
      }
    }
    const raw = window.localStorage.getItem(EMA_PREFS_KEY);
    if (!raw) return normalizeEmaSet(DEFAULT_EMAS);
    const parsed = JSON.parse(raw);
    return normalizeEmaSet(parsed);
  } catch {
    return normalizeEmaSet(DEFAULT_EMAS);
  }
}

export function persistEmaSet(source = []) {
  if (typeof window === 'undefined') return;
  try {
    const normalized = normalizeEmaSet(source);
    window.localStorage.setItem(EMA_PREFS_KEY, JSON.stringify(normalized));
    window.dispatchEvent(new CustomEvent(EMA_PREFS_UPDATED_EVENT, { detail: normalized }));
  } catch {
    // Ignore storage write failures (private mode/quota/security).
  }
}

export function getPersistedVolumeVisible(defaultValue = true) {
  if (typeof window === 'undefined') {
    return isDistributionProfile ? false : defaultValue;
  }
  try {
    if (isDistributionProfile) {
      const migrated = window.localStorage.getItem(DIST_VOLUME_DEFAULTS_VERSION_KEY);
      if (migrated !== DIST_VOLUME_DEFAULTS_VERSION) {
        window.localStorage.setItem(VOLUME_PREFS_KEY, 'false');
        window.localStorage.setItem(DIST_VOLUME_DEFAULTS_VERSION_KEY, DIST_VOLUME_DEFAULTS_VERSION);
        return false;
      }
    }
    const raw = window.localStorage.getItem(VOLUME_PREFS_KEY);
    if (raw == null) return isDistributionProfile ? false : defaultValue;
    return raw === 'true';
  } catch {
    return isDistributionProfile ? false : defaultValue;
  }
}

export function persistVolumeVisible(value) {
  if (typeof window === 'undefined') return;
  try {
    const next = !!value;
    window.localStorage.setItem(VOLUME_PREFS_KEY, String(next));
    window.dispatchEvent(new CustomEvent(VOLUME_PREFS_UPDATED_EVENT, { detail: next }));
  } catch {
    // Ignore storage write failures (private mode/quota/security).
  }
}

export function normalizeVisiblePanels(source = {}) {
  const base = isDistributionProfile ? DISTRIBUTION_PANELS : STANDARD_PANELS;
  return {
    stochrsi: coerceBool(source?.stochrsi, base.stochrsi),
    macd: coerceBool(source?.macd, base.macd),
  };
}

export function getPersistedVisiblePanels() {
  if (typeof window === 'undefined') return normalizeVisiblePanels(DEFAULT_PANELS);
  try {
    if (isDistributionProfile) {
      const migrated = window.localStorage.getItem(DIST_PANELS_DEFAULTS_VERSION_KEY);
      if (migrated !== DIST_PANELS_DEFAULTS_VERSION) {
        const normalizedDefault = normalizeVisiblePanels(DEFAULT_PANELS);
        window.localStorage.setItem(PANELS_PREFS_KEY, JSON.stringify(normalizedDefault));
        window.localStorage.setItem(DIST_PANELS_DEFAULTS_VERSION_KEY, DIST_PANELS_DEFAULTS_VERSION);
        // Legacy per-page key forced MACD/StochRSI on in Movers regardless of distribution defaults.
        window.localStorage.removeItem('flowx.movers.visiblePanels');
        return normalizedDefault;
      }
    }
    const raw = window.localStorage.getItem(PANELS_PREFS_KEY);
    if (!raw) return normalizeVisiblePanels(DEFAULT_PANELS);
    const parsed = JSON.parse(raw);
    return normalizeVisiblePanels(parsed);
  } catch {
    return normalizeVisiblePanels(DEFAULT_PANELS);
  }
}

export function persistVisiblePanels(source = {}) {
  if (typeof window === 'undefined') return;
  try {
    const normalized = normalizeVisiblePanels(source);
    window.localStorage.setItem(PANELS_PREFS_KEY, JSON.stringify(normalized));
    window.dispatchEvent(new CustomEvent(PANELS_PREFS_UPDATED_EVENT, { detail: normalized }));
  } catch {
    // Ignore storage write failures (private mode/quota/security).
  }
}
