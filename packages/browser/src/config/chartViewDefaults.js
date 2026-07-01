
/** Default multi-chart view: 1D + 1W + 2W in three-panel layout. */
export const DEFAULT_CHART_TIMEFRAME_1 = '1D';
export const DEFAULT_CHART_TIMEFRAME_2 = '1W';
export const DEFAULT_CHART_TIMEFRAME_3 = '2W';

export const DEFAULT_CHART_TIMEFRAMES = [
  DEFAULT_CHART_TIMEFRAME_1,
  DEFAULT_CHART_TIMEFRAME_2,
  DEFAULT_CHART_TIMEFRAME_3,
];

/** Dashboard / watchlist: three charts (1D + 1W + 2W) — same for showcase and dev. */
export const DEFAULT_CHART_LAYOUT = '3h';

/** Split chart tab: three charts side by side. */
export const DEFAULT_SPLIT_LAYOUT = '3s';

export function timeframeForPanelIndex(index) {
  return DEFAULT_CHART_TIMEFRAMES[index] ?? DEFAULT_CHART_TIMEFRAME_1;
}

/** Migrate legacy monthly third panel to 2W when loading saved layout. */
export function normalizeSavedTimeframe3(tf) {
  if (!tf || tf === '1M') return DEFAULT_CHART_TIMEFRAME_3;
  return tf;
}
