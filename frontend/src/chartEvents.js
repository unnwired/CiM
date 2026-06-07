/** Fired when admin jobs finish so open charts refetch without a full page reload. */
export const CHART_DATA_UPDATED_EVENT = 'nse-pulse-chart-data-updated';

/** Header Refresh on Market Pulse dispatches this so indices reload without a second on-page button. */
export const MARKET_PULSE_REFRESH_EVENT = 'flowx-market-pulse-refresh';

/** Header Refresh on Market Movers reloads movers lists. */
export const MOVERS_REFRESH_EVENT = 'flowx-market-movers-refresh';

export function dispatchChartDataUpdated(detail = {}) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(CHART_DATA_UPDATED_EVENT, { detail }));
}
