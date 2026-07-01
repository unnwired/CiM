/**
 * StochRSI filter preview — synthetic %K history with real K/D smoothing, tail-solved per condition.
 * Display ~28 points (~1y of 2W periods) spanning full plot width for visual depth.
 */

export const PREVIEW_VIEW_W = 480;
export const PREVIEW_PAD_L = 8;
export const PREVIEW_PAD_R = 8;
export const PREVIEW_PLOT_W = PREVIEW_VIEW_W - PREVIEW_PAD_L - PREVIEW_PAD_R;
export const PREVIEW_VIEW_H = 128;
export const PREVIEW_CHART_TOP = 8;
export const PREVIEW_CHART_H = 92;
export const PREVIEW_Y_PAD = 8;

/** ~26–28 two-week periods ≈ one year of macro swings visible in the panel. */
export const POINT_COUNT = 28;
export const PREVIEW_SLOT_PX = Math.floor(PREVIEW_PLOT_W / Math.max(1, POINT_COUNT - 1));

export const K_SMOOTH = 3;
export const D_SMOOTH = 3;
const HOLD_POINTS = 8;

const Y_MIN = PREVIEW_CHART_TOP + PREVIEW_Y_PAD;
const Y_MAX = PREVIEW_CHART_TOP + PREVIEW_CHART_H - PREVIEW_Y_PAD;

export function parsePct(value) {
  const n = parseFloat(String(value));
  return Number.isFinite(n) && n > 0 ? n : 5;
}

export function parseTargetValue(value, fallback = 80) {
  const n = parseFloat(String(value));
  if (!Number.isFinite(n)) return fallback;
  return Math.max(0, Math.min(100, n));
}

export function clampVal(v) {
  return Math.max(2, Math.min(98, v));
}

export function pointX(index, count = POINT_COUNT) {
  if (count <= 1) return PREVIEW_PAD_L;
  return PREVIEW_PAD_L + (index / (count - 1)) * PREVIEW_PLOT_W;
}

function clampY(y) {
  return Math.min(Y_MAX, Math.max(Y_MIN, y));
}

/** Map StochRSI value (0–100) → SVG y inside padded chart. */
export function valToY(v) {
  const norm = Math.max(0, Math.min(100, v));
  const t = 1 - norm / 100;
  return clampY(PREVIEW_CHART_TOP + PREVIEW_Y_PAD + t * (PREVIEW_CHART_H - 2 * PREVIEW_Y_PAD));
}

export function evalCondition(condition, src, srcPrev, tgt, tgtPrev, pct) {
  switch (condition) {
    case 'above':
      return src > tgt;
    case 'above_eq':
      return src >= tgt;
    case 'below':
      return src < tgt;
    case 'below_eq':
      return src <= tgt;
    case 'crosses_up':
      return srcPrev != null && tgtPrev != null && srcPrev <= tgtPrev && src > tgt;
    case 'crosses_down':
      return srcPrev != null && tgtPrev != null && srcPrev >= tgtPrev && src < tgt;
    case 'above_pct':
      return tgt !== 0 && src > tgt * (1 + pct / 100);
    case 'below_pct':
      return tgt !== 0 && src < tgt * (1 - pct / 100);
    default:
      return true;
  }
}

function sma(series, period) {
  return series.map((_, i) => {
    const start = Math.max(0, i - period + 1);
    const slice = series.slice(start, i + 1);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

/** %D = double-smoothed %K (K smooth 3, D smooth 3). */
export function deriveDFromK(k) {
  const kSmooth = sma(k, K_SMOOTH);
  return sma(kSmooth, D_SMOOTH);
}

function addKJitter(k, amount = 2.4) {
  return k.map((v, i) => {
    const wobble = amount * Math.sin(i * 1.65 + 0.4) * Math.sin(i * 0.31 + 1.1);
    const fade = i >= k.length - HOLD_POINTS ? 0 : 1;
    return clampVal(v + wobble * fade);
  });
}

/** Multi-cycle %K walk — long + mid + short swings for chart depth. */
function classicKWave(n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const t = i;
    const longCycle = Math.sin(t * (2 * Math.PI / 26)) * 30;
    const midCycle = Math.sin(t * 0.38 + 0.2) * 12;
    const shortCycle = Math.sin(t * 0.15 + 0.5) * 7;
    const fine = 4 * Math.sin((2 * Math.PI * 11 * i) / Math.max(1, n - 1));
    out.push(clampVal(50 + longCycle + midCycle + shortCycle + fine));
  }
  return out;
}

function bullishEndKWave(n) {
  const base = classicKWave(n);
  const riseFrom = Math.max(0, n - 10);
  for (let i = riseFrom; i < n; i++) {
    const t = (i - riseFrom) / Math.max(1, n - 1 - riseFrom);
    base[i] = clampVal(22 + t * 68 + 6 * Math.sin(t * Math.PI));
  }
  return base;
}

function bearishEndKWave(n) {
  const base = classicKWave(n);
  const fallFrom = Math.max(0, n - 10);
  for (let i = fallFrom; i < n; i++) {
    const t = (i - fallFrom) / Math.max(1, n - 1 - fallFrom);
    base[i] = clampVal(78 - t * 68 - 4 * Math.sin(t * Math.PI));
  }
  return base;
}

function kCrossUpValue(n, targetValue) {
  const base = classicKWave(n);
  const p = n - 1;
  base[p - 1] = clampVal(Math.min(base[p - 1], targetValue - 2));
  base[p] = clampVal(targetValue + 8);
  return base;
}

function kCrossDownValue(n, targetValue) {
  const base = classicKWave(n);
  const p = n - 1;
  base[p - 1] = clampVal(Math.max(base[p - 1], targetValue + 2));
  base[p] = clampVal(targetValue - 8);
  return base;
}

function crossUpEndKWave(n) {
  const base = classicKWave(n);
  const p = n - 1;
  base[p - 1] = clampVal(Math.min(base[p - 1], 45));
  base[p] = clampVal(base[p - 1] + 14);
  return base;
}

function crossDownEndKWave(n) {
  const base = classicKWave(n);
  const p = n - 1;
  base[p - 1] = clampVal(Math.max(base[p - 1], 55));
  base[p] = clampVal(base[p - 1] - 14);
  return base;
}

function valueCrossDownKWave(n, targetValue) {
  const base = classicKWave(n);
  const liftFrom = Math.max(0, n - 9);
  for (let i = liftFrom; i < n - 1; i++) {
    base[i] = clampVal(Math.max(base[i], targetValue + 4));
  }
  const p = n - 1;
  base[p - 1] = clampVal(targetValue + 8);
  base[p] = clampVal(targetValue - 10);
  return base;
}

/** %D crosses up a fixed value — needs sustained high %K (double SMA lags ~5 bars). */
function dCrossUpValueKWave(n, targetValue) {
  const base = classicKWave(n);
  const lowFrom = Math.max(0, n - 12);
  for (let i = lowFrom; i < n - 4; i++) {
    base[i] = clampVal(Math.min(base[i], targetValue - 35));
  }
  for (let i = n - 4; i < n - 1; i++) {
    base[i] = clampVal(targetValue + 5);
  }
  base[n - 1] = clampVal(targetValue + 15);
  return base;
}

function valueCrossUpKWave(n, targetValue) {
  return dCrossUpValueKWave(n, targetValue);
}

function pickBaseKWave(condition, source, target, targetValue = 80) {
  const n = POINT_COUNT;
  if (condition === 'crosses_up' && target === 'value') {
    if (source === 'k') return kCrossUpValue(n, targetValue);
    return valueCrossUpKWave(n, targetValue);
  }
  if (condition === 'crosses_down' && target === 'value') {
    if (source === 'k') return kCrossDownValue(n, targetValue);
    return valueCrossDownKWave(n, targetValue);
  }
  if (source === 'd' && target === 'k') {
    if (['above', 'above_eq', 'above_pct', 'crosses_up'].includes(condition)) {
      return bearishEndKWave(n);
    }
    if (['below', 'below_eq', 'below_pct', 'crosses_down'].includes(condition)) {
      return bullishEndKWave(n);
    }
  }
  if (source === 'k' && target === 'd') {
    if (['above', 'above_eq', 'above_pct', 'crosses_up'].includes(condition)) {
      return bullishEndKWave(n);
    }
    if (['below', 'below_eq', 'below_pct', 'crosses_down'].includes(condition)) {
      return bearishEndKWave(n);
    }
  }
  if (target === 'value') {
    if (['below', 'below_eq', 'below_pct', 'crosses_down'].includes(condition)) {
      return bearishEndKWave(n);
    }
    if (['above', 'above_eq', 'above_pct', 'crosses_up'].includes(condition)) {
      return bullishEndKWave(n);
    }
  }
  if (condition === 'crosses_up') return crossUpEndKWave(n);
  if (condition === 'crosses_down') return crossDownEndKWave(n);
  return classicKWave(n);
}

function evalOnSeries(k, d, condition, source, target, targetValue, pct) {
  const n = k.length - 1;
  const p = n - 1;
  const srcS = source === 'k' ? k : d;
  const tgtN = target === 'value'
    ? targetValue
    : (target === 'k' ? k[n] : d[n]);
  const tgtP = target === 'value'
    ? targetValue
    : (target === 'k' ? k[p] : d[p]);
  return evalCondition(condition, srcS[n], srcS[p], tgtN, tgtP, pct);
}

function tuneTailForCondition(k, condition, source, target, targetValue, pct) {
  const n = k.length;
  const steps = [-12, -10, -8, -6, -4, -3, -2, -1, 0, 1, 2, 3, 4, 6, 8, 10, 12, 15];

  const attempt = (trial) => {
    const d = deriveDFromK(trial);
    return evalOnSeries(trial, d, condition, source, target, targetValue, pct)
      ? { k: trial.map(clampVal), d: d.map(clampVal) }
      : null;
  };

  let hit = attempt(k);
  if (hit) return hit;

  for (const d1 of steps) {
    for (const d2 of steps) {
      const trial = [...k];
      trial[n - 2] += d1;
      trial[n - 1] += d2;
      hit = attempt(trial);
      if (hit) return hit;
    }
  }

  for (const d0 of steps) {
    for (const d1 of steps) {
      for (const d2 of steps) {
        const trial = [...k];
        trial[n - 3] += d0;
        trial[n - 2] += d1;
        trial[n - 1] += d2;
        hit = attempt(trial);
        if (hit) return hit;
      }
    }
  }

  for (const d0 of steps) {
    for (const d1 of steps) {
      for (const d2 of steps) {
        for (const d3 of steps) {
          const trial = [...k];
          trial[n - 4] += d0;
          trial[n - 3] += d1;
          trial[n - 2] += d2;
          trial[n - 1] += d3;
          hit = attempt(trial);
          if (hit) return hit;
        }
      }
    }
  }

  const fallback = [...k];
  if (['crosses_up', 'above', 'above_eq'].includes(condition)) {
    fallback[n - 2] = clampVal(target === 'value' ? targetValue - 8 : 35);
    fallback[n - 1] = clampVal(target === 'value' ? targetValue + 6 : 72);
  } else if (['crosses_down', 'below', 'below_eq'].includes(condition)) {
    fallback[n - 2] = clampVal(target === 'value' ? targetValue + 8 : 65);
    fallback[n - 1] = clampVal(target === 'value' ? targetValue - 6 : 28);
  }
  const d = deriveDFromK(fallback);
  return { k: fallback, d };
}

export function buildStochRsiPreviewSample(
  condition,
  source,
  target,
  targetValue = 80,
  pctValue = 5,
) {
  const pct = parsePct(pctValue);
  const tgtVal = parseTargetValue(targetValue);

  let k = addKJitter(pickBaseKWave(condition, source, target, tgtVal));
  const tuned = tuneTailForCondition(k, condition, source, target, tgtVal, pct);
  k = tuned.k;
  const d = tuned.d;
  const n = k.length;
  const holdStart = condition === 'crosses_up' || condition === 'crosses_down'
    ? n - 2
    : n - HOLD_POINTS;
  const highlightFrom = Math.max(0, holdStart);

  return {
    k,
    d,
    holdStart: highlightFrom,
    highlightIndices: condition === 'crosses_up' || condition === 'crosses_down'
      ? [n - 2, n - 1]
      : Array.from({ length: n - highlightFrom }, (_, j) => highlightFrom + j),
    newestIndex: n - 1,
  };
}

export function getStochRsiPreviewCaption(condition, source, target, targetValue, pctValue = 5) {
  const pct = parsePct(pctValue);
  const src = source === 'k' ? 'StochRSI %K' : 'StochRSI %D';
  const tgt = target === 'value'
    ? `value ${parseTargetValue(targetValue)}`
    : target === 'k' ? 'StochRSI %K' : 'StochRSI %D';

  switch (condition) {
    case 'above':
      return `On the newest bar (right), ${src} sits above ${tgt}.`;
    case 'above_eq':
      return `On the newest bar (right), ${src} is at or above ${tgt}.`;
    case 'below':
      return `On the newest bar (right), ${src} sits below ${tgt}.`;
    case 'below_eq':
      return `On the newest bar (right), ${src} is at or below ${tgt}.`;
    case 'crosses_up':
      return `${src} was at or below ${tgt} on the prior point, then crossed above on the newest bar.`;
    case 'crosses_down':
      return `${src} was at or above ${tgt} on the prior point, then crossed below on the newest bar.`;
    case 'above_pct':
      return `${src} is more than ${pct}% above ${tgt} on the newest bar.`;
    case 'below_pct':
      return `${src} is more than ${pct}% below ${tgt} on the newest bar.`;
    default:
      return `${src} compared to ${tgt}.`;
  }
}
