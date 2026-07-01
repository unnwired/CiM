/**
 * MACD Round 1 — verify eval + in-frame bounds + visual quality audit per condition.
 * Imports real-calc core (same path as MACDFilterPreview).
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import {
  buildMacdPreviewSample,
  evalCondition,
  auditMacdSample,
  PREVIEW_BAR_W,
  PREVIEW_PAD_L,
  PREVIEW_PAD_R,
  PREVIEW_SLOT_PX,
  PREVIEW_VIEW_W,
  VIS_BAR_COUNT,
  parsePct,
} from '../src/utils/macdFilterPreviewCore.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(__dirname, '../../../runtime/macd-round1');

const VIEW_W = PREVIEW_VIEW_W;
const VIEW_H = 128;
const PAD_L = PREVIEW_PAD_L;
const PAD_R = PREVIEW_PAD_R;
const CHART_TOP = 6;
const CHART_H = 92;
const BAR_W = PREVIEW_BAR_W;
const SLOT_PX = PREVIEW_SLOT_PX;
const Y_PAD = 6;
const Y_MIN = CHART_TOP + Y_PAD;
const Y_MAX = CHART_TOP + CHART_H - Y_PAD;
const PLOT_W = VIEW_W - PAD_L - PAD_R;
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

function histColor(h, prev) {
  const expanding = prev == null || Math.abs(h) >= Math.abs(prev);
  if (h >= 0) return expanding ? '#3fb950' : '#3fb95066';
  return expanding ? '#f85149' : '#f8514966';
}

function renderSvg(sample, label) {
  const { macd, signal, histogram } = sample;
  const zeroY = CHART_TOP + CHART_H / 2;
  const peak = computeScalePeak(macd, signal, histogram, 0, 'value');
  const valY = (v) => valueToY(v, peak, zeroY);

  let body = '';
  body += `<line x1="${PAD_L}" y1="${zeroY}" x2="${VIEW_W - PAD_R}" y2="${zeroY}" stroke="#6e7681" stroke-width="1"/>`;

  histogram.forEach((h, i) => {
    const barTop = valY(h);
    const barH = Math.max(2, Math.abs(barTop - zeroY));
    const y = Math.min(barTop, zeroY);
    const prev = i > 0 ? histogram[i - 1] : null;
    body += `<rect x="${barX(i) - BAR_W / 2}" y="${y}" width="${BAR_W}" height="${barH}" rx="2" fill="${histColor(h, prev)}"/>`;
  });

  const linePath = (series) => series.map((v, i) => `${barX(i)},${valY(v)}`).join(' ');
  body += `<polyline points="${linePath(signal)}" fill="none" stroke="#d29922" stroke-width="2"/>`;
  body += `<polyline points="${linePath(macd)}" fill="none" stroke="#58a6ff" stroke-width="2"/>`;

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${VIEW_W} ${VIEW_H}" width="${VIEW_W}" height="${VIEW_H}">
  <rect width="100%" height="100%" fill="#161b22"/>
  <text x="8" y="14" fill="#8b949e" font-size="10" font-family="monospace">${label}</text>
  <g>${body}</g>
</svg>`;
}

const conditions = ['above', 'above_eq', 'below', 'below_eq', 'crosses_up', 'crosses_down', 'above_pct', 'below_pct'];
const sources = ['macd', 'signal'];
const targets = ['value', 'macd', 'signal'];

let evalFail = 0;
let boundsFail = 0;
let qualityWarn = 0;
let skip = 0;
const rows = [];

fs.mkdirSync(OUT_DIR, { recursive: true });

for (const source of sources) {
  for (const target of targets) {
    if (source === target) continue;
    for (const condition of conditions) {
      if ((condition === 'above_pct' || condition === 'below_pct') && target === 'value') {
        skip++;
        continue;
      }
      const pct = 5;
      const tv = 0;
      const sample = buildMacdPreviewSample(condition, source, target, tv, pct);
      const n = sample.histogram.length - 1;
      const srcS = source === 'signal' ? sample.signal : sample.macd;
      const evalOk = evalCondition(
        condition,
        srcS[n],
        srcS[n - 1],
        target === 'value' ? tv : (target === 'signal' ? sample.signal[n] : sample.macd[n]),
        target === 'value' ? tv : (target === 'signal' ? sample.signal[n - 1] : sample.macd[n - 1]),
        pct,
      );
      const inFrame = boundsOk(sample, target, tv);
      const audit = auditMacdSample(sample, tv, target);

      if (!evalOk) evalFail++;
      if (!inFrame) boundsFail++;

      const qualityOk = audit.ok;
      if (!qualityOk) qualityWarn++;

      const slug = `${source}_${target}_${condition}`;
      fs.writeFileSync(path.join(OUT_DIR, `${slug}.svg`), renderSvg(sample, slug));

      rows.push({
        slug,
        evalOk,
        inFrame,
        qualityOk,
        issues: audit.issues.join(',') || '—',
        peakHist: audit.peakHist,
        histSwing: audit.histSwing,
        zeroCrosses: audit.zeroCrosses,
        avgHistPx: audit.avgHistPx,
        yUsagePct: audit.yUsagePct,
        newestHist: sample.histogram[n],
        newestMacd: sample.macd[n],
        newestSignal: sample.signal[n],
      });
    }
  }
}

console.log('=== MACD Round 1 audit ===');
console.log(`VIS_BAR_COUNT: ${VIS_BAR_COUNT}`);
console.log(`SVG output: ${OUT_DIR}`);
console.log(`Combos: ${rows.length}  skipped: ${skip}`);
console.log(`Eval failures: ${evalFail}`);
console.log(`Bounds failures: ${boundsFail}`);
console.log(`Quality warnings: ${qualityWarn}`);
console.log('');

const hdr = 'slug'.padEnd(28)
  + 'eval'.padEnd(6)
  + 'frame'.padEnd(7)
  + 'qual'.padEnd(6)
  + 'issues'.padEnd(18)
  + 'pkHist'.padEnd(8)
  + 'hSwing'.padEnd(8)
  + 'zx'.padEnd(4)
  + 'hPx'.padEnd(6)
  + 'yUse%';
console.log(hdr);
console.log('-'.repeat(hdr.length));

for (const r of rows) {
  console.log(
    r.slug.padEnd(28)
      + String(r.evalOk).padEnd(6)
      + String(r.inFrame).padEnd(7)
      + String(r.qualityOk).padEnd(6)
      + r.issues.padEnd(18)
      + String(r.peakHist).padEnd(8)
      + String(r.histSwing).padEnd(8)
      + String(r.zeroCrosses).padEnd(4)
      + String(r.avgHistPx).padEnd(6)
      + String(r.yUsagePct),
  );
}

const bad = rows.filter((r) => !r.evalOk || !r.inFrame || !r.qualityOk);
if (bad.length) {
  console.log('\n--- needs Round 2 attention ---');
  bad.forEach((r) => console.log(`  ${r.slug}: eval=${r.evalOk} frame=${r.inFrame} issues=${r.issues}`));
  process.exitCode = 1;
} else {
  console.log('\nAll combos pass eval, bounds, and quality gates.');
}
