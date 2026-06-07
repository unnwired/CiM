import React, { useState } from 'react';

const TF_GROUPS = {
  D: ['1D','2D','3D','4D','5D','6D','7D'],
  W: ['1W','2W','3W','4W'],
  M: ['1M','2M','3M','4M','5M','6M','7M','8M','9M','10M','11M','12M'],
};

function getTFGroupKey(tf) {
  if (!tf) return 'D';
  if (/^\d+m$/.test(tf) || /^\d+h$/.test(tf)) return 'D';
  if (tf.endsWith('D')) return 'D';
  if (tf.endsWith('W')) return 'W';
  return 'M';
}

// ChartHeaderBar — D / W / M group switcher + timeframe buttons.
// symbol is optional (shown when provided).
export default function ChartHeaderBar({ symbol, timeframe, onTimeframeChange }) {
  const [activeGroup, setActiveGroup] = useState(() => getTFGroupKey(timeframe));

  // Keep activeGroup in sync when timeframe is changed from outside
  // (e.g. top bar dropdown on panel 1)
  const currentGroupKey = getTFGroupKey(timeframe);
  const displayGroup    = currentGroupKey !== activeGroup ? currentGroupKey : activeGroup;
  const group           = TF_GROUPS[displayGroup] || TF_GROUPS.D;

  function handleGroupClick(g) {
    setActiveGroup(g);
    onTimeframeChange(TF_GROUPS[g][0]);
  }

  return (
    <div style={{
      height:          28,
      flexShrink:      0,
      width:           '100%',
      minWidth:        0,
      display:         'flex',
      alignItems:      'center',
      backgroundColor: 'var(--bg-secondary)',
      borderBottom:    '1px solid var(--border)',
      padding:         '0 10px',
      gap:             6,
    }}>
      {/* Symbol */}
      {symbol && (
        <>
          <span style={{
            fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11,
            color: 'var(--accent-blue)', flexShrink: 0,
          }}>
            {symbol}
          </span>
          <span style={{ color: 'var(--border)', fontSize: 11 }}>|</span>
        </>
      )}

      {/* D / W / M group switcher */}
      <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
        {Object.keys(TF_GROUPS).map(g => {
          const isActive = g === displayGroup;
          return (
            <button
              key={g}
              onClick={() => handleGroupClick(g)}
              style={{
                backgroundColor: isActive ? 'var(--bg-active)' : 'transparent',
                border:          `1px solid ${isActive ? 'var(--border)' : 'transparent'}`,
                borderRadius:    3,
                padding:         '1px 6px',
                fontSize:        10,
                fontFamily:      'var(--font-mono)',
                fontWeight:      isActive ? 700 : 400,
                color:           isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                cursor:          'pointer',
              }}
              onMouseEnter={e => { if (!isActive) e.currentTarget.style.color = 'var(--text-primary)'; }}
              onMouseLeave={e => { if (!isActive) e.currentTarget.style.color = 'var(--text-muted)'; }}
            >
              {g}
            </button>
          );
        })}
      </div>

      <span style={{ color: 'var(--border)', fontSize: 11, flexShrink: 0 }}>|</span>

      {/* Timeframe buttons for active group — scroll when many (e.g. 1M…12M) */}
      <div style={{
        flex:                   1,
        minWidth:               0,
        display:                'flex',
        alignItems:             'center',
        gap:                    2,
        overflowX:              'auto',
        overflowY:              'hidden',
        WebkitOverflowScrolling: 'touch',
      }}>
        {group.map(tf => {
          const isSelected = tf === timeframe;
          return (
            <button
              key={tf}
              onClick={() => onTimeframeChange(tf)}
              style={{
                flexShrink:      0,
                backgroundColor: isSelected ? 'var(--accent-blue)' : 'transparent',
                border:          isSelected ? 'none' : '1px solid transparent',
                borderRadius:    3,
                padding:         '1px 6px',
                fontSize:        10,
                fontFamily:      'var(--font-mono)',
                fontWeight:      isSelected ? 700 : 400,
                color:           isSelected ? '#fff' : 'var(--text-muted)',
                cursor:          'pointer',
              }}
              onMouseEnter={e => { if (!isSelected) e.currentTarget.style.color = 'var(--text-primary)'; }}
              onMouseLeave={e => { if (!isSelected) e.currentTarget.style.color = 'var(--text-muted)'; }}
            >
              {tf}
            </button>
          );
        })}
      </div>
    </div>
  );
}