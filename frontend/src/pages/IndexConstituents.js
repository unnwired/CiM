import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  STOCK_LIST_HEADER_HEIGHT,
  STOCK_LIST_ROW_HEIGHT,
  stockListHeaderStripStyle,
  stockListFooterStripStyle,
} from '../components/stockTableChrome';
import InstrumentNotesIcon from '../components/InstrumentNotesIcon';
import { formatMarketCap } from '../utils/formatMarketCap';

const API = '';

export default function IndexConstituents({ index, onBack, onOpenChart }) {
  const [stocks, setStocks]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy]   = useState('symbol');
  const [sortDir, setSortDir] = useState('asc');

  useEffect(() => {
    axios.get(`${API}/api/index-constituents/${encodeURIComponent(index.symbol)}`)
      .then(r => { setStocks(r.data.data || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [index.symbol]);

  function handleSort(col) {
    if (col === 'note') return;
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortBy(col); setSortDir('asc'); }
  }

  const sorted = [...stocks].sort((a, b) => {
    const av = a[sortBy];
    const bv = b[sortBy];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    return sortDir === 'asc'
      ? (typeof av === 'string' ? av.localeCompare(bv) : av - bv)
      : (typeof av === 'string' ? bv.localeCompare(av) : bv - av);
  });

  /** Aligned grid with ConstituentsPage / Pulse numerics (11px mono); extra OHLC cols. */
  const COLS = [
    { key: 'symbol',     label: 'Symbol',    width: 90 },
    { key: 'market_cap', label: 'Mkt Cap',   width: 110 },
    { key: 'note',       label: '',          width: 36 },
    { key: 'last_price', label: 'Price',     width: 85 },
    { key: 'change_pct', label: '1D Chg %',  width: 80 },
    { key: 'change_30d', label: '30D %',     width: 80 },
    { key: 'change_1y',  label: '1Y %',      width: 80 },
    { key: 'volume',     label: 'Volume',    width: 100 },
    { key: 'year_high',  label: '52W High',  width: 88 },
    { key: 'year_low',   label: '52W Low',   width: 88 },
  ];

  return (
    <div style={{
      display:         'flex',
      flexDirection:   'column',
      height:          '100%',
      width:           '100%',
      backgroundColor: 'var(--bg-primary)',
      overflow:        'hidden',
      fontSize:        12,
    }}>
      {/* Header */}
      <div style={{
        height:          52,
        backgroundColor: 'var(--bg-secondary)',
        borderBottom:    '1px solid var(--border)',
        display:         'flex',
        alignItems:      'center',
        padding:         '0 16px',
        gap:             12,
        flexShrink:      0,
      }}>
        <button onClick={onBack}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)',
            borderRadius: 5, padding: '0 10px', height: 28,
            color: 'var(--text-secondary)', fontSize: 12,
          }}
        >← Back to Chart</button>

        <div style={{ width: 1, height: 20, backgroundColor: 'var(--border)' }} />

        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          {index.name}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          — Constituents ({stocks.length})
        </span>
      </div>

      {/* Table header */}
      <div style={stockListHeaderStripStyle}>
        {COLS.map(col => (
          <div key={col.key}
            onClick={() => col.key !== 'note' && handleSort(col.key)}
            style={{
              width:       col.width,
              minWidth:    col.width,
              flexShrink:  0,
              padding:     '0 8px',
              height:      STOCK_LIST_HEADER_HEIGHT,
              display:     'flex',
              alignItems:  'center',
              cursor:      col.key === 'note' ? 'default' : 'pointer',
              fontSize:    11,
              fontWeight:  600,
              color:       sortBy === col.key ? 'var(--accent-blue)' : 'var(--text-secondary)',
              borderRight: '1px solid var(--border-light)',
              userSelect:  'none',
            }}
          >
            {col.label}
            {col.key !== 'note' && sortBy === col.key && (
              <span style={{ marginLeft: 3, fontSize: 9 }}>
                {sortDir === 'asc' ? '▲' : '▼'}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Table body */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {loading ? (
          <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>
            Loading constituents...
          </div>
        ) : sorted.length === 0 ? (
          <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>
            Constituents not available for this index.
          </div>
        ) : (
          sorted.map((stock) => (
            <div key={stock.symbol}
              onClick={() => onOpenChart(stock.symbol)}
              style={{
                display:         'flex',
                height:          STOCK_LIST_ROW_HEIGHT,
                borderBottom:    '1px solid var(--border-light)',
                cursor:          'pointer',
                backgroundColor: 'transparent',
              }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              {COLS.map(col => (
                <div key={col.key} style={{
                  width:       col.width,
                  minWidth:    col.width,
                  flexShrink:  0,
                  padding:     col.key === 'note' ? '0 4px' : '0 8px',
                  display:     'flex',
                  alignItems:  'center',
                  justifyContent: col.key === 'note' ? 'center' : undefined,
                  borderRight: '1px solid var(--border-light)',
                  overflow:    'hidden',
                }} onClick={col.key === 'note' ? e => e.stopPropagation() : undefined}>
                  {col.key === 'note' ? (
                    <InstrumentNotesIcon symbol={stock.symbol} instrumentType="stock" />
                  ) : col.key === 'symbol' ? (
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 600,
                      fontSize: 11,
                      color: stock.change_pct > 0 ? 'var(--accent-green)' : stock.change_pct < 0 ? 'var(--accent-red)' : 'var(--text-primary)',
                    }}>{stock.symbol}</span>
                  ) : (
                    <CellValue col={col.key} value={stock[col.key]} />
                  )}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
      <div style={stockListFooterStripStyle}>
        {sorted.length} {sorted.length === 1 ? 'stock' : 'stocks'}
      </div>
    </div>
  );
}

function CellValue({ col, value }) {
  if (value === null || value === undefined) {
    return <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>;
  }

  if (col === 'market_cap') {
    return (
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
        {formatMarketCap(value)}
      </span>
    );
  }

  if (col === 'last_price' || col === 'year_high' || col === 'year_low') {
    return (
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)' }}>
        ₹{Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    );
  }

  if (col === 'volume') {
    return (
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
        {Number(value).toLocaleString('en-IN')}
      </span>
    );
  }

  if (['change_pct', 'change_30d', 'change_1y'].includes(col)) {
    const n     = parseFloat(value);
    const color = n > 0 ? 'var(--accent-green)' : n < 0 ? 'var(--accent-red)' : 'var(--text-secondary)';
    return (
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color, fontWeight: 500 }}>
        {n > 0 ? '+' : ''}{n.toFixed(2)}%
      </span>
    );
  }

  return <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{value}</span>;
}
