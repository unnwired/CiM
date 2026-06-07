import React, { useState, useRef, useCallback } from 'react';

export const DEFAULT_WIDTHS = {
  'Symbol':                       120,
  'Market Cap':                   110,
  'Price':                         90,
  'Change %':                      85,
  'Monthly Change %':               90,
  'PE':                             70,
  'Revenue Growth TTM YoY':        105,
  'Revenue Growth Quarterly QoQ':  115,
  'Net Income TTM YoY':            100,
  'Net Income Quarterly QoQ':      110,
  'EBITDA Growth Quarterly QoQ':   115,
};

export const COLUMNS = [
  { key: 'Symbol',                       main: 'Symbol',          suffix: ''              },
  { key: 'Market Cap',                   main: 'Market Cap',      suffix: ''              },
  { key: 'Price',                        main: 'Price',           suffix: ''              },
  { key: 'Change %',                     main: 'Change',          suffix: '%'             },
  { key: 'Monthly Change %',             main: 'Monthly Change',  suffix: '%'             },
  { key: 'PE',                           main: 'PE',              suffix: ''              },
  { key: 'Revenue Growth TTM YoY',       main: 'Revenue Growth',  suffix: 'TTM YoY'       },
  { key: 'Revenue Growth Quarterly QoQ', main: 'Revenue Growth',  suffix: 'Quarterly QoQ' },
  { key: 'Net Income TTM YoY',           main: 'Net Income',      suffix: 'TTM YoY'       },
  { key: 'Net Income Quarterly QoQ',     main: 'Net Income',      suffix: 'Quarterly QoQ' },
  { key: 'EBITDA Growth Quarterly QoQ',  main: 'EBITDA Growth',   suffix: 'Quarterly QoQ' },
];

const MIN_COL_WIDTH = 55;

function SortIcon({ direction }) {
  if (!direction) return (
    <svg width="10" height="10" viewBox="0 0 10 10" style={{ opacity: 0.3 }}>
      <path d="M5 2L8 6H2L5 2Z" fill="currentColor" />
      <path d="M5 8L2 4H8L5 8Z" fill="currentColor" />
    </svg>
  );
  if (direction === 'asc') return (
    <svg width="10" height="10" viewBox="0 0 10 10">
      <path d="M5 2L8 7H2L5 2Z" fill="var(--accent-blue)" />
    </svg>
  );
  return (
    <svg width="10" height="10" viewBox="0 0 10 10">
      <path d="M5 8L2 3H8L5 8Z" fill="var(--accent-blue)" />
    </svg>
  );
}

export default function TableHeader({ sortBy, sortDir, onSort, colWidths, onColWidthChange }) {
  const [resizing, setResizing] = useState(null);
  const startX                  = useRef(0);
  const startWidth              = useRef(0);

  const handleMouseDown = useCallback((e, colKey) => {
    e.preventDefault();
    e.stopPropagation();
    startX.current     = e.clientX;
    startWidth.current = colWidths[colKey];
    setResizing(colKey);

    function onMouseMove(ev) {
      const delta    = ev.clientX - startX.current;
      const newWidth = Math.max(MIN_COL_WIDTH, startWidth.current + delta);
      onColWidthChange(colKey, newWidth);
    }

    function onMouseUp() {
      setResizing(null);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    }

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, [colWidths, onColWidthChange]);

  return (
    <div style={{
      display:         'flex',
      borderBottom:    '2px solid var(--border)',
      backgroundColor: 'var(--bg-secondary)',
      position:        'sticky',
      top:             0,
      zIndex:          10,
      userSelect:      'none',
    }}>
      {COLUMNS.map((col) => {
        const isActive = sortBy === col.key;
        const dir      = isActive ? sortDir : null;
        const width    = colWidths[col.key];

        return (
          <div
            key={col.key}
            style={{
              position:        'relative',
              width:           width,
              minWidth:        width,
              maxWidth:        width,
              flexShrink:      0,
              padding:         '0 20px 0 8px',
              height:          'var(--header-height)',
              display:         'flex',
              flexDirection:   'column',
              alignItems:      'flex-start',
              justifyContent:  'center',
              gap:             '1px',
              cursor:          'pointer',
              borderRight:     '1px solid var(--border)',
              backgroundColor: isActive ? 'var(--bg-tertiary)' : 'transparent',
              transition:      'background 0.15s',
              boxSizing:       'border-box',
            }}
            onClick={() => onSort(col.key)}
            title={col.key}
          >
            {/* Main label */}
            <div style={{
              display:              '-webkit-box',
              WebkitLineClamp:      2,
              WebkitBoxOrient:      'vertical',
              overflow:             'hidden',
              fontSize:             '11px',
              fontWeight:           600,
              color:                isActive ? 'var(--accent-blue)' : 'var(--text-primary)',
              lineHeight:           '1.3',
              wordBreak:            'break-word',
              width:                '100%',
            }}>
              {col.main}
            </div>

            {/* Suffix label */}
            {col.suffix && (
              <div style={{
                fontSize:      '9.5px',
                color:         isActive ? 'var(--accent-blue)' : 'var(--text-secondary)',
                fontWeight:    500,
                whiteSpace:    'nowrap',
                letterSpacing: '0.02em',
              }}>
                {col.suffix}
              </div>
            )}

            {/* Sort icon */}
            <div style={{ position: 'absolute', top: 6, right: 18 }}>
              <SortIcon direction={dir} />
            </div>

            {/* Resize handle */}
            <div
              onMouseDown={e => handleMouseDown(e, col.key)}
              onClick={e => e.stopPropagation()}
              style={{
                position:        'absolute',
                right:           0,
                top:             0,
                bottom:          0,
                width:           4,
                cursor:          'col-resize',
                backgroundColor: resizing === col.key
                  ? 'var(--accent-blue)'
                  : 'transparent',
                transition:      'background 0.15s',
                zIndex:          2,
              }}
              onMouseEnter={e => {
                if (resizing !== col.key)
                  e.currentTarget.style.backgroundColor = 'var(--border)';
              }}
              onMouseLeave={e => {
                if (resizing !== col.key)
                  e.currentTarget.style.backgroundColor = 'transparent';
              }}
            />
          </div>
        );
      })}
    </div>
  );
}