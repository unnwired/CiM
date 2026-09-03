/** Pure helpers — overlay session quotes onto server rows (never writes shared DB). */

import { computePlPct } from '../utils/portfolioEntry';

/** Timeframes that receive live price overlay after Refresh prices (1D = full session candle). */
export function isIntradayLiveTimeframe(timeframe) {
  const tf = String(timeframe || '').trim().toUpperCase();
  return tf === '1D' || tf === '4H' || tf === '1W' || tf === '2W';
}

function finite(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function snapshotChangePct(snap) {
  if (!snap) return null;
  const chg = finite(snap.change_pct);
  if (chg != null) return Math.round(chg * 100) / 100;
  const px = finite(snap.price);
  const prev = finite(snap.previous_close);
  if (px == null || prev == null || prev <= 0) return null;
  return Math.round(((px - prev) / prev) * 10000) / 100;
}

export function snapshotPrice(snap) {
  const px = finite(snap?.price);
  return px != null ? Math.round(px * 100) / 100 : null;
}

/** Prefer live 1D % over stale server 0% (same rule as chart header). */
export function resolveStockRowDayChangePct(row, snap) {
  const live = snapshotChangePct(snap);
  if (live == null) return finite(row?.['Change %']);
  const official = finite(row?.['Change %']);
  if (official != null && Math.abs(official) < 0.005 && Math.abs(live) >= 0.005) {
    return live;
  }
  return live;
}

/** Screener / portfolio table row (Symbol, Price, Change %). */
export function applyPatchToStockRow(row, snap) {
  if (!row || !snap) return row;
  const px = snapshotPrice(snap);
  const chg = resolveStockRowDayChangePct(row, snap);
  if (px == null && chg == null) return row;
  const out = { ...row };
  if (px != null) out.Price = px;
  if (chg != null) out['Change %'] = chg;
  return out;
}

/** Index list row (symbol, last_price, change_pct). */
export function applyPatchToIndexRow(row, snap) {
  if (!row || !snap) return row;
  const px = snapshotPrice(snap);
  const chg = snapshotChangePct(snap);
  if (px == null && chg == null) return row;
  const out = { ...row };
  if (px != null) out.last_price = px;
  if (chg != null) out.change_pct = chg;
  return out;
}

/** Market movers row (symbol, price, change_pct). */
export function applyPatchToMoversRow(row, snap) {
  if (!row || !snap) return row;
  const px = snapshotPrice(snap);
  const chg = snapshotChangePct(snap);
  if (px == null && chg == null) return row;
  const out = { ...row };
  if (px != null) out.price = px;
  if (chg != null) out.change_pct = chg;
  return out;
}

/** Market map constituent (symbol, last_price, change_pct). */
export function applyPatchToMapStock(row, snap) {
  if (!row || !snap) return row;
  const px = snapshotPrice(snap);
  const chg = snapshotChangePct(snap);
  if (px == null && chg == null) return row;
  const out = { ...row };
  if (px != null) out.last_price = px;
  if (chg != null) out.change_pct = chg;
  return out;
}

/** Market map index summary row (index_change_pct on index symbol). */
export function applyPatchToMapIndexSummary(row, snap) {
  if (!row || !snap) return row;
  const chg = snapshotChangePct(snap);
  if (chg == null) return row;
  return { ...row, index_change_pct: chg };
}

/** Potential swings / constituents / generic { price, last_price, change_pct, symbol }. */
export function applyPatchToGenericQuoteRow(row, snap) {
  if (!row || !snap) return row;
  const px = snapshotPrice(snap);
  const chg = snapshotChangePct(snap);
  if (px == null && chg == null) return row;
  const out = { ...row };
  if (px != null) {
    out.price = px;
    out.last_price = px;
  }
  if (chg != null) out.change_pct = chg;
  return out;
}

/**
 * Earnings beats row — Upstox live price + 1D %.
 * 1M % is derived from live LTP vs month_ref_close captured at fetch time (no TradingView).
 */
export function applyPatchToEarningsRow(row, snap) {
  if (!row || !snap) return row;
  const px = snapshotPrice(snap);
  const chg = snapshotChangePct(snap);
  if (px == null && chg == null) return row;
  const out = { ...row };
  if (px != null) out.price = px;
  if (chg != null) out.change_1d_pct = chg;
  const ref = finite(row.month_ref_close);
  if (px != null && ref != null && ref > 0) {
    out.change_1m_pct = Math.round(((px - ref) / ref) * 10000) / 100;
  }
  return out;
}

/** Capture a fixed month reference close from fetch-time price + 1M % (for live 1M derivation). */
export function monthRefCloseFromRow(row) {
  const px = finite(row?.price);
  const m1 = finite(row?.change_1m_pct);
  if (px == null || px <= 0 || m1 == null) return null;
  const denom = 1 + m1 / 100;
  if (!Number.isFinite(denom) || Math.abs(denom) < 1e-9) return null;
  return Math.round((px / denom) * 100) / 100;
}

export function attachEarningsMonthRefClose(row) {
  if (!row || typeof row !== 'object') return row;
  const ref = monthRefCloseFromRow(row);
  if (ref == null) return row;
  return { ...row, month_ref_close: ref };
}

/** P&L open row — price, 1D %, unrealized P/L and P/L % from session quote. */
export function applyPatchToPnlRow(row, snap) {
  if (!row || !snap) return row;
  const px = snapshotPrice(snap);
  const chg = snapshotChangePct(snap);
  if (px == null && chg == null) return row;
  const out = { ...row };
  if (px != null) {
    out.price = px;
    const entryN = Number(row.entry_price);
    const qtyN = Number(row.qty);
    if (Number.isFinite(entryN) && Number.isFinite(qtyN) && qtyN > 0) {
      out.pl_pct = computePlPct(px, entryN);
      out.unrealized_pl = Math.round(qtyN * (px - entryN) * 100) / 100;
      out.invested = Math.round(entryN * qtyN * 100) / 100;
    }
    out.session_price = true;
  }
  if (chg != null) out.change_1d = chg;
  return out;
}

export function overlayRows(rows, getSymbol, applyFn, getSnapshot) {
  if (!rows?.length || !getSnapshot) return rows || [];
  return rows.map((row) => {
    const sym = String(getSymbol(row) || '').trim().toUpperCase();
    if (!sym) return row;
    const snap = getSnapshot(sym);
    return snap ? applyFn(row, snap) : row;
  });
}
