/** Smoke test — real MACD calc preview (imports macdFilterPreviewCore). */

import {
  buildMacdPreviewSample,
  evalCondition,
  PREVIEW_BAR_W,
  PREVIEW_PAD_L,
  PREVIEW_PAD_R,
  PREVIEW_SLOT_PX,
  PREVIEW_VIEW_W,
  VIS_BAR_COUNT,
} from '../src/utils/macdFilterPreviewCore.js';

const VIEW_W = PREVIEW_VIEW_W;
const PAD_L = PREVIEW_PAD_L;
const CHART_TOP = 6;
const CHART_H = 92;
const BAR_W = PREVIEW_BAR_W;
const SLOT_PX = PREVIEW_SLOT_PX;
const Y_PAD = 6;
const Y_MIN = CHART_TOP + Y_PAD;
const Y_MAX = CHART_TOP + CHART_H - Y_PAD;
const PLOT_W = VIEW_W - PAD_L - PREVIEW_PAD_R;
const plotRight = PAD_L + PLOT_W;

function barX(i) {
  return PAD_L + BAR_W / 2 + i * SLOT_PX;
}

function computeScalePeak(macd, signal, histogram, targetValue = 0, target = 'value') {
  let peak = 1;
  for (const v of histogram) peak = Math.max(peak, Math.abs(v));
  for (const v of macd) peak = Math.max(peak, Math.abs(v));
  for (const v of signal) peak = Math.max(peak, Math.abs(v));
  if (target === 'value') peak = Math.max(peak, Math.abs(targetValue));
  return peak;
}

function valueToY(v, peakAbs, zeroY) {
  const half = CHART_H / 2 - Y_PAD;
  const y = zeroY - (v / peakAbs) * half;
  return Math.min(Y_MAX, Math.max(Y_MIN, y));
}

function boundsOk(s, target, targetValue) {
  const zeroY = CHART_TOP + CHART_H / 2;
  const peak = computeScalePeak(s.macd, s.signal, s.histogram, targetValue, target);
  const n = s.histogram.length;
  if (barX(n - 1) + BAR_W / 2 > plotRight + 0.5) return false;
  for (let i = 0; i < n; i++) {
    if (valueToY(s.histogram[i], peak, zeroY) < Y_MIN || valueToY(s.histogram[i], peak, zeroY) > Y_MAX) return false;
    if (valueToY(s.macd[i], peak, zeroY) < Y_MIN || valueToY(s.macd[i], peak, zeroY) > Y_MAX) return false;
    if (valueToY(s.signal[i], peak, zeroY) < Y_MIN || valueToY(s.signal[i], peak, zeroY) > Y_MAX) return false;
  }
  return true;
}

const conditions = ['above', 'above_eq', 'below', 'below_eq', 'crosses_up', 'crosses_down', 'above_pct', 'below_pct'];
const sources = ['macd', 'signal'];
const targets = ['value', 'macd', 'signal'];
let fail = 0;
let skip = 0;

for (const source of sources) {
  for (const target of targets) {
    if (source === target) continue;
    for (const condition of conditions) {
      if ((condition === 'above_pct' || condition === 'below_pct') && target === 'value') {
        skip++;
        continue;
      }
      const s = buildMacdPreviewSample(condition, source, target, 0, 5);
      const n = s.histogram.length - 1;
      const srcS = source === 'signal' ? s.signal : s.macd;
      const ok = evalCondition(
        condition,
        srcS[n],
        srcS[n - 1],
        target === 'value' ? 0 : (target === 'signal' ? s.signal[n] : s.macd[n]),
        target === 'value' ? 0 : (target === 'signal' ? s.signal[n - 1] : s.macd[n - 1]),
        5,
      );
      const inFrame = boundsOk(s, target, 0);
      const peak = Math.max(...s.histogram.map((h) => Math.abs(h)));
      if (!ok || peak < 0.01 || !inFrame || s.histogram.length < VIS_BAR_COUNT - 4) {
        console.log('FAIL', { source, target, condition, ok, peak, inFrame, bars: s.histogram.length });
        fail++;
      }
    }
  }
}

console.log('VIS_BAR_COUNT', VIS_BAR_COUNT);
if (skip) console.log(`skipped ${skip} (pct + value target)`);
console.log(fail ? `${fail} failures` : 'all macd preview combos ok (real calc)');
