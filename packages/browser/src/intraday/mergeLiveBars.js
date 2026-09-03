function finite(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** OHLC fields must be strictly positive — 0 poisons candle merge (0→price spike). */
function positiveFinite(v) {
  const n = finite(v);
  return n != null && n > 0 ? n : null;
}

function istTodayYmd() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
}

function round2(n) {
  return Math.round(n * 100) / 100;
}

function pctChange(px, prev) {
  const p = positiveFinite(px);
  const r = positiveFinite(prev);
  if (p == null || r == null) return null;
  return ((p - r) / r) * 100;
}

/** Clamp invalid EOD OHLC (zeros) before rendering — prevents 0→price spikes from bad DB rows. */
export function sanitizeBarsForDisplay(bars) {
  if (!Array.isArray(bars) || !bars.length) return bars || [];
  return bars.map((b, i) => {
    const prevClose = i > 0 ? positiveFinite(bars[i - 1].close) : null;
    const close = positiveFinite(b.close);
    if (close == null) return { ...b };
    let open = positiveFinite(b.open);
    let high = positiveFinite(b.high);
    let low = positiveFinite(b.low);
    if (open == null) open = prevClose ?? close;
    if (high == null) high = Math.max(open, close);
    if (low == null) low = Math.min(open, close);
    high = Math.max(high, open, close);
    low = Math.min(low, open, close);
    return {
      ...b,
      open: round2(open),
      high: round2(high),
      low: round2(low),
      close: round2(close),
    };
  });
}

function istHourMinute(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(now);
  const h = Number(parts.find((p) => p.type === 'hour')?.value);
  const m = Number(parts.find((p) => p.type === 'minute')?.value);
  return { mins: h * 60 + m };
}

/** True from 09:15 IST — pre-open quotes must not paint today's daily candle. */
export function isAfterNseCashOpen(now = new Date()) {
  const { mins } = istHourMinute(now);
  return mins >= 9 * 60 + 15;
}

/** Port of server/movers_live.merge_live_into_daily_bars for client-side overlay. */
export function mergeLiveIntoDailyBars(bars, snapshot, now = new Date()) {
  if (!Array.isArray(bars) || !bars.length || !snapshot) {
    return { bars: bars || [], dayChangePct: null };
  }
  // Pre-open quotes often reuse prior-session OHLC/volume as "today".
  if (!isAfterNseCashOpen(now)) {
    return { bars, dayChangePct: null };
  }
  const today = istTodayYmd();
  let px = positiveFinite(snapshot.price);
  if (px == null) return { bars, dayChangePct: null };
  px = Math.round(px * 100) / 100;

  const prev = positiveFinite(snapshot.previous_close);
  let vol = finite(snapshot.volume);
  if (vol == null || vol < 0) vol = 0;

  const out = bars.map((b) => ({ ...b }));
  const last = out[out.length - 1];
  const lastDay = String(last.time || '').slice(0, 10);

  if (lastDay > today) {
    return { bars, dayChangePct: null };
  }

  const lastOpen = positiveFinite(last.open);
  const lastHigh = positiveFinite(last.high);
  const lastLow = positiveFinite(last.low);

  let hi = positiveFinite(snapshot.high);
  let lo = positiveFinite(snapshot.low);
  // Never use previous_close or LTP as today's open — wait for session seed (9:15).
  let op = positiveFinite(snapshot.open);
  if (op == null && lastDay === today && lastOpen != null) op = lastOpen;
  if (op == null) {
    if (lastDay === today && lastOpen != null) {
      last.close = px;
      const hiTouch = positiveFinite(snapshot.high) ?? px;
      const loTouch = positiveFinite(snapshot.low) ?? px;
      last.high = round2(Math.max(lastHigh ?? px, hiTouch, px));
      last.low = round2(Math.min(lastLow ?? px, loTouch, px));
      if (vol > 0) last.volume = round2(vol);
      last.live = true;
      const dayChangePct = pctChange(px, prev) ?? finite(snapshot.change_pct);
      return { bars: out, dayChangePct };
    }
    return { bars, dayChangePct: pctChange(px, prev) ?? finite(snapshot.change_pct) };
  }
  if (hi == null) hi = px;
  if (lo == null) lo = px;
  hi = Math.max(hi, px, op);
  lo = Math.min(lo, px, op);

  if (lastDay === today) {
    last.close = px;
    // Prefer live/session snapshot open (9:15) over a prior LTP stub on the bar.
    last.open = round2(op ?? lastOpen ?? px);
    last.high = round2(Math.max(lastHigh ?? px, hi, px, op));
    last.low = round2(Math.min(lastLow ?? px, lo, px, op));
    if (vol > 0) last.volume = round2(vol);
    last.live = true;
  } else {
    out.push({
      time: today,
      open: round2(op),
      high: round2(hi),
      low: round2(lo),
      close: px,
      volume: round2(vol),
      live: true,
    });
  }

  const dayChangePct = pctChange(px, prev) ?? finite(snapshot.change_pct);
  return { bars: out, dayChangePct };
}

/** Port of server session 4H buckets for client-side overlay (09:15 / 13:15 IST). */
function session4hBarStartUnix(sessionDate, bucket) {
  const h = bucket === 1 ? 9 : 13;
  const iso = `${sessionDate}T${String(h).padStart(2, '0')}:15:00+05:30`;
  return Math.floor(new Date(iso).getTime() / 1000);
}

function current4hSessionTarget(now = new Date()) {
  const today = istTodayYmd();
  const { mins } = istHourMinute(now);
  const open = 9 * 60 + 15;
  const mid = 13 * 60 + 15;
  const close = 15 * 60 + 30;
  if (mins < open) return null;
  if (mins >= close) return { sessionDate: today, bucket: 2 };
  return { sessionDate: today, bucket: mins < mid ? 1 : 2 };
}

export function mergeLiveInto4hBars(bars, snapshot) {
  if (!Array.isArray(bars) || !bars.length || !snapshot) {
    return { bars: bars || [], dayChangePct: null };
  }
  const target = current4hSessionTarget();
  if (!target) return { bars, dayChangePct: null };

  let px = positiveFinite(snapshot.price);
  if (px == null) return { bars, dayChangePct: null };
  px = round2(px);

  const prev = positiveFinite(snapshot.previous_close);
  let vol = finite(snapshot.volume);
  if (vol == null || vol < 0) vol = 0;

  const barUnix = session4hBarStartUnix(target.sessionDate, target.bucket);
  const out = bars.map((b) => ({ ...b }));
  let idx = out.findIndex((b) => Number(b.time) === barUnix);
  if (idx < 0) idx = out.length - 1;

  const bar = out[idx];
  const lastOpen = positiveFinite(bar.open);
  const lastHigh = positiveFinite(bar.high);
  const lastLow = positiveFinite(bar.low);

  let hi = positiveFinite(snapshot.high);
  let lo = positiveFinite(snapshot.low);
  let op = positiveFinite(snapshot.open);
  if (op == null && lastOpen != null) op = lastOpen;
  if (op == null) {
    if (Number(bar.time) === barUnix && lastOpen != null) {
      bar.close = px;
      const hiTouch = positiveFinite(snapshot.high) ?? px;
      const loTouch = positiveFinite(snapshot.low) ?? px;
      bar.high = round2(Math.max(lastHigh ?? px, hiTouch, px));
      bar.low = round2(Math.min(lastLow ?? px, loTouch, px));
      if (vol > 0) bar.volume = round2(vol);
      bar.live = true;
      const dayChangePct = pctChange(px, prev) ?? finite(snapshot.change_pct);
      return { bars: out, dayChangePct };
    }
    return { bars, dayChangePct: pctChange(px, prev) ?? finite(snapshot.change_pct) };
  }
  if (hi == null) hi = px;
  if (lo == null) lo = px;
  hi = Math.max(hi, px, op);
  lo = Math.min(lo, px, op);

  if (Number(bar.time) === barUnix) {
    bar.close = px;
    bar.open = round2(lastOpen ?? op);
    bar.high = round2(Math.max(lastHigh ?? px, hi, px));
    bar.low = round2(Math.min(lastLow ?? px, lo, px));
    if (vol > 0) bar.volume = round2(vol);
    bar.live = true;
  } else if (barUnix > Number(bar.time)) {
    out.push({
      time: barUnix,
      open: round2(op),
      high: round2(hi),
      low: round2(lo),
      close: px,
      volume: round2(vol),
      live: true,
    });
  } else {
    return { bars, dayChangePct: null };
  }

  const dayChangePct = pctChange(px, prev) ?? finite(snapshot.change_pct);
  return { bars: out, dayChangePct };
}

export function mergeLiveIntoChartBars(bars, snapshot, timeframe) {
  const tf = String(timeframe || '1D').trim().toUpperCase();
  if (tf === '1D') return mergeLiveIntoDailyBars(bars, snapshot);
  if (tf === '4H') return mergeLiveInto4hBars(bars, snapshot);
  if (!bars?.length || !snapshot) return { bars: bars || [], dayChangePct: null };
  const px = positiveFinite(snapshot.price);
  if (px == null) return { bars, dayChangePct: null };
  const prev = positiveFinite(snapshot.previous_close);
  const hi = positiveFinite(snapshot.high) ?? px;
  const lo = positiveFinite(snapshot.low) ?? px;
  const out = bars.map((b) => ({ ...b }));
  const last = out[out.length - 1];
  const lastHigh = positiveFinite(last.high);
  const lastLow = positiveFinite(last.low);
  last.close = round2(px);
  last.high = round2(Math.max(lastHigh ?? px, hi, px));
  last.low = round2(Math.min(lastLow ?? px, lo, px));
  last.live = true;
  return { bars: out, dayChangePct: pctChange(px, prev) ?? finite(snapshot.change_pct) };
}
