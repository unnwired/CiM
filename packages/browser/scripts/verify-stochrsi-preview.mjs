/** Smoke + in-frame bounds test for StochRSI filter preview. */

import {
  buildStochRsiPreviewSample,
  evalCondition,
  parsePct,
  pointX,
  POINT_COUNT,
  PREVIEW_CHART_H,
  PREVIEW_CHART_TOP,
  PREVIEW_PAD_L,
  PREVIEW_PLOT_W,
  PREVIEW_Y_PAD,
  valToY,
} from '../src/utils/stochrsiFilterPreviewCore.js';

const CHART_TOP = PREVIEW_CHART_TOP;
const CHART_H = PREVIEW_CHART_H;
const Y_PAD = PREVIEW_Y_PAD;
const Y_MIN = CHART_TOP + Y_PAD;
const Y_MAX = CHART_TOP + CHART_H - Y_PAD;
const PAD_L = PREVIEW_PAD_L;

function boundsOk(k, d) {
  for (let i = 0; i < k.length; i++) {
    const yk = valToY(k[i]);
    const yd = valToY(d[i]);
    if (yk < Y_MIN || yk > Y_MAX || yd < Y_MIN || yd > Y_MAX) return false;
    if (pointX(i) < PAD_L - 0.5 || pointX(i) > PAD_L + PREVIEW_PLOT_W + 0.5) return false;
  }
  const swing = Math.max(...k) - Math.min(...k);
  if (swing < 30) return false;
  return true;
}

const conditions = ['above', 'above_eq', 'below', 'below_eq', 'crosses_up', 'crosses_down', 'above_pct', 'below_pct'];
const sources = ['k', 'd'];
const targets = ['value', 'k', 'd'];
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
      const s = buildStochRsiPreviewSample(condition, source, target, 80, 5);
      const n = s.k.length - 1;
      const srcS = source === 'k' ? s.k : s.d;
      const ok = evalCondition(
        condition,
        srcS[n],
        srcS[n - 1],
        target === 'value' ? 80 : (target === 'k' ? s.k[n] : s.d[n]),
        target === 'value' ? 80 : (target === 'k' ? s.k[n - 1] : s.d[n - 1]),
        parsePct(5),
      );
      const inFrame = boundsOk(s.k, s.d);
      if (!ok || !inFrame || s.k.length < POINT_COUNT - 2) {
        console.log('FAIL', { source, target, condition, ok, inFrame, points: s.k.length });
        fail++;
      }
    }
  }
}

console.log('POINT_COUNT', POINT_COUNT);
if (skip) console.log(`skipped ${skip} (pct + value target)`);
console.log(fail ? `${fail} failures` : 'all stochrsi preview combos ok');
