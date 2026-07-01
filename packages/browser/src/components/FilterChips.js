import React, { useState, useRef, useEffect } from 'react';

const AVAILABLE_FILTERS = [
  { key: 'EMA',      label: 'EMA' },
  { key: 'StochRSI', label: 'StochRSI' },
  { key: 'MACD',     label: 'MACD' },
];

export default function FilterChips({ filters, onAdd, onRemove }) {
  const [open, setOpen] = useState(false);
  const ref             = useRef(null);

  useEffect(() => {
    function handle(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  const activeKeys = filters.map(f => f.key);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'nowrap' }}>
      {/* Active filter chips */}
      {filters.map(f => (
        <div key={f.key} style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          backgroundColor: 'var(--bg-active)',
          border: '1px solid var(--accent-blue)',
          borderRadius: 4,
          padding: '0 8px',
          height: 28,
          fontSize: 12,
          color: 'var(--accent-blue)',
          fontWeight: 500,
          whiteSpace: 'nowrap',
        }}>
          {f.label}
          <button
            onClick={() => onRemove(f.key)}
            style={{
              background: 'none',
              color: 'var(--text-secondary)',
              fontSize: 14,
              lineHeight: 1,
              padding: '0 2px',
              marginLeft: 2,
            }}
          >×</button>
        </div>
      ))}

      {/* Add filter button */}
      <div ref={ref} style={{ position: 'relative' }}>
        <button
          onClick={() => setOpen(o => !o)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            backgroundColor: open ? 'var(--bg-active)' : 'var(--bg-tertiary)',
            border: '1px solid var(--border)',
            borderRadius: 4,
            padding: '0 10px',
            height: 28,
            color: 'var(--text-secondary)',
            fontSize: 13,
            fontWeight: 500,
            transition: 'all 0.15s',
          }}
        >
          <span style={{ fontSize: 16, lineHeight: 1 }}>+</span>
          <span>Filter</span>
        </button>

        {open && (
          <div style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            zIndex: 1000,
            overflow: 'hidden',
            minWidth: 140,
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          }}>
            {AVAILABLE_FILTERS.map(f => {
              const added = activeKeys.includes(f.key);
              return (
                <div
                  key={f.key}
                  onClick={() => { if (!added) { onAdd(f); setOpen(false); } }}
                  style={{
                    padding: '8px 14px',
                    cursor: added ? 'default' : 'pointer',
                    color: added ? 'var(--text-muted)' : 'var(--text-primary)',
                    fontSize: 13,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 12,
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => { if (!added) e.currentTarget.style.background = 'var(--bg-hover)'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                >
                  {f.label}
                  {added && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>added</span>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
