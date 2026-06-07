import React, { useState } from 'react';

const CONDITIONS = [
  { key: 'above',        label: 'Above'          },
  { key: 'above_eq',     label: 'Above or Equal'  },
  { key: 'below',        label: 'Below'           },
  { key: 'below_eq',     label: 'Below or Equal'  },
  { key: 'crosses_up',   label: 'Crosses Up'      },
  { key: 'crosses_down', label: 'Crosses Down'    },
  { key: 'above_pct',    label: 'Above %'         },
  { key: 'below_pct',    label: 'Below %'         },
];

const TARGETS = [
  { key: 'open',  label: 'Open'  },
  { key: 'high',  label: 'High'  },
  { key: 'low',   label: 'Low'   },
  { key: 'ema',   label: 'EMA'   },
];

const TIMEFRAME_GROUPS = {
  D: ['1D','2D','3D','4D','5D','6D','7D'],
  W: ['1W','2W','3W','4W'],
  M: ['1M','2M','3M','4M','5M','6M','7M','8M','9M','10M','11M','12M'],
};

function getTFGroupKey(tf) {
  if (!tf) return 'D';
  if (/^\d+m$/.test(tf) || /^\d+h$/.test(tf)) return 'D';
  if (tf.endsWith('D')) return 'D';
  if (tf.endsWith('W')) return 'W';
  return 'M';
}

const inputStyle = {
  backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)',
  borderRadius: 4, padding: '4px 8px', color: 'var(--text-primary)',
  fontSize: 12, fontFamily: 'var(--font-mono)',
};

const sectionLabel = {
  fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
  textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8,
};

function Chip({ item, isSelected, onSelect }) {
  return (
    <div onClick={() => onSelect(item.key)} style={{
      padding: '5px 10px', borderRadius: 5, cursor: 'pointer',
      backgroundColor: isSelected ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)',
      border: `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border)'}`,
      fontSize: 12, color: isSelected ? 'var(--accent-blue)' : 'var(--text-secondary)',
      userSelect: 'none',
    }}>
      {item.label}
    </div>
  );
}

export default function PriceFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = initialValues || {};

  const [tfGroup,   setTfGroup]   = useState(getTFGroupKey(init.timeframe || '1D'));
  const [timeframe, setTimeframe] = useState(init.timeframe  || '1D');
  const [condition, setCondition] = useState(init.condition  || 'above');
  const [pctValue,  setPctValue]  = useState(init.pct_value != null && init.pct_value !== 0 ? String(init.pct_value) : '');
  const [target,    setTarget]    = useState(init.target     || 'ema');
  const [emaPeriod, setEmaPeriod] = useState(init.ema_period || 21);

  const isEditMode = !!initialValues;
  const showPct    = condition === 'above_pct' || condition === 'below_pct';
  const showEma    = target === 'ema';

  function handleApply() {
    if (showPct && (!pctValue || isNaN(parseFloat(pctValue)))) {
      alert('Please enter a valid % value'); return;
    }
    if (showEma) {
      const period = parseInt(emaPeriod);
      if (isNaN(period) || period < 1 || period > 500) {
        alert('EMA period must be between 1 and 500'); return;
      }
    }
    onApply({
      filter_type: 'price',
      timeframe,
      condition,
      pct_value:  showPct ? parseFloat(pctValue) : 0,
      target,
      ema_period: showEma ? parseInt(emaPeriod) : 21,
    });
  }

  function chipLabel() {
    const cond = {
      above: '>', above_eq: '≥', below: '<', below_eq: '≤',
      crosses_up: '↑✕', crosses_down: '↓✕',
      above_pct: `>${pctValue}%`, below_pct: `<${pctValue}%`,
    }[condition] || '>';
    const tgtStr = target === 'ema'
      ? `EMA ${emaPeriod} (${timeframe})`
      : `${target.charAt(0).toUpperCase() + target.slice(1)} (${timeframe})`;
    return `Price ${cond} ${tgtStr}`;
  }

  return (
    <div style={{ position:'fixed', inset:0, backgroundColor:'rgba(0,0,0,0.5)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}>
      <div style={{ backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:8, width:480, maxHeight:'90vh', boxShadow:'0 16px 48px rgba(0,0,0,0.6)', overflow:'hidden' }}>

        {/* Header */}
        <div style={{ padding:'12px 16px', borderBottom:'1px solid var(--border)', backgroundColor:'var(--bg-tertiary)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <span style={{ fontSize:13, fontWeight:600, color:'var(--text-primary)' }}>
              {isEditMode ? 'Edit Price Filter' : 'Price Filter'}
            </span>
            <span style={{ fontSize:10, color:'var(--text-muted)', fontFamily:'var(--font-mono)', backgroundColor:'var(--bg-active)', padding:'2px 8px', borderRadius:3 }}>Source: Last Close</span>
          </div>
          <button onClick={onCancel} style={{ background:'none', color:'var(--text-muted)', fontSize:18 }}>×</button>
        </div>

        <div style={{ padding:16, display:'flex', flexDirection:'column', gap:18, overflowY:'auto', maxHeight:'calc(90vh - 52px)' }}>

          {/* Timeframe — shared by price source and all targets */}
          <div>
            <div style={sectionLabel}>Timeframe</div>
            <div style={{ display:'flex', gap:4, marginBottom:8, flexWrap:'nowrap', overflowX:'auto', WebkitOverflowScrolling:'touch' }}>
              {Object.keys(TIMEFRAME_GROUPS).map(g => (
                <button key={g} onClick={() => { setTfGroup(g); setTimeframe(TIMEFRAME_GROUPS[g][0]); }}
                  style={{ flexShrink:0, padding:'4px 14px', borderRadius:4, cursor:'pointer', fontSize:12, fontFamily:'var(--font-mono)', fontWeight:600,
                    backgroundColor: tfGroup===g ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                    border:`1px solid ${tfGroup===g ? 'var(--accent-blue)' : 'var(--border)'}`,
                    color: tfGroup===g ? '#fff' : 'var(--text-secondary)' }}>
                  {g}
                </button>
              ))}
            </div>
            <div style={{ display:'flex', flexWrap:'nowrap', gap:3, overflowX:'auto', WebkitOverflowScrolling:'touch' }}>
              {TIMEFRAME_GROUPS[tfGroup].map(tf => (
                <button key={tf} onClick={() => setTimeframe(tf)}
                  style={{ flexShrink:0, padding:'3px 8px', borderRadius:4, cursor:'pointer', fontSize:11, fontFamily:'var(--font-mono)',
                    backgroundColor: timeframe===tf ? 'rgba(56,139,253,0.15)' : 'transparent',
                    border:`1px solid ${timeframe===tf ? 'var(--accent-blue)' : 'var(--border)'}`,
                    color: timeframe===tf ? 'var(--accent-blue)' : 'var(--text-secondary)' }}>
                  {tf}
                </button>
              ))}
            </div>
            <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:6 }}>
              Price source = last candle close · Open / High / Low = last candle of this timeframe
            </div>
          </div>

          {/* Condition */}
          <div>
            <div style={sectionLabel}>Condition</div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
              {CONDITIONS.map(item => (
                <Chip key={item.key} item={item} isSelected={condition===item.key} onSelect={setCondition} />
              ))}
            </div>
            {showPct && (
              <div style={{ display:'flex', alignItems:'center', gap:8, marginTop:10 }}>
                <span style={{ fontSize:12, color:'var(--text-secondary)' }}>% Value</span>
                <input type="number" min="0" step="0.1" value={pctValue}
                  onChange={e => setPctValue(e.target.value)} placeholder="e.g. 5"
                  style={{ ...inputStyle, width:90 }} />
              </div>
            )}
          </div>

          {/* Target */}
          <div>
            <div style={sectionLabel}>Target Value</div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
              {TARGETS.map(item => (
                <Chip key={item.key} item={item} isSelected={target===item.key} onSelect={setTarget} />
              ))}
            </div>
            {showEma && (
              <div style={{ display:'flex', alignItems:'center', gap:8, marginTop:10 }}>
                <span style={{ fontSize:12, color:'var(--text-secondary)' }}>EMA Period</span>
                <input type="number" min="1" max="500" value={emaPeriod}
                  onChange={e => setEmaPeriod(e.target.value)}
                  style={{ ...inputStyle, width:70 }} />
                <span style={{ fontSize:11, color:'var(--text-muted)' }}>uses same timeframe as above</span>
              </div>
            )}
          </div>

          {/* Preview */}
          <div style={{ backgroundColor:'var(--bg-tertiary)', borderRadius:5, padding:'8px 12px', border:'1px solid var(--border)', fontSize:12, color:'var(--accent-blue)', fontFamily:'var(--font-mono)' }}>
            Filter: {chipLabel()}
          </div>

          {/* Buttons */}
          <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
            <button onClick={onCancel} style={{ padding:'7px 16px', borderRadius:5, fontSize:12, cursor:'pointer', backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', color:'var(--text-secondary)' }}>Cancel</button>
            <button onClick={handleApply} style={{ padding:'7px 16px', borderRadius:5, fontSize:12, cursor:'pointer', backgroundColor:'var(--accent-blue)', border:'none', color:'#fff', fontWeight:600 }}>
              {isEditMode ? 'Update Filter' : 'Apply Filter'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}