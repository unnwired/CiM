import { isDistributionProfile } from '../config/exportProfile';
import { normalizePanelHeights } from '../hooks/useSyncedPanelHeights';

/** Global StochRSI/MACD heights — shared across every chart page (not per-page). */
export const INDICATOR_HEIGHTS_PREFS_KEY = isDistributionProfile
  ? 'cim.chart.indicatorHeights.distribution'
  : 'cim.chart.indicatorHeights';

function readPanelOrder(raw) {
  if (!Array.isArray(raw) || raw.length !== 2) return null;
  const keys = raw.map(String);
  if (keys.includes('stochrsi') && keys.includes('macd')) return keys;
  return null;
}

export function loadPersistedIndicatorPanelHeights() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(INDICATOR_HEIGHTS_PREFS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    const stoch = Number(parsed.stochrsi);
    const macd = Number(parsed.macd);
    const out = {};
    if (Number.isFinite(stoch)) out.stochrsi = stoch;
    if (Number.isFinite(macd)) out.macd = macd;
    const order = readPanelOrder(parsed.panelOrder);
    if (order) out.panelOrder = order;
    return Object.keys(out).length > 0 ? out : null;
  } catch {
    return null;
  }
}

/** Synchronous write — survives hard refresh even if debounced server save never ran. */
export function persistIndicatorPanelHeightsLocal(heights, panelOrder) {
  if (typeof window === 'undefined') return;
  const normalized = normalizePanelHeights(heights);
  const order = readPanelOrder(panelOrder);
  const payload = {
    stochrsi: normalized.stochrsi,
    macd: normalized.macd,
    ...(order ? { panelOrder: order } : {}),
    savedAt: new Date().toISOString(),
  };
  try {
    window.localStorage.setItem(INDICATOR_HEIGHTS_PREFS_KEY, JSON.stringify(payload));
  } catch {
    // quota / private mode
  }
}
