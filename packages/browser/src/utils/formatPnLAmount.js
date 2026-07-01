/**
 * P&L page monetary display — full rupees, K, or L (lakhs). No M/B/T.
 */

function signPrefix(n) {
  return n < 0 ? '-' : '';
}

/**
 * Invested / unrealized / realized amounts on the P&L page only.
 * - Below ₹1,000: full value (e.g. ₹527.75)
 * - ₹1,000 – ₹99,999: K suffix (e.g. ₹52.8K, ₹10K)
 * - ₹1,00,000+: lakhs (e.g. ₹5.27L)
 */
export function formatPnLAmount(val) {
  if (val === null || val === undefined || val === '') return '—';
  const n = Number(val);
  if (!Number.isFinite(n)) return '—';

  const abs = Math.abs(n);
  const sign = signPrefix(n);

  if (abs < 1000) {
    const frac = abs % 1 === 0 ? 0 : 2;
    return `${sign}₹${abs.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: frac })}`;
  }

  if (abs < 1e5) {
    const k = abs / 1e3;
    const digits = k >= 100 ? 0 : k >= 10 ? 1 : 2;
    const rounded = Number(k.toFixed(digits));
    const text = rounded % 1 === 0 ? String(Math.round(rounded)) : rounded.toFixed(digits);
    return `${sign}₹${text}K`;
  }

  const lakhs = abs / 1e5;
  const lDigits = lakhs >= 100 ? 1 : 2;
  return `${sign}₹${lakhs.toFixed(lDigits)}L`;
}

/** Section header totals — full rupee integer, no K/L/M abbreviation. */
export function formatPnLHeaderTotal(val) {
  const n = Math.round(Math.abs(Number(val)));
  if (!Number.isFinite(n)) return '—';
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}
