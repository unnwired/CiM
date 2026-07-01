/**
 * MACD filter preview — real calculateMacd on synthetic closes, tail-solved per condition.
 * Display ~28 MACD bars (~1y of 2W periods) for visual depth; longer walk feeds warmup/history.
 */

import { calculateMacd, MACD_MIN_CLOSES } from './calculateMacd.js';

/** Layout: fill the plot width so ~28 bars span the full preview (visible depth). */
export const PREVIEW_VIEW_W = 480;
export const PREVIEW_PAD_L = 8;
export const PREVIEW_PAD_R = 8;
export const PREVIEW_PLOT_W = PREVIEW_VIEW_W - PREVIEW_PAD_L - PREVIEW_PAD_R;
/** ~26–28 two-week periods ≈ one year of macro swings visible in the panel. */
export const VIS_BAR_COUNT = 28;
export const PREVIEW_SLOT_PX = Math.floor(PREVIEW_PLOT_W / VIS_BAR_COUNT);
export const PREVIEW_GAP_PX = 4;
export const PREVIEW_BAR_W = Math.max(6, PREVIEW_SLOT_PX - PREVIEW_GAP_PX);

export const TOTAL_CLOSE_BARS = Math.max(
  140,
  MACD_MIN_CLOSES + VIS_BAR_COUNT + 72,
);

const MAX_BAR_DELTA_PCT = 0.022;
const OSCILLATE = [0.009, -0.011, 0.008, -0.010, 0.007, -0.009, 0.012, -0.008, 0.006, -0.007];

export function parsePct(value) {
  const n = parseFloat(String(value));
  return Number.isFinite(n) && n > 0 ? n : 5;
}

export function parseTargetValue(value) {
  const n = parseFloat(String(value));
  return Number.isFinite(n) ? n : 0;
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

function enforceMaxDelta(closes, maxPct = MAX_BAR_DELTA_PCT) {
  const out = [closes[0]];
  for (let i = 1; i < closes.length; i++) {
    const prev = out[i - 1];
    const cap = i === closes.length - 1 ? maxPct * 1.35 : maxPct;
    out.push(Math.max(prev * (1 - cap), Math.min(prev * (1 + cap), closes[i])));
  }
  return out;
}

/** Multi-swing price history so MACD has long arcs before the displayed tail. */
export function macdHistoryWalk(barCount = TOTAL_CLOSE_BARS, phase = 0) {
  const closes = [100];
  for (let i = 1; i < barCount; i++) {
    const t = i + phase;
    const longCycle = Math.sin(t * (2 * Math.PI / 26)) * 0.034;
    const midCycle = Math.sin(t * 0.38) * 0.022;
    const shortCycle = Math.sin(t * 0.15) * 0.012;
    const wave = longCycle + midCycle + shortCycle + OSCILLATE[i % OSCILLATE.length];
    closes.push(closes[i - 1] * (1 + wave));
  }
  return closes;
}

function evalOnCloses(closes, condition, source, target, targetValue, pct) {
  const { macd, signal } = calculateMacd(closes);
  const n = closes.length - 1;
  const p = n - 1;
  if (macd[n] == null || signal[n] == null || macd[p] == null || signal[p] == null) {
    return false;
  }
  const srcS = source === 'signal' ? signal : macd;
  const tgtN = target === 'value'
    ? targetValue
    : (target === 'signal' ? signal[n] : macd[n]);
  const tgtP = target === 'value'
    ? targetValue
    : (target === 'signal' ? signal[p] : macd[p]);
  return evalCondition(condition, srcS[n], srcS[p], tgtN, tgtP, pct);
}

function applyTailHints(closes, condition) {
  const n = closes.length;
  if (n < 4) return closes;
  const out = [...closes];
  if (['above', 'above_eq', 'above_pct'].includes(condition)) {
    out[n - 3] = out[n - 4] * (1 - 0.012);
  } else if (['below', 'below_eq', 'below_pct'].includes(condition)) {
    out[n - 3] = out[n - 4] * (1 + 0.012);
  } else if (condition === 'crosses_up') {
    out[n - 2] = out[n - 3] * (1 - 0.014);
    out[n - 1] = out[n - 2] * (1 + 0.022);
  } else if (condition === 'crosses_down') {
    out[n - 2] = out[n - 3] * (1 + 0.014);
    out[n - 1] = out[n - 2] * (1 - 0.022);
  }
  return enforceMaxDelta(out);
}

function findTailAdjustments(base, condition, source, target, targetValue, pct) {
  const n = base.length;
  const steps = [-0.028, -0.022, -0.018, -0.012, -0.008, -0.004, 0, 0.004, 0.008, 0.012, 0.018, 0.022, 0.028, 0.034];
  let best = null;
  let bestCost = Infinity;

  const tryTail = (mults) => {
    let trial = [...base];
    const from = n - mults.length;
    mults.forEach((m, j) => {
      trial[from + j] = trial[from + j - 1] * (1 + m);
    });
    trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT * 1.25);
    if (!evalOnCloses(trial, condition, source, target, targetValue, pct)) return;
    const cost = mults.reduce((s, m) => s + Math.abs(m), 0);
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

  const coarse = [-0.024, -0.012, 0, 0.012, 0.024];
  for (const d4 of coarse) {
    for (const d3 of coarse) {
      for (const d2 of coarse) {
        for (const d1 of coarse) {
          for (const d0 of coarse) {
            tryTail([d4, d3, d2, d1, d0]);
          }
        }
      }
    }
  }

  if (best) return best;

  for (const d1 of steps) {
    for (const d2 of steps) {
      let trial = [...base];
      trial[n - 2] = trial[n - 3] * (1 + d1);
      trial[n - 1] = trial[n - 2] * (1 + d2);
      trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT * 1.35);
      if (!evalOnCloses(trial, condition, source, target, targetValue, pct)) continue;
      const cost = Math.abs(d1) + Math.abs(d2);
      if (cost < bestCost) {
        bestCost = cost;
        best = trial;
      }
    }
  }

  return best;
}

function solveCloses(condition, source, target, targetValue, pct) {
  const phases = [0, 3, 5, 7, 11, 13, 17, 21, 29, 33, 41, 55];
  const bases = phases.map((ph) => applyTailHints(macdHistoryWalk(TOTAL_CLOSE_BARS, ph), condition));

  if (condition === 'crosses_up' || condition === 'crosses_down') {
    for (const ph of [2, 9, 19, 27, 44]) {
      bases.unshift(applyTailHints(macdHistoryWalk(TOTAL_CLOSE_BARS, ph), condition));
    }
  }

  for (const base of bases) {
    const hit = findTailAdjustments(base, condition, source, target, targetValue, pct);
    if (hit) return hit;
  }

  return enforceMaxDelta(applyTailHints(macdHistoryWalk(TOTAL_CLOSE_BARS, 0), condition));
}

function sliceDisplaySeries(macd, signal, histogram, count = VIS_BAR_COUNT) {
  const n = macd.length;
  const valid = [];
  for (let i = n - 1; i >= 0 && valid.length < count; i--) {
    if (macd[i] != null && signal[i] != null && histogram[i] != null) {
      valid.unshift({
        macd: macd[i],
        signal: signal[i],
        histogram: histogram[i],
      });
    }
  }
  return {
    macd: valid.map((v) => v.macd),
    signal: valid.map((v) => v.signal),
    histogram: valid.map((v) => v.histogram),
  };
}

export function buildMacdPreviewSample(
  condition,
  source,
  target,
  targetValue = 0,
  pctValue = 5,
) {
  const pct = parsePct(pctValue);
  const tgtVal = parseTargetValue(targetValue);
  const closes = solveCloses(condition, source, target, tgtVal, pct);
  const full = calculateMacd(closes);
  const { macd, signal, histogram } = sliceDisplaySeries(
    full.macd,
    full.signal,
    full.histogram,
  );
  const n = histogram.length;
  const holdStart = condition === 'crosses_up' || condition === 'crosses_down'
    ? Math.max(0, n - 2)
    : Math.max(0, n - 5);
  const highlightIndices = condition === 'crosses_up' || condition === 'crosses_down'
    ? [n - 2, n - 1].filter((i) => i >= 0)
    : Array.from({ length: n - holdStart }, (_, j) => holdStart + j);

  return {
    macd,
    signal,
    histogram,
    holdStart,
    highlightIndices,
    newestIndex: n - 1,
    closes,
  };
}

/** Round-1 quality metrics for audit (not just boolean pass). */
export function auditMacdSample(sample, targetValue = 0, target = 'value') {
  const { macd, signal, histogram } = sample;
  const n = histogram.length;
  if (!n) {
    return { ok: false, reason: 'empty' };
  }

  const absHist = histogram.map((h) => Math.abs(h));
  const peakHist = Math.max(...absHist, 0);
  const histSwing = Math.max(...histogram) - Math.min(...histogram);
  const lineSwing = Math.max(
    Math.max(...macd) - Math.min(...macd),
    Math.max(...signal) - Math.min(...signal),
  );

  let zeroCrosses = 0;
  for (let i = 1; i < n; i++) {
    if ((histogram[i - 1] <= 0 && histogram[i] > 0) || (histogram[i - 1] >= 0 && histogram[i] < 0)) {
      zeroCrosses++;
    }
  }

  const peakScale = Math.max(
    peakHist,
    ...macd.map(Math.abs),
    ...signal.map(Math.abs),
    target === 'value' ? Math.abs(targetValue) : 0,
    0.01,
  );
  const avgHistPx = absHist.reduce((s, h) => s + (h / peakScale) * 36, 0) / n;
  const yUsage = (lineSwing / peakScale) * 100;

  const flatLines = lineSwing < peakHist * 0.15 && peakHist > 0.01;
  const tinyHist = avgHistPx < 4;
  const noHistory = zeroCrosses < 1 && n >= 10;

  const issues = [];
  if (tinyHist) issues.push('tiny_hist');
  if (flatLines) issues.push('flat_lines');
  if (noHistory) issues.push('no_zero_cross');
  if (peakHist < 0.05) issues.push('near_zero');

  return {
    ok: issues.length === 0,
    issues,
    peakHist: round2(peakHist),
    histSwing: round2(histSwing),
    lineSwing: round2(lineSwing),
    zeroCrosses,
    avgHistPx: round2(avgHistPx),
    yUsagePct: round2(yUsage),
    barCount: n,
  };
}

function round2(v) {
  return Math.round(v * 100) / 100;
}
