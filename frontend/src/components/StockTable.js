import React, { useCallback } from 'react';
import { COLUMNS } from './TableHeader';
import { formatMarketCap } from '../utils/formatMarketCap';

function formatPercent(val) {
  if (val === null || val === undefined) return '—';
  const n = parseFloat(val);
  if (isNaN(n)) return '—';
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function formatPrice(val) {
  if (val === null || val === undefined) return '—';
  const n = parseFloat(val);
  if (isNaN(n)) return '—';
  return `₹${n.toFixed(2)}`;
}

function formatPE(val) {
  if (val === null || val === undefined) return '—';
  const n = parseFloat(val);
  if (isNaN(n)) return '—';
  return n.toFixed(2);
}

const PERCENT_COLS = new Set([
  'Change %', 'Monthly Change %', 'Revenue Growth TTM YoY',
  'Revenue Growth Quarterly QoQ', 'Net Income TTM YoY',
  'Net Income Quarterly QoQ', 'EBITDA Growth Quarterly QoQ',
]);

function CellValue({ colKey, value }) {
  if (colKey === 'Symbol') {
    return (
      <span style={{
        fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12,
        color: 'var(--accent-blue)', letterSpacing: '0.03em',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>{value}</span>
    );
  }
  if (colKey === 'Market Cap') {
    return <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 12, whiteSpace: 'nowrap' }}>{formatMarketCap(value)}</span>;
  }
  if (colKey === 'Price') {
    return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{formatPrice(value)}</span>;
  }
  if (colKey === 'PE') {
    return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{formatPE(value)}</span>;
  }
  if (PERCENT_COLS.has(colKey)) {
    if (value === null || value === undefined) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
    const n = parseFloat(value);
    if (isNaN(n)) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
    const color = n > 0 ? 'var(--accent-green)' : n < 0 ? 'var(--accent-red)' : 'var(--text-secondary)';
    return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color, fontWeight: 500, whiteSpace: 'nowrap' }}>{formatPercent(n)}</span>;
  }
  return <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{value ?? '—'}</span>;
}

export default function StockTable({ data, loading, colWidths, onRowClick }) {
  const handleRowClick = useCallback((symbol) => {
    if (onRowClick) onRowClick(symbol);
  }, [onRowClick]);

  if (loading && data.length === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, color: 'var(--text-muted)', fontSize: 13 }}>
        Loading stocks...
      </div>
    );
  }

  return (
    <div style={{ width: '100%' }}>
      {data.map((row, idx) => (
        <div
          key={row.Symbol}
          onClick={() => handleRowClick(row.Symbol)}
          style={{
            display: 'flex', height: 'var(--row-height)',
            borderBottom: '1px solid var(--border-light)',
            cursor: 'pointer',
            backgroundColor: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
            transition: 'background 0.1s',
          }}
          onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--bg-hover)'}
          onMouseLeave={e => e.currentTarget.style.backgroundColor = idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)'}
        >
          {COLUMNS.map(col => {
            const width = colWidths[col.key];
            return (
              <div key={col.key} style={{
                width, minWidth: width, maxWidth: width, flexShrink: 0,
                padding: '0 8px', display: 'flex', alignItems: 'center',
                borderRight: '1px solid var(--border-light)', overflow: 'hidden', boxSizing: 'border-box',
              }}>
                <CellValue colKey={col.key} value={row[col.key]} />
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
