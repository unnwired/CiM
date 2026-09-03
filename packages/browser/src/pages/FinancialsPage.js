import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { formatMarketCap, formatINRFromCrores } from '../utils/formatMarketCap';
import { isTypingContext } from '../utils/isTypingTarget';

const API = '';

function formatEps(val) {
  if (val === null || val === undefined) return '—';
  const n = parseFloat(val);
  if (!Number.isFinite(n)) return '—';
  return n.toFixed(2);
}

function formatPct(val) {
  if (val === null || val === undefined) return '—';
  return `${parseFloat(val).toFixed(2)}%`;
}

// Quarter month label e.g. "Dec-25" → "Dec"
function quarterMonth(period) {
  return period ? period.split('-')[0].toLowerCase() : '';
}

export default function FinancialsPage({ onOpenChart, selectedSymbol, onSelectSymbol }) {
  const [stocks, setStocks]         = useState([]);
  const [search, setSearch]         = useState('');
  const [loading, setLoading]       = useState(true);
  const [selected, setSelected]     = useState(selectedSymbol || null);
  const [data, setData]             = useState(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [hoveredMonth, setHoveredMonth] = useState(null);
  const listRef                     = useRef(null);
  const rowRefs                     = useRef({});

  // Load all stocks via pagination
  useEffect(() => {
    async function loadAll() {
      try {
        let all  = [];
        let page = 1;
        const pageSize = 500;
        while (true) {
          const r = await axios.get(`${API}/api/stocks?page=${page}&pageSize=${pageSize}&sortBy=Market+Cap&sortDir=desc`);
          const data = r.data.data || [];
          all = [...all, ...data];
          if (all.length >= r.data.total || data.length === 0) break;
          page++;
        }
        setStocks(all);
        setLoading(false);
        if (!selected && all.length > 0) {
          setSelected(all[0].Symbol);
        }
      } catch {
        setLoading(false);
      }
    }
    loadAll();
  }, []);

  // Load financial data when selection changes
  useEffect(() => {
    if (!selected) return;
    setDataLoading(true);
    setData(null);
    axios.get(`${API}/api/financials/${selected}`)
      .then(r => { setData(r.data); setDataLoading(false); })
      .catch(() => setDataLoading(false));
  }, [selected]);

  // Sync external symbol selection
  useEffect(() => {
    if (selectedSymbol && selectedSymbol !== selected) {
      setSelected(selectedSymbol);
    }
  }, [selectedSymbol]);

  const filtered = stocks.filter(s =>
    !search || s.Symbol?.toUpperCase().includes(search.toUpperCase())
  );

  function handleSelect(symbol) {
    setSelected(symbol);
    if (onSelectSymbol) onSelectSymbol(symbol);
  }

  // Arrow key navigation
  useEffect(() => {
    function handleKey(e) {
      if (!['ArrowUp','ArrowDown'].includes(e.key)) return;
      if (isTypingContext(e)) return;
      e.preventDefault();
      const idx = filtered.findIndex(s => s.Symbol === selected);
      if (idx === -1) return;
      const next = e.key === 'ArrowDown'
        ? Math.min(idx + 1, filtered.length - 1)
        : Math.max(idx - 1, 0);
      handleSelect(filtered[next].Symbol);
      rowRefs.current[next]?.scrollIntoView({ block: 'nearest' });
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [filtered, selected]);

  return (
    <div style={{
      display: 'flex', height: '100%', width: '100%',
      backgroundColor: 'var(--bg-primary)', overflow: 'hidden',
    }}>
      {/* Left pane — stock list */}
      <div style={{
        width: 220, minWidth: 220, flexShrink: 0,
        display: 'flex', flexDirection: 'column',
        borderRight: '1px solid var(--border)', overflow: 'hidden',
      }}>
        {/* Search */}
        <div style={{
          padding: '8px 10px', borderBottom: '1px solid var(--border)',
          backgroundColor: 'var(--bg-secondary)', flexShrink: 0,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)',
            borderRadius: 5, padding: '0 8px', height: 28,
          }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="var(--text-muted)">
              <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z"/>
            </svg>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search..."
              style={{ background: 'transparent', color: 'var(--text-primary)', flex: 1, fontSize: 12 }}
            />
            {search && (
              <button onClick={() => setSearch('')}
                style={{ background: 'none', color: 'var(--text-muted)', fontSize: 14 }}>×</button>
            )}
          </div>
        </div>

        {/* Stock list */}
        <div ref={listRef} style={{ flex: 1, overflowY: 'auto' }}>
          {loading ? (
            <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>Loading...</div>
          ) : filtered.map((stock, idx) => {
            const isSelected = stock.Symbol === selected;
            const chg        = stock['Change %'];
            const chgColor   = chg > 0 ? 'var(--accent-green)' : chg < 0 ? 'var(--accent-red)' : 'var(--text-muted)';
            return (
              <div
                key={stock.Symbol}
                ref={el => rowRefs.current[idx] = el}
                onClick={() => handleSelect(stock.Symbol)}
                style={{
                  padding:         '8px 10px',
                  cursor:          'pointer',
                  borderBottom:    '1px solid var(--border-light)',
                  borderLeft:      isSelected ? '2px solid var(--accent-blue)' : '2px solid transparent',
                  backgroundColor: isSelected ? 'rgba(56,139,253,0.08)' : 'transparent',
                }}
                onMouseEnter={e => { if (!isSelected) e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                onMouseLeave={e => { if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, color: isSelected ? 'var(--accent-blue)' : 'var(--text-primary)' }}>
                    {stock.Symbol}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: chgColor }}>
                    {chg != null ? `${chg > 0 ? '+' : ''}${chg.toFixed(2)}%` : '—'}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                  ₹{stock.Price?.toLocaleString('en-IN', { minimumFractionDigits: 2 }) || '—'}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right pane — detail */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {dataLoading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
            Loading {selected}...
          </div>
        ) : !data ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
            Select a stock to view financials
          </div>
        ) : (
          <DetailPanel
            data={data}
            hoveredMonth={hoveredMonth}
            setHoveredMonth={setHoveredMonth}
            onOpenChart={onOpenChart}
            dataLoading={dataLoading}
          />
        )}
      </div>
    </div>
  );
}

function DetailPanel({ data, hoveredMonth, setHoveredMonth, onOpenChart, dataLoading }) {
  const quarters = data.quarterly || [];

  // Determine which quarters to highlight based on hover
  function isHighlighted(period) {
    if (!hoveredMonth) return false;
    return quarterMonth(period) === hoveredMonth;
  }

  // Latest quarter month for permanent highlight
  const latestMonth = quarters.length > 0 ? quarterMonth(quarters[0].period) : null;

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
      {/* Company header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        marginBottom: 20,
      }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 4px' }}>
            {data.company_name}
          </h2>
          {data.industry && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{data.industry}</span>
          )}
        </div>
        <button
          onClick={() => onOpenChart && onOpenChart(data.symbol)}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            backgroundColor: 'var(--accent-blue)', border: 'none',
            borderRadius: 6, padding: '0 14px', height: 32,
            color: '#fff', fontSize: 12, fontWeight: 600,
            cursor: 'pointer', flexShrink: 0,
          }}
          onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
          onMouseLeave={e => e.currentTarget.style.opacity = '1'}
        >
          Open Chart ↗
        </button>
      </div>

      {/* Key metrics */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
        gap: 10, marginBottom: 24,
      }}>
        {[
          { label: 'Market Cap',     value: formatMarketCap(data.market_cap) },
          { label: 'Current Price',  value: `₹${data.price?.toLocaleString('en-IN', { minimumFractionDigits: 2 }) || '—'}` },
          { label: 'Stock PE',       value: data.pe ? data.pe.toFixed(2) : '—' },
          { label: '52W High',       value: data.year_high ? `₹${data.year_high.toLocaleString('en-IN')}` : '—' },
          { label: '52W Low',        value: data.year_low  ? `₹${data.year_low.toLocaleString('en-IN')}` : '—' },
          { label: 'Change %',       value: data.change_pct != null ? `${data.change_pct > 0 ? '+' : ''}${data.change_pct.toFixed(2)}%` : '—',
            color: data.change_pct > 0 ? 'var(--accent-green)' : data.change_pct < 0 ? 'var(--accent-red)' : null },
        ].map(metric => (
          <div key={metric.label} style={{
            backgroundColor: 'var(--bg-secondary)',
            border:          '1px solid var(--border)',
            borderRadius:    6, padding: '10px 12px',
          }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {metric.label}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: metric.color || 'var(--text-primary)' }}>
              {metric.value}
            </div>
          </div>
        ))}
      </div>

      {/* About */}
      {data.about && (
        <div style={{
          backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 6, padding: '14px 16px', marginBottom: 24,
        }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            About
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
            {data.about}
          </p>
        </div>
      )}

      {/* Peers */}
      {data.peers?.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <SectionHeader title="Peers" />
          <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--bg-tertiary)', borderBottom: '2px solid var(--border)' }}>
                  {['#', 'Name', 'CMP', 'Market Cap', 'PE'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: h === '#' || h === 'CMP' || h === 'Market Cap' || h === 'PE' ? 'right' : 'left', color: 'var(--text-secondary)', fontWeight: 600, fontSize: 11 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.peers.map((peer, idx) => (
                  <tr
                    key={peer.symbol}
                    onClick={() => window.dispatchEvent(new CustomEvent('open-chart', { detail: peer.symbol }))}
                    style={{ borderBottom: '1px solid var(--border-light)', cursor: 'pointer', transition: 'background 0.1s' }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--bg-hover)'}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                  >
                    <td style={{ padding: '8px 12px', color: 'var(--text-muted)', textAlign: 'right' }}>{idx + 1}</td>
                    <td style={{ padding: '8px 12px', color: 'var(--text-primary)', fontWeight: 500 }}>{peer.name}</td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>₹{peer.cmp?.toLocaleString('en-IN') || '—'}</td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{formatMarketCap(peer.market_cap)}</td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{peer.pe?.toFixed(2) || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Quarterly Results */}
      {quarters.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <SectionHeader title="Quarterly Results" subtitle="Monetary figures in ₹M · ₹B · ₹T" />
          <div style={{
            backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)',
            borderRadius: 6, overflow: 'auto',
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, minWidth: 600 }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--bg-tertiary)', borderBottom: '2px solid var(--border)' }}>
                  <th style={{ padding: '8px 14px', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600, fontSize: 11, width: 160, position: 'sticky', left: 0, backgroundColor: 'var(--bg-tertiary)', zIndex: 1 }}>
                    Period
                  </th>
                  {quarters.map(q => {
                    const isLatest = q.period === quarters[0].period;
                    const isHover  = isHighlighted(q.period);
                    return (
                      <th
                        key={q.period}
                        onMouseEnter={() => setHoveredMonth(quarterMonth(q.period))}
                        onMouseLeave={() => setHoveredMonth(null)}
                        style={{
                          padding:         '8px 14px',
                          textAlign:       'right',
                          color:           isLatest ? 'var(--accent-blue)' : 'var(--text-secondary)',
                          fontWeight:      600,
                          fontSize:        11,
                          cursor:          'default',
                          backgroundColor: isHover
                            ? 'rgba(56,139,253,0.12)'
                            : isLatest
                            ? 'rgba(56,139,253,0.06)'
                            : 'var(--bg-tertiary)',
                          transition:      'background 0.15s',
                          whiteSpace:      'nowrap',
                        }}
                      >
                        {q.period}
                        {isLatest && (
                          <div style={{ fontSize: 9, color: 'var(--accent-blue)', fontWeight: 400 }}>Latest</div>
                        )}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {[
                  { key: 'revenue',      label: 'Revenue',            fmt: formatINRFromCrores },
                  { key: 'other_income', label: 'Other Income',       fmt: formatINRFromCrores },
                  { key: 'total_income', label: 'Total Income',       fmt: formatINRFromCrores, bold: true },
                  { key: 'expenditure',  label: 'Expenditure',        fmt: formatINRFromCrores },
                  { key: 'interest',     label: 'Interest',           fmt: formatINRFromCrores },
                  { key: 'pbdt',         label: 'PBDT',               fmt: formatINRFromCrores, bold: true },
                  { key: 'depreciation', label: 'Depreciation',       fmt: formatINRFromCrores },
                  { key: 'pbt',          label: 'Profit Before Tax',  fmt: formatINRFromCrores, bold: true },
                  { key: 'tax',          label: 'Tax',                fmt: formatINRFromCrores },
                  { key: 'net_profit',   label: 'Net Profit',         fmt: formatINRFromCrores, bold: true },
                  { key: 'eps',          label: 'EPS (₹)',            fmt: formatEps },
                  { key: 'opm_percent',  label: 'OPM %',              fmt: formatPct },
                  { key: 'npm_percent',  label: 'NPM %',              fmt: formatPct },
                ].map((row, rowIdx) => (
                  <tr
                    key={row.key}
                    style={{
                      borderBottom: '1px solid var(--border-light)',
                      backgroundColor: rowIdx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                    }}
                  >
                    <td style={{
                      padding:         '7px 14px',
                      color:           row.bold ? 'var(--text-primary)' : 'var(--text-secondary)',
                      fontWeight:      row.bold ? 600 : 400,
                      position:        'sticky',
                      left:            0,
                      backgroundColor: rowIdx % 2 === 0 ? 'var(--bg-primary)' : 'var(--bg-secondary)',
                      zIndex:          1,
                      whiteSpace:      'nowrap',
                    }}>
                      {row.label}
                    </td>
                    {quarters.map(q => {
                      const isLatest = q.period === quarters[0].period;
                      const isHover  = isHighlighted(q.period);
                      const val      = q[row.key];
                      return (
                        <td
                          key={q.period}
                          onMouseEnter={() => setHoveredMonth(quarterMonth(q.period))}
                          onMouseLeave={() => setHoveredMonth(null)}
                          style={{
                            padding:         '7px 14px',
                            textAlign:       'right',
                            fontFamily:      'var(--font-mono)',
                            fontSize:        12,
                            fontWeight:      row.bold ? 600 : 400,
                            color:           row.bold ? 'var(--text-primary)' : 'var(--text-secondary)',
                            backgroundColor: isHover
                              ? 'rgba(56,139,253,0.10)'
                              : isLatest
                              ? 'rgba(56,139,253,0.04)'
                              : 'transparent',
                            transition:      'background 0.15s',
                            whiteSpace:      'nowrap',
                          }}
                        >
                          {row.fmt(val)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
            Hover over a quarter to highlight related quarters across all years
          </div>
        </div>
      )}

      {quarters.length === 0 && !dataLoading && (
        <div style={{
          backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 6, padding: '24px', textAlign: 'center',
          color: 'var(--text-muted)', fontSize: 13,
        }}>
          No quarterly data available. Run Fetch Latest Financials in Data Management.
        </div>
      )}
    </div>
  );
}

function SectionHeader({ title, subtitle }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</span>
      {subtitle && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{subtitle}</span>}
      <div style={{ flex: 1, height: 1, backgroundColor: 'var(--border)' }} />
    </div>
  );
}
