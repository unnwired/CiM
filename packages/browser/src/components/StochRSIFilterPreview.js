import React, { useMemo } from 'react';
import {
  buildStochRsiPreviewSample,
  getStochRsiPreviewCaption,
  parseTargetValue,
  pointX,
  POINT_COUNT,
  PREVIEW_CHART_H,
  PREVIEW_CHART_TOP,
  PREVIEW_PAD_L,
  PREVIEW_PAD_R,
  PREVIEW_SLOT_PX,
  PREVIEW_VIEW_H,
  PREVIEW_VIEW_W,
  valToY,
} from '../utils/stochrsiFilterPreviewCore';

const K_LINE = '#58a6ff';
const D_LINE = '#d29922';
const TARGET_LINE = '#8b949e';
const GRID_LINE = '#6e768166';
const GRID_LINE_STRONG = '#6e768199';
const MARKER_LINE = '#6e7681cc';

const VIEW_W = PREVIEW_VIEW_W;
const VIEW_H = PREVIEW_VIEW_H;
const PAD_L = PREVIEW_PAD_L;
const PAD_R = PREVIEW_PAD_R;
const CHART_TOP = PREVIEW_CHART_TOP;
const CHART_H = PREVIEW_CHART_H;
const LEGEND_Y = VIEW_H - 8;
const PLOT_W = VIEW_W - PAD_L - PAD_R;

const LINE_STROKE = 2;
const K_STROKE = 2;
const D_STROKE = 2;

export { POINT_COUNT, valToY, evalCondition, deriveDFromK, buildStochRsiPreviewSample, getStochRsiPreviewCaption } from '../utils/stochrsiFilterPreviewCore';

function plotLabel(key) {
  if (key === 'd') return '%D';
  if (key === 'value') return 'Value';
  return '%K';
}

function linePath(series) {
  return series.map((v, i) => `${pointX(i)},${valToY(v)}`).join(' ');
}

function ribbonPoints(k, d, from, to) {
  const pts = [];
  for (let i = from; i <= to; i++) pts.push(`${pointX(i)},${valToY(k[i])}`);
  for (let i = to; i >= from; i--) pts.push(`${pointX(i)},${valToY(d[i])}`);
  return pts.join(' ');
}

function LegendSwatch({ x, y, color }) {
  return (
    <line
      x1={x}
      y1={y}
      x2={x + 14}
      y2={y}
      stroke={color}
      strokeWidth={LINE_STROKE}
      strokeLinecap="round"
    />
  );
}

export default function StochRSIFilterPreview({
  source,
  condition,
  target,
  targetValue,
  pctValue,
}) {
  const sample = useMemo(
    () => buildStochRsiPreviewSample(condition, source, target, targetValue, pctValue),
    [condition, source, target, targetValue, pctValue],
  );
  const caption = useMemo(
    () => getStochRsiPreviewCaption(condition, source, target, targetValue, pctValue),
    [condition, source, target, targetValue, pctValue],
  );

  const { k, d, holdStart, highlightIndices, newestIndex } = sample;
  const tgtVal = parseTargetValue(targetValue);
  const srcSeries = source === 'k' ? k : d;
  const tgtSeries = target === 'value' ? null : (target === 'k' ? k : d);
  const newestX = pointX(newestIndex);
  const showPctBand = (condition === 'above_pct' || condition === 'below_pct') && target !== 'value';

  const gridLevels = [20, 50, 80];

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
        <span>EXAMPLE — StochRSI ({POINT_COUNT} points · older ← → newer)</span>
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
          <clipPath id="stochrsi-filter-plot-clip">
            <rect x={PAD_L} y={CHART_TOP} width={PLOT_W} height={CHART_H} />
          </clipPath>
          <linearGradient id="stochrsi-ribbon-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(88,166,255,0.14)" />
            <stop offset="100%" stopColor="rgba(210,153,34,0.10)" />
          </linearGradient>
        </defs>

        <g clipPath="url(#stochrsi-filter-plot-clip)">
          {gridLevels.map((lvl) => (
            <line
              key={`h-${lvl}`}
              x1={PAD_L}
              y1={valToY(lvl)}
              x2={VIEW_W - PAD_R}
              y2={valToY(lvl)}
              stroke={lvl === 50 ? GRID_LINE_STRONG : GRID_LINE}
              strokeWidth={1}
              strokeDasharray={lvl === 50 ? '2 3' : '1 4'}
            />
          ))}

          {target === 'value' && (
            <line
              x1={PAD_L}
              y1={valToY(tgtVal)}
              x2={VIEW_W - PAD_R}
              y2={valToY(tgtVal)}
              stroke={TARGET_LINE}
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
          )}

          <polygon
            points={ribbonPoints(k, d, 0, newestIndex)}
            fill="url(#stochrsi-ribbon-fill)"
            stroke="none"
          />

          {highlightIndices.length > 0 && (
            <rect
              x={pointX(highlightIndices[0]) - PREVIEW_SLOT_PX * 0.45}
              y={CHART_TOP}
              width={pointX(newestIndex) - pointX(highlightIndices[0]) + PREVIEW_SLOT_PX * 0.9}
              height={CHART_H}
              fill="rgba(56,139,253,0.05)"
              stroke="rgba(56,139,253,0.18)"
              strokeWidth={1}
              rx={2}
            />
          )}

          {showPctBand && tgtSeries && (
            <polygon
              points={(() => {
                const pts = [];
                for (let i = holdStart; i <= newestIndex; i++) {
                  pts.push(`${pointX(i)},${valToY(srcSeries[i])}`);
                }
                for (let i = newestIndex; i >= holdStart; i--) {
                  pts.push(`${pointX(i)},${valToY(tgtSeries[i])}`);
                }
                return pts.join(' ');
              })()}
              fill="rgba(88,166,255,0.1)"
              stroke="rgba(88,166,255,0.28)"
              strokeWidth={1}
            />
          )}

          <polyline
            points={linePath(d)}
            fill="none"
            stroke={D_LINE}
            strokeWidth={D_STROKE}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <polyline
            points={linePath(k)}
            fill="none"
            stroke={K_LINE}
            strokeWidth={K_STROKE}
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          <line
            x1={newestX}
            y1={CHART_TOP}
            x2={newestX}
            y2={CHART_TOP + CHART_H}
            stroke={MARKER_LINE}
            strokeWidth={1}
            strokeDasharray="2 3"
          />

          <circle cx={newestX} cy={valToY(k[newestIndex])} r={3} fill={K_LINE} stroke="var(--bg-secondary)" strokeWidth={1} />
          <circle cx={newestX} cy={valToY(d[newestIndex])} r={3} fill={D_LINE} stroke="var(--bg-secondary)" strokeWidth={1} />
          <circle
            cx={newestX}
            cy={valToY(srcSeries[newestIndex])}
            r={3.5}
            fill={source === 'k' ? K_LINE : D_LINE}
            stroke="#fff"
            strokeWidth={1.2}
          />
          {target === 'value' ? (
            <circle cx={newestX} cy={valToY(tgtVal)} r={3.2} fill={TARGET_LINE} stroke="var(--bg-secondary)" strokeWidth={1.2} />
          ) : (
            <circle
              cx={newestX}
              cy={valToY(tgtSeries[newestIndex])}
              r={3.2}
              fill={target === 'k' ? K_LINE : D_LINE}
              stroke="var(--border)"
              strokeWidth={1.2}
            />
          )}
        </g>

        <LegendSwatch x={PAD_L} y={LEGEND_Y} color={K_LINE} />
        <text x={PAD_L + 18} y={LEGEND_Y + 3} fontSize={9} fill={K_LINE} fontFamily="var(--font-mono)">
          %K
        </text>
        <LegendSwatch x={PAD_L + 48} y={LEGEND_Y} color={D_LINE} />
        <text x={PAD_L + 66} y={LEGEND_Y + 3} fontSize={9} fill={D_LINE} fontFamily="var(--font-mono)">
          %D
        </text>
        <text x={PAD_L + 96} y={LEGEND_Y + 3} fontSize={9} fill="var(--text-muted)" fontFamily="var(--font-mono)">
          0–100
        </text>
        {target === 'value' && (
          <>
            <line x1={PAD_L + 132} y1={LEGEND_Y} x2={PAD_L + 146} y2={LEGEND_Y} stroke={TARGET_LINE} strokeWidth={1.5} strokeDasharray="3 2" />
            <text x={PAD_L + 150} y={LEGEND_Y + 3} fontSize={9} fill={TARGET_LINE} fontFamily="var(--font-mono)">
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
