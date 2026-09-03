import React from 'react';
import { EARNINGS_PLUS_COLOR } from '../utils/marketMapTileStyle';

/** Boxless gold "E+" text marker for symbol-list rows (Earnings+ qualified). */
export default function EarningsPlusInlineMark({ title = 'Earnings+ quality' }) {
  return (
    <span
      aria-label={title}
      title={title}
      style={{
        flexShrink: 0,
        color: EARNINGS_PLUS_COLOR,
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        fontWeight: 700,
        lineHeight: 1,
      }}
    >
      E+
    </span>
  );
}
