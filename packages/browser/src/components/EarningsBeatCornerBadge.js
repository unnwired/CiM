import React from 'react';
import { DUAL_BEAT_BORDER } from '../utils/portfolioEarnings';

/** Green E — dual EPS+Rev beat vs estimates on latest reported quarter (Market Map grid). */
export default function EarningsBeatCornerBadge({ title = 'Beat EPS+Rev vs estimates (latest quarter)' }) {
  return (
    <span
      aria-label={title}
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: 16,
        height: 16,
        padding: '0 3px',
        borderRadius: 3,
        backgroundColor: DUAL_BEAT_BORDER,
        color: '#0d1117',
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        fontWeight: 700,
        lineHeight: 1,
        boxShadow: '0 1px 2px rgba(0,0,0,0.35)',
      }}
    >
      E
    </span>
  );
}
