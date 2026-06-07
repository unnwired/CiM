import React from 'react';
import EarningsBeatCornerBadge from './EarningsBeatCornerBadge';
import EarningsPlusCornerBadge from './EarningsPlusCornerBadge';

/** Grid-only corner badges: green E (dual beat) beside gold E+ (Earnings+). */
export default function MarketMapEarningsBadges({ earningsBeat, earningsPlus }) {
  if (!earningsBeat && !earningsPlus) return null;
  return (
    <div
      style={{
        position: 'absolute',
        top: 4,
        right: 4,
        display: 'flex',
        flexDirection: 'row-reverse',
        alignItems: 'center',
        gap: 3,
        pointerEvents: 'none',
        zIndex: 2,
      }}
    >
      {earningsPlus && <EarningsPlusCornerBadge />}
      {earningsBeat && <EarningsBeatCornerBadge />}
    </div>
  );
}
