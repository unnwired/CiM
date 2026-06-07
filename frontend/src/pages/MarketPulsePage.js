import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { MARKET_PULSE_REFRESH_EVENT } from '../chartEvents';

const API = '';

function formatPrice(val) {
  if (val === null || val === undefined) return '—';
  return Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ChangeBadge({ value }) {
  if (value === null || value === undefined) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
  const n     = parseFloat(value);
  const color = n > 0 ? 'var(--accent-green)' : n < 0 ? 'var(--accent-red)' : 'var(--text-secondary)';
  return (
    <span style={{ color, fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500 }}>
      {n > 0 ? '+' : ''}{n.toFixed(2)}%
    </span>
  );
}

export default function MarketPulsePage() {
  const [indices, setIndices]       = useState([]);
  const [loading, setLoading]       = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);

  const fetchIndices = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/indices`);
      setIndices(r.data.data || []);
      setLastUpdate(new Date());
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIndices();
  }, [fetchIndices]);

  useEffect(() => {
    const handler = () => { fetchIndices(); };
    window.addEventListener(MARKET_PULSE_REFRESH_EVENT, handler);
    return () => window.removeEventListener(MARKET_PULSE_REFRESH_EVENT, handler);
  }, [fetchIndices]);

  const equity = indices.filter(i => i.category === 'equity');
  const nseAll = indices.filter(i => i.category === 'equity_nse');

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100%', width: '100%',
      backgroundColor: 'var(--bg-primary)', overflow: 'hidden',
    }}>
      {/* Top bar */}
      <div style={{
        height: 52, backgroundColor: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center',
        padding: '0 20px', gap: 16, flexShrink: 0,
      }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          Market Indices
        </span>
        {lastUpdate && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            Updated {lastUpdate.toLocaleTimeString('en-IN')}
          </span>
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
        {loading ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: 20 }}>Loading indices...</div>
        ) : (
          <>
            <Section title="Equity Indices" indices={equity} />
            <Section title="Equity Indices (Non-Chartable)" indices={nseAll} isNonChartable />
          </>
        )}
      </div>
    </div>
  );
}

function Section({ title, indices, isNonChartable }) {
  if (!indices.length) return null;

  return (
    <div style={{ marginBottom: 32 }}>
      <div style={{
        fontSize: 11, fontWeight: 700, color: 'var(--text-muted)',
        letterSpacing: '0.08em', textTransform: 'uppercase',
        marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10,
      }}>
        {title}
        <div style={{ flex: 1, height: 1, backgroundColor: 'var(--border)' }} />
        <span style={{ fontSize: 10, fontWeight: 400 }}>{indices.length}</span>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: isNonChartable
          ? 'repeat(auto-fill, minmax(220px, 1fr))'
          : 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: isNonChartable ? 8 : 12,
      }}>
        {indices.map(idx => (
          isNonChartable
            ? <NonChartableCard key={idx.symbol} index={idx} />
            : <IndexCard key={idx.symbol} index={idx} />
        ))}
      </div>
    </div>
  );
}

function IndexCard({ index }) {
  const isUp   = index.change_pct > 0;
  const isDown = index.change_pct < 0;

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-secondary)',
        border:          `1px solid ${isUp ? '#3fb95033' : isDown ? '#f8514933' : 'var(--border)'}`,
        borderRadius:    8, padding: '14px 16px',
        transition: 'all 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
            {index.name}
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {index.symbol}
          </div>
        </div>
        <div style={{
          backgroundColor: isUp ? 'rgba(63,185,80,0.12)' : isDown ? 'rgba(248,81,73,0.12)' : 'var(--bg-tertiary)',
          border:          `1px solid ${isUp ? '#3fb95044' : isDown ? '#f8514944' : 'var(--border)'}`,
          borderRadius:    5, padding: '3px 8px', minWidth: 60, textAlign: 'center',
        }}>
          <ChangeBadge value={index.change_pct} />
        </div>
      </div>

      <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', marginBottom: 10 }}>
        {formatPrice(index.last_price)}
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>1M</div>
          <ChangeBadge value={index.change_30d} />
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>1Y</div>
          <ChangeBadge value={index.change_1y} />
        </div>
      </div>
    </div>
  );
}

function NonChartableCard({ index }) {
  const isUp   = index.change_pct > 0;
  const isDown = index.change_pct < 0;

  return (
    <div style={{
      backgroundColor: 'var(--bg-secondary)',
      border:          `1px solid ${isUp ? '#3fb95022' : isDown ? '#f8514922' : 'var(--border-light)'}`,
      borderRadius:    6, padding: '10px 12px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)', flex: 1, marginRight: 8, lineHeight: 1.3 }}>
          {index.name}
        </span>
        <ChangeBadge value={index.change_pct} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          {Number(index.last_price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 1 }}>1M</div>
            <ChangeBadge value={index.change_30d} />
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 1 }}>1Y</div>
            <ChangeBadge value={index.change_1y} />
          </div>
        </div>
      </div>
    </div>
  );
}
