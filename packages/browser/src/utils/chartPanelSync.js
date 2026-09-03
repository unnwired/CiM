import { normalizeChartTimeKey } from './chartTime';

/** Keep right price-scale gutter equal across price + indicator panes so crosshair lines align. */
export const CHART_RIGHT_SCALE_MIN_WIDTH = 84;

export const CHART_RIGHT_PRICE_SCALE = {
  borderColor: '#30363d',
  minimumWidth: CHART_RIGHT_SCALE_MIN_WIDTH,
};

/**
 * Logical index on the price chart where an indicator series starts (warmup trim).
 * Prefer matching first indicator timestamp to price bars — length delta alone drifts on 1W/1M.
 */
export function computeSeriesLeadOffset(priceBars, indicatorSeries) {
  if (!Array.isArray(priceBars) || !priceBars.length) return 0;
  if (!Array.isArray(indicatorSeries) || !indicatorSeries.length) return 0;
  const firstInd = normalizeChartTimeKey(indicatorSeries[0].time);
  const idx = priceBars.findIndex((b) => normalizeChartTimeKey(b.time) === firstInd);
  if (idx >= 0) return idx;
  return Math.max(0, priceBars.length - indicatorSeries.length);
}

/** Map crosshair time from price master to an indicator pane using shared logical index. */
export function resolveSyncedCrosshairTime(sourceChart, pointX, fallbackTime, targetChart, leadOffset) {
  if (!targetChart || !leadOffset) return fallbackTime;
  try {
    const logical = sourceChart?.timeScale()?.coordinateToLogical(pointX);
    if (logical == null || !Number.isFinite(logical)) return fallbackTime;
    const mapped = targetChart.timeScale().logicalToTime(logical - leadOffset);
    return mapped != null ? mapped : fallbackTime;
  } catch {
    return fallbackTime;
  }
}

/** Map crosshair time from indicator pane back to the price master. */
export function resolveSyncedCrosshairTimeToPrice(sourceChart, pointX, fallbackTime, priceChart, leadOffset) {
  if (!priceChart || !leadOffset) return fallbackTime;
  try {
    const logical = sourceChart?.timeScale()?.coordinateToLogical(pointX);
    if (logical == null || !Number.isFinite(logical)) return fallbackTime;
    const mapped = priceChart.timeScale().logicalToTime(logical + leadOffset);
    return mapped != null ? mapped : fallbackTime;
  } catch {
    return fallbackTime;
  }
}
