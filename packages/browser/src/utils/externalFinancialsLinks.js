/** External financials URLs for NSE-listed equities (screener.in + TradingView India). */

import { screenerCompanySlug } from './screenerCompanySlug';

export function normalizeEquitySymbol(symbol) {
  return String(symbol || '').trim().toUpperCase();
}

export function screenerFinancialsUrl(symbol, basis = 'standalone') {
  const slug = screenerCompanySlug(symbol);
  if (!slug) return null;
  const b = String(basis || 'standalone').trim().toLowerCase();
  if (b === 'consolidated') {
    return `https://www.screener.in/company/${encodeURIComponent(slug)}/consolidated/#quarters`;
  }
  return `https://www.screener.in/company/${encodeURIComponent(slug)}/#quarters`;
}

/** TradingView India — NSE symbol financials overview. */
export function tradingViewFinancialsUrl(symbol) {
  const sym = normalizeEquitySymbol(symbol);
  if (!sym) return null;
  return `https://in.tradingview.com/symbols/NSE-${encodeURIComponent(sym)}/financials-overview/`;
}

/** TradingView India — earnings tab, quarterly (FQ) EPS and revenue. */
export function tradingViewEarningsUrl(symbol) {
  const sym = normalizeEquitySymbol(symbol);
  if (!sym) return null;
  return (
    `https://in.tradingview.com/symbols/NSE-${encodeURIComponent(sym)}/financials-earnings/`
    + '?earnings-period=FQ&revenues-period=FQ'
  );
}
