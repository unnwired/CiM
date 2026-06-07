/** Shared Market Map tile colors (grid + treemap). */

export const EARNINGS_PLUS_COLOR = '#d29922';

export const MM_TEXT_PRIMARY = '#FFFFFF';
export const MM_TEXT_SECONDARY = '#C9C9C9';
export const MM_RED_BG_MID = '#E14A44';
export const MM_RED_BG_STRONG = '#BD413C';
export const MM_RED_TILE_PCT = '#7B140F';

export function tileBackground(pct) {
  if (pct == null || !Number.isFinite(Number(pct))) return 'var(--bg-tertiary)';
  const p = Number(pct);
  if (p >= 3) return 'rgba(46, 160, 67, 0.9)';
  if (p >= 2) return 'rgba(46, 160, 67, 0.75)';
  if (p >= 1) return 'rgba(46, 160, 67, 0.55)';
  if (p >= 0.25) return 'rgba(46, 160, 67, 0.35)';
  if (p > -0.25) return 'var(--bg-tertiary)';
  if (p > -1) return 'rgba(248, 81, 73, 0.35)';
  if (p > -2) return MM_RED_BG_MID;
  return MM_RED_BG_STRONG;
}

export function tilePctColor(pct, backgroundColor) {
  if (backgroundColor === MM_RED_BG_MID || backgroundColor === MM_RED_BG_STRONG) {
    return MM_RED_TILE_PCT;
  }
  if (pct == null || !Number.isFinite(Number(pct))) return 'var(--text-muted)';
  const p = Number(pct);
  if (p > 0) return 'var(--accent-green)';
  if (p < 0) return 'var(--accent-red)';
  return 'var(--text-muted)';
}

export function treemapNodeValue(stock) {
  const m = Number(stock?.market_cap);
  if (Number.isFinite(m) && m > 0) return m;
  return 1;
}
