import React, { useState } from 'react';
import StochRSIFilterPreview from './StochRSIFilterPreview';

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

// Source: which StochRSI line the condition is applied FROM
const SOURCE_PLOTS = [
  { key: 'k', label: '%K', desc: 'K line' },
  { key: 'd', label: '%D', desc: 'D line' },
];

// Target: what the source is compared TO
const TARGET_PLOTS = [
  { key: 'value', label: 'Value', desc: '0 – 100 range' },
  { key: 'k',     label: '%K',    desc: 'K line'        },
  { key: 'd',     label: '%D',    desc: 'D line'        },
];

const TIMEFRAME_GROUPS = {
  D: ['4H','1D','2D','3D','4D','5D','6D','7D'],
  W: ['1W','2W','3W','4W'],
  M: ['1M','2M','3M','4M','5M','6M','7M','8M','9M','10M','11M','12M'],
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
  border:          '1px solid var(--border)',
  borderRadius:    4,
  padding:         '4px 8px',
  color:           'var(--text-primary)',
  fontSize:        12,
  fontFamily:      'var(--font-mono)',
};

const sectionLabel = {
  fontSize:      11,
  fontWeight:    600,
  color:         'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom:  8,
};

function RadioChip({ item, isSelected, disabled, onSelect }) {
  return (
    <div
      onClick={() => !disabled && onSelect(item.key)}
      style={{
        display:         'flex',
        flexDirection:   'column',
        padding:         '6px 12px',
        borderRadius:    5,
        cursor:          disabled ? 'not-allowed' : 'pointer',
        backgroundColor: isSelected
          ? 'rgba(56,139,253,0.15)'
          : disabled ? 'var(--bg-primary)' : 'var(--bg-tertiary)',
        border:    `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border)'}`,
        opacity:   disabled ? 0.4 : 1,
        userSelect:'none',
        minWidth:  72,
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 600, color: isSelected ? 'var(--accent-blue)' : disabled ? 'var(--text-muted)' : 'var(--text-secondary)' }}>
        {item.label}
      </span>
      {item.desc && (
        <span style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{item.desc}</span>
      )}
    </div>
  );
}

function ConditionChip({ item, isSelected, onSelect }) {
  return (
    <div
      onClick={() => onSelect(item.key)}
      style={{
        padding:         '5px 10px',
        borderRadius:    5,
        cursor:          'pointer',
        backgroundColor: isSelected ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)',
        border:          `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border)'}`,
        fontSize:        12,
        color:           isSelected ? 'var(--accent-blue)' : 'var(--text-secondary)',
        userSelect:      'none',
      }}
    >
      {item.label}
    </div>
  );
}

// initialValues — when provided, the builder opens pre-populated (edit mode)
export default function StochRSIFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = initialValues || {};

  const [source,    setSource]    = useState(init.source    || 'k');
  const [tfGroup,   setTfGroup]   = useState(getTFGroupKey(init.timeframe || '1D'));
  const [timeframe, setTimeframe] = useState(init.timeframe || '1D');
  const [condition, setCondition] = useState(init.condition || 'above');
  const [pctValue,  setPctValue]  = useState(init.pct_value != null && init.pct_value !== 0 ? String(init.pct_value) : '');
  const [target,    setTarget]    = useState(init.target    || 'value');
  const [targetVal, setTargetVal] = useState(init.target_value != null ? String(init.target_value) : '80');

  const isEditMode = !!initialValues;
  const showPct    = condition === 'above_pct' || condition === 'below_pct';
  const showValIn  = target === 'value';

  // Mutual exclusion: target cannot be same line as source
  function isTargetDisabled(tKey) {
    if (tKey === 'value') return false;
    return tKey === source;
  }

  function handleSetSource(key) {
    setSource(key);
    if (target === key) setTarget('value');
  }

  function handleSetTarget(key) {
    if (isTargetDisabled(key)) return;
    setTarget(key);
  }

  function handleApply() {
    if (showPct && (!pctValue || isNaN(parseFloat(pctValue)))) {
      alert('Please enter a valid % value');
      return;
    }
    if (showValIn && (targetVal === '' || isNaN(parseFloat(targetVal)))) {
      alert('Please enter a valid target value');
      return;
    }
    const tv = parseFloat(targetVal);
    if (showValIn && (tv < 0 || tv > 100)) {
      alert('StochRSI value must be between 0 and 100');
      return;
    }
    onApply({
      filter_type:  'stochrsi',
      source,
      timeframe,
      condition,
      pct_value:    showPct   ? parseFloat(pctValue) : 0,
      target,
      target_value: showValIn ? tv : 0,
    });
  }

  function chipLabel() {
    const srcLabel  = source === 'k' ? 'StochRSI %K' : 'StochRSI %D';
    const condLabel = {
      above: '>', above_eq: '≥', below: '<', below_eq: '≤',
      crosses_up: '↑✕', crosses_down: '↓✕',
      above_pct: `>${pctValue}%`, below_pct: `<${pctValue}%`,
    }[condition] || '>';
    const tgtLabel = target === 'value'
      ? (targetVal || '80')
      : target === 'k' ? '%K' : '%D';
    return `${srcLabel} (${timeframe}) ${condLabel} ${tgtLabel}`;
  }

  return (
    <div
      style={{ position:'fixed', inset:0, backgroundColor:'rgba(0,0,0,0.5)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div style={{ backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:8, width:480, boxShadow:'0 16px 48px rgba(0,0,0,0.6)', overflow:'hidden' }}>

        {/* Header */}
        <div style={{ padding:'12px 16px', borderBottom:'1px solid var(--border)', backgroundColor:'var(--bg-tertiary)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <span style={{ fontSize:13, fontWeight:600, color:'var(--text-primary)' }}>
              {isEditMode ? 'Edit StochRSI Filter' : 'StochRSI Filter'}
            </span>
            <span style={{ fontSize:10, color:'var(--text-muted)', fontFamily:'var(--font-mono)', backgroundColor:'var(--bg-active)', padding:'2px 8px', borderRadius:3 }}>
              K 3 · D 3 · RSI 14 · Stoch 14
            </span>
          </div>
          <button onClick={onCancel} style={{ background:'none', color:'var(--text-muted)', fontSize:18 }}>×</button>
        </div>

        <div style={{ padding:16, display:'flex', flexDirection:'column', gap:18, maxHeight:'calc(90vh - 52px)', overflowY:'auto' }}>

          {/* Source */}
          <div>
            <div style={sectionLabel}>StochRSI Plot — Source</div>
            <div style={{ display:'flex', gap:8 }}>
              {SOURCE_PLOTS.map(item => (
                <RadioChip key={item.key} item={item} isSelected={source===item.key} disabled={false} onSelect={handleSetSource} />
              ))}
            </div>
          </div>

          {/* Timeframe */}
          <div>
            <div style={sectionLabel}>Timeframe</div>
            <div style={{ display:'flex', gap:4, marginBottom:8, flexWrap:'nowrap', overflowX:'auto', WebkitOverflowScrolling:'touch' }}>
              {Object.keys(TIMEFRAME_GROUPS).map(g => (
                <button key={g}
                  onClick={() => { setTfGroup(g); setTimeframe(tfForGroup(g)); }}
                  style={{
                    flexShrink:0,
                    padding:'4px 14px', borderRadius:4, cursor:'pointer', fontSize:12,
                    fontFamily:'var(--font-mono)', fontWeight:600,
                    backgroundColor: tfGroup===g ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                    border:`1px solid ${tfGroup===g ? 'var(--accent-blue)' : 'var(--border)'}`,
                    color: tfGroup===g ? '#fff' : 'var(--text-secondary)',
                  }}
                >{g}</button>
              ))}
            </div>
            <div style={{ display:'flex', flexWrap:'nowrap', gap:4, overflowX:'auto', WebkitOverflowScrolling:'touch' }}>
              {TIMEFRAME_GROUPS[tfGroup].map(tf => (
                <button key={tf}
                  onClick={() => setTimeframe(tf)}
                  style={{
                    flexShrink:0,
                    padding:'3px 8px', borderRadius:4, cursor:'pointer', fontSize:11,
                    fontFamily:'var(--font-mono)',
                    backgroundColor: timeframe===tf ? 'rgba(56,139,253,0.15)' : 'transparent',
                    border:`1px solid ${timeframe===tf ? 'var(--accent-blue)' : 'var(--border)'}`,
                    color: timeframe===tf ? 'var(--accent-blue)' : 'var(--text-secondary)',
                  }}
                >{tf}</button>
              ))}
            </div>
          </div>

          {/* Condition */}
          <div>
            <div style={sectionLabel}>Condition</div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
              {CONDITIONS.map(item => (
                <ConditionChip key={item.key} item={item} isSelected={condition===item.key} onSelect={setCondition} />
              ))}
            </div>
            {showPct && (
              <div style={{ display:'flex', alignItems:'center', gap:8, marginTop:10 }}>
                <span style={{ fontSize:12, color:'var(--text-secondary)' }}>% Value</span>
                <input
                  type="number" min="0" step="0.1"
                  value={pctValue}
                  onChange={e => setPctValue(e.target.value)}
                  placeholder="e.g. 5"
                  style={{ ...inputStyle, width:90 }}
                />
              </div>
            )}
          </div>

          {/* Target */}
          <div>
            <div style={sectionLabel}>Target Value</div>
            <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
              {TARGET_PLOTS.map(item => (
                <RadioChip
                  key={item.key}
                  item={item}
                  isSelected={target===item.key}
                  disabled={isTargetDisabled(item.key)}
                  onSelect={handleSetTarget}
                />
              ))}
            </div>
            {showValIn && (
              <div style={{ display:'flex', alignItems:'center', gap:8, marginTop:10 }}>
                <span style={{ fontSize:12, color:'var(--text-secondary)' }}>Value</span>
                <input
                  type="number" min="0" max="100" step="1"
                  value={targetVal}
                  onChange={e => setTargetVal(e.target.value)}
                  placeholder="80"
                  style={{ ...inputStyle, width:90 }}
                />
                <span style={{ fontSize:11, color:'var(--text-muted)' }}>range: 0 – 100</span>
              </div>
            )}
          </div>

          {/* Wait for timeframe closes — static label */}
          <div style={{ display:'flex', alignItems:'center', gap:8, backgroundColor:'var(--bg-tertiary)', borderRadius:5, padding:'8px 12px', border:'1px solid var(--border)' }}>
            <div style={{ width:8, height:8, borderRadius:'50%', backgroundColor:'var(--accent-blue)', flexShrink:0 }} />
            <span style={{ fontSize:11, color:'var(--text-secondary)' }}>
              <span style={{ color:'var(--text-primary)', fontWeight:600 }}>Wait for timeframe closes</span>
              {' '}— only fully completed bars are used for calculation
            </span>
          </div>

          <div>
            <div style={sectionLabel}>Visual Example</div>
            <StochRSIFilterPreview
              source={source}
              condition={condition}
              target={target}
              targetValue={targetVal}
              pctValue={pctValue}
            />
          </div>

          {/* Preview */}
          <div style={{ backgroundColor:'var(--bg-tertiary)', borderRadius:5, padding:'8px 12px', border:'1px solid var(--border)', fontSize:12, color:'var(--accent-blue)', fontFamily:'var(--font-mono)' }}>
            Filter: {chipLabel()}
          </div>

          {/* Buttons */}
          <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
            <button onClick={onCancel}
              style={{ padding:'7px 16px', borderRadius:5, fontSize:12, cursor:'pointer', backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', color:'var(--text-secondary)' }}>
              Cancel
            </button>
            <button onClick={handleApply}
              style={{ padding:'7px 16px', borderRadius:5, fontSize:12, cursor:'pointer', backgroundColor:'var(--accent-blue)', border:'none', color:'#fff', fontWeight:600 }}>
              {isEditMode ? 'Update Filter' : 'Apply Filter'}
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}