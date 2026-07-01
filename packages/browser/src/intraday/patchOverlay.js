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

/** Screener / portfolio table row (Symbol, Price, Change %). */
export function applyPatchToStockRow(row, snap) {
  if (!row || !snap) return row;
  const px = snapshotPrice(snap);
  const chg = snapshotChangePct(snap);
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

/** Potential swings / generic { price, change_pct, symbol }. */
export function applyPatchToGenericQuoteRow(row, snap) {
  if (!row || !snap) return row;
  const px = snapshotPrice(snap);
  const chg = snapshotChangePct(snap);
  if (px == null && chg == null) return row;
  const out = { ...row };
  if (px != null) out.price = px;
  if (chg != null) out.change_pct = chg;
  return out;
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
