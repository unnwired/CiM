/** Portfolio entry price and P/L % display helpers. */

export function computePlPct(price, entryPrice) {
  const px = Number(price);
  const entry = Number(entryPrice);
  if (!Number.isFinite(px) || !Number.isFinite(entry) || entry <= 0) return null;
  return Math.round(((px - entry) / entry) * 10000) / 100;
}

export function formatPlPct(pct) {
  if (pct == null || !Number.isFinite(Number(pct))) return '—';
  const n = Number(pct);
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

export function plPctColor(pct) {
  if (pct == null || !Number.isFinite(Number(pct))) return 'var(--text-muted)';
  const n = Number(pct);
  if (n > 0) return 'var(--accent-green)';
  if (n < 0) return 'var(--accent-red)';
  return 'var(--text-muted)';
}
