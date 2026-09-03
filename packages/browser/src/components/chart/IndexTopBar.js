import React, { useState, useRef } from 'react';
import BasketToolbarButton from '../Basket';
import EMAControls from './EMAControls';
import { useWheelHorizontalScroll } from '../../hooks/useWheelHorizontalScroll';

const INDICATOR_OPTIONS = [
  { key: 'stochrsi', label: 'StochRSI' },
  { key: 'macd',     label: 'MACD'     },
];

export default function IndexTopBar({
  index,
  timeframe: _tf,
  onTimeframeChange: _onTf,
  emas, onEmasChange,
  volumeVisible, onToggleVolume,
  visiblePanels, onTogglePanel,
  lastCandleChange,
  onShowConstituents,
  onSaveLayout,
  onBack,
}) {
  const [indOpen, setIndOpen] = useState(false);
  const toolbarScrollRef = useRef(null);
  useWheelHorizontalScroll(toolbarScrollRef);

  const hasConstituents = !['GC=F', 'SI=F'].includes(index?.symbol);

  const changeColor = lastCandleChange === null ? 'var(--text-secondary)'
    : lastCandleChange >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

  const formatPrice = (val, cat) => {
    if (!val) return '—';
    if (cat === 'commodity') {
      return `₹${Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
    }
    return Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2 });
  };

  return (
    <div ref={toolbarScrollRef} className="chart-app-toolbar" style={{
      height:          52,
      minHeight:       52,
      backgroundColor: 'var(--bg-secondary)',
      borderBottom:    '1px solid var(--border)',
      display:         'flex',
      alignItems:      'center',
      padding:         '0 14px',
      gap:             12,
      flexShrink:      0,
      zIndex:          300000,
      overflowX:       'auto',
      overflowY:       'visible',
      position:        'relative',
    }}>

      {/* Back button */}
      {onBack && (
        <button
          onClick={onBack}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)',
            borderRadius: 5, padding: '0 10px', height: 28,
            color: 'var(--text-secondary)', fontSize: 12, flexShrink: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-blue)'; e.currentTarget.style.color = 'var(--accent-blue)'; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
        >
          ← Market Indices
        </button>
      )}

      {/* Index name + price */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexShrink: 0 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 15, color: 'var(--text-primary)' }}>
          {index?.name}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)' }}>
          {formatPrice(index?.last_price, index?.category)}
          {index?.category === 'commodity' && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 4 }}>
              {index?.symbol === 'GC=F' ? '/10g' : '/kg'}
            </span>
          )}
        </span>
        {lastCandleChange !== null && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: changeColor, fontWeight: 500 }}>
            {lastCandleChange >= 0 ? '+' : ''}{Number(lastCandleChange).toFixed(2)}%
          </span>
        )}
      </div>

      <div style={{ width: 1, height: 20, backgroundColor: 'var(--border)', flexShrink: 0 }} />

      {/* Volume toggle */}
      <div onClick={onToggleVolume} style={{
        display: 'flex', alignItems: 'center', gap: 5,
        backgroundColor: 'var(--bg-tertiary)',
        border: `1px solid ${volumeVisible ? '#388bfd55' : 'var(--border)'}`,
        borderRadius: 4, padding: '0 8px', height: 28,
        opacity: volumeVisible ? 1 : 0.5, cursor: 'pointer', flexShrink: 0,
      }}>
        <div style={{ width: 8, height: 8, backgroundColor: '#388bfd', borderRadius: 2 }} />
        <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 500 }}>Vol</span>
        <span style={{ fontSize: 11, color: volumeVisible ? 'var(--accent-blue)' : 'var(--text-muted)' }}>
          {volumeVisible ? '●' : '○'}
        </span>
      </div>

      {/* EMA controls */}
      <EMAControls emas={emas} onChange={onEmasChange} />

      <div style={{ flex: 1, minWidth: 8 }} />

      <BasketToolbarButton />

      {/* Constituents button */}
      {hasConstituents && onShowConstituents && (
        <button
          onClick={onShowConstituents}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)',
            borderRadius: 5, padding: '0 12px', height: 28,
            color: 'var(--text-secondary)', fontSize: 12, flexShrink: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-blue)'; e.currentTarget.style.color = 'var(--accent-blue)'; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
        >
          Constituents ↗
        </button>
      )}

      {/* Indicators */}
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <button
          onClick={() => setIndOpen(o => !o)}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            backgroundColor: indOpen ? 'var(--bg-active)' : 'var(--bg-tertiary)',
            border: '1px solid var(--border)', borderRadius: 5,
            padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12,
          }}
        >
          Indicators
          <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6 }}>
            <path d="M0 0l4 5 4-5z" />
          </svg>
        </button>
        {indOpen && (
          <div style={{
            position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 9999,
            backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)',
            borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            minWidth: 160, overflow: 'hidden',
          }}>
            {INDICATOR_OPTIONS.map(ind => {
              const active = visiblePanels[ind.key];
              return (
                <div key={ind.key}
                  onClick={() => { onTogglePanel(ind.key); setIndOpen(false); }}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '9px 14px', cursor: 'pointer', fontSize: 13,
                    color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                  }}
                  onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--bg-hover)'}
                  onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                  {ind.label}
                  <div style={{
                    width: 14, height: 14, borderRadius: 3,
                    border: '1px solid var(--border)',
                    backgroundColor: active ? 'var(--accent-blue)' : 'transparent',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {active && (
                      <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
                        <path d="M1 3.5L3.5 6L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Save Layout */}
      {onSaveLayout && (
        <button
          onClick={onSaveLayout}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            backgroundColor: 'var(--bg-tertiary)',
            border: '1px solid var(--border)',
            borderRadius: 5, padding: '0 10px', height: 28,
            color: 'var(--text-secondary)', fontSize: 12, flexShrink: 0,
          }}
          onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
        >
          Save Layout
        </button>
      )}
    </div>
  );
}
