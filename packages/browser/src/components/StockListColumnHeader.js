import React from 'react';
import {
  STOCK_LIST_HEADER_HEIGHT,
  stockListCellPad,
  stockListGridCellStyle,
} from './stockTableChrome';

/**
 * Resizable stock-list header cell (grid child). Drag the right edge to resize the column.
 */
export default function StockListColumnHeader({
  colKey,
  isLast = false,
  widthKey,
  resizingKey,
  onResizeStart,
  onClick,
  sortable = true,
  children,
  style,
}) {
  const isResizing = resizingKey === widthKey;
  const pad = stockListCellPad(colKey);

  return (
    <div
      style={{
        position: 'relative',
        ...stockListGridCellStyle({ isLast }),
        height: STOCK_LIST_HEADER_HEIGHT,
        display: 'flex',
        alignItems: 'center',
        userSelect: 'none',
        ...style,
      }}
    >
      {sortable && onClick ? (
        <button
          type="button"
          onClick={onClick}
          style={{
            width: '100%',
            height: '100%',
            padding: pad,
            display: 'flex',
            alignItems: 'center',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--text-secondary)',
            fontFamily: 'inherit',
            textAlign: 'left',
            minWidth: 0,
          }}
        >
          {children}
        </button>
      ) : (
        <span style={{ padding: pad, fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', width: '100%', minWidth: 0 }}>
          {children}
        </span>
      )}
      {!isLast ? (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize column"
          onMouseDown={(e) => onResizeStart(e)}
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute',
            right: -3,
            top: 0,
            bottom: 0,
            width: 6,
            cursor: 'col-resize',
            backgroundColor: isResizing ? 'var(--accent-blue)' : 'transparent',
            transition: 'background 0.15s',
            zIndex: 2,
          }}
          onMouseEnter={(e) => {
            if (!isResizing) e.currentTarget.style.backgroundColor = 'var(--border)';
          }}
          onMouseLeave={(e) => {
            if (!isResizing) e.currentTarget.style.backgroundColor = 'transparent';
          }}
        />
      ) : null}
    </div>
  );
}
