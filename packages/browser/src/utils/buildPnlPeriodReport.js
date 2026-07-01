/**
 * Period activity report for P&L right panel — buys/sells in a calendar window,
 * realized from sales in period, unrealized on open lots (scope A).
 */

import { daysInMonth, toCalendarDate } from '../components/PnLDateSelect';

export const PERIOD_DAY_ALL = 0;
export const PERIOD_MONTH_ALL = 0;

function pad2(n) {
  return String(n).padStart(2, '0');
}

export function periodBounds(year, month, day) {
  const y = Number(year);
  const m = Number(month);
  const d = Number(day);
  if (!Number.isFinite(y)) {
    return { from: null, to: null, isAllMonths: false, isAllDays: false };
  }
  if (m === PERIOD_MONTH_ALL || !Number.isFinite(m) || m < 1) {
    return {
      from: `${y}-01-01`,
      to: `${y}-12-31`,
      isAllMonths: true,
      isAllDays: true,
    };
  }
  if (d === PERIOD_DAY_ALL || !Number.isFinite(d) || d < 1) {
    const last = daysInMonth(y, m);
    return {
      from: `${y}-${pad2(m)}-01`,
      to: `${y}-${pad2(m)}-${pad2(last)}`,
      isAllMonths: false,
      isAllDays: true,
    };
  }
  const one = toCalendarDate(y, m, d);
  return { from: one, to: one, isAllMonths: false, isAllDays: false };
}

/** Inclusive range from start triple (from) through end triple (to). */
export function periodRangeBounds(start, end) {
  const s = periodBounds(start?.year, start?.month, start?.day);
  const e = periodBounds(end?.year, end?.month, end?.day);
  let from = s.from;
  let to = e.to;
  if (!from || !to) return { from: null, to: null };
  if (from > to) to = from;
  return { from, to };
}

export function clampEndTripleForward(start, end) {
  const sy = Number(start?.year);
  const sm = Number(start?.month);
  const sd = Number(start?.day);
  let ey = Number(end?.year);
  let em = Number(end?.month);
  let ed = Number(end?.day);

  if (!Number.isFinite(ey) || ey < sy) ey = sy;

  if (ey > sy) {
    return { year: ey, month: em, day: ed };
  }

  const startMonthSpecific = sm > 0;
  const endMonthSpecific = em > 0;

  if (startMonthSpecific && endMonthSpecific && em < sm) {
    em = sm;
    ed = sd;
  }

  if (startMonthSpecific && endMonthSpecific && em === sm) {
    const startDaySpecific = sd > 0;
    const endDaySpecific = ed > 0;
    if (startDaySpecific && endDaySpecific && ed < sd) {
      ed = sd;
    }
  }

  return { year: ey, month: em, day: ed };
}

export function endMinMonthForRange(start, end) {
  const sy = Number(start?.year);
  const ey = Number(end?.year);
  const sm = Number(start?.month);
  if (ey !== sy || sm <= 0) return 0;
  return sm;
}

export function endMinDayForRange(start, end) {
  const sy = Number(start?.year);
  const ey = Number(end?.year);
  const sm = Number(start?.month);
  const em = Number(end?.month);
  const sd = Number(start?.day);
  if (ey !== sy || sm <= 0 || em <= 0 || sm !== em || sd <= 0) return 0;
  return sd;
}

export function periodFilenameSuffix(year, month, day) {
  const { isAllMonths, isAllDays } = periodBounds(year, month, day);
  if (isAllMonths) return `${year}-all`;
  if (isAllDays) return `${year}-${pad2(month)}-all`;
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

export function periodRangeFilenameSuffix(start, end) {
  const { from, to } = periodRangeBounds(start, end);
  if (!from || !to) return 'range';
  if (from === to) return from;
  return `${from}_to_${to}`;
}

export function formatPeriodDateLabel(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(`${iso}T12:00:00`);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return String(iso);
  }
}

export function formatPeriodShowing(from, to) {
  if (!from || !to) return '—';
  const a = formatPeriodDateLabel(from);
  const b = formatPeriodDateLabel(to);
  if (from === to) return a;
  return `${a} – ${b}`;
}

function inRange(dateStr, from, to) {
  if (!from || !to || !dateStr) return false;
  const d = String(dateStr).slice(0, 10);
  return d >= from && d <= to;
}

function computeOpenBookSummary(openRows) {
  let total_invested = 0;
  let unrealized_pl = 0;
  let open_qty = 0;
  let unrealized_pct_weighted = 0;
  let portfolio_value = 0;

  for (const lot of openRows || []) {
    if (!lot || lot.is_placeholder) continue;
    const qty = Math.trunc(Number(lot.qty)) || 0;
    const inv = Number(lot.invested);
    const upl = Number(lot.unrealized_pl);
    const pct = Number(lot.pl_pct);
    const entry = Number(lot.entry_price);
    const price = Number(lot.price);
    open_qty += qty;
    if (Number.isFinite(inv)) {
      total_invested += inv;
    } else if (qty > 0 && Number.isFinite(entry) && entry > 0) {
      total_invested += qty * entry;
    }
    if (Number.isFinite(upl)) unrealized_pl += upl;
    if (qty > 0 && Number.isFinite(pct)) unrealized_pct_weighted += pct * qty;
    if (qty > 0 && Number.isFinite(price) && price > 0) {
      portfolio_value += qty * price;
    } else if (Number.isFinite(inv)) {
      portfolio_value += inv;
    } else if (qty > 0 && Number.isFinite(entry) && entry > 0) {
      portfolio_value += qty * entry;
    }
  }

  return {
    total_invested: Math.round(total_invested * 100) / 100,
    unrealized_pl: Math.round(unrealized_pl * 100) / 100,
    unrealized_pl_pct: open_qty > 0
      ? Math.round((unrealized_pct_weighted / open_qty) * 100) / 100
      : null,
    open_qty,
    portfolio_value: Math.round(portfolio_value * 100) / 100,
  };
}

function emptyRow(symbol) {
  return {
    symbol,
    qty_bought: 0,
    qty_sold: 0,
    invested_period: 0,
    realized_pl: 0,
    realized_cost_basis: 0,
    sale_proceeds: 0,
    unrealized_pl: 0,
    open_invested: 0,
    open_qty: 0,
    unrealized_pct_weighted: 0,
  };
}

function finalizeRow(row) {
  const realized_pl_pct = row.realized_cost_basis > 0
    ? Math.round((row.realized_pl / row.realized_cost_basis) * 10000) / 100
    : null;
  const unrealized_pl_pct = row.open_qty > 0
    ? Math.round((row.unrealized_pct_weighted / row.open_qty) * 100) / 100
    : null;
  return {
    ...row,
    invested_period: Math.round(row.invested_period * 100) / 100,
    realized_pl: Math.round(row.realized_pl * 100) / 100,
    realized_pl_pct,
    sale_proceeds: Math.round(row.sale_proceeds * 100) / 100,
    unrealized_pl: Math.round(row.unrealized_pl * 100) / 100,
    open_invested: Math.round(row.open_invested * 100) / 100,
    unrealized_pl_pct,
  };
}

export function buildPnlPeriodReport({ openRows, closedTrades, start, end, year, month, day }) {
  const periodStart = start || { year, month, day };
  const periodEnd = end || { year, month, day };
  const { from, to } = periodRangeBounds(periodStart, periodEnd);
  if (!from || !to) {
    return {
      from,
      to,
      rows: [],
      summary: {
        realized_pl: 0,
        realized_pl_pct: null,
        unrealized_pl: 0,
        unrealized_pl_pct: null,
        total_invested: 0,
        period_invested: 0,
        sale_proceeds: 0,
        portfolio_value: 0,
        realized_cost_basis: 0,
      },
    };
  }

  const bySymbol = new Map();

  function ensure(sym) {
    const s = String(sym || '').trim().toUpperCase();
    if (!s) return null;
    if (!bySymbol.has(s)) bySymbol.set(s, emptyRow(s));
    return bySymbol.get(s);
  }

  for (const row of openRows || []) {
    if (!row || row.is_placeholder) continue;
    const sym = row.symbol;
    const ed = row.entry_date;
    const qty = Math.trunc(Number(row.qty)) || 0;
    const entry = Number(row.entry_price);
    if (inRange(ed, from, to) && qty > 0 && Number.isFinite(entry) && entry > 0) {
      const r = ensure(sym);
      if (!r) continue;
      r.qty_bought += qty;
      r.invested_period += qty * entry;
    }
  }

  for (const t of closedTrades || []) {
    if (!t || typeof t !== 'object') continue;
    const sym = t.symbol;
    const ed = t.entry_date;
    const sd = t.sale_date;
    const qs = Math.trunc(Number(t.qty_sold)) || 0;
    const entry = Number(t.entry_price);
    const exit = Number(t.exit_price);
    const pl = Number(t.realized_pl);

    if (inRange(ed, from, to) && qs > 0 && Number.isFinite(entry) && entry > 0) {
      const r = ensure(sym);
      if (!r) continue;
      r.qty_bought += qs;
      r.invested_period += qs * entry;
    }
    if (inRange(sd, from, to) && qs > 0) {
      const r = ensure(sym);
      if (!r) continue;
      r.qty_sold += qs;
      if (Number.isFinite(pl)) r.realized_pl += pl;
      if (Number.isFinite(entry) && entry > 0) r.realized_cost_basis += qs * entry;
      if (Number.isFinite(exit) && exit > 0) r.sale_proceeds += qs * exit;
    }
  }

  const openBySymbol = new Map();
  for (const row of openRows || []) {
    if (!row || row.is_placeholder) continue;
    const sym = String(row.symbol || '').trim().toUpperCase();
    if (!sym) continue;
    if (!openBySymbol.has(sym)) openBySymbol.set(sym, []);
    openBySymbol.get(sym).push(row);
  }

  for (const [sym, r] of bySymbol) {
    const lots = openBySymbol.get(sym) || [];
    for (const lot of lots) {
      const qty = Math.trunc(Number(lot.qty)) || 0;
      const inv = Number(lot.invested);
      const upl = Number(lot.unrealized_pl);
      const pct = Number(lot.pl_pct);
      r.open_qty += qty;
      if (Number.isFinite(inv)) r.open_invested += inv;
      if (Number.isFinite(upl)) r.unrealized_pl += upl;
      if (qty > 0 && Number.isFinite(pct)) r.unrealized_pct_weighted += pct * qty;
    }
  }

  const rows = [...bySymbol.values()]
    .map(finalizeRow)
    .filter((r) => r.qty_bought > 0 || r.qty_sold > 0)
    .sort((a, b) => a.symbol.localeCompare(b.symbol));

  let realized_pl = 0;
  let realized_cost_basis = 0;
  let sale_proceeds = 0;
  let period_invested = 0;

  for (const r of rows) {
    realized_pl += r.realized_pl;
    realized_cost_basis += r.realized_cost_basis;
    sale_proceeds += r.sale_proceeds;
    period_invested += r.invested_period;
  }

  const openBook = computeOpenBookSummary(openRows);

  const summary = {
    realized_pl: Math.round(realized_pl * 100) / 100,
    realized_pl_pct: realized_cost_basis > 0
      ? Math.round((realized_pl / realized_cost_basis) * 10000) / 100
      : null,
    unrealized_pl: openBook.unrealized_pl,
    unrealized_pl_pct: openBook.unrealized_pl_pct,
    total_invested: openBook.total_invested,
    period_invested: Math.round(period_invested * 100) / 100,
    sale_proceeds: Math.round(sale_proceeds * 100) / 100,
    portfolio_value: openBook.portfolio_value,
    realized_cost_basis: Math.round(realized_cost_basis * 100) / 100,
    open_qty: openBook.open_qty,
  };

  return { from, to, rows, summary };
}

function csvCell(val) {
  if (val == null || val === '') return '';
  const s = String(val);
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function exportPeriodReportCsv(report, { start, end, year, month, day, availableCash }) {
  const { from, to, rows, summary } = report;
  const periodStart = start || { year, month, day };
  const periodEnd = end || { year, month, day };
  const lines = [];
  lines.push(`Period,${from} to ${to}`);
  lines.push(`Realized P/L,${summary.realized_pl},${summary.realized_pl_pct ?? ''}`);
  lines.push(`Unrealized P/L,${summary.unrealized_pl},${summary.unrealized_pl_pct ?? ''}`);
  lines.push(`Total invested (open book),${summary.total_invested}`);
  lines.push(`Portfolio value,${summary.portfolio_value}`);
  const cash = Number.isFinite(Number(availableCash)) ? Number(availableCash) : 0;
  lines.push(`Available cash,${cash}`);
  lines.push('');
  lines.push([
    'Symbol', 'Bought', 'Sold', 'Invested', 'Realized P/L', 'Realized %',
    'Unrealized P/L', 'Unrealized %', 'Open Qty',
  ].join(','));
  for (const r of rows) {
    lines.push([
      r.symbol,
      r.qty_bought,
      r.qty_sold,
      r.invested_period,
      r.realized_pl,
      r.realized_pl_pct ?? '',
      r.unrealized_pl,
      r.unrealized_pl_pct ?? '',
      r.open_qty,
    ].map(csvCell).join(','));
  }
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `pnl-period-${periodRangeFilenameSuffix(periodStart, periodEnd)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
