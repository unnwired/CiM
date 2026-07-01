import React, { useState } from 'react';
import { formatCompactCount } from '../utils/formatMarketCap';

const CONDITIONS = [
  { key: 'above', label: 'Above' },
  { key: 'above_eq', label: 'Above or Equal' },
];

const sectionLabel = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 8,
};

const inputStyle = {
  backgroundColor: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  padding: '6px 10px',
  color: 'var(--text-primary)',
  fontSize: 13,
  fontFamily: 'var(--font-mono)',
  width: '100%',
  outline: 'none',
};

function parseVolumeInput(raw) {
  if (!raw || !raw.toString().trim()) return null;
  const s = raw.toString().trim().toUpperCase().replace(/,/g, '');
  if (s.endsWith('T')) { const n = parseFloat(s); return Number.isNaN(n) ? null : n * 1e12; }
  if (s.endsWith('B')) { const n = parseFloat(s); return Number.isNaN(n) ? null : n * 1e9; }
  if (s.endsWith('M')) { const n = parseFloat(s); return Number.isNaN(n) ? null : n * 1e6; }
  if (s.endsWith('K')) { const n = parseFloat(s); return Number.isNaN(n) ? null : n * 1e3; }
  const n = parseFloat(s);
  return Number.isNaN(n) ? null : n;
}

function Chip({ item, isSelected, onSelect }) {
  return (
    <div
      onClick={() => onSelect(item.key)}
      style={{
        padding: '5px 10px', borderRadius: 5, cursor: 'pointer',
        backgroundColor: isSelected ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)',
        border: `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border)'}`,
        fontSize: 12, color: isSelected ? 'var(--accent-blue)' : 'var(--text-secondary)',
        userSelect: 'none',
      }}
    >
      {item.label}
    </div>
  );
}

export default function AvgVolumeFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = initialValues || {};
  const [period, setPeriod] = useState(String(init.period ?? 10));
  const [condition, setCondition] = useState(init.condition || 'above');
  const [minRaw, setMinRaw] = useState(init.min_raw || '');
  const [minErr, setMinErr] = useState('');
  const isEditMode = !!initialValues;

  const minVal = parseVolumeInput(minRaw);

  function handleApply() {
    setMinErr('');
    if (!minRaw.trim()) {
      setMinErr('Enter a minimum average volume');
      return;
    }
    if (minVal === null) {
      setMinErr('Invalid value');
      return;
    }
    const p = parseInt(period, 10);
    if (Number.isNaN(p) || p < 1 || p > 60) {
      alert('Period must be 1–60 days');
      return;
    }
    onApply({
      filter_type: 'avg_volume',
      period: p,
      condition,
      min_volume: minVal,
      min_raw: minRaw,
    });
  }

  function chipLabel() {
    const cond = condition === 'above_eq' ? '≥' : '>';
    return `Avg ${period}D vol ${cond} ${formatCompactCount(minVal)}`;
  }

  return (
    <div
      style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8, width: 400, boxShadow: '0 16px 48px rgba(0,0,0,0.6)', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {isEditMode ? 'Edit Avg Volume Filter' : 'Avg Volume Filter'}
          </span>
          <button type="button" onClick={onCancel} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18 }}>×</button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', backgroundColor: 'var(--bg-tertiary)', borderRadius: 4, padding: '6px 10px', border: '1px solid var(--border)' }}>
            Filters out thinly traded names. Uses average daily share volume over the last N sessions from price history.
            Accepts <span style={{ fontFamily: 'var(--font-mono)' }}>500K · 2M · 1.5B</span> or plain numbers.
          </div>

          <div>
            <div style={sectionLabel}>Average period (days)</div>
            <input
              type="number"
              min="1"
              max="60"
              value={period}
              onChange={e => setPeriod(e.target.value)}
              style={inputStyle}
            />
          </div>

          <div>
            <div style={sectionLabel}>Condition</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {CONDITIONS.map(c => (
                <Chip key={c.key} item={c} isSelected={condition === c.key} onSelect={setCondition} />
              ))}
            </div>
          </div>

          <div>
            <div style={sectionLabel}>Minimum average volume</div>
            <input
              value={minRaw}
              onChange={e => { setMinRaw(e.target.value); setMinErr(''); }}
              placeholder="e.g. 500K or 2000000"
              style={{ ...inputStyle, border: minErr ? '1px solid var(--accent-red)' : '1px solid var(--border)' }}
            />
            {minVal !== null && !minErr && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
                {formatCompactCount(minVal)} shares/day
              </div>
            )}
            {minErr && <div style={{ fontSize: 10, color: 'var(--accent-red)', marginTop: 3 }}>{minErr}</div>}
          </div>

          <div style={{ backgroundColor: 'var(--bg-tertiary)', borderRadius: 5, padding: '8px 12px', border: '1px solid var(--border)', fontSize: 12, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)' }}>
            Filter: {minVal !== null ? chipLabel() : '—'}
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" onClick={onCancel} style={{ padding: '7px 16px', borderRadius: 5, fontSize: 12, cursor: 'pointer', backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>Cancel</button>
            <button type="button" onClick={handleApply} style={{ padding: '7px 16px', borderRadius: 5, fontSize: 12, cursor: 'pointer', backgroundColor: 'var(--accent-blue)', border: 'none', color: '#fff', fontWeight: 600 }}>
              {isEditMode ? 'Update Filter' : 'Apply Filter'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
