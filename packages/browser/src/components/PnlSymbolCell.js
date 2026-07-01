import React from 'react';

export const PNL_SYMBOL_DRAG_WIDTH = 14;
export const PNL_SYMBOL_CHEVRON_WIDTH = 10;

const rowStyle = {
  display: 'flex',
  alignItems: 'center',
  minWidth: 0,
  width: '100%',
};

const dragSlotStyle = {
  flexShrink: 0,
  width: PNL_SYMBOL_DRAG_WIDTH,
  fontSize: 10,
  lineHeight: 1,
  userSelect: 'none',
  letterSpacing: '-0.12em',
  color: 'var(--text-muted)',
};

const chevronSlotStyle = {
  flexShrink: 0,
  width: PNL_SYMBOL_CHEVRON_WIDTH,
  fontSize: 9,
  lineHeight: 1,
  textAlign: 'center',
  color: 'var(--text-muted)',
};

/**
 * Fixed-width drag + expand gutters so symbol tickers align across P&L rows.
 */
export default function PnlSymbolCell({
  symbol,
  variant = 'parent',
  showDrag = false,
  onDragStart,
  onDragEnd,
  showExpand = false,
  expanded = false,
}) {
  return (
    <span style={rowStyle}>
      <span
        title={showDrag ? 'Drag to reorder' : undefined}
        draggable={showDrag || undefined}
        onDragStart={showDrag ? onDragStart : undefined}
        onDragEnd={showDrag ? onDragEnd : undefined}
        onClick={showDrag ? (e) => e.stopPropagation() : undefined}
        style={{
          ...dragSlotStyle,
          cursor: showDrag ? 'grab' : 'default',
          visibility: showDrag ? 'visible' : 'hidden',
        }}
        aria-hidden={!showDrag}
      >
        ⋮⋮
      </span>
      <span style={chevronSlotStyle} aria-hidden={!showExpand}>
        {showExpand ? (expanded ? '▾' : '▸') : '\u00a0'}
      </span>
      {variant === 'parent' ? (
        <span
          title={symbol}
          style={{
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            fontSize: 11,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            minWidth: 0,
            flex: 1,
          }}
        >
          {symbol}
        </span>
      ) : null}
    </span>
  );
}
