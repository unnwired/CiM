import React, { useState } from 'react';

const TIMEFRAME_GROUPS = {
  D: ['4H', '1D', '2D', '3D', '4D', '5D', '6D', '7D'],
  W: ['1W', '2W', '3W', '4W'],
  M: ['1M', '2M', '3M', '4M', '5M', '6M', '7M', '8M', '9M', '10M', '11M', '12M'],
};

function getTFGroupKey(tf) {
  if (!tf) return 'D';
  if (/^\d+m$/.test(tf) || /^\d+[Hh]$/.test(tf)) return 'D';
  if (tf.endsWith('D')) return 'D';
  if (tf.endsWith('W')) return 'W';
  return 'M';
}

function tfForGroup(g) {
  return g === 'D' ? '1D' : TIMEFRAME_GROUPS[g][0];
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

export default function RangeChannelFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = initialValues || {};
  const [tfGroup, setTfGroup] = useState(getTFGroupKey(init.timeframe || '3D'));
  const [timeframe, setTimeframe] = useState(init.timeframe || '3D');
  const [lookbackBars, setLookbackBars] = useState(String(init.lookback_bars ?? 18));
  const [maxWidthPct, setMaxWidthPct] = useState(String(init.max_channel_width_pct ?? 20));
  const [macdStragglers, setMacdStragglers] = useState(String(init.macd_allowed_stragglers ?? 2));
  const [histStragglers, setHistStragglers] = useState(String(init.hist_flat_stragglers ?? 2));
  const isEditMode = !!initialValues;

  function handleApply() {
    const lookback = parseInt(lookbackBars, 10);
    const width = parseFloat(maxWidthPct);
    const macdStr = parseInt(macdStragglers, 10);
    const histStr = parseInt(histStragglers, 10);
    if (Number.isNaN(lookback) || lookback < 4) {
      alert('Lookback bars must be at least 4');
      return;
    }
    if (Number.isNaN(width) || width < 5) {
      alert('Max channel width must be at least 5%');
      return;
    }
    if (Number.isNaN(macdStr) || macdStr < 0 || macdStr > 3) {
      alert('MACD stragglers must be 0–3');
      return;
    }
    if (Number.isNaN(histStr) || histStr < 0 || histStr > 5) {
      alert('Histogram stragglers must be 0–5');
      return;
    }
    onApply({
      filter_type: 'range_channel',
      timeframe,
      lookback_bars: lookback,
      max_channel_width_pct: width,
      macd_allowed_stragglers: macdStr,
      hist_flat_stragglers: histStr,
    });
  }

  function chipLabel() {
    return `${timeframe} Range ≤${maxWidthPct}% · MACD+ (≤${macdStragglers} str) · Hist flat (≤${histStragglers} str, no spikes)`;
  }

  return (
    <div
      style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8, width: 460, maxHeight: '90vh', overflow: 'auto', boxShadow: '0 16px 48px rgba(0,0,0,0.6)' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {isEditMode ? 'Edit Range Channel Filter' : 'Range Channel Filter'}
          </span>
          <button type="button" onClick={onCancel} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18 }}>×</button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', backgroundColor: 'var(--bg-tertiary)', borderRadius: 4, padding: '8px 10px', border: '1px solid var(--border)', lineHeight: 1.45 }}>
            Finds sideways horizontal channels with MACD line above signal. Histogram <b>spikes always fail</b> (breakout) — they are never counted as stragglers.
          </div>

          <div>
            <div style={sectionLabel}>Timeframe</div>
            <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
              {['D', 'W', 'M'].map(g => (
                <button
                  key={g}
                  type="button"
                  onClick={() => { setTfGroup(g); setTimeframe(tfForGroup(g)); }}
                  style={{
                    padding: '4px 14px', borderRadius: 4, cursor: 'pointer', fontSize: 12, fontFamily: 'var(--font-mono)', fontWeight: 600,
                    backgroundColor: tfGroup === g ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                    border: `1px solid ${tfGroup === g ? 'var(--accent-blue)' : 'var(--border)'}`,
                    color: tfGroup === g ? '#fff' : 'var(--text-secondary)',
                  }}
                >{g}</button>
              ))}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {TIMEFRAME_GROUPS[tfGroup].map(tf => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => setTimeframe(tf)}
                  style={{
                    padding: '3px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 11, fontFamily: 'var(--font-mono)',
                    backgroundColor: timeframe === tf ? 'rgba(56,139,253,0.15)' : 'transparent',
                    border: `1px solid ${timeframe === tf ? 'var(--accent-blue)' : 'var(--border)'}`,
                    color: timeframe === tf ? 'var(--accent-blue)' : 'var(--text-secondary)',
                  }}
                >{tf}</button>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <div style={{ ...sectionLabel, marginBottom: 6 }}>Lookback bars</div>
              <input type="number" min="4" max="40" value={lookbackBars} onChange={e => setLookbackBars(e.target.value)} style={{ ...inputStyle, width: '100%' }} />
            </div>
            <div>
              <div style={{ ...sectionLabel, marginBottom: 6 }}>Max channel width %</div>
              <input type="number" min="5" max="60" step="0.5" value={maxWidthPct} onChange={e => setMaxWidthPct(e.target.value)} style={{ ...inputStyle, width: '100%' }} />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <div style={{ ...sectionLabel, marginBottom: 6 }}>MACD+ stragglers</div>
              <input type="number" min="0" max="3" value={macdStragglers} onChange={e => setMacdStragglers(e.target.value)} style={{ ...inputStyle, width: '100%' }} />
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>Bars where MACD ≤ signal (default 2)</div>
            </div>
            <div>
              <div style={{ ...sectionLabel, marginBottom: 6 }}>Hist flat stragglers</div>
              <input type="number" min="0" max="5" value={histStragglers} onChange={e => setHistStragglers(e.target.value)} style={{ ...inputStyle, width: '100%' }} />
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>Minor wobbles only — spikes always fail</div>
            </div>
          </div>

          <div style={{ backgroundColor: 'var(--bg-tertiary)', borderRadius: 5, padding: '8px 12px', border: '1px solid var(--border)', fontSize: 12, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)' }}>
            Filter: {chipLabel()}
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
