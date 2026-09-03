import { chartTimeToMs, isUnixChartTime } from './chartTime';

const DEFAULT_FUTURE_SLOTS = 64;
const DAY_MS = 24 * 60 * 60 * 1000;
const IST_OFFSET_MS = (5 * 60 + 30) * 60 * 1000;

function isWeekendUtc(ms) {
  const day = new Date(ms).getUTCDay();
  return day === 0 || day === 6;
}

function nextBusinessDayUtc(ms, days = 1) {
  let next = ms;
  let remaining = Math.max(1, days);
  while (remaining > 0) {
    next += DAY_MS;
    if (!isWeekendUtc(next)) remaining -= 1;
  }
  return next;
}

function addUtcMonths(ms, months) {
  const d = new Date(ms);
  const originalDay = d.getUTCDate();
  const originalLastDay = new Date(Date.UTC(
    d.getUTCFullYear(),
    d.getUTCMonth() + 1,
    0,
  )).getUTCDate();
  const preserveMonthEnd = originalDay === originalLastDay;
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + months);
  const lastDay = new Date(Date.UTC(
    d.getUTCFullYear(),
    d.getUTCMonth() + 1,
    0,
  )).getUTCDate();
  d.setUTCDate(preserveMonthEnd ? lastDay : Math.min(originalDay, lastDay));
  return d.getTime();
}

function next4hSessionMs(ms) {
  const ist = new Date(ms + IST_OFFSET_MS);
  const hour = ist.getUTCHours();
  const minute = ist.getUTCMinutes();
  const atOrAfterAfternoonBar = hour > 13 || (hour === 13 && minute >= 15);
  if (!atOrAfterAfternoonBar) {
    ist.setUTCHours(13, 15, 0, 0);
    return ist.getTime() - IST_OFFSET_MS;
  }

  let nextDay = nextBusinessDayUtc(Date.UTC(
    ist.getUTCFullYear(),
    ist.getUTCMonth(),
    ist.getUTCDate(),
  ));
  const next = new Date(nextDay);
  next.setUTCHours(9, 15, 0, 0);
  return next.getTime() - IST_OFFSET_MS;
}

function next30mSessionMs(ms) {
  const ist = new Date(ms + IST_OFFSET_MS);
  const hour = ist.getUTCHours();
  const minute = ist.getUTCMinutes();
  // Last session bar starts at 15:15 IST.
  const atOrAfterLastBar = hour > 15 || (hour === 15 && minute >= 15);
  if (atOrAfterLastBar) {
    const nextDay = nextBusinessDayUtc(Date.UTC(
      ist.getUTCFullYear(),
      ist.getUTCMonth(),
      ist.getUTCDate(),
    ));
    const next = new Date(nextDay);
    next.setUTCHours(9, 15, 0, 0);
    return next.getTime() - IST_OFFSET_MS;
  }
  ist.setUTCMinutes(ist.getUTCMinutes() + 30);
  return ist.getTime() - IST_OFFSET_MS;
}

function parseTimeframe(timeframe) {
  const tf = String(timeframe || '1D').trim().toUpperCase();
  const match = tf.match(/^(\d+)([DWM])$/);
  if (!match) return { count: 1, unit: 'D' };
  return { count: Number(match[1]) || 1, unit: match[2] };
}

function nextFutureMs(ms, timeframe) {
  const tf = String(timeframe || '1D').trim();
  const tfUpper = tf.toUpperCase();
  if (tfUpper === '4H') return next4hSessionMs(ms);
  if (tf === '30m' || tfUpper === '30M') return next30mSessionMs(ms);

  const { count, unit } = parseTimeframe(tfUpper);
  if (unit === 'W') return ms + count * 7 * DAY_MS;
  if (unit === 'M') return addUtcMonths(ms, count);
  return nextBusinessDayUtc(ms, count);
}

function toChartTime(ms, sampleTime) {
  if (isUnixChartTime(sampleTime)) return Math.floor(ms / 1000);
  const d = new Date(ms);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  if (
    sampleTime
    && typeof sampleTime === 'object'
    && sampleTime.year != null
    && sampleTime.month != null
    && sampleTime.day != null
  ) {
    return { year: y, month: Number(m), day: Number(day) };
  }
  return `${y}-${m}-${day}`;
}

/**
 * Add time-only points after the final candle so Lightweight Charts can render
 * its native crosshair date label in the blank projection area.
 */
export function buildFutureWhitespaceBars(bars, timeframe, count = DEFAULT_FUTURE_SLOTS) {
  if (!Array.isArray(bars) || bars.length === 0 || count <= 0) return [];
  const sampleTime = bars[bars.length - 1]?.time;
  let ms = chartTimeToMs(sampleTime);
  if (!Number.isFinite(ms)) return [];

  const out = [];
  for (let i = 0; i < count; i += 1) {
    ms = nextFutureMs(ms, timeframe);
    out.push({ time: toChartTime(ms, sampleTime) });
  }
  return out;
}

export function appendFutureWhitespace(data, futureBars) {
  if (!Array.isArray(data)) return [];
  if (!Array.isArray(futureBars) || futureBars.length === 0) return data;
  return [...data, ...futureBars];
}
