/**
 * MACD calculator — mirrors packages/server/server.py calculate_macd (12/26/9).
 */

function emaFull(data, period) {
  const k = 2 / (period + 1);
  let ema = data[0];
  const out = [ema];
  for (let i = 1; i < data.length; i++) {
    ema = data[i] * k + ema * (1 - k);
    out.push(ema);
  }
  return out;
}

function round2(v) {
  return Math.round(v * 100) / 100;
}

export function calculateMacd(closes, fast = 12, slow = 26, signalPeriod = 9) {
  const n = closes.length;
  if (n < slow + signalPeriod) {
    return {
      macd: Array(n).fill(null),
      signal: Array(n).fill(null),
      histogram: Array(n).fill(null),
    };
  }

  const fastEma = emaFull(closes, fast);
  const slowEma = emaFull(closes, slow);
  const macdRaw = fastEma.map((f, i) => round2(f - slowEma[i]));

  const sigInput = macdRaw.slice(slow - 1);
  const sigEma = emaFull(sigInput, signalPeriod);

  const macdOut = [...Array(slow - 1).fill(null), ...macdRaw.slice(slow - 1)];
  const sigOut = [
    ...Array(slow - 1 + signalPeriod - 1).fill(null),
    ...sigEma.slice(signalPeriod - 1).map(round2),
  ];

  const histOut = macdOut.map((m, i) => {
    const s = sigOut[i];
    return m != null && s != null ? round2(m - s) : null;
  });

  return { macd: macdOut, signal: sigOut, histogram: histOut };
}

export const MACD_FAST = 12;
export const MACD_SLOW = 26;
export const MACD_SIGNAL = 9;
export const MACD_MIN_CLOSES = MACD_SLOW + MACD_SIGNAL + 1;
