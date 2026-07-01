/** Shared earnings table + quarterly expand panel layout (upcoming is the reference). */

export const EARNINGS_UPCOMING_COLUMN_COUNT = 8;
export const EARNINGS_REPORTED_COLUMN_COUNT = 12;

/** Fixed column widths so reported/upcoming tables and expand panels align. */
export const EARNINGS_COL_WIDTH = {
  symbol: 100,
  marketCap: 76,
  price: 76,
  changePct: 62,
  date: 92,
  eps: 68,
  revenue: 76,
  surprise: 68,
};

const UPCOMING_WIDTH_SUM =
  EARNINGS_COL_WIDTH.symbol
  + EARNINGS_COL_WIDTH.marketCap
  + EARNINGS_COL_WIDTH.price
  + EARNINGS_COL_WIDTH.changePct * 2
  + EARNINGS_COL_WIDTH.date
  + EARNINGS_COL_WIDTH.eps
  + EARNINGS_COL_WIDTH.revenue;

const REPORTED_EXTRA_SUM =
  EARNINGS_COL_WIDTH.eps * 2
  + EARNINGS_COL_WIDTH.surprise
  + EARNINGS_COL_WIDTH.revenue * 2
  + EARNINGS_COL_WIDTH.surprise;

export const EARNINGS_UPCOMING_TABLE_MIN_WIDTH_PX = UPCOMING_WIDTH_SUM;
export const EARNINGS_REPORTED_TABLE_MIN_WIDTH_PX = UPCOMING_WIDTH_SUM + REPORTED_EXTRA_SUM;

/** Col widths for <colgroup> — upcoming (8 cols). */
export const UPCOMING_COLGROUP = [
  EARNINGS_COL_WIDTH.symbol,
  EARNINGS_COL_WIDTH.marketCap,
  EARNINGS_COL_WIDTH.price,
  EARNINGS_COL_WIDTH.changePct,
  EARNINGS_COL_WIDTH.changePct,
  EARNINGS_COL_WIDTH.date,
  EARNINGS_COL_WIDTH.eps,
  EARNINGS_COL_WIDTH.revenue,
];

/** Col widths for <colgroup> — reported (12 cols). */
export const REPORTED_COLGROUP = [
  ...UPCOMING_COLGROUP.slice(0, 6),
  EARNINGS_COL_WIDTH.eps,
  EARNINGS_COL_WIDTH.eps,
  EARNINGS_COL_WIDTH.surprise,
  EARNINGS_COL_WIDTH.revenue,
  EARNINGS_COL_WIDTH.revenue,
  EARNINGS_COL_WIDTH.surprise,
];

/** Profile column width in the quarterly expand row (table takes the rest). */
export const EARNINGS_QUARTERLY_PROFILE_WIDTH_PX = 600;

/** Portfolio earnings modal: profile −⅓, quarterly table gains the freed width via flex. */
export const PORTFOLIO_EARNINGS_MODAL_PROFILE_WIDTH_PX = Math.round(
  EARNINGS_QUARTERLY_PROFILE_WIDTH_PX * (2 / 3),
);

/** Wider popup so the quarterly table shows one more recent quarter without growing the profile pane. */
export const PORTFOLIO_EARNINGS_MODAL_WIDTH_PX = 1320;

export function earningsTableMinWidthPx(mode) {
  return mode === 'reported'
    ? EARNINGS_REPORTED_TABLE_MIN_WIDTH_PX
    : EARNINGS_UPCOMING_TABLE_MIN_WIDTH_PX;
}
