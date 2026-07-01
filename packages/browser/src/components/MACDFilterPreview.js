import React, { useMemo } from 'react';
import {
  buildMacdPreviewSample,
  parseTargetValue,
  PREVIEW_BAR_W,
  PREVIEW_GAP_PX,
  PREVIEW_PAD_L,
  PREVIEW_PAD_R,
  PREVIEW_SLOT_PX,
  PREVIEW_VIEW_W,
  VIS_BAR_COUNT,
} from '../utils/macdFilterPreviewCore';

const GREEN = '#3fb950';
const GREEN_DIM = '#3fb95066';
const RED = '#f85149';
const RED_DIM = '#f8514966';
const MACD_LINE = '#58a6ff';
const SIGNAL_LINE = '#d29922';
const TARGET_LINE = '#8b949e';
const ZERO_LINE = '#6e7681';

const VIEW_W = PREVIEW_VIEW_W;
const VIEW_H = 128;
const PAD_L = PREVIEW_PAD_L;
const PAD_R = PREVIEW_PAD_R;
const CHART_TOP = 6;
const CHART_H = 92;

const PLOT_W = VIEW_W - PAD_L - PAD_R;
const BAR_W = PREVIEW_BAR_W;
const GAP_PX = PREVIEW_GAP_PX;
const SLOT_PX = PREVIEW_SLOT_PX;

const LINE_STROKE = 2;
const Y_PAD = 6;
const Y_MIN = CHART_TOP + Y_PAD;
const Y_MAX = CHART_TOP + CHART_H - Y_PAD;

export { VIS_BAR_COUNT };

function parsePct(value) {
  const n = parseFloat(String(value));
  return Number.isFinite(n) && n > 0 ? n : 5;
}

function barX(index) {
  return PAD_L + BAR_W / 2 + index * SLOT_PX;
}

export function computeScalePeak(macd, signal, histogram, targetValue = 0, target = 'value') {
  let peak = 1;
  for (const v of histogram) peak = Math.max(peak, Math.abs(v));
  for (const v of macd) peak = Math.max(peak, Math.abs(v));
  for (const v of signal) peak = Math.max(peak, Math.abs(v));
  if (target === 'value') peak = Math.max(peak, Math.abs(targetValue));
  return peak;
}

function clampY(y) {
  return Math.min(Y_MAX, Math.max(Y_MIN, y));
}

function valueToY(v, peakAbs, zeroY) {
  const half = CHART_H / 2 - Y_PAD;
  return clampY(zeroY - (v / peakAbs) * half);
}

export { evalCondition } from '../utils/macdFilterPreviewCore';
export { buildMacdPreviewSample };

function targetLevelAt(macd, signal, target, targetValue, index) {
  if (target === 'value') return targetValue;
  if (target === 'signal') return signal[index];
  return macd[index];
}

function plotLabel(key) {
  if (key === 'signal') return 'Signal';
  if (key === 'value') return 'Value';
  return 'Level';
}

export function getMacdPreviewCaption(condition, source, target, targetValue, pctValue = 5) {
  const pct = parsePct(pctValue);
  const src = source === 'signal' ? 'MACD Signal' : 'MACD Level';
  const tgt = target === 'value'
    ? `value ${parseTargetValue(targetValue)}`
    : target === 'signal' ? 'MACD Signal' : 'MACD Level';

  switch (condition) {
    case 'above':
      return `On the newest bar (right), ${src} sits above ${tgt}. Histogram = Level − Signal.`;
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
      return `${src} is more than ${pct}% above ${tgt} on the newest bar.`;
    case 'below_pct':
      return `${src} is more than ${pct}% below ${tgt} on the newest bar.`;
    default:
      return `${src} compared to ${tgt}.`;
  }
}

function histBarColor(v, prev) {
  const expanding = prev == null || Math.abs(v) >= Math.abs(prev);
  if (v >= 0) return expanding ? GREEN : GREEN_DIM;
  return expanding ? RED : RED_DIM;
}

function linePathFromSeries(series, peakAbs, zeroY) {
  return series.map((v, i) => {
    const y = valueToY(v, peakAbs, zeroY);
    return `${barX(i)},${y}`;
  }).join(' ');
}

function LegendSwatch({ x, y, color, dash }) {
  if (dash) {
    return (
      <line x1={x} y1={y} x2={x + 14} y2={y} stroke={color} strokeWidth={2} strokeDasharray="3 2" />
    );
  }
  return <line x1={x} y1={y} x2={x + 14} y2={y} stroke={color} strokeWidth={LINE_STROKE} strokeLinecap="round" />;
}

export default function MACDFilterPreview({
  source,
  condition,
  target,
  targetValue,
  pctValue,
}) {
  const sample = useMemo(
    () => buildMacdPreviewSample(condition, source, target, targetValue, pctValue),
    [condition, source, target, targetValue, pctValue],
  );
  const caption = useMemo(
    () => getMacdPreviewCaption(condition, source, target, targetValue, pctValue),
    [condition, source, target, targetValue, pctValue],
  );

  const { macd, signal, histogram, highlightIndices, newestIndex, holdStart } = sample;
  const zeroY = CHART_TOP + CHART_H / 2;
  const tgtVal = parseTargetValue(targetValue);
  const peakAbs = computeScalePeak(macd, signal, histogram, tgtVal, target);
  const halfSlot = SLOT_PX * 0.48;

  const srcSeries = source === 'signal' ? signal : macd;
  const newestX = barX(newestIndex);
  const valY = (v) => valueToY(v, peakAbs, zeroY);
  const newestSrcY = valY(srcSeries[newestIndex]);
  const newestTgtY = valY(targetLevelAt(macd, signal, target, tgtVal, newestIndex));

  const showPctBand = (condition === 'above_pct' || condition === 'below_pct') && target !== 'value';
  const tgtSeries = target === 'signal' ? signal : macd;

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-tertiary)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '8px 10px 6px',
        overflow: 'hidden',
        maxWidth: VIEW_W + 20,
      }}
    >
      <div style={{
        fontSize: 10,
        color: 'var(--text-muted)',
        marginBottom: 6,
        letterSpacing: '0.04em',
        display: 'flex',
        justifyContent: 'space-between',
        gap: 8,
      }}
      >
        <span>EXAMPLE — MACD panel ({VIS_BAR_COUNT} bars · older ← → newer)</span>
        {(condition === 'crosses_up' || condition === 'crosses_down') && (
          <span style={{ flexShrink: 0 }}>cross at right edge</span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        width="100%"
        height={VIEW_H}
        style={{ display: 'block', maxWidth: VIEW_W, overflow: 'hidden' }}
        preserveAspectRatio="xMidYMid meet"
        aria-hidden
      >
        <defs>
          <clipPath id="macd-filter-plot-clip">
            <rect x={PAD_L} y={CHART_TOP} width={PLOT_W} height={CHART_H} />
          </clipPath>
        </defs>

        <g clipPath="url(#macd-filter-plot-clip)">
          <line
            x1={PAD_L}
            y1={zeroY}
            x2={VIEW_W - PAD_R}
            y2={zeroY}
            stroke={ZERO_LINE}
            strokeWidth={1}
          />

          {target === 'value' && Math.abs(tgtVal) > 0.001 && (
            <line
              x1={PAD_L}
              y1={valY(tgtVal)}
              x2={VIEW_W - PAD_R}
              y2={valY(tgtVal)}
              stroke={TARGET_LINE}
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
          )}

          {histogram.map((h, i) => {
            const barTop = valueToY(h, peakAbs, zeroY);
            const barH = Math.abs(barTop - zeroY);
            const prev = i > 0 ? histogram[i - 1] : null;
            return (
              <rect
                key={`h-${i}`}
                x={barX(i) - BAR_W / 2}
                y={Math.min(barTop, zeroY)}
                width={BAR_W}
                height={Math.max(2, barH)}
                rx={2}
                fill={histBarColor(h, prev)}
              />
            );
          })}

          {highlightIndices.map((hi) => (
            <rect
              key={`hl-${hi}`}
              x={barX(hi) - halfSlot}
              y={CHART_TOP}
              width={halfSlot * 2}
              height={CHART_H}
              fill="rgba(56,139,253,0.06)"
              stroke="rgba(56,139,253,0.22)"
              strokeWidth={1}
              rx={2}
            />
          ))}

          {showPctBand && (
            <polygon
              points={(() => {
                const pts = [];
                for (let i = holdStart; i <= newestIndex; i++) {
                  pts.push(`${barX(i)},${valY(srcSeries[i])}`);
                }
                for (let i = newestIndex; i >= holdStart; i--) {
                  pts.push(`${barX(i)},${valY(tgtSeries[i])}`);
                }
                return pts.join(' ');
              })()}
              fill="rgba(88,166,255,0.1)"
              stroke="rgba(88,166,255,0.28)"
              strokeWidth={1}
            />
          )}

          <polyline
            points={linePathFromSeries(signal, peakAbs, zeroY)}
            fill="none"
            stroke={SIGNAL_LINE}
            strokeWidth={LINE_STROKE}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <polyline
            points={linePathFromSeries(macd, peakAbs, zeroY)}
            fill="none"
            stroke={MACD_LINE}
            strokeWidth={LINE_STROKE}
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          <circle cx={newestX} cy={valY(macd[newestIndex])} r={3} fill={MACD_LINE} stroke="var(--bg-secondary)" strokeWidth={1} />
          <circle cx={newestX} cy={valY(signal[newestIndex])} r={3} fill={SIGNAL_LINE} stroke="var(--bg-secondary)" strokeWidth={1} />
          <circle
            cx={newestX}
            cy={newestSrcY}
            r={3.5}
            fill={source === 'signal' ? SIGNAL_LINE : MACD_LINE}
            stroke="#fff"
            strokeWidth={1.2}
          />
          {target !== 'value' && (
            <circle
              cx={newestX}
              cy={newestTgtY}
              r={3.2}
              fill={target === 'signal' ? SIGNAL_LINE : MACD_LINE}
              stroke="var(--border)"
              strokeWidth={1.2}
            />
          )}
          {target === 'value' && (
            <circle cx={newestX} cy={newestTgtY} r={3.2} fill={TARGET_LINE} stroke="var(--bg-secondary)" strokeWidth={1.2} />
          )}
        </g>

        <LegendSwatch x={PAD_L} y={VIEW_H - 10} color={MACD_LINE} />
        <text x={PAD_L + 18} y={VIEW_H - 7} fontSize={9} fill={MACD_LINE} fontFamily="var(--font-mono)">
          Level
        </text>
        <LegendSwatch x={PAD_L + 58} y={VIEW_H - 10} color={SIGNAL_LINE} />
        <text x={PAD_L + 76} y={VIEW_H - 7} fontSize={9} fill={SIGNAL_LINE} fontFamily="var(--font-mono)">
          Signal
        </text>
        <rect x={PAD_L + 118} y={VIEW_H - 14} width={8} height={8} rx={1} fill={GREEN} />
        <text x={PAD_L + 130} y={VIEW_H - 7} fontSize={9} fill="var(--text-muted)" fontFamily="var(--font-mono)">
          Hist
        </text>
        {target === 'value' && Math.abs(tgtVal) > 0.001 && (
          <>
            <LegendSwatch x={PAD_L + 162} y={VIEW_H - 10} color={TARGET_LINE} dash />
            <text x={PAD_L + 180} y={VIEW_H - 7} fontSize={9} fill={TARGET_LINE} fontFamily="var(--font-mono)">
              {tgtVal}
            </text>
          </>
        )}
      </svg>
      <p style={{ margin: '8px 0 0', fontSize: 11, lineHeight: 1.45, color: 'var(--text-secondary)' }}>
        {caption}
        {' '}
        <span style={{ color: 'var(--text-muted)' }}>
          (Source: {plotLabel(source)} → Target: {target === 'value' ? `Value ${tgtVal}` : plotLabel(target)})
        </span>
      </p>
    </div>
  );
}
