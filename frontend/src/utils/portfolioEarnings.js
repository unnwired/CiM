/** IST calendar helpers for portfolio / watchlist earnings highlights. */

const IST = 'Asia/Kolkata';

export function istTodayYmd() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: IST }).format(new Date());
}

export function daysUntilYmd(ymd, todayYmd = istTodayYmd()) {
  const parse = (s) => {
    const [y, m, d] = String(s || '').split('-').map(Number);
    if (!y || !m || !d) return null;
    return Date.UTC(y, m - 1, d);
  };
  const target = parse(ymd);
  const today = parse(todayYmd);
  if (target == null || today == null) return null;
  return Math.round((target - today) / 86400000);
}

/** Days since a past report date (0 = reported today). */
export function daysSinceYmd(ymd, todayYmd = istTodayYmd()) {
  const until = daysUntilYmd(ymd, todayYmd);
  if (until == null) return null;
  return -until;
}

/** Compact badge label, e.g. "12 Jun". */
export function formatEarningsBadgeDate(ymd) {
  const [y, m, d] = String(ymd || '').split('-').map(Number);
  if (!y || !m || !d) return '';
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: IST });
}

export const PORTFOLIO_EARNINGS_WINDOW_DAYS = 30;
export const WATCHLIST_EARNINGS_WINDOW_DAYS = 20;
export const DUAL_BEAT_WINDOW_DAYS = 10;
export const EARNINGS_PRIORITY_DEFAULT_DIR = 'asc';

/** Dual beat: both surprise % ≥ 0 (matches Earnings tab). TV often omits revenue actual. */
export function isDualBeatRow(row) {
  const eps = Number(row?.eps_surprise_pct);
  const rev = Number(row?.revenue_surprise_pct);
  if (!Number.isFinite(eps) || !Number.isFinite(rev)) return false;
  if (eps < 0 || rev < 0) return false;
  if (
    row?.eps_actual == null
    && row?.revenue_actual == null
    && eps === 0
    && rev === 0
  ) {
    return false;
  }
  return true;
}

/**
 * Row display when both beat and upcoming exist: dual beat (green) wins for up to
 * DUAL_BEAT_WINDOW_DAYS after earnings_release_date; otherwise amber "E <date>".
 */
export function resolveEarningsRowHighlight(beatInfo, upcomingInfo) {
  if (beatInfo) return { kind: 'beat', info: beatInfo };
  if (upcomingInfo) return { kind: 'upcoming', info: upcomingInfo };
  return { kind: null, info: null };
}

export function getEarningsPriorityMeta(beatInfo, upcomingInfo) {
  const highlight = resolveEarningsRowHighlight(beatInfo, upcomingInfo);
  if (highlight.kind === 'upcoming') {
    return { group: 0, dateRank: highlight.info?.days_until ?? null, highlight };
  }
  if (highlight.kind === 'beat') {
    return { group: 1, dateRank: highlight.info?.days_since_report ?? null, highlight };
  }
  return { group: 2, dateRank: null, highlight };
}

/**
 * Reorder rows so upcoming earnings are first, then beat rows, then the rest.
 * Inside each earnings group, dateRank follows dir while the original base order
 * is preserved for ties and non-highlighted rows.
 */
export function sortItemsByEarningsPriority(items, {
  getSymbol,
  isEligible = () => true,
  beatBySymbol,
  upcomingBySymbol,
  dir = EARNINGS_PRIORITY_DEFAULT_DIR,
}) {
  const factor = dir === 'desc' ? -1 : 1;
  const decorated = (items || []).map((item, index) => {
    if (!isEligible(item)) {
      return {
        item,
        index,
        meta: { group: 2, dateRank: null, highlight: { kind: null, info: null } },
      };
    }
    const sym = String(getSymbol(item) || '').trim().toUpperCase();
    const beatInfo = sym ? beatBySymbol?.get(sym) : null;
    const upcomingInfo = sym ? upcomingBySymbol?.get(sym) : null;
    return {
      item,
      index,
      meta: getEarningsPriorityMeta(beatInfo, upcomingInfo),
    };
  });
  decorated.sort((a, b) => {
    if (a.meta.group !== b.meta.group) return a.meta.group - b.meta.group;
    if (a.meta.group < 2 && a.meta.dateRank != null && b.meta.dateRank != null) {
      const cmp = a.meta.dateRank - b.meta.dateRank;
      if (cmp !== 0) return factor * cmp;
    }
    return a.index - b.index;
  });
  return decorated.map(({ item }) => item);
}

/**
 * Build Map<symbol, { earnings_release_date, days_since_report }> for dual EPS+Rev beats
 * reported within maxDaysSince (IST). Uses TradingView last FQ actuals vs estimates; API
 * should scope rows by earnings_release_date (e.g. report_window=rolling_10_days).
 */
export function buildDualBeatEarningsMap(rows, stockSymbols, maxDaysSince = DUAL_BEAT_WINDOW_DAYS) {
  const allowed = stockSymbols instanceof Set ? stockSymbols : new Set(stockSymbols);
  const map = new Map();
  for (const row of rows || []) {
    const sym = String(row?.symbol || '').trim().toUpperCase();
    if (!sym || !allowed.has(sym)) continue;
    if (!isDualBeatRow(row)) continue;
    const date = String(row?.earnings_release_date || '').trim();
    if (!date) continue;
    const daysSince = daysSinceYmd(date);
    if (daysSince == null || daysSince < 0 || daysSince > maxDaysSince) continue;
    const prev = map.get(sym);
    if (!prev || daysSince < prev.days_since_report) {
      map.set(sym, { earnings_release_date: date, days_since_report: daysSince });
    }
  }
  return map;
}

/**
 * Build Map<symbol, { earnings_release_next_date, days_until }> for listed stocks only.
 * When duplicate symbols appear, keep the nearest upcoming date.
 */
export function buildUpcomingEarningsMap(rows, stockSymbols, maxDays = PORTFOLIO_EARNINGS_WINDOW_DAYS) {
  const allowed = stockSymbols instanceof Set ? stockSymbols : new Set(stockSymbols);
  const map = new Map();
  for (const row of rows || []) {
    const sym = String(row?.symbol || '').trim().toUpperCase();
    if (!sym || !allowed.has(sym)) continue;
    const date = String(row?.earnings_release_next_date || '').trim();
    if (!date) continue;
    const daysUntil = daysUntilYmd(date);
    if (daysUntil == null || daysUntil < 0 || daysUntil > maxDays) continue;
    const prev = map.get(sym);
    if (!prev || daysUntil < prev.days_until) {
      map.set(sym, { earnings_release_next_date: date, days_until: daysUntil });
    }
  }
  return map;
}

/** @deprecated Use buildUpcomingEarningsMap */
export const buildPortfolioEarningsMap = buildUpcomingEarningsMap;

/** Upcoming earnings (amber). */
export const PORTFOLIO_EARNINGS_ROW_BG = 'rgba(210, 153, 34, 0.07)';
export const PORTFOLIO_EARNINGS_BORDER = '#d29922';
export const PORTFOLIO_EARNINGS_ROW_HOVER = 'rgba(210, 153, 34, 0.12)';
export const PORTFOLIO_EARNINGS_LABEL_COLOR = '#d29922';

/** Dual beat EPS+Rev (green) — takes priority over upcoming on the same row. */
export const DUAL_BEAT_ROW_BG = 'rgba(46, 160, 67, 0.07)';
export const DUAL_BEAT_BORDER = '#2ea043';
export const DUAL_BEAT_ROW_HOVER = 'rgba(46, 160, 67, 0.12)';
export const DUAL_BEAT_LABEL_COLOR = 'var(--accent-green)';

/** Taller row when symbol cell shows stacked earnings line (default list row is 32px). */
export const PORTFOLIO_EARNINGS_ROW_HEIGHT = 40;
