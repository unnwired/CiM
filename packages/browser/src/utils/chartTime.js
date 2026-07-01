/** True when chart bar `time` is UTCTimestamp (seconds), not a YYYY-MM-DD string. */
export function isUnixChartTime(t) {
  if (typeof t === 'number' && Number.isFinite(t)) return t > 1e8;
  if (typeof t === 'string' && /^\d{9,11}$/.test(t.trim())) return true;
  return false;
}

/** Milliseconds since epoch for LW chart times (daily string, BusinessDay, or unix seconds). */
export function chartTimeToMs(t) {
  if (t == null) return NaN;
  if (typeof t === 'number' && Number.isFinite(t)) {
    return t > 1e12 ? t : t * 1000;
  }
  if (typeof t === 'object' && t.year != null && t.month != null && t.day != null) {
    return Date.UTC(t.year, t.month - 1, t.day);
  }
  const s = String(t).trim();
  if (/^\d{9,11}$/.test(s)) return Number(s) * 1000;
  const parsed = Date.parse(s);
  return Number.isFinite(parsed) ? parsed : NaN;
}

/** Normalize for equality / map keys (daily → YYYY-MM-DD, unix → numeric string). */
export function normalizeChartTimeKey(t) {
  if (t == null) return '';
  if (typeof t === 'object' && t.year != null && t.month != null && t.day != null) {
    const m = String(t.month).padStart(2, '0');
    const d = String(t.day).padStart(2, '0');
    return `${t.year}-${m}-${d}`;
  }
  if (isUnixChartTime(t)) return String(typeof t === 'number' ? t : Number(t));
  const s = String(t);
  return s.length >= 10 ? s.slice(0, 10) : s;
}

export function formatChartAxisLabel(time) {
  const ms = chartTimeToMs(time);
  if (!Number.isFinite(ms)) return '';
  const d = new Date(ms);
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const day = days[d.getUTCDay()];
  const date = d.getUTCDate();
  const month = months[d.getUTCMonth()];
  const year = String(d.getUTCFullYear()).slice(-2);
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  if (isUnixChartTime(time)) {
    return `${day} ${date} ${month} '${year} ${hh}:${mm}`;
  }
  return `${day} ${date} ${month} '${year}`;
}

export function chartTimeDiffMs(a, b) {
  return Math.abs(chartTimeToMs(a) - chartTimeToMs(b));
}
