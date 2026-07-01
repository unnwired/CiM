import React from 'react';
import { EARNINGS_PLUS_COLOR } from '../utils/marketMapTileStyle';

/** Small gold E+ badge (matches chart Earnings+ styling). */
export default function EarningsPlusCornerBadge({ title = 'Earnings+ quality' }) {
  return (
    <span
      aria-label={title}
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: 18,
        height: 16,
        padding: '0 3px',
        borderRadius: 3,
        backgroundColor: EARNINGS_PLUS_COLOR,
        color: '#0d1117',
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        fontWeight: 700,
        lineHeight: 1,
        boxShadow: '0 1px 2px rgba(0,0,0,0.35)',
      }}
    >
      E+
    </span>
  );
}
