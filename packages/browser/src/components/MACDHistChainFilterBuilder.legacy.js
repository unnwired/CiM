import React, { useState } from 'react';
import MACDHistChainPreview from './MACDHistChainPreview';

const TIMEFRAME_GROUPS = {
  D: ['1D', '2D', '3D', '4D', '5D', '6D', '7D'],
  W: ['1W', '2W', '3W', '4W'],
  M: ['1M', '2M', '3M', '4M', '5M', '6M', '7M', '8M', '9M', '10M', '11M', '12M'],
};

const SIDE_OPTIONS = [
  { key: 'negative', label: 'Negative only', desc: 'All bars below zero' },
  { key: 'positive', label: 'Positive only', desc: 'All bars above zero' },
  { key: 'both', label: 'Both', desc: 'Either side chain' },
];

const CHAIN_MODE_OPTIONS = [
  { key: 'receding', label: 'Receding', desc: 'Magnitude moves toward zero' },
  { key: 'increasing', label: 'Increasing', desc: 'Magnitude moves away from zero' },
];

function getTFGroupKey(tf) {
  if (!tf) return 'D';
  if (/^\d+m$/.test(tf) || /^\d+h$/.test(tf)) return 'D';
  if (tf.endsWith('D')) return 'D';
  if (tf.endsWith('W')) return 'W';
  return 'M';
}

const inputStyle = {
  backgroundColor: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  padding: '4px 8px',
  color: 'var(--text-primary)',
  fontSize: 12,
  fontFamily: 'var(--font-mono)',
};

const sectionLabel = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 8,
};

function RadioChip({ item, isSelected, onSelect }) {
  return (
    <div
      onClick={() => onSelect(item.key)}
      style={{
        display: 'flex',
        flexDirection: 'column',
        padding: '6px 12px',
        borderRadius: 5,
        cursor: 'pointer',
        backgroundColor: isSelected ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)',
        border: `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border)'}`,
        userSelect: 'none',
        minWidth: 98,
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 600, color: isSelected ? 'var(--accent-blue)' : 'var(--text-secondary)' }}>
        {item.label}
      </span>
      {item.desc && (
        <span style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{item.desc}</span>
      )}
    </div>
  );
}

export default function MACDHistChainFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = initialValues || {};
  const [tfGroup, setTfGroup] = useState(getTFGroupKey(init.timeframe || '1D'));
  const [timeframe, setTimeframe] = useState(init.timeframe || '1D');
  const [barsToCompare, setBarsToCompare] = useState(String(init.bars_to_compare ?? 4));
  const [allowedStragglers, setAllowedStragglers] = useState(String(init.allowed_stragglers ?? 0));
  const [histogramSide, setHistogramSide] = useState(init.histogram_side || 'negative');
  const [chainMode, setChainMode] = useState(init.chain_mode || 'receding');
  const [allowCrossZero, setAllowCrossZero] = useState(Boolean(init.allow_cross_zero));
  const isEditMode = !!initialValues;
  const crossZeroApplies = histogramSide === 'both';

  function handleHistogramSideChange(side) {
    setHistogramSide(side);
    if (side !== 'both') setAllowCrossZero(false);
  }

  function handleApply() {
    const bars = parseInt(barsToCompare, 10);
    const stragglers = parseInt(allowedStragglers, 10);
    if (Number.isNaN(bars) || bars < 2) {
      alert('Bars to compare must be at least 2');
      return;
    }
    if (Number.isNaN(stragglers) || stragglers < 0) {
      alert('Allowed stragglers must be 0 or greater');
      return;
    }
    onApply({
      filter_type: 'macd_hist_chain',
      timeframe,
      bars_to_compare: bars,
      allowed_stragglers: stragglers,
      histogram_side: histogramSide,
      chain_mode: chainMode,
      allow_cross_zero: crossZeroApplies ? allowCrossZero : false,
    });
  }

  function chipLabel() {
    const modeLabel = chainMode === 'increasing' ? 'increasing' : 'receding';
    const sideLabel = histogramSide === 'negative' ? 'neg' : histogramSide === 'positive' ? 'pos' : 'both';
    const crossLabel = histogramSide === 'both'
      ? (allowCrossZero ? 'cross-zero' : 'same-side')
      : null;
    const parts = [
      `MACD Histogram (${timeframe})`,
      modeLabel,
      `${barsToCompare || '4'} bars`,
      `stragglers ${allowedStragglers || '0'}`,
      sideLabel,
    ];
    if (crossLabel) parts.push(crossLabel);
    return parts.join(' · ');
  }

  return (
    <div
      style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8, width: 520, boxShadow: '0 16px 48px rgba(0,0,0,0.6)', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              {isEditMode ? 'Edit MACD Histogram Filter' : 'MACD Histogram Filter'}
            </span>
          </div>
          <button onClick={onCancel} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18 }}>×</button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 18, maxHeight: 'calc(90vh - 52px)', overflowY: 'auto' }}>
          <div>
            <div style={sectionLabel}>Timeframe</div>
            <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'nowrap', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
              {Object.keys(TIMEFRAME_GROUPS).map(g => (
                <button
                  key={g}
                  onClick={() => { setTfGroup(g); setTimeframe(TIMEFRAME_GROUPS[g][0]); }}
                  style={{
                    flexShrink: 0,
                    padding: '4px 14px',
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontSize: 12,
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                    backgroundColor: tfGroup === g ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                    border: `1px solid ${tfGroup === g ? 'var(--accent-blue)' : 'var(--border)'}`,
                    color: tfGroup === g ? '#fff' : 'var(--text-secondary)',
                  }}
                >{g}</button>
              ))}
            </div>
            <div style={{ display: 'flex', flexWrap: 'nowrap', gap: 4, overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
              {TIMEFRAME_GROUPS[tfGroup].map(tf => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  style={{
                    flexShrink: 0,
                    padding: '3px 8px',
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                    backgroundColor: timeframe === tf ? 'rgba(56,139,253,0.15)' : 'transparent',
                    border: `1px solid ${timeframe === tf ? 'var(--accent-blue)' : 'var(--border)'}`,
                    color: timeframe === tf ? 'var(--accent-blue)' : 'var(--text-secondary)',
                  }}
                >{tf}</button>
              ))}
            </div>
          </div>

          <div>
            <div style={sectionLabel}>Chain Direction</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {CHAIN_MODE_OPTIONS.map(item => (
                <RadioChip key={item.key} item={item} isSelected={chainMode === item.key} onSelect={setChainMode} />
              ))}
            </div>
          </div>

          <div>
            <div style={sectionLabel}>Histogram Side</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {SIDE_OPTIONS.map(item => (
                <RadioChip key={item.key} item={item} isSelected={histogramSide === item.key} onSelect={handleHistogramSideChange} />
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Bars to compare</span>
              <input
                type="number"
                min="2"
                step="1"
                value={barsToCompare}
                onChange={e => setBarsToCompare(e.target.value)}
                style={{ ...inputStyle, width: 80 }}
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Allowed stragglers</span>
              <input
                type="number"
                min="0"
                step="1"
                value={allowedStragglers}
                onChange={e => setAllowedStragglers(e.target.value)}
                style={{ ...inputStyle, width: 80 }}
              />
            </div>
          </div>

          <label
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
              cursor: crossZeroApplies ? 'pointer' : 'not-allowed',
              userSelect: 'none',
              opacity: crossZeroApplies ? 1 : 0.5,
            }}
            title={crossZeroApplies ? undefined : 'Only applies when Histogram side is Both'}
          >
            <input
              type="checkbox"
              checked={crossZeroApplies && allowCrossZero}
              disabled={!crossZeroApplies}
              onChange={e => setAllowCrossZero(e.target.checked)}
            />
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
              Allow Cross-Zero Chain
              {!crossZeroApplies && (
                <span style={{ display: 'block', fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                  Select Both to allow chains that cross the zero line.
                </span>
              )}
            </span>
          </label>

          <div>
            <div style={sectionLabel}>Visual Example</div>
            <MACDHistChainPreview
              chainMode={chainMode}
              histogramSide={histogramSide}
              allowCrossZero={crossZeroApplies && allowCrossZero}
              barsToCompare={barsToCompare}
            />
          </div>

          <div style={{ backgroundColor: 'var(--bg-tertiary)', borderRadius: 5, padding: '8px 12px', border: '1px solid var(--border)', fontSize: 12, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)' }}>
            Filter: {chipLabel()}
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button
              onClick={onCancel}
              style={{ padding: '7px 16px', borderRadius: 5, fontSize: 12, cursor: 'pointer', backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
            >
              Cancel
            </button>
            <button
              onClick={handleApply}
              style={{ padding: '7px 16px', borderRadius: 5, fontSize: 12, cursor: 'pointer', backgroundColor: 'var(--accent-blue)', border: 'none', color: '#fff', fontWeight: 600 }}
            >
              {isEditMode ? 'Update Filter' : 'Apply Filter'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
