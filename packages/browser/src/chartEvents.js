/** Fired when admin jobs finish so open charts refetch without a full page reload. */
export const CHART_DATA_UPDATED_EVENT = 'nse-pulse-chart-data-updated';

/** Header Refresh on Market Pulse dispatches this so indices reload without a second on-page button. */
export const MARKET_PULSE_REFRESH_EVENT = 'cim-market-pulse-refresh';

/** Header Refresh on Market Movers reloads movers lists. */
export const MOVERS_REFRESH_EVENT = 'cim-market-movers-refresh';

/** Showcase: refetch live movers ranking before intraday price patch. */
export const MOVERS_LIVE_PREFETCH_EVENT = 'cim-movers-live-prefetch';

/** Generic list/table pages that only need a server refetch after host data jobs. */
export const APP_DATA_REFRESH_EVENT = 'cim-app-data-refresh';

/** Header ↻ Refresh on P&L — fetch session prices for open P&L symbols only. */
export const PNL_REFRESH_EVENT = 'cim-pnl-refresh';

export function dispatchChartDataUpdated(detail = {}) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(CHART_DATA_UPDATED_EVENT, { detail }));
}

/**
 * Single completion bus after OHLCV / chart-data admin jobs.
 * Fans out to charts, lists, movers, pulse, and intraday patch invalidation.
 */
export function dispatchAppDataRefresh(detail = {}) {
  if (typeof window === 'undefined') return;
  const payload = { invalidatePatches: true, ...detail };
  dispatchChartDataUpdated(payload);
  window.dispatchEvent(new CustomEvent(MARKET_PULSE_REFRESH_EVENT, { detail: payload }));
  window.dispatchEvent(new CustomEvent(MOVERS_REFRESH_EVENT, { detail: payload }));
  window.dispatchEvent(new CustomEvent('dashboard-refresh', { detail: payload }));
  window.dispatchEvent(new CustomEvent(APP_DATA_REFRESH_EVENT, { detail: payload }));
}

/** First visible chart with data — cues Knowledge Base sidebar chrome intro (once per page load). */
export const CIM_CHROME_INTRO_READY_EVENT = 'cim-chrome-intro-ready';

let chromeIntroReadyDispatched = false;

export function dispatchChromeIntroReadyOnce() {
  if (chromeIntroReadyDispatched || typeof window === 'undefined') return;
  chromeIntroReadyDispatched = true;
  window.dispatchEvent(new CustomEvent(CIM_CHROME_INTRO_READY_EVENT));
}
