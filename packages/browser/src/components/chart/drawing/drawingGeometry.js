import { FIB_LEVELS } from './drawingTypes';

export function timeToNum(t) {
  if (t == null) return NaN;
  if (typeof t === 'object' && t.__logical != null) {
    const n = Number(t.__logical);
    return Number.isFinite(n) ? n : NaN;
  }
  if (typeof t === 'number') return t;
  if (typeof t === 'string') return new Date(t + (t.length <= 10 ? 'T12:00:00Z' : '')).getTime();
  if (typeof t === 'object' && t.year != null) {
    return Date.UTC(t.year, (t.month || 1) - 1, t.day || 1);
  }
  return NaN;
}

/** @param {import('lightweight-charts').IChartApi} chart */
export function timeToX(chart, series, t) {
  if (!chart || !series || t == null) return null;
  try {
    if (typeof t === 'object' && t.__logical != null) {
      const xFromLogical = chart.timeScale().logicalToCoordinate(Number(t.__logical));
      return xFromLogical == null ? null : xFromLogical;
    }
    const x = chart.timeScale().timeToCoordinate(t);
    return x == null ? null : x;
  } catch {
    return null;
  }
}

/** @param {import('lightweight-charts').ISeriesApi} series */
export function priceToY(series, price) {
  if (!series || price == null || !Number.isFinite(price)) return null;
  try {
    return series.priceToCoordinate(price);
  } catch {
    return null;
  }
}

/** @param {import('lightweight-charts').IChartApi} chart */
export function xToTime(chart, x) {
  if (!chart) return null;
  try {
    const ts = chart.timeScale();
    const t = ts.coordinateToTime(x);
    if (t != null) return t;
    const logical = ts.coordinateToLogical(x);
    if (logical == null || Number.isNaN(logical)) return null;
    return { __logical: logical };
  } catch {
    return null;
  }
}

/** @param {import('lightweight-charts').ISeriesApi} series */
export function yToPrice(series, y) {
  if (!series) return null;
  try {
    return series.coordinateToPrice(y);
  } catch {
    return null;
  }
}

export function clipSegmentToRect(x1, y1, x2, y2, w, h) {
  // Cohen–Sutherland clip
  const INSIDE = 0, LEFT = 1, RIGHT = 2, BOTTOM = 4, TOP = 8;
  const region = (x, y) => {
    let c = INSIDE;
    if (x < 0) c |= LEFT;
    else if (x > w) c |= RIGHT;
    if (y < 0) c |= TOP;
    else if (y > h) c |= BOTTOM;
    return c;
  };
  let x1c = x1, y1c = y1, x2c = x2, y2c = y2;
  let r1 = region(x1c, y1c), r2 = region(x2c, y2c);
  let guard = 0;
  while (guard++ < 10 && (r1 | r2) !== 0) {
    if ((r1 & r2) !== 0) return null;
    const r = r1 !== 0 ? r1 : r2;
    let x = 0, y = 0;
    if (r & TOP) {
      x = x1c + ((x2c - x1c) * (0 - y1c)) / (y2c - y1c || 1e-9);
      y = 0;
    } else if (r & BOTTOM) {
      x = x1c + ((x2c - x1c) * (h - y1c)) / (y2c - y1c || 1e-9);
      y = h;
    } else if (r & RIGHT) {
      y = y1c + ((y2c - y1c) * (w - x1c)) / (x2c - x1c || 1e-9);
      x = w;
    } else if (r & LEFT) {
      y = y1c + ((y2c - y1c) * (0 - x1c)) / (x2c - x1c || 1e-9);
      x = 0;
    }
    if (r === r1) {
      x1c = x; y1c = y; r1 = region(x1c, y1c);
    } else {
      x2c = x; y2c = y; r2 = region(x2c, y2c);
    }
  }
  if ((r1 | r2) !== 0) return null;
  return { x1: x1c, y1: y1c, x2: x2c, y2: y2c };
}

/** Line through (t1,p1)-(t2,p2) in time-num space: price = m * t + b */
export function lineTpFromTwoPoints(t1, p1, t2, p2) {
  const u1 = timeToNum(t1);
  const u2 = timeToNum(t2);
  if (!Number.isFinite(u1) || !Number.isFinite(u2) || Math.abs(u2 - u1) < 1e-6) return null;
  const m = (p2 - p1) / (u2 - u1);
  const b = p1 - m * u1;
  return { m, b };
}

export function priceAtTime(line, t) {
  if (!line) return null;
  const u = timeToNum(t);
  if (!Number.isFinite(u)) return null;
  return line.m * u + line.b;
}

export function fibPrices(pHigh, pLow) {
  const hi = Math.max(pHigh, pLow);
  const lo = Math.min(pHigh, pLow);
  const rng = hi - lo;
  return FIB_LEVELS.map(r => hi - rng * r);
}

/** Ray from p1 through p2, infinite beyond p2; return segment clipped to [0,w]x[0,h] on the p2 side only */
export function rayClipFromP1ThroughP2(x1, y1, x2, y2, w, h) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) return null;
  // Far point in direction p1 -> p2
  const farT = Math.max(w, h) * 4;
  const len = Math.hypot(dx, dy);
  const ux = (dx / len) * farT;
  const uy = (dy / len) * farT;
  const x3 = x2 + ux;
  const y3 = y2 + uy;
  return clipSegmentToRect(x1, y1, x3, y3, w, h);
}
