/**
 * Charts In Motion INR / large-number display contract
 *
 * All monetary UI uses short-scale ₹M / ₹B / ₹T only — never Cr, L, or lakh/crore labels.
 * Backend market cap & TradingView revenue fields store full INR.
 * BSE quarterly_results stores crore figures — use formatINRFromCrores() for those.
 *
 * Below ₹1M: still shown in millions with 2 decimals (e.g. ₹0.85M).
 */
/** Parse UI market-cap filter to full INR. Returns null if empty, NaN if invalid. */
export function parseMarketCapInput(raw) {
  const s0 = String(raw || '').trim();
  if (!s0) return null;

  const spaced = s0.toUpperCase().replace(/,/g, '').replace(/\s+/g, ' ').trim();
  const word = spaced.match(
    /^([0-9]*\.?[0-9]+)\s*(BILLION|BILLIONS|BIL|BN|MILLION|MILLIONS|MIL|M|TRILLION|TRILLIONS|TRIL|T|CRORE|CRORES|CR)$/,
  );
  if (word) {
    const base = Number(word[1]);
    if (!Number.isFinite(base)) return NaN;
    const u = word[2];
    if (u === 'M' || u.startsWith('MIL')) return base * 1e6;
    if (u.startsWith('BIL') || u === 'BN') return base * 1e9;
    if (u.startsWith('TRIL') || u === 'T') return base * 1e12;
    if (u.startsWith('CRO')) return base * 1e7;
  }

  const compact = spaced.replace(/\s+/g, '');
  if (compact.endsWith('CR') || compact.endsWith('CRORE') || compact.endsWith('CRORES')) {
    const n = parseFloat(compact);
    return Number.isFinite(n) ? n * 1e7 : NaN;
  }
  if (compact.endsWith('B') || compact.endsWith('BN')) {
    const n = parseFloat(compact);
    return Number.isFinite(n) ? n * 1e9 : NaN;
  }
  if (compact.endsWith('M')) {
    const n = parseFloat(compact);
    return Number.isFinite(n) ? n * 1e6 : NaN;
  }
  if (compact.endsWith('T')) {
    const n = parseFloat(compact);
    return Number.isFinite(n) ? n * 1e12 : NaN;
  }

  const n = parseFloat(compact);
  if (!Number.isFinite(n)) return NaN;
  // Already full rupees when very large (e.g. 50000000000).
  if (n >= 1e8) return n;
  // 1000+ without suffix → treat as crores when parsing filter input only.
  if (n >= 1000) return n * 1e7;
  // Small bare numbers → billions (e.g. 50 → ₹50B), not millions.
  return n * 1e9;
}

export function formatMarketCap(val) {
  if (val === null || val === undefined || val === '') return '—';
  const n = Number(val);
  if (!Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}₹${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}₹${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}₹${(abs / 1e6).toFixed(2)}M`;
  return `${sign}₹${(abs / 1e6).toFixed(2)}M`;
}

/** Alias — same ₹M / ₹B / ₹T formatter for any full-INR amount (revenue, income, etc.). */
export const formatINR = formatMarketCap;

/** BSE quarterly_results amounts are stored in crores; convert to full INR before display. */
export function formatINRFromCrores(val) {
  if (val === null || val === undefined || val === '') return '—';
  const n = Number(val);
  if (!Number.isFinite(n)) return '—';
  return formatMarketCap(n * 1e7);
}

/** Share counts / volume — K / M / B / T scale without ₹ prefix (never Cr or L). */
export function formatCompactCount(val) {
  if (val === null || val === undefined || val === '') return '—';
  const n = Number(val);
  if (!Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(2)}K`;
  return `${sign}${Math.round(abs).toLocaleString('en-IN')}`;
}
