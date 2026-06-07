function distPointSeg(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  if (len2 < 1e-12) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * dx + (py - y1) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  const qx = x1 + t * dx;
  const qy = y1 + t * dy;
  return Math.hypot(px - qx, py - qy);
}

/**
 * @param {number} px
 * @param {number} py
 * @param {{ x1: number, y1: number, x2: number, y2: number }[]} segments
 * @param {number} threshold
 */
export function hitTestSegments(px, py, segments, threshold = 8) {
  let best = -1;
  let bestD = Infinity;
  segments.forEach((seg, i) => {
    const d = distPointSeg(px, py, seg.x1, seg.y1, seg.x2, seg.y2);
    if (d < bestD && d <= threshold) {
      bestD = d;
      best = i;
    }
  });
  return best;
}
