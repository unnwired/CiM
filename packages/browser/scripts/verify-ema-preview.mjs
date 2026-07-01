/** Pure logic smoke test for EMA preview (mirrors EMAFilterPreview.js). */

const BAR_COUNT = 1 + Math.floor((396 - 4) / 6);

function parsePct(v) { const n = parseFloat(String(v)); return Number.isFinite(n) && n > 0 ? n : 5; }
function parsePeriod(v, f = 21) { const n = parseInt(String(v), 10); return Number.isFinite(n) && n >= 1 ? n : f; }

function computeEmaSeries(closes, period) {
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

const MAX_BAR_DELTA_PCT = 0.020;
const MIN_BODY_PCT = 0.012;
const WICK_PCT = 0.008;
const OSCILLATE_DELTAS = [0.004, -0.005, 0.003, -0.004, 0.002, -0.003, 0.005, -0.002];

function enforceMaxDelta(closes, maxPct = MAX_BAR_DELTA_PCT) {
  const out = [closes[0]];
  for (let i = 1; i < closes.length; i++) {
    const prev = out[i - 1];
    out.push(Math.max(prev * (1 - maxPct), Math.min(prev * (1 + maxPct), closes[i])));
  }
  return out;
}

function meanRevertingWalk(barCount, anchor = 100) {
  const closes = [anchor];
  for (let i = 1; i < barCount; i++) {
    const prev = closes[i - 1];
    const pull = (anchor - prev) / prev * 0.06;
    const delta = OSCILLATE_DELTAS[(i - 1) % OSCILLATE_DELTAS.length] + pull;
    closes.push(prev * (1 + delta));
  }
  return enforceMaxDelta(closes, MAX_BAR_DELTA_PCT);
}

function applyTailHints(closes, condition) {
  const n = closes.length;
  if (n < 4) return closes;
  const out = [...closes];
  const up = ['above', 'above_eq', 'above_pct'].includes(condition);
  const down = ['below', 'below_eq', 'below_pct'].includes(condition);
  if (up) out[n - 3] = out[n - 4] * (1 - 0.013);
  else if (down) out[n - 3] = out[n - 4] * (1 + 0.013);
  else if (condition === 'crosses_up') {
    out[n - 2] = out[n - 3] * (1 - 0.012);
    out[n - 1] = out[n - 2] * (1 + 0.016);
  } else if (condition === 'crosses_down') {
    out[n - 2] = out[n - 3] * (1 + 0.012);
    out[n - 1] = out[n - 2] * (1 - 0.016);
  }
  return enforceMaxDelta(out, MAX_BAR_DELTA_PCT);
}

function baseWalkForCondition(condition) {
  return applyTailHints(meanRevertingWalk(BAR_COUNT), condition);
}

function closesToBars(closes) {
  return closes.map((close, i) => {
    const open = i === 0 ? close * (1 - MIN_BODY_PCT * 0.5) : closes[i - 1];
    const wick = close * WICK_PCT;
    return { open, high: Math.max(open, close) + wick, low: Math.min(open, close) - wick, close };
  });
}

function targetAtBar(bar, emaT, i, target) {
  if (target === 'open') return bar.open;
  if (target === 'high') return bar.high;
  if (target === 'low') return bar.low;
  if (target === 'ema') return emaT[i];
  return bar.close;
}

function evalCondition(c, src, srcP, tgt, tgtP, pct) {
  if (c === 'above') return src > tgt;
  if (c === 'above_eq') return src >= tgt;
  if (c === 'below') return src < tgt;
  if (c === 'below_eq') return src <= tgt;
  if (c === 'crosses_up') return srcP <= tgtP && src > tgt;
  if (c === 'crosses_down') return srcP >= tgtP && src < tgt;
  if (c === 'above_pct') return tgt !== 0 && src > tgt && ((src - tgt) / Math.abs(tgt)) * 100 <= pct;
  if (c === 'below_pct') return tgt !== 0 && src < tgt && ((tgt - src) / Math.abs(tgt)) * 100 <= pct;
  return true;
}

function pack(closes, emaP, tgtEmaP, target) {
  const bars = closesToBars(closes);
  const emaSource = computeEmaSeries(closes, emaP);
  const emaTarget = target === 'ema' ? computeEmaSeries(closes, tgtEmaP) : null;
  return { bars, emaSource, emaTarget };
}

function evalOn(closes, condition, target, emaP, tgtEmaP, pct) {
  const { bars, emaSource, emaTarget } = pack(closes, emaP, tgtEmaP, target);
  const n = closes.length;
  return evalCondition(condition, emaSource[n - 1], emaSource[n - 2],
    targetAtBar(bars[n - 1], emaTarget, n - 1, target),
    targetAtBar(bars[n - 2], emaTarget, n - 2, target), pct);
}

function findTail(base, condition, target, emaP, tgtEmaP, pct) {
  const n = base.length;
  const steps = [-0.009, -0.006, -0.003, 0, 0.003, 0.006, 0.009];
  let best = null, bestCost = Infinity;
  const tryTail = (deltas) => {
    let trial = [...base];
    const from = n - deltas.length;
    deltas.forEach((d, j) => { trial[from + j] *= 1 + d; });
    trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT);
    if (!evalOn(trial, condition, target, emaP, tgtEmaP, pct)) return;
    const cost = deltas.reduce((s, d) => s + Math.abs(d), 0);
    if (cost < bestCost) { bestCost = cost; best = trial; }
  };
  for (const d3 of steps) for (const d2 of steps) for (const d1 of steps) for (const d0 of steps) tryTail([d3, d2, d1, d0]);
  if (best) return best;
  const wider = [-0.012, -0.009, -0.006, -0.003, 0, 0.003, 0.006, 0.009, 0.012];
  for (const d1 of wider) for (const d2 of wider) {
    let trial = [...base];
    trial[n - 2] *= 1 + d1; trial[n - 1] *= 1 + d2;
    trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT * 1.1);
    if (!evalOn(trial, condition, target, emaP, tgtEmaP, pct)) continue;
    const cost = Math.abs(d1) + Math.abs(d2);
    if (cost < bestCost) { bestCost = cost; best = trial; }
  }
  return best;
}

function fineTailSolve(base, condition, target, emaP, tgtEmaP, pct) {
  const n = base.length;
  let best = null, bestCost = Infinity;
  const fine = [-0.009, -0.0075, -0.006, -0.0045, -0.003, -0.0015, 0, 0.0015, 0.003, 0.0045, 0.006, 0.0075, 0.009];
  const tryLast = (kPrev, kLast) => {
    let trial = [...base];
    trial[n - 2] = trial[n - 3] * (1 + kPrev);
    trial[n - 1] = trial[n - 2] * (1 + kLast);
    trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT);
    if (!evalOn(trial, condition, target, emaP, tgtEmaP, pct)) return;
    const cost = Math.abs(kPrev) + Math.abs(kLast);
    if (cost < bestCost) { bestCost = cost; best = trial; }
  };
  for (const kPrev of fine) for (const kLast of fine) tryLast(kPrev, kLast);
  if (best) return best;
  for (const k0 of fine) for (const k1 of fine) for (const k2 of fine) {
    let trial = [...base];
    trial[n - 3] = trial[n - 4] * (1 + k0);
    trial[n - 2] = trial[n - 3] * (1 + k1);
    trial[n - 1] = trial[n - 2] * (1 + k2);
    trial = enforceMaxDelta(trial, MAX_BAR_DELTA_PCT);
    if (!evalOn(trial, condition, target, emaP, tgtEmaP, pct)) continue;
    const cost = Math.abs(k0) + Math.abs(k1) + Math.abs(k2);
    if (cost < bestCost) { bestCost = cost; best = trial; }
  }
  return best;
}

function build(condition, target, pctV = 5, emaP = 21, tgtEmaP = 50) {
  const pct = parsePct(pctV);
  const bases = [baseWalkForCondition(condition), meanRevertingWalk(BAR_COUNT),
    baseWalkForCondition(condition === 'crosses_up' ? 'below' : condition === 'crosses_down' ? 'above' : condition)];
  let closes = null;
  for (const b of bases) {
    closes = findTail(b, condition, target, emaP, tgtEmaP, pct);
    if (closes) break;
    closes = fineTailSolve(b, condition, target, emaP, tgtEmaP, pct);
    if (closes) break;
  }
  if (!closes) closes = enforceMaxDelta(meanRevertingWalk(BAR_COUNT), MAX_BAR_DELTA_PCT);
  return pack(closes, emaP, tgtEmaP, target);
}

const conditions = ['above', 'above_eq', 'below', 'below_eq', 'crosses_up', 'crosses_down', 'above_pct', 'below_pct'];
const targets = ['open', 'high', 'low', 'price', 'ema'];
let fail = 0;
console.log('BAR_COUNT', BAR_COUNT);
for (const c of conditions) for (const t of targets) {
  const s = build(c, t);
  const n = s.bars.length;
  const ok = evalCondition(c, s.emaSource[n-1], s.emaSource[n-2],
    targetAtBar(s.bars[n-1], s.emaTarget, n-1, t),
    targetAtBar(s.bars[n-2], s.emaTarget, n-2, t), 5);
  const maxD = Math.max(...s.bars.slice(1).map((b, j) => Math.abs(b.close - s.bars[j].close) / s.bars[j].close));
  if (!ok) { console.log('FAIL', c, t, { ok, maxD: maxD.toFixed(4) }); fail++; }
}
console.log(fail ? `${fail} failures` : 'all 40 combos ok');
