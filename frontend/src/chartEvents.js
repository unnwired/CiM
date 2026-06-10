/** Fired when admin jobs finish so open charts refetch without a full page reload. */
export const CHART_DATA_UPDATED_EVENT = 'nse-pulse-chart-data-updated';

/** Header Refresh on Market Pulse dispatches this so indices reload without a second on-page button. */
export const MARKET_PULSE_REFRESH_EVENT = 'cim-market-pulse-refresh';

/** Header Refresh on Market Movers reloads movers lists. */
export const MOVERS_REFRESH_EVENT = 'cim-market-movers-refresh';

export function dispatchChartDataUpdated(detail = {}) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(CHART_DATA_UPDATED_EVENT, { detail }));
}

/** First visible chart with data — cues Knowledge Base sidebar chrome intro (once per page load). */
export const CIM_CHROME_INTRO_READY_EVENT = 'cim-chrome-intro-ready';

let chromeIntroReadyDispatched = false;

export function dispatchChromeIntroReadyOnce() {
  if (chromeIntroReadyDispatched || typeof window === 'undefined') return;
  chromeIntroReadyDispatched = true;
  window.dispatchEvent(new CustomEvent(CIM_CHROME_INTRO_READY_EVENT));
}
