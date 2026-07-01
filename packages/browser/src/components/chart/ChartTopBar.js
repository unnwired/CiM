import React, { useState, useEffect, useRef } from 'react';
import { fetchStockDetail, searchStocks } from '../../api/client';
import EMAControls from './EMAControls';
import DrawingToolsDesignControl from './drawing/DrawingToolsDesignControl';
import ExternalFinancialsLinks from '../ExternalFinancialsLinks';

const INDICATOR_OPTIONS = [
  { key: 'stochrsi', label: 'StochRSI' },
  { key: 'macd',     label: 'MACD'     },
];

export default function ChartTopBar({
  symbol,
  timeframe: _tf,
  onTimeframeChange: _onTf,
  emas, onEmasChange,
  volumeVisible, onToggleVolume,
  visiblePanels, onTogglePanel,
  onSymbolChange,
  lastCandleChange,
  onSaveLayout,
}) {
  const [detail, setDetail]           = useState(null);
  const [indOpen, setIndOpen]         = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [searchOpen, setSearchOpen]   = useState(false);
  const [activeIdx, setActiveIdx]     = useState(-1);
  const indBtnRef                     = useRef(null);
  const indMenuRef                    = useRef(null);
  const debounceRef                   = useRef(null);

  useEffect(() => {
    if (!symbol) return;
    fetchStockDetail(symbol).then(setDetail).catch(() => setDetail(null));
  }, [symbol]);

  // Search autocomplete
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!searchQuery.trim()) { setSuggestions([]); setSearchOpen(false); return; }
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await searchStocks(searchQuery);
        setSuggestions(data.results || []);
        setSearchOpen((data.results || []).length > 0);
      } catch {
        setSuggestions([]); setSearchOpen(false);
      }
    }, 200);
  }, [searchQuery]);

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e) {
      if (indBtnRef.current && !indBtnRef.current.contains(e.target) &&
          indMenuRef.current && !indMenuRef.current.contains(e.target)) {
        setIndOpen(false);
      }
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  function handleSelectSymbol(sym) {
    setSearchQuery('');
    setSuggestions([]);
    setSearchOpen(false);
    onSymbolChange(sym);
  }

  function handleSearchKeyDown(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(p => Math.min(p + 1, suggestions.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(p => Math.max(p - 1, 0)); }
    else if (e.key === 'Enter') { if (activeIdx >= 0 && suggestions[activeIdx]) handleSelectSymbol(suggestions[activeIdx]); }
    else if (e.key === 'Escape') { setSearchOpen(false); setSearchQuery(''); }
  }

  const change      = detail?.['Change %'] ?? null;
  const price       = detail?.['Price']    ?? null;
  const changeColor = change === null
    ? 'var(--text-secondary)'
    : change >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

  return (
    <div className="chart-app-toolbar" style={{
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

      {/* Symbol search */}
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <div style={{
          display:         'flex',
          alignItems:      'center',
          gap:             7,
          backgroundColor: 'var(--bg-tertiary)',
          border:          '1px solid var(--border)',
          borderRadius:    5,
          padding:         '0 10px',
          height:          28,
          minWidth:        140,
        }}>
          <svg width="11" height="11" viewBox="0 0 16 16" fill="var(--text-muted)">
            <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z" />
          </svg>
          <input
            value={searchQuery}
            onChange={e => { setSearchQuery(e.target.value); setActiveIdx(-1); }}
            onKeyDown={handleSearchKeyDown}
            onBlur={() => setTimeout(() => setSearchOpen(false), 150)}
            onFocus={() => suggestions.length > 0 && setSearchOpen(true)}
            placeholder={symbol}
            style={{
              background:  'transparent',
              color:       'var(--text-primary)',
              flex:        1,
              fontSize:    12,
              fontFamily:  'var(--font-mono)',
              fontWeight:  600,
              width:       90,
            }}
          />
        </div>
        {searchOpen && suggestions.length > 0 && (
          <div style={{
            position:        'fixed',
            top:             'auto',
            marginTop:       4,
            backgroundColor: 'var(--bg-secondary)',
            border:          '1px solid var(--border)',
            borderRadius:    6,
            zIndex:          9999,
            overflow:        'hidden',
            width:           180,
            boxShadow:       '0 8px 24px rgba(0,0,0,0.6)',
          }}>
            {suggestions.map((s, i) => (
              <div key={s} onMouseDown={() => handleSelectSymbol(s)}
                style={{
                  padding:         '7px 12px',
                  cursor:          'pointer',
                  backgroundColor: i === activeIdx ? 'var(--bg-active)' : 'transparent',
                  color:           i === activeIdx ? 'var(--accent-blue)' : 'var(--text-primary)',
                  fontFamily:      'var(--font-mono)',
                  fontSize:        12,
                  fontWeight:      500,
                }}
                onMouseEnter={() => setActiveIdx(i)}
              >{s}</div>
            ))}
          </div>
        )}
      </div>

      {/* Price info */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexShrink: 0 }}>
        {price !== null && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-primary)', fontWeight: 600 }}>
            ₹{Number(price).toFixed(2)}
          </span>
        )}
        {lastCandleChange !== null && lastCandleChange !== undefined ? (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500,
            color: lastCandleChange >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
          }}>
            {lastCandleChange >= 0 ? '+' : ''}{Number(lastCandleChange).toFixed(2)}%
          </span>
        ) : change !== null && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: changeColor, fontWeight: 500 }}>
            {change >= 0 ? '+' : ''}{Number(change).toFixed(2)}%
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
        <div style={{ width: 8, height: 8, backgroundColor: '#388bfd', borderRadius: 2, flexShrink: 0 }} />
        <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 500 }}>Vol</span>
        <span style={{ fontSize: 11, color: volumeVisible ? 'var(--accent-blue)' : 'var(--text-muted)' }}>
          {volumeVisible ? '●' : '○'}
        </span>
      </div>

      {/* EMA controls */}
      <EMAControls emas={emas} onChange={onEmasChange} />

      <ExternalFinancialsLinks symbol={symbol} />

      <div style={{ flex: 1, minWidth: 8 }} />

      <DrawingToolsDesignControl />

      {/* Indicators dropdown */}
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <button
          ref={indBtnRef}
          onClick={() => setIndOpen(o => !o)}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            backgroundColor: indOpen ? 'var(--bg-active)' : 'var(--bg-tertiary)',
            border: '1px solid var(--border)', borderRadius: 5,
            padding: '0 10px', height: 28,
            color: 'var(--text-secondary)', fontSize: 12,
          }}
        >
          Indicators
          <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6 }}>
            <path d="M0 0l4 5 4-5z" />
          </svg>
        </button>
        {indOpen && (
          <div
            ref={indMenuRef}
            style={{
              position:        'absolute',
              top:             'calc(100% + 4px)',
              left:            0,
              zIndex:          9999,
              backgroundColor: 'var(--bg-secondary)',
              border:          '1px solid var(--border)',
              borderRadius:    6,
              boxShadow:       '0 8px 24px rgba(0,0,0,0.6)',
              minWidth:        160,
              overflow:        'hidden',
            }}
          >
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
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
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
            color: 'var(--text-secondary)', fontSize: 12,
            flexShrink: 0,
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
