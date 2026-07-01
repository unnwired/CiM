import React from 'react';
import { stockListCellPad, stockListGridCellStyle } from './stockTableChrome';

/** Body cell — grid child; divider aligns with header because the row shares gridTemplateColumns. */
export default function StockListGridCell({
  colKey,
  isLast = false,
  compact = false,
  children,
  onClick,
  style,
  innerStyle,
}) {
  return (
    <div
      onClick={onClick}
      style={{
        ...stockListGridCellStyle({ isLast }),
        display: 'flex',
        alignItems: 'center',
        justifyContent: colKey === 'note' || colKey === 'act' ? 'center' : undefined,
        ...style,
      }}
    >
      <div
        style={{
          padding: stockListCellPad(colKey, { compact }),
          minWidth: 0,
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: colKey === 'note' || colKey === 'act' ? 'center' : undefined,
          gap: compact ? 4 : undefined,
          ...innerStyle,
        }}
      >
        {children}
      </div>
    </div>
  );
}
