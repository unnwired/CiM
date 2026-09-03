import React from 'react';
import {
  stockListFooterStripStyle,
  stockListSplitColumnStyle,
  stockListSplitRowStyle,
} from './stockTableChrome';

/**
 * Shared list|chart body shell: full-width status footer under the split.
 * Put pane-resize refs on `splitRef` (the horizontal row), not the outer column.
 */
export default function StockListSplitBody({
  splitRef,
  children,
  footer,
  columnStyle,
  splitStyle,
}) {
  return (
    <div style={{ ...stockListSplitColumnStyle, ...columnStyle }}>
      <div ref={splitRef} style={{ ...stockListSplitRowStyle, ...splitStyle }}>
        {children}
      </div>
      {footer != null ? (
        <div style={stockListFooterStripStyle}>{footer}</div>
      ) : null}
    </div>
  );
}
