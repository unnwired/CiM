import React, { useMemo } from 'react';

const GREEN = '#3fb950';
const RED = '#f85149';

const CROSS_ZERO_RECEDING = {
  2: [-2, -1],
  3: [-2, -1, 1],
  4: [-3, -2, -1, 1],
  5: [-4, -3, -2, -1, 1],
  6: [-5, -4, -3, -2, -1, 1],
};

const CROSS_ZERO_INCREASING = {
  2: [-1, 1],
  3: [-1, 1, 2],
  4: [-1, 1, 2, 3],
  5: [-1, 1, 2, 3, 4],
  6: [-1, 1, 2, 3, 4, 5],
};

/** Sample histogram values for the filter preview (oldest → newest, left → right). */
export function buildHistChainSampleValues(chainMode, histogramSide, allowCrossZero, barCount) {
  const n = Math.max(2, Math.min(parseInt(String(barCount), 10) || 4, 6));
  const increasing = chainMode === 'increasing';

  if (histogramSide === 'negative') {
    return Array.from({ length: n }, (_, i) => (increasing ? -(i + 1) : -(n - i)));
  }

  if (histogramSide === 'positive') {
    return Array.from({ length: n }, (_, i) => (increasing ? i + 1 : n - i));
  }

  if (allowCrossZero) {
    const table = increasing ? CROSS_ZERO_INCREASING : CROSS_ZERO_RECEDING;
    return table[n] || table[4];
  }

  return Array.from({ length: n }, (_, i) => (increasing ? -(i + 1) : -(n - i)));
}

export function getHistChainPreviewCaption(chainMode, histogramSide, allowCrossZero) {
  const increasing = chainMode === 'increasing';
  const toward = 'Each bar moves closer to the zero line (smaller magnitude).';
  const away = 'Each bar moves farther from the zero line (larger magnitude).';
  const motion = increasing ? away : toward;

  if (histogramSide === 'negative') {
    return increasing
      ? `${motion} Bars stay below zero and grow more negative.`
      : `${motion} Bars stay below zero and shrink toward zero.`;
  }
  if (histogramSide === 'positive') {
    return increasing
      ? `${motion} Bars stay above zero and grow more positive.`
      : `${motion} Bars stay above zero and shrink toward zero.`;
  }
  if (allowCrossZero) {
    return increasing
      ? `${motion} Chain may cross zero (example shows negative → positive).`
      : `${motion} Chain may cross zero while magnitudes shrink (example shows negative → positive).`;
  }
  return increasing
    ? `${motion} All bars on the same side of zero (example: negative).`
    : `${motion} All bars on the same side of zero (example: negative).`;
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
}) {
  const values = useMemo(
    () => buildHistChainSampleValues(chainMode, histogramSide, allowCrossZero, barsToCompare),
    [chainMode, histogramSide, allowCrossZero, barsToCompare],
  );
  const caption = useMemo(
    () => getHistChainPreviewCaption(chainMode, histogramSide, allowCrossZero),
    [chainMode, histogramSide, allowCrossZero],
  );

  const maxAbs = Math.max(...values.map((v) => Math.abs(v)), 1);
  const barSlot = 44;
  const chartW = values.length * barSlot + 24;
  const midY = 38;
  const maxBarH = 28;

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-tertiary)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '10px 12px 8px',
      }}
    >
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6, letterSpacing: '0.04em' }}>
        EXAMPLE — older ← → newer
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
        {values.map((v, i) => {
          const h = Math.max(2, (Math.abs(v) / maxAbs) * maxBarH);
          const x = 12 + i * barSlot;
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
