import React, { useState } from 'react';

const METRICS = [
  { key: 'total_revenue', label: 'Total Revenue' },
  { key: 'net_income', label: 'Net Income' },
];

const CONDITIONS = [
  { key: 'ttm_gt_annual', label: 'TTM > Annual' },
  { key: 'ttm_lt_annual', label: 'TTM < Annual' },
];

const BASES = [
  { key: 'consolidated', label: 'Consolidated' },
  { key: 'standalone', label: 'Standalone' },
];

const sectionLabel = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 8,
};

function normalizeMetrics(init) {
  if (Array.isArray(init?.metrics) && init.metrics.length) {
    return METRICS.map((m) => m.key).filter((k) => init.metrics.includes(k));
  }
  if (init?.metric === 'net_income') return ['net_income'];
  if (init?.metric === 'total_revenue') return ['total_revenue'];
  return ['total_revenue'];
}

function normalizeCondition(raw) {
  if (raw === 'ttm_lt_annual' || raw === 'annual_gt_ttm') return 'ttm_lt_annual';
  if (raw === 'ttm_gt_annual' || raw === 'annual_lt_ttm') return 'ttm_gt_annual';
  return 'ttm_gt_annual';
}

function Chip({ item, isSelected, onSelect }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(item.key)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(item.key);
        }
      }}
      style={{
        padding: '5px 10px',
        borderRadius: 5,
        cursor: 'pointer',
        backgroundColor: isSelected ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)',
        border: `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border)'}`,
        fontSize: 12,
        color: isSelected ? 'var(--accent-blue)' : 'var(--text-secondary)',
        userSelect: 'none',
      }}
    >
      {item.label}
    </div>
  );
}

export function buildAnnualVsTtmFilterLabel(def) {
  const metrics = normalizeMetrics(def);
  const metricLabel = metrics
    .map((k) => (k === 'net_income' ? 'Net Income' : 'Total Revenue'))
    .join(' + ');
  const cond = normalizeCondition(def?.condition) === 'ttm_lt_annual'
    ? 'TTM < Annual'
    : 'TTM > Annual';
  return `${metricLabel}: ${cond}`;
}

export default function AnnualVsTtmFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = initialValues || {};
  const [metrics, setMetrics] = useState(() => normalizeMetrics(init));
  const [condition, setCondition] = useState(() => normalizeCondition(init.condition));
  const [basis, setBasis] = useState(init.basis || 'consolidated');
  const [metricErr, setMetricErr] = useState('');
  const isEditMode = !!initialValues;

  function toggleMetric(key) {
    setMetricErr('');
    setMetrics((prev) => {
      if (prev.includes(key)) {
        if (prev.length === 1) return prev; // keep at least one selected
        return prev.filter((k) => k !== key);
      }
      return METRICS.map((m) => m.key).filter((k) => k === key || prev.includes(k));
    });
  }

  function handleApply() {
    if (!metrics.length) {
      setMetricErr('Select at least one metric');
      return;
    }
    onApply({
      filter_type: 'annual_vs_ttm',
      metrics,
      condition,
      basis,
    });
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.5)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          width: 420,
          boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '12px 16px',
            borderBottom: '1px solid var(--border)',
            backgroundColor: 'var(--bg-tertiary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {isEditMode ? 'Edit Annual vs TTM Filter' : 'Annual vs TTM Filter'}
          </span>
          <button type="button" onClick={onCancel} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18 }}>
            ×
          </button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div
            style={{
              fontSize: 11,
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-tertiary)',
              borderRadius: 4,
              padding: '8px 10px',
              border: '1px solid var(--border)',
              lineHeight: 1.45,
            }}
          >
            Compares trailing twelve months (latest 4 Screener quarters) to the last completed
            financial year. Select one or both metrics — both must match when both are selected.
            Uses cached Screener data only.
          </div>

          <div>
            <div style={sectionLabel}>Metrics (select one or both)</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {METRICS.map((item) => (
                <Chip
                  key={item.key}
                  item={item}
                  isSelected={metrics.includes(item.key)}
                  onSelect={toggleMetric}
                />
              ))}
            </div>
            {metricErr && (
              <div style={{ fontSize: 10, color: 'var(--accent-red)', marginTop: 6 }}>{metricErr}</div>
            )}
          </div>

          <div>
            <div style={sectionLabel}>Condition</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {CONDITIONS.map((item) => (
                <Chip key={item.key} item={item} isSelected={condition === item.key} onSelect={setCondition} />
              ))}
            </div>
          </div>

          <div>
            <div style={sectionLabel}>Basis</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {BASES.map((item) => (
                <Chip key={item.key} item={item} isSelected={basis === item.key} onSelect={setBasis} />
              ))}
            </div>
          </div>

          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            Preview chip:{' '}
            <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
              {buildAnnualVsTtmFilterLabel({ metrics, condition })}
            </span>
          </div>
        </div>

        <div
          style={{
            padding: '12px 16px',
            borderTop: '1px solid var(--border)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
          }}
        >
          <button
            type="button"
            onClick={onCancel}
            style={{
              backgroundColor: 'var(--bg-tertiary)',
              border: '1px solid var(--border)',
              borderRadius: 5,
              padding: '6px 14px',
              color: 'var(--text-secondary)',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleApply}
            style={{
              backgroundColor: 'var(--accent-blue)',
              border: 'none',
              borderRadius: 5,
              padding: '6px 14px',
              color: '#fff',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {isEditMode ? 'Update' : 'Apply'}
          </button>
        </div>
      </div>
    </div>
  );
}
