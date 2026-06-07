import {
  timeToX,
  priceToY,
  clipSegmentToRect,
  rayClipFromP1ThroughP2,
  lineTpFromTwoPoints,
  priceAtTime,
  fibPrices,
} from './drawingGeometry';
import { FIB_LEVELS } from './drawingTypes';

/**
 * Build drawable polylines for a drawing (pixel coords).
 * @returns {{ type: 'line', x1: number, y1: number, x2: number, y2: number, drawingId: string, kind: string }[]}
 */
export function segmentsForDrawing(d, chart, series, w, h) {
  const out = [];
  const id = d.id;
  const pts = d.points || [];
  if (!chart || !series || w <= 0 || h <= 0) return out;

  const pushSeg = (x1, y1, x2, y2, kind) => {
    if (x1 == null || y1 == null || x2 == null || y2 == null) return;
    const c = clipSegmentToRect(x1, y1, x2, y2, w, h);
    if (!c) return;
    out.push({ type: 'line', ...c, drawingId: id, kind });
  };

  if (d.type === 'h_line' && pts[0]) {
    const y = priceToY(series, pts[0].price);
    if (y == null) return out;
    pushSeg(0, y, w, y, 'h');
    return out;
  }

  if (d.type === 'v_line' && pts[0]) {
    const x = timeToX(chart, series, pts[0].time);
    if (x == null) return out;
    pushSeg(x, 0, x, h, 'v');
    return out;
  }

  if (d.type === 'cross' && pts[0]) {
    const x = timeToX(chart, series, pts[0].time);
    const y = priceToY(series, pts[0].price);
    if (x != null && y != null) {
      pushSeg(0, y, w, y, 'h');
      pushSeg(x, 0, x, h, 'v');
    }
    return out;
  }

  if (d.type === 'trendline' && pts.length >= 2) {
    const x1 = timeToX(chart, series, pts[0].time);
    const y1 = priceToY(series, pts[0].price);
    const x2 = timeToX(chart, series, pts[1].time);
    const y2 = priceToY(series, pts[1].price);
    pushSeg(x1, y1, x2, y2, 't');
    return out;
  }

  if (d.type === 'ray' && pts.length >= 2) {
    const x1 = timeToX(chart, series, pts[0].time);
    const y1 = priceToY(series, pts[0].price);
    const x2 = timeToX(chart, series, pts[1].time);
    const y2 = priceToY(series, pts[1].price);
    const ray = rayClipFromP1ThroughP2(x1, y1, x2, y2, w, h);
    if (ray) out.push({ type: 'line', ...ray, drawingId: id, kind: 'r' });
    return out;
  }

  if (d.type === 'h_ray' && pts.length >= 2) {
    const y = priceToY(series, pts[0].price);
    const x0 = timeToX(chart, series, pts[1].time);
    if (y == null || x0 == null) return out;
    pushSeg(x0, y, w, y, 'hr');
    return out;
  }

  if (d.type === 'channel' && pts.length >= 3) {
    const A = pts[0], B = pts[1], C = pts[2];
    const x1 = timeToX(chart, series, A.time);
    const y1 = priceToY(series, A.price);
    const x2 = timeToX(chart, series, B.time);
    const y2 = priceToY(series, B.price);
    pushSeg(x1, y1, x2, y2, 'c1');
    const line = lineTpFromTwoPoints(A.time, A.price, B.time, B.price);
    if (!line) return out;
    const pC = priceAtTime(line, C.time);
    if (pC == null) return out;
    const offset = C.price - pC;
    const pA2 = A.price + offset;
    const pB2 = B.price + offset;
    const y1b = priceToY(series, pA2);
    const y2b = priceToY(series, pB2);
    pushSeg(x1, y1b, x2, y2b, 'c2');
    return out;
  }

  if (d.type === 'fib' && pts.length >= 2) {
    const tA = pts[0].time;
    const tB = pts[1].time;
    const pA = pts[0].price;
    const pB = pts[1].price;
    const xL = timeToX(chart, series, tA);
    const xR = timeToX(chart, series, tB);
    if (xL == null || xR == null) return out;
    const xa = Math.min(xL, xR);
    const xb = Math.max(xL, xR);
    const levels = fibPrices(pA, pB);
    levels.forEach((price, i) => {
      const y = priceToY(series, price);
      if (y == null) return;
      pushSeg(xa, y, xb, y, `f${FIB_LEVELS[i]}`);
    });
    return out;
  }

  if (d.type === 'price_range' && pts.length >= 2) {
    const x1 = timeToX(chart, series, pts[0].time);
    const y1 = priceToY(series, pts[0].price);
    const x2 = timeToX(chart, series, pts[1].time);
    const y2 = priceToY(series, pts[1].price);
    if (x1 == null || y1 == null || x2 == null || y2 == null) return out;
    const xa = Math.min(x1, x2);
    const xb = Math.max(x1, x2);
    const yTop = Math.min(y1, y2);
    const yBottom = Math.max(y1, y2);
    const xMid = xa + (xb - xa) / 2;
    const p1 = Number(pts[0].price);
    const p2 = Number(pts[1].price);
    const isUp = p2 >= p1;
    const arrowHead = 8;
    const arrowHalf = 4;
    pushSeg(xa, yTop, xb, yTop, 'pr_top');
    pushSeg(xa, yBottom, xb, yBottom, 'pr_bottom');
    if (isUp) {
      pushSeg(xMid, yBottom, xMid, yTop, 'pr_mid');
      pushSeg(xMid, yTop, xMid - arrowHalf, yTop + arrowHead, 'pr_head_l');
      pushSeg(xMid, yTop, xMid + arrowHalf, yTop + arrowHead, 'pr_head_r');
    } else {
      pushSeg(xMid, yTop, xMid, yBottom, 'pr_mid');
      pushSeg(xMid, yBottom, xMid - arrowHalf, yBottom - arrowHead, 'pr_head_l');
      pushSeg(xMid, yBottom, xMid + arrowHalf, yBottom - arrowHead, 'pr_head_r');
    }
    return out;
  }

  return out;
}

export function handlePositions(d, chart, series) {
  const pts = d.points || [];
  const h = [];
  pts.forEach((p, idx) => {
    const x = timeToX(chart, series, p.time);
    const y = priceToY(series, p.price);
    if (x != null && y != null) h.push({ x, y, idx });
  });
  return h;
}

/** Midpoints on fib for hit — use horizontal bands near each level */
export function hitSegmentsForDrawing(d, chart, series, w, h) {
  const segs = segmentsForDrawing(d, chart, series, w, h);
  return segs.filter(s => s.type === 'line').map(s => ({
    x1: s.x1, y1: s.y1, x2: s.x2, y2: s.y2, drawingId: s.drawingId, kind: s.kind,
  }));
}
