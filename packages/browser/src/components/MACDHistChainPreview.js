import React, { useMemo } from 'react';

const GREEN = '#3fb950';
const RED = '#f85149';

function clampBarCount(value, min, max) {
  const n = parseInt(String(value), 10);
  if (Number.isNaN(n)) return min;
  return Math.max(min, Math.min(n, max));
}

function buildRecedingChain(length, side) {
  const n = clampBarCount(length, 2, 8);
  if (side === 'positive') {
    return Array.from({ length: n }, (_, i) => n - i);
  }
  return Array.from({ length: n }, (_, i) => -(n - i));
}

function buildIncreasingChain(length, side) {
  const n = clampBarCount(length, 2, 8);
  if (side === 'positive') {
    return Array.from({ length: n }, (_, i) => i + 1);
  }
  return Array.from({ length: n }, (_, i) => -(i + 1));
}

function buildSameSideChain(length, side, chainMode) {
  return chainMode === 'increasing'
    ? buildIncreasingChain(length, side)
    : buildRecedingChain(length, side);
}

/** Sample histogram values (oldest → newest). Mirrors server segment resolver. */
export function buildHistChainSampleValues(chainMode, histogramSide, allowCrossZero, barCount, crossZeroBarCount = 3) {
  const side = histogramSide === 'positive' ? 'positive' : 'negative';
  const opposite = side === 'negative' ? 'positive' : 'negative';
  const mainBars = clampBarCount(barCount, 2, 6);
  const crossBars = clampBarCount(crossZeroBarCount, 1, 4);

  if (!allowCrossZero) {
    const values = buildSameSideChain(mainBars, side, chainMode);
    return { values, mainCount: values.length, crossCount: 0 };
  }

  if (chainMode === 'receding') {
    const segSelected = buildRecedingChain(mainBars, side);
    const segOpposite = buildIncreasingChain(crossBars, opposite);
    return {
      values: [...segSelected, ...segOpposite],
      mainCount: segSelected.length,
      crossCount: segOpposite.length,
    };
  }

  const segOpposite = buildRecedingChain(crossBars, opposite);
  const segSelected = buildIncreasingChain(mainBars, side);
  return {
    values: [...segOpposite, ...segSelected],
    mainCount: segSelected.length,
    crossCount: segOpposite.length,
  };
}

export function getHistChainPreviewCaption(chainMode, histogramSide, allowCrossZero, crossZeroBars) {
  const side = histogramSide === 'positive' ? 'positive' : 'negative';
  const opposite = side === 'negative' ? 'positive' : 'negative';

  if (!allowCrossZero) {
    const motion = chainMode === 'increasing'
      ? 'Each bar moves farther from the zero line.'
      : 'Each bar moves closer to the zero line.';
    return `${motion} All bars stay on the ${side} side of zero.`;
  }

  const cz = clampBarCount(crossZeroBars, 1, 8);
  if (chainMode === 'receding') {
    return `${side} bars recede toward zero (${mainVerb(side)}), cross zero, then ${cz} ${opposite} bar${cz === 1 ? '' : 's'} increase away from zero.`;
  }
  return `${cz} ${opposite} bar${cz === 1 ? '' : 's'} recede toward zero before cross, then ${side} bars increase away from zero.`;
}

function mainVerb(side) {
  return side === 'negative' ? 'highest → lowest negative' : 'highest → lowest positive';
}

function barColor(value, prevValue) {
  const expanding = prevValue == null || Math.abs(value) >= Math.abs(prevValue);
  if (value >= 0) return expanding ? GREEN : `${GREEN}66`;
  return expanding ? RED : `${RED}66`;
}

export default function MACDHistChainPreview({
  chainMode,
  histogramSide,
  allowCrossZero,
  barsToCompare,
  crossZeroBars,
}) {
  const { values, mainCount, crossCount } = useMemo(
    () => buildHistChainSampleValues(chainMode, histogramSide, allowCrossZero, barsToCompare, crossZeroBars),
    [chainMode, histogramSide, allowCrossZero, barsToCompare, crossZeroBars],
  );
  const caption = useMemo(
    () => getHistChainPreviewCaption(chainMode, histogramSide, allowCrossZero, crossZeroBars),
    [chainMode, histogramSide, allowCrossZero, crossZeroBars],
  );

  const dividerIndex = allowCrossZero && crossCount > 0
    ? (chainMode === 'receding' ? mainCount : crossCount)
    : null;

  const maxAbs = Math.max(...values.map((v) => Math.abs(v)), 1);
  const barSlot = 44;
  const dividerGap = dividerIndex != null ? 12 : 0;
  const chartW = values.length * barSlot + dividerGap + 24;
  const midY = 38;
  const maxBarH = 28;
  const dividerX = dividerIndex != null
    ? 12 + dividerIndex * barSlot - barSlot / 2 + dividerGap / 2
    : null;

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-tertiary)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '10px 12px 8px',
        opacity: allowCrossZero || crossCount === 0 ? 1 : 1,
      }}
    >
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6, letterSpacing: '0.04em' }}>
        EXAMPLE — older ← → newer
        {allowCrossZero && crossCount > 0 && (
          <span style={{ marginLeft: 8 }}>
            {chainMode === 'increasing' ? 'before cross | after cross' : 'selected side | after cross'}
          </span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${chartW} 72`}
        width="100%"
        height={72}
        style={{ display: 'block', maxWidth: chartW }}
        aria-hidden
      >
        <line
          x1={8}
          y1={midY}
          x2={chartW - 8}
          y2={midY}
          stroke="var(--border)"
          strokeWidth={1}
        />
        {dividerX != null && (
          <line
            x1={dividerX}
            y1={8}
            x2={dividerX}
            y2={56}
            stroke="var(--accent-blue)"
            strokeWidth={1}
            strokeDasharray="3 3"
            opacity={0.7}
          />
        )}
        {values.map((v, i) => {
          const h = Math.max(2, (Math.abs(v) / maxAbs) * maxBarH);
          const crossOffset = dividerIndex != null && i >= dividerIndex ? dividerGap : 0;
          const x = 12 + i * barSlot + crossOffset;
          const y = v >= 0 ? midY - h : midY;
          const prev = i > 0 ? values[i - 1] : null;
          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={18}
                height={h}
                rx={2}
                fill={barColor(v, prev)}
              />
              <text
                x={x + 9}
                y={66}
                textAnchor="middle"
                fontSize={9}
                fill="var(--text-muted)"
                fontFamily="var(--font-mono)"
              >
                {v > 0 ? `+${v}` : v}
              </text>
            </g>
          );
        })}
      </svg>
      <p style={{ margin: '8px 0 0', fontSize: 11, lineHeight: 1.45, color: 'var(--text-secondary)' }}>
        {caption}
      </p>
    </div>
  );
}
