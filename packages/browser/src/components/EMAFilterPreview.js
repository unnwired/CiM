import React, { useMemo } from 'react';

const GREEN = '#3fb950';
const RED = '#f85149';
const EMA_SOURCE = '#58a6ff';
const EMA_TARGET = '#d29922';
const TARGET_LINE = '#8b949e';

const VIEW_W = 412;
const VIEW_H = 108;
const PAD_L = 8;
const PAD_R = 8;
const CHART_TOP = 8;
const CHART_H = 74;

const PLOT_W = VIEW_W - PAD_L - PAD_R;
const BODY_WIDTH_PX = 4;
/** 2× prior ~1px gap between bodies. */
const GAP_PX = 2;
const SLOT_PX = BODY_WIDTH_PX + GAP_PX;
export const BAR_COUNT = 1 + Math.floor((PLOT_W - BODY_WIDTH_PX) / SLOT_PX);

const MAX_BAR_DELTA_PCT = 0.020;
const MIN_BODY_PCT = 0.012;
const WICK_PCT = 0.008;
const MIN_BODY_HEIGHT_PX = 15;
const BODY_H_MIN = 12;
const BODY_H_MAX = 22;
const BODY_W_MIN = 3;
const BODY_W_MAX = 5;
const Y_CLAMP_MIN = CHART_TOP + 12;
const Y_CLAMP_MAX = CHART_TOP + CHART_H - 12;
const EMA_STROKE_WIDTH = 2;
const EMA_PAIR_STROKE_WIDTH = 2.5;
const EMA_PAIR_DOT_R = 3.5;
/** Minimum pixel gap between source & target in the “before” zone. */
const EMA_PAIR_MIN_GAP = 14;
/** Gap after crossover / in the end-state zone. */
const EMA_PAIR_POST_GAP = 10;
/** Bars spent easing from start relationship → end relationship. */
const EMA_PAIR_CROSS_SPAN = 10;
/** Bars at the right where the end condition is clearly visible. */
const EMA_PAIR_HOLD_BARS = 8;

const BAR_VISUAL = [
  { upperWick: 1.55, lowerWick: 0.45, wickStroke: 1.3 },
  { upperWick: 0.50, lowerWick: 1.45, wickStroke: 1.5 },
  { upperWick: 1.20, lowerWick: 0.70, wickStroke: 1.4 },
  { upperWick: 0.65, lowerWick: 1.60, wickStroke: 1.6 },
  { upperWick: 1.75, lowerWick: 0.40, wickStroke: 1.5 },
  { upperWick: 0.55, lowerWick: 1.25, wickStroke: 1.4 },
  { upperWick: 1.05, lowerWick: 0.95, wickStroke: 1.5 },
  { upperWick: 1.40, lowerWick: 0.55, wickStroke: 1.4 },
  { upperWick: 0.48, lowerWick: 1.70, wickStroke: 1.6 },
  { upperWick: 1.30, lowerWick: 0.60, wickStroke: 1.4 },
  { upperWick: 0.72, lowerWick: 1.35, wickStroke: 1.5 },
  { upperWick: 1.48, lowerWick: 0.52, wickStroke: 1.4 },
];

const OSCILLATE_DELTAS = [0.004, -0.005, 0.003, -0.004, 0.002, -0.003, 0.005, -0.002];

function parsePct(value) {
  const n = parseFloat(String(value));
  return Number.isFinite(n) && n > 0 ? n : 5;
}

function parsePeriod(value, fallback = 21) {
  const n = parseInt(String(value), 10);
  return Number.isFinite(n) && n >= 1 ? n : fallback;
}

function targetLabel(target, targetEmaPeriod) {
  if (target === 'ema') return `EMA ${targetEmaPeriod}`;
  if (target === 'price') return 'Close';
  return target.charAt(0).toUpperCase() + target.slice(1);
}

function hashSeed(parts) {
  const s = parts.join('|');
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function seededRng(seed) {
  let state = seed || 1;
  return () => {
    state = (state + 0x6D2B79F5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randInt(rng, min, max) {
  return min + Math.floor(rng() * (max - min + 1));
}

function clampY(y) {
  return Math.max(Y_CLAMP_MIN, Math.min(Y_CLAMP_MAX, y));
}

/** Smooth ease for display-only EMA tail ramp (0→1). */
function easeInOutCubic(t) {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return t < 0.5 ? 4 * t * t * t : 1 - ((-2 * t + 2) ** 3) / 2;
}

function visualProfile(index) {
  return BAR_VISUAL[index % BAR_VISUAL.length];
}

function tailKeepFor(condition) {
  return (condition === 'crosses_up' || condition === 'crosses_down') ? 3 : 2;
}

/** Fixed pitch: first body flush left inner edge, last flush right. */
function barX(index) {
  return PAD_L + BODY_WIDTH_PX / 2 + index * SLOT_PX;
}

/** Seeded segment walk — up runs, chop, drops, etc. (illustration only). */
export function buildIllustrationCandles(count, seed) {
  if (count <= 0) return [];
  const rng = seededRng(seed);
  const regimes = ['upRun', 'downRun', 'chop', 'drop', 'rip'];
  const candles = [];
  let centerY = CHART_TOP + CHART_H / 2;

  let i = 0;
  while (i < count) {
    const regime = regimes[randInt(rng, 0, regimes.length - 1)];
    let len;
    switch (regime) {
      case 'upRun':
        len = randInt(rng, 2, 4);
        break;
      case 'downRun':
        len = randInt(rng, 2, 4);
        break;
      case 'chop':
        len = randInt(rng, 3, 5);
        break;
      case 'drop':
        len = randInt(rng, 1, 2);
        break;
      case 'rip':
        len = randInt(rng, 1, 2);
        break;
      default:
        len = 2;
    }
    len = Math.min(len, count - i);

    for (let j = 0; j < len; j++) {
      const vis = visualProfile(i);
      const bodyH = randInt(rng, BODY_H_MIN, BODY_H_MAX);
      const bodyW = randInt(rng, BODY_W_MIN, BODY_W_MAX);
      const wickScale = 0.8 + rng() * 0.6;
      let dy;
      let up;

      if (regime === 'chop') {
        dy = (j % 2 === 0 ? -1 : 1) * randInt(rng, 1, 3);
        up = dy < 0;
      } else if (regime === 'drop') {
        dy = randInt(rng, 6, 10);
        up = false;
      } else if (regime === 'rip') {
        dy = -randInt(rng, 6, 10);
        up = true;
      } else if (regime === 'upRun') {
        dy = -randInt(rng, 3, 6);
        up = true;
      } else {
        dy = randInt(rng, 3, 6);
        up = false;
      }

      centerY = clampY(centerY + dy);
      candles.push({
        centerY,
        bodyH,
        bodyW,
        up,
        wickUp: 3 + vis.upperWick * 2.5 * wickScale,
        wickDown: 3 + vis.lowerWick * 2.5 * wickScale,
        wickStroke: vis.wickStroke,
      });
      i += 1;
    }
  }
  return candles;
}

/**
 * Display EMA Y path: illustration follows candle centers; tail eases smoothly
 * into the real newest-bar EMA (may run above/below candles — illustration only).
 */
export function buildEmaDisplayYs(
  illustrationCandles,
  tailStartIndex,
  barCount,
  emaValues,
  emaPeriod,
  ymin,
  ymax,
  lagPeriod = null,
) {
  const ys = new Array(barCount);
  const centers = illustrationCandles.map((c) => c.centerY);
  const alphaFast = 2 / (Math.max(2, emaPeriod) + 1);
  const alphaSlow = lagPeriod != null ? 2 / (Math.max(2, lagPeriod) + 1) : alphaFast;
  const alpha = lagPeriod != null ? alphaSlow : alphaFast;

  const illEnd = Math.min(tailStartIndex, barCount);
  let smooth = centers[0] ?? (CHART_TOP + CHART_H / 2);
  for (let i = 0; i < illEnd; i++) {
    const c = centers[i] ?? smooth;
    smooth = i === 0 ? c : alpha * c + (1 - alpha) * smooth;
    ys[i] = clampY(smooth);
  }

  if (tailStartIndex >= barCount) {
    return ys;
  }

  const newestAnchor = priceToY(
    emaValues[barCount - 1],
    ymin,
    ymax,
    CHART_TOP,
    CHART_H,
  );

  /** Include one pre-tail bar so the move into the tail is gradual, not a cliff. */
  const rampStart = Math.max(0, tailStartIndex - 1);
  const startY = rampStart > 0
    ? ys[rampStart - 1]
    : (centers[0] ?? CHART_TOP + CHART_H / 2);
  const rampLen = barCount - rampStart;

  for (let j = 0; j < rampLen; j++) {
    const i = rampStart + j;
    const t = rampLen <= 1 ? 1 : j / (rampLen - 1);
    const eased = easeInOutCubic(t);
    const rampY = startY + (newestAnchor - startY) * eased;
    ys[i] = clampY(i === barCount - 1 ? newestAnchor : rampY);
  }

  return ys;
}

function emaPathFromYs(barCount, ys) {
  return Array.from({ length: barCount }, (_, i) => {
    const x = barX(i);
    return `${x},${ys[i]}`;
  }).join(' ');
}

function smoothPixelSeries(values, period) {
  const alpha = 2 / (Math.max(2, period) + 1);
  const out = [];
  let smooth = values[0];
  for (let i = 0; i < values.length; i++) {
    smooth = i === 0 ? values[0] : alpha * values[i] + (1 - alpha) * smooth;
    out.push(smooth);
  }
  return out;
}

/** +offset => source below target in SVG (higher Y). */
function emaPairStartOffset(condition, gap) {
  switch (condition) {
    case 'above':
    case 'above_eq':
    case 'above_pct':
    case 'crosses_up':
      return gap;
    case 'below':
    case 'below_eq':
    case 'below_pct':
    case 'crosses_down':
      return -gap;
    default:
      return gap;
  }
}

function emaPairEndOffset(condition, postGap, pct) {
  switch (condition) {
    case 'above':
    case 'crosses_up':
      return -postGap;
    case 'above_eq':
      return -3;
    case 'below':
    case 'crosses_down':
      return postGap;
    case 'below_eq':
      return 3;
    case 'above_pct':
      return -(4 + Math.min(pct, 12) * 0.35);
    case 'below_pct':
      return 4 + Math.min(pct, 12) * 0.35;
    default:
      return -postGap;
  }
}

/**
 * EMA-vs-EMA illustration: two separated lines, gradual transition, multi-bar end state.
 * Display-only — filter math stays in buildEmaPreviewSample.
 */
export function buildEmaVsEmaDisplayPair(barCount, condition, pctValue, seed) {
  const pct = parsePct(pctValue);
  const rng = seededRng(seed);
  const midY = CHART_TOP + CHART_H / 2;
  const n = barCount;
  const holdStart = Math.max(0, n - EMA_PAIR_HOLD_BARS);
  const transStart = Math.max(2, holdStart - EMA_PAIR_CROSS_SPAN);

  const rawTarget = [];
  let ty = midY;
  for (let i = 0; i < n; i++) {
    ty += (rng() - 0.48) * 1.35;
    ty = clampY(ty);
    rawTarget.push(ty);
  }
  const targetYs = smoothPixelSeries(rawTarget, 12).map(clampY);

  const sourceYs = new Array(n);
  const startOff = emaPairStartOffset(condition, EMA_PAIR_MIN_GAP);
  const endOff = emaPairEndOffset(condition, EMA_PAIR_POST_GAP, pct);

  if (condition === 'crosses_up' || condition === 'crosses_down') {
    const approachStart = Math.max(0, n - EMA_PAIR_CROSS_SPAN - EMA_PAIR_HOLD_BARS);
    const penult = n - 2;
    const crossEndOff = condition === 'crosses_up' ? -EMA_PAIR_POST_GAP : EMA_PAIR_POST_GAP;
    const crossStartOff = emaPairStartOffset(condition, EMA_PAIR_MIN_GAP);
    const meetOff = condition === 'crosses_up' ? 2 : -2;

    for (let i = 0; i < n; i++) {
      let off;
      if (i < approachStart) {
        off = crossStartOff;
      } else if (i < penult) {
        const t = (i - approachStart) / Math.max(1, penult - approachStart);
        off = crossStartOff + (meetOff - crossStartOff) * easeInOutCubic(t);
      } else if (i === penult) {
        off = meetOff;
      } else {
        off = crossEndOff;
      }
      sourceYs[i] = clampY(targetYs[i] + off);
    }
  } else {
    for (let i = 0; i < n; i++) {
      let off;
      if (i < transStart) {
        off = startOff;
      } else if (i < holdStart) {
        const t = (i - transStart) / Math.max(1, holdStart - transStart - 1);
        off = startOff + (endOff - startOff) * easeInOutCubic(t);
      } else {
        off = endOff;
      }
      sourceYs[i] = clampY(targetYs[i] + off);
    }
  }

  return { sourceYs, targetYs, holdStart };
}

export function emaVsEmaHighlightIndices(condition, barCount, holdStart) {
  if (condition === 'crosses_up' || condition === 'crosses_down') {
    return [barCount - 2, barCount - 1];
  }
  const from = Math.max(0, holdStart);
  return Array.from({ length: barCount - from }, (_, j) => from + j);
}

function emaPairBandPolygon(sourceYs, targetYs, fromIndex, toIndex) {
  const pts = [];
  for (let i = fromIndex; i <= toIndex; i++) {
    pts.push(`${barX(i)},${sourceYs[i]}`);
  }
  for (let i = toIndex; i >= fromIndex; i--) {
    pts.push(`${barX(i)},${targetYs[i]}`);
  }
  return pts.join(' ');
}

/** Standard EMA: α = 2 / (period + 1). */
export function computeEmaSeries(closes, period) {
  const p = Math.max(2, parsePeriod(period, 9));
  const alpha = 2 / (p + 1);
  const out = [];
  let ema = closes[0];
  for (let i = 0; i < closes.length; i++) {
    ema = i === 0 ? closes[0] : alpha * closes[i] + (1 - alpha) * ema;
    out.push(ema);
  }
  return out;
}

/** Mean-reverting walk for math layer — no net drift across history. */
export function meanRevertingWalk(barCount, anchor = 100) {
  const closes = [anchor];
  for (let i = 1; i < barCount; i++) {
    const prev = closes[i - 1];
    const pull = (anchor - prev) / prev * 0.06;
    const delta = OSCILLATE_DELTAS[(i - 1) % OSCILLATE_DELTAS.length] + pull;
    closes.push(prev * (1 + delta));
  }
  return enforceMaxDelta(closes, MAX_BAR_DELTA_PCT);
}

/** @deprecated alias for tests */
export function smoothWalk(barCount, startPrice = 100) {
  return meanRevertingWalk(barCount, startPrice);
}

export function enforceMaxDelta(closes, maxPct = MAX_BAR_DELTA_PCT) {
  if (!closes.length) return [];
  const out = [closes[0]];
  for (let i = 1; i < closes.length; i++) {
    const prev = out[i - 1];
    const lo = prev * (1 - maxPct);
    const hi = prev * (1 + maxPct);
    out.push(Math.max(lo, Math.min(hi, closes[i])));
  }
  return out;
}

function closesToBars(closes) {
  return closes.map((close, i) => {
    const open = i === 0 ? close * (1 - MIN_BODY_PCT * 0.5) : closes[i - 1];
    const adjClose = close;
    let bodyTop = Math.max(open, adjClose);
    let bodyBot = Math.min(open, adjClose);
    const minBody = close * MIN_BODY_PCT;
    if (bodyTop - bodyBot < minBody) {
      const mid = (open + adjClose) / 2;
      bodyTop = mid + minBody / 2;
      bodyBot = mid - minBody / 2;
    }
    const vis = visualProfile(i);
    const wickBase = Math.max(close * WICK_PCT, minBody * 0.45);
    return {
      open,
      high: bodyTop + wickBase * vis.upperWick,
      low: bodyBot - wickBase * vis.lowerWick,
      close: adjClose,
      wickStroke: vis.wickStroke,
    };
  });
}

function applyVisualOHLC(bars, ymin, ymax) {
  if (ymax <= ymin) return bars;
  const pricePerPx = (ymax - ymin) / CHART_H;
  const minHalfBody = (MIN_BODY_HEIGHT_PX * pricePerPx) / 2;
  return bars.map((bar, i) => {
    const openAnchor = i === 0 ? bar.open : bars[i - 1].close;
    const up = bar.close >= openAnchor;
    const mid = (openAnchor + bar.close) / 2;
    const halfBody = Math.max(Math.abs(bar.close - openAnchor) / 2, minHalfBody);
    const open = up ? mid - halfBody : mid + halfBody;
    const close = bar.close;
    const bodyTop = Math.max(open, close);
    const bodyBot = Math.min(open, close);
    const vis = visualProfile(i);
    const wickUnit = minHalfBody * 1.1;
    return {
      ...bar,
      open,
      close,
      high: bodyTop + wickUnit * vis.upperWick,
      low: bodyBot - wickUnit * vis.lowerWick,
    };
  });
}

function computeYScale(bars, emaSource, emaTarget, band, indexOffset = 0) {
  const allPrices = [];
  for (let i = 0; i < bars.length; i++) {
    allPrices.push(bars[i].high, bars[i].low, emaSource[indexOffset + i]);
    if (emaTarget) allPrices.push(emaTarget[indexOffset + i]);
  }
  if (band) allPrices.push(band.lower, band.upper);
  const rawMin = Math.min(...allPrices);
  const rawMax = Math.max(...allPrices);
  const pad = Math.max((rawMax - rawMin) * 0.08, (bars[0]?.close ?? 100) * 0.004);
  return { ymin: rawMin - pad, ymax: rawMax + pad };
}

function targetAtBar(bar, emaTargetSeries, index, target) {
  if (target === 'open') return bar.open;
  if (target === 'high') return bar.high;
  if (target === 'low') return bar.low;
  if (target === 'ema') return emaTargetSeries[index];
  return bar.close;
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
      return srcPrev <= tgtPrev && src > tgt;
    case 'crosses_down':
      return srcPrev >= tgtPrev && src < tgt;
    case 'above_pct': {
      if (tgt === 0) return false;
      const gap = ((src - tgt) / Math.abs(tgt)) * 100;
      return src > tgt && gap <= pct;
    }
    case 'below_pct': {
      if (tgt === 0) return false;
      const gap = ((tgt - src) / Math.abs(tgt)) * 100;
      return src < tgt && gap <= pct;
    }
    default:
      return true;
  }
}

function packSample(closes, emaPeriod, targetEmaPeriod, target) {
  const bars = closesToBars(closes);
  const emaSource = computeEmaSeries(closes, emaPeriod);
  const emaTarget = target === 'ema' ? computeEmaSeries(closes, targetEmaPeriod) : null;
  return { bars, emaSource, emaTarget, closes };
}

function evalOnCloses(closes, condition, target, emaPeriod, targetEmaPeriod, pct) {
  const { bars, emaSource, emaTarget } = packSample(closes, emaPeriod, targetEmaPeriod, target);
  const n = closes.length;
  const i = n - 1;
  const ip = n - 2;
  return evalCondition(
    condition,
    emaSource[i],
    emaSource[ip],
    targetAtBar(bars[i], emaTarget, i, target),
    targetAtBar(bars[ip], emaTarget, ip, target),
    pct,
  );
}

function findTailAdjustments(base, condition, target, emaPeriod, targetEmaPeriod, pct) {
  const n = base.length;
  const steps = [-0.012, -0.009, -0.006, -0.003, 0, 0.003, 0.006, 0.009, 0.012];
  let best = null;
  let bestCost = Infinity;

  const tryTail = (deltas) => {
    let trial = [...base];
    const from = n - deltas.length;
    deltas.forEach((d, j) => {
      trial[from + j] *= 1 + d;
    });
    trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT);
    if (!evalOnCloses(trial, condition, target, emaPeriod, targetEmaPeriod, pct)) return;
    const cost = deltas.reduce((s, d) => s + Math.abs(d), 0);
    if (cost < bestCost) {
      bestCost = cost;
      best = trial;
    }
  };

  for (const d3 of steps) {
    for (const d2 of steps) {
      for (const d1 of steps) {
        for (const d0 of steps) {
          tryTail([d3, d2, d1, d0]);
        }
      }
    }
  }

  if (best) return best;

  const wider = [-0.012, -0.009, -0.006, -0.003, 0, 0.003, 0.006, 0.009, 0.012];
  for (const d1 of wider) {
    for (const d2 of wider) {
      let trial = [...base];
      trial[n - 2] *= 1 + d1;
      trial[n - 1] *= 1 + d2;
      trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT * 1.1);
      if (!evalOnCloses(trial, condition, target, emaPeriod, targetEmaPeriod, pct)) continue;
      const cost = Math.abs(d1) + Math.abs(d2);
      if (cost < bestCost) {
        bestCost = cost;
        best = trial;
      }
    }
  }

  return best;
}

function fineTailSolve(base, condition, target, emaPeriod, targetEmaPeriod, pct) {
  const n = base.length;
  let best = null;
  let bestCost = Infinity;
  const fine = [-0.009, -0.0075, -0.006, -0.0045, -0.003, -0.0015, 0, 0.0015, 0.003, 0.0045, 0.006, 0.0075, 0.009];

  const tryLast = (kPrev, kLast) => {
    let trial = [...base];
    trial[n - 2] = trial[n - 3] * (1 + kPrev);
    trial[n - 1] = trial[n - 2] * (1 + kLast);
    trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT);
    if (!evalOnCloses(trial, condition, target, emaPeriod, targetEmaPeriod, pct)) return;
    const cost = Math.abs(kPrev) + Math.abs(kLast);
    if (cost < bestCost) {
      bestCost = cost;
      best = trial;
    }
  };

  for (const kPrev of fine) {
    for (const kLast of fine) {
      tryLast(kPrev, kLast);
    }
  }

  if (best) return best;

  for (const k0 of fine) {
    for (const k1 of fine) {
      for (const k2 of fine) {
        let trial = [...base];
        trial[n - 3] = trial[n - 4] * (1 + k0);
        trial[n - 2] = trial[n - 3] * (1 + k1);
        trial[n - 1] = trial[n - 2] * (1 + k2);
        trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT);
        if (!evalOnCloses(trial, condition, target, emaPeriod, targetEmaPeriod, pct)) continue;
        const cost = Math.abs(k0) + Math.abs(k1) + Math.abs(k2);
        if (cost < bestCost) {
          bestCost = cost;
          best = trial;
        }
      }
    }
  }

  return best;
}

function applyTailHints(closes, condition) {
  const n = closes.length;
  if (n < 4) return closes;
  const out = [...closes];
  const up = condition === 'above' || condition === 'above_eq' || condition === 'above_pct';
  const down = condition === 'below' || condition === 'below_eq' || condition === 'below_pct';
  const crossUp = condition === 'crosses_up';
  const crossDown = condition === 'crosses_down';

  if (up) {
    out[n - 3] = out[n - 4] * (1 - 0.013);
  } else if (down) {
    out[n - 3] = out[n - 4] * (1 + 0.013);
  } else if (crossUp) {
    out[n - 2] = out[n - 3] * (1 - 0.012);
    out[n - 1] = out[n - 2] * (1 + 0.016);
  } else if (crossDown) {
    out[n - 2] = out[n - 3] * (1 + 0.012);
    out[n - 1] = out[n - 2] * (1 - 0.016);
  }
  return enforceMaxDelta(out, MAX_BAR_DELTA_PCT);
}

function baseWalkForCondition(condition) {
  return applyTailHints(meanRevertingWalk(BAR_COUNT), condition);
}

function emaCrossWalk(crossUp) {
  const closes = meanRevertingWalk(BAR_COUNT - 2);
  if (crossUp) {
    closes.push(closes[closes.length - 1] * (1 - 0.009));
    closes.push(closes[closes.length - 1] * (1 + 0.026));
  } else {
    closes.push(closes[closes.length - 1] * (1 + 0.009));
    closes.push(closes[closes.length - 1] * (1 - 0.026));
  }
  return enforceMaxDeltaFlexible(closes);
}

function enforceMaxDeltaFlexible(closes) {
  if (!closes.length) return [];
  const out = [closes[0]];
  for (let i = 1; i < closes.length; i++) {
    const maxPct = i === closes.length - 1 ? 0.028 : MAX_BAR_DELTA_PCT;
    const prev = out[i - 1];
    out.push(Math.max(prev * (1 - maxPct), Math.min(prev * (1 + maxPct), closes[i])));
  }
  return out;
}

function buildBand(condition, bars, emaSource, emaTarget, target, pct, newestIndex) {
  if (condition !== 'above_pct' && condition !== 'below_pct') return null;
  const bar = bars[newestIndex];
  const tgt = targetAtBar(bar, emaTarget, newestIndex, target);
  const src = emaSource[newestIndex];
  const half = Math.abs(tgt) * (pct / 100);
  if (condition === 'above_pct') {
    return { lower: tgt, upper: tgt + half, ema: src };
  }
  return { lower: tgt - half, upper: tgt, ema: src };
}

function highlightIndicesFor(condition, barCount) {
  if (condition === 'crosses_up' || condition === 'crosses_down') {
    return [barCount - 2, barCount - 1];
  }
  return [barCount - 1];
}

function previewSeed(condition, target, pctValue, emaPeriod, targetEmaPeriod) {
  return hashSeed([condition, target, String(emaPeriod), String(targetEmaPeriod), String(pctValue)]);
}

/** Synthetic OHLC + computed EMA series (oldest → newest). Not market data. */
export function buildEmaPreviewSample(
  condition,
  target,
  pctValue = 5,
  emaPeriod = 21,
  targetEmaPeriod = 50,
) {
  const pct = parsePct(pctValue);
  const tailKeep = tailKeepFor(condition);
  const seed = previewSeed(condition, target, pctValue, emaPeriod, targetEmaPeriod);

  if (target === 'ema' && (condition === 'crosses_up' || condition === 'crosses_down')) {
    const crossCloses = emaCrossWalk(condition === 'crosses_up');
    if (evalOnCloses(crossCloses, condition, target, emaPeriod, targetEmaPeriod, pct)) {
      const { bars, emaSource, emaTarget } = packSample(
        crossCloses, emaPeriod, targetEmaPeriod, target,
      );
      const newestIndex = bars.length - 1;
      const tailStart = bars.length - tailKeep;
      return {
        bars,
        emaSource,
        emaTarget,
        illustrationCandles: buildIllustrationCandles(tailStart, seed),
        tailStartIndex: tailStart,
        tailKeep,
        highlightIndices: highlightIndicesFor(condition, bars.length),
        newestIndex,
        band: null,
      };
    }
  }

  const bases = [
    baseWalkForCondition(condition),
    meanRevertingWalk(BAR_COUNT),
    baseWalkForCondition(
      condition === 'crosses_up' ? 'below'
        : condition === 'crosses_down' ? 'above'
          : condition,
    ),
  ];

  if (target === 'ema' && (condition === 'crosses_up' || condition === 'crosses_down')) {
    bases.unshift(emaCrossWalk(condition === 'crosses_up'));
  }
  if (target === 'high' && (condition === 'above' || condition === 'above_eq' || condition === 'above_pct')) {
    bases.unshift(baseWalkForCondition('above'));
  }

  let closes = null;
  for (const base of bases) {
    closes = findTailAdjustments(base, condition, target, emaPeriod, targetEmaPeriod, pct);
    if (closes) break;
    closes = fineTailSolve(base, condition, target, emaPeriod, targetEmaPeriod, pct);
    if (closes) break;
  }

  if (!closes) {
    closes = enforceMaxDelta(meanRevertingWalk(BAR_COUNT), MAX_BAR_DELTA_PCT);
  }

  const { bars, emaSource, emaTarget } = packSample(closes, emaPeriod, targetEmaPeriod, target);
  const newestIndex = bars.length - 1;
  const tailStartIndex = bars.length - tailKeep;
  const highlightIndices = highlightIndicesFor(condition, bars.length);
  const band = buildBand(condition, bars, emaSource, emaTarget, target, pct, newestIndex);

  return {
    bars,
    emaSource,
    emaTarget,
    illustrationCandles: buildIllustrationCandles(tailStartIndex, seed),
    tailStartIndex,
    tailKeep,
    highlightIndices,
    newestIndex,
    band,
  };
}

export function getEmaPreviewCaption(condition, target, emaPeriod, targetEmaPeriod, pctValue = 5) {
  const pct = parsePct(pctValue);
  const src = `EMA ${emaPeriod}`;
  const tgt = targetLabel(target, targetEmaPeriod);

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
      return `${src} was at or below ${tgt} on the prior bar, then crossed above on the newest bar.`;
    case 'crosses_down':
      return `${src} was at or above ${tgt} on the prior bar, then crossed below on the newest bar.`;
    case 'above_pct':
      return `${src} is above ${tgt} on the newest bar but only within ${pct}% — not stretched too far.`;
    case 'below_pct':
      return `${src} is below ${tgt} on the newest bar but only within ${pct}% — not stretched too far.`;
    default:
      return `${src} compared to ${tgt}.`;
  }
}

function priceToY(price, ymin, ymax, top, height) {
  if (ymax === ymin) return top + height / 2;
  return top + ((ymax - price) / (ymax - ymin)) * height;
}

function IllustrationCandle({ x, candle, dimmed }) {
  const color = candle.up ? GREEN : RED;
  const opacity = dimmed ? 0.65 : 1;
  const bodyTop = candle.centerY - candle.bodyH / 2;
  const yHigh = bodyTop - candle.wickUp;
  const yLow = bodyTop + candle.bodyH + candle.wickDown;

  return (
    <g opacity={opacity}>
      <line
        x1={x}
        y1={yHigh}
        x2={x}
        y2={yLow}
        stroke={color}
        strokeWidth={candle.wickStroke ?? 1.5}
        strokeLinecap="round"
      />
      <rect
        x={x - candle.bodyW / 2}
        y={bodyTop}
        width={candle.bodyW}
        height={candle.bodyH}
        fill={color}
        rx={1.5}
      />
    </g>
  );
}

function PriceCandle({ x, bar, ymin, ymax, bodyW, dimmed }) {
  const yHigh = priceToY(bar.high, ymin, ymax, CHART_TOP, CHART_H);
  const yLow = priceToY(bar.low, ymin, ymax, CHART_TOP, CHART_H);
  const yOpen = priceToY(bar.open, ymin, ymax, CHART_TOP, CHART_H);
  const yClose = priceToY(bar.close, ymin, ymax, CHART_TOP, CHART_H);
  const up = bar.close >= bar.open;
  const color = up ? GREEN : RED;
  const bodyH = Math.max(MIN_BODY_HEIGHT_PX, Math.abs(yClose - yOpen));
  const opacity = dimmed ? 0.65 : 1;
  const drawTop = (yOpen + yClose) / 2 - bodyH / 2;
  const w = bodyW ?? BODY_WIDTH_PX;
  const wickW = bar.wickStroke ?? 1.5;

  return (
    <g opacity={opacity}>
      <line x1={x} y1={yHigh} x2={x} y2={yLow} stroke={color} strokeWidth={wickW} strokeLinecap="round" />
      <rect x={x - w / 2} y={drawTop} width={w} height={bodyH} fill={color} rx={1.5} />
    </g>
  );
}

function LegendSwatch({ x, y, color, dash }) {
  if (dash) {
    return (
      <line x1={x} y1={y} x2={x + 14} y2={y} stroke={color} strokeWidth={2} strokeDasharray="3 2" />
    );
  }
  return <line x1={x} y1={y} x2={x + 14} y2={y} stroke={color} strokeWidth={EMA_STROKE_WIDTH} strokeLinecap="round" />;
}

export default function EMAFilterPreview({
  emaPeriod,
  condition,
  target,
  targetEmaPeriod,
  pctValue,
}) {
  const isEmaPair = target === 'ema';

  const sample = useMemo(
    () => buildEmaPreviewSample(condition, target, pctValue, emaPeriod, targetEmaPeriod),
    [condition, target, pctValue, emaPeriod, targetEmaPeriod],
  );
  const caption = useMemo(
    () => getEmaPreviewCaption(condition, target, emaPeriod, targetEmaPeriod, pctValue),
    [condition, target, emaPeriod, targetEmaPeriod, pctValue],
  );

  const seed = useMemo(
    () => previewSeed(condition, target, pctValue, emaPeriod, targetEmaPeriod),
    [condition, target, pctValue, emaPeriod, targetEmaPeriod],
  );

  const {
    bars,
    emaSource,
    emaTarget,
    illustrationCandles,
    tailStartIndex,
    highlightIndices: sampleHighlights,
    newestIndex,
    band,
  } = sample;
  const n = bars.length;

  const emaPairDisplay = useMemo(() => {
    if (!isEmaPair) return null;
    return buildEmaVsEmaDisplayPair(n, condition, pctValue, seed);
  }, [isEmaPair, n, condition, pctValue, seed]);

  const highlightIndices = isEmaPair && emaPairDisplay
    ? emaVsEmaHighlightIndices(condition, n, emaPairDisplay.holdStart)
    : sampleHighlights;
  const highlightSet = new Set(highlightIndices);

  const priceModeDisplay = useMemo(() => {
    if (isEmaPair) return null;
    const tailBars = bars.slice(tailStartIndex);
    const tailEma = emaSource.slice(tailStartIndex);
    const tailEmaTarget = emaTarget ? emaTarget.slice(tailStartIndex) : null;
    const prelim = computeYScale(tailBars, tailEma, tailEmaTarget, band, 0);
    const tailDisplay = applyVisualOHLC(tailBars, prelim.ymin, prelim.ymax);
    const scale = computeYScale(tailDisplay, tailEma, tailEmaTarget, band, 0);
    const yminLocal = scale.ymin;
    const ymaxLocal = scale.ymax;
    return {
      ymin: yminLocal,
      ymax: ymaxLocal,
      tailDisplay,
      sourceEmaYs: buildEmaDisplayYs(
        illustrationCandles,
        tailStartIndex,
        n,
        emaSource,
        emaPeriod,
        yminLocal,
        ymaxLocal,
        null,
      ),
      targetEmaYs: emaTarget
        ? buildEmaDisplayYs(
          illustrationCandles,
          tailStartIndex,
          n,
          emaTarget,
          emaPeriod,
          yminLocal,
          ymaxLocal,
          targetEmaPeriod,
        )
        : null,
      newestTargetY: priceToY(
        targetAtBar(bars[newestIndex], emaTarget, newestIndex, target),
        yminLocal,
        ymaxLocal,
        CHART_TOP,
        CHART_H,
      ),
    };
  }, [
    isEmaPair,
    bars,
    tailStartIndex,
    emaSource,
    emaTarget,
    band,
    illustrationCandles,
    n,
    emaPeriod,
    targetEmaPeriod,
    newestIndex,
    target,
  ]);

  const sourceEmaYs = isEmaPair && emaPairDisplay
    ? emaPairDisplay.sourceYs
    : priceModeDisplay.sourceEmaYs;
  const targetEmaYs = isEmaPair && emaPairDisplay
    ? emaPairDisplay.targetYs
    : priceModeDisplay?.targetEmaYs ?? null;
  const newestTargetY = isEmaPair
    ? (targetEmaYs?.[newestIndex] ?? 0)
    : priceModeDisplay.newestTargetY;
  const ymin = priceModeDisplay?.ymin ?? 0;
  const ymax = priceModeDisplay?.ymax ?? 1;

  const emaPath = emaPathFromYs(n, sourceEmaYs);
  const targetEmaPath = targetEmaYs ? emaPathFromYs(n, targetEmaYs) : null;

  const newestX = barX(newestIndex);
  const newestEmaY = sourceEmaYs[newestIndex];
  const newestTargetEmaY = targetEmaYs ? targetEmaYs[newestIndex] : null;

  const showPctBand = isEmaPair
    && (condition === 'above_pct' || condition === 'below_pct')
    && emaPairDisplay;
  const pctBandFrom = emaPairDisplay?.holdStart ?? 0;

  const strokeW = isEmaPair ? EMA_PAIR_STROKE_WIDTH : EMA_STROKE_WIDTH;
  const dotR = isEmaPair ? EMA_PAIR_DOT_R : 3;

  const gridYs = [0.25, 0.5, 0.75].map((f) => CHART_TOP + CHART_H * f);
  const halfSlot = SLOT_PX * 0.48;

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-tertiary)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '8px 10px 6px',
      }}
    >
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 8,
        fontSize: 10,
        color: 'var(--text-muted)',
        marginBottom: 6,
        letterSpacing: '0.04em',
      }}
      >
        <span>
          {isEmaPair
            ? 'EXAMPLE — two EMAs (illustration only)'
            : 'EXAMPLE — older ← → newer (illustration only)'}
        </span>
        {(condition === 'crosses_up' || condition === 'crosses_down') && (
          <span style={{ flexShrink: 0 }}>
            {isEmaPair ? 'EMA cross at right edge' : 'cross at right edge'}
          </span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        width="100%"
        height={VIEW_H}
        style={{ display: 'block' }}
        aria-hidden
      >
        <defs>
          <clipPath id="ema-preview-plot-clip">
            <rect x={PAD_L} y={CHART_TOP} width={PLOT_W} height={CHART_H} />
          </clipPath>
        </defs>
        {gridYs.map((gy) => (
          <line
            key={gy}
            x1={PAD_L}
            y1={gy}
            x2={VIEW_W - PAD_R}
            y2={gy}
            stroke="var(--border)"
            strokeWidth={0.5}
            opacity={0.45}
          />
        ))}

        <g clipPath="url(#ema-preview-plot-clip)">
          {highlightIndices.map((hi) => {
            const x = barX(hi);
            return (
              <rect
                key={`hl-${hi}`}
                x={x - halfSlot}
                y={CHART_TOP - 2}
                width={halfSlot * 2}
                height={CHART_H + 4}
                fill="rgba(56,139,253,0.08)"
                stroke="rgba(56,139,253,0.35)"
                strokeWidth={1}
                rx={2}
              />
            );
          })}

          {band && !isEmaPair && (
            <rect
              x={PAD_L}
              y={priceToY(band.upper, ymin, ymax, CHART_TOP, CHART_H)}
              width={VIEW_W - PAD_L - PAD_R}
              height={Math.max(
                2,
                priceToY(band.lower, ymin, ymax, CHART_TOP, CHART_H)
                  - priceToY(band.upper, ymin, ymax, CHART_TOP, CHART_H),
              )}
              fill="rgba(88,166,255,0.1)"
              stroke="rgba(88,166,255,0.3)"
              strokeWidth={1}
              rx={2}
            />
          )}

          {showPctBand && targetEmaYs && (
            <polygon
              points={emaPairBandPolygon(sourceEmaYs, targetEmaYs, pctBandFrom, newestIndex)}
              fill="rgba(88,166,255,0.14)"
              stroke="rgba(88,166,255,0.35)"
              strokeWidth={1}
            />
          )}

          {!isEmaPair && priceModeDisplay && illustrationCandles.map((candle, i) => (
            <IllustrationCandle
              key={`ill-${i}`}
              x={barX(i)}
              candle={candle}
              dimmed={!highlightSet.has(i) && (condition === 'crosses_up' || condition === 'crosses_down')}
            />
          ))}

          {!isEmaPair && priceModeDisplay && priceModeDisplay.tailDisplay.map((bar, j) => {
            const i = tailStartIndex + j;
            return (
              <PriceCandle
                key={`tail-${i}`}
                x={barX(i)}
                bar={bar}
                ymin={ymin}
                ymax={ymax}
                bodyW={BODY_WIDTH_PX}
                dimmed={!highlightSet.has(i) && (condition === 'crosses_up' || condition === 'crosses_down')}
              />
            );
          })}

          {targetEmaPath && (
            <polyline
              points={targetEmaPath}
              fill="none"
              stroke={EMA_TARGET}
              strokeWidth={strokeW}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          <polyline
            points={emaPath}
            fill="none"
            stroke={EMA_SOURCE}
            strokeWidth={strokeW}
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {target !== 'ema' && (
            <line
              x1={newestX - BODY_WIDTH_PX * 1.15}
              y1={newestTargetY}
              x2={newestX + BODY_WIDTH_PX * 1.15}
              y2={newestTargetY}
              stroke={TARGET_LINE}
              strokeWidth={2}
              strokeDasharray="4 3"
            />
          )}

          <circle cx={newestX} cy={newestEmaY} r={dotR} fill={EMA_SOURCE} stroke="var(--bg-secondary)" strokeWidth={1.2} />
          {target === 'ema' && newestTargetEmaY != null && (
            <circle cx={newestX} cy={newestTargetEmaY} r={dotR} fill={EMA_TARGET} stroke="var(--bg-secondary)" strokeWidth={1.2} />
          )}
          {target !== 'ema' && (
            <circle cx={newestX} cy={newestTargetY} r={3.2} fill={TARGET_LINE} stroke="var(--bg-secondary)" strokeWidth={1.2} />
          )}
        </g>

        <LegendSwatch x={PAD_L} y={VIEW_H - 8} color={EMA_SOURCE} />
        <text x={PAD_L + 18} y={VIEW_H - 5} fontSize={9} fill={EMA_SOURCE} fontFamily="var(--font-mono)">
          EMA {emaPeriod}
        </text>
        {target === 'ema' ? (
          <>
            <LegendSwatch x={PAD_L + 72} y={VIEW_H - 8} color={EMA_TARGET} />
            <text x={PAD_L + 90} y={VIEW_H - 5} fontSize={9} fill={EMA_TARGET} fontFamily="var(--font-mono)">
              EMA {targetEmaPeriod}
            </text>
          </>
        ) : (
          <>
            <LegendSwatch x={PAD_L + 72} y={VIEW_H - 8} color={TARGET_LINE} dash />
            <text x={PAD_L + 90} y={VIEW_H - 5} fontSize={9} fill={TARGET_LINE} fontFamily="var(--font-mono)">
              {targetLabel(target, targetEmaPeriod)}
            </text>
          </>
        )}
      </svg>
      <p style={{ margin: '8px 0 0', fontSize: 11, lineHeight: 1.45, color: 'var(--text-secondary)' }}>
        {caption}
      </p>
    </div>
  );
}
