import React, { useState } from 'react';
import { formatMarketCap } from '../utils/formatMarketCap';

const sectionLabel = {
  fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
  textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8,
};

const inputStyle = {
  backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)',
  borderRadius: 4, padding: '6px 10px', color: 'var(--text-primary)',
  fontSize: 13, fontFamily: 'var(--font-mono)', width: '100%',
  outline: 'none',
};

// Parse abbreviations: 500K → 500000, 2.5M → 2500000, 1B → 1000000000
function parseValue(raw) {
  if (!raw || !raw.toString().trim()) return null;
  const s = raw.toString().trim().toUpperCase().replace(/,/g, '');
  if (s.endsWith('B'))   { const n = parseFloat(s); return isNaN(n) ? null : n * 1e9; }
  if (s.endsWith('M'))   { const n = parseFloat(s); return isNaN(n) ? null : n * 1e6; }
  if (s.endsWith('K'))   { const n = parseFloat(s); return isNaN(n) ? null : n * 1e3; }
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

export default function MarketCapFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = initialValues || {};

  const [fromRaw, setFromRaw] = useState(init.from_raw || '');
  const [toRaw,   setToRaw]   = useState(init.to_raw   || '');
  const [fromErr, setFromErr] = useState('');
  const [toErr,   setToErr]   = useState('');

  const isEditMode = !!initialValues;

  const fromVal = parseValue(fromRaw);
  const toVal   = parseValue(toRaw);

  function validate() {
    let ok = true;
    setFromErr(''); setToErr('');
    if (fromRaw.trim() && fromVal === null) { setFromErr('Invalid value'); ok = false; }
    if (toRaw.trim()   && toVal   === null) { setToErr('Invalid value');   ok = false; }
    if (fromVal !== null && toVal !== null && fromVal > toVal) {
      setToErr('Must be ≥ From value'); ok = false;
    }
    if (!fromRaw.trim() && !toRaw.trim()) {
      setFromErr('Enter at least one value'); ok = false;
    }
    return ok;
  }

  function handleApply() {
    if (!validate()) return;
    onApply({
      filter_type: 'marketcap',
      from_value:  fromVal,
      to_value:    toVal,
      from_raw:    fromRaw,
      to_raw:      toRaw,
    });
  }

  function chipLabel() {
    if (fromVal !== null && toVal !== null) return `Mkt Cap ${formatMarketCap(fromVal)} – ${formatMarketCap(toVal)}`;
    if (fromVal !== null) return `Mkt Cap ≥ ${formatMarketCap(fromVal)}`;
    if (toVal   !== null) return `Mkt Cap ≤ ${formatMarketCap(toVal)}`;
    return 'Market Cap filter';
  }

  return (
    <div style={{ position:'fixed', inset:0, backgroundColor:'rgba(0,0,0,0.5)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}>
      <div style={{ backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:8, width:400, boxShadow:'0 16px 48px rgba(0,0,0,0.6)', overflow:'hidden' }}>

        {/* Header */}
        <div style={{ padding:'12px 16px', borderBottom:'1px solid var(--border)', backgroundColor:'var(--bg-tertiary)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <span style={{ fontSize:13, fontWeight:600, color:'var(--text-primary)' }}>
            {isEditMode ? 'Edit Market Cap Filter' : 'Market Cap Filter'}
          </span>
          <button onClick={onCancel} style={{ background:'none', color:'var(--text-muted)', fontSize:18 }}>×</button>
        </div>

        <div style={{ padding:16, display:'flex', flexDirection:'column', gap:16 }}>

          {/* Hint */}
          <div style={{ fontSize:11, color:'var(--text-muted)', backgroundColor:'var(--bg-tertiary)', borderRadius:4, padding:'6px 10px', border:'1px solid var(--border)' }}>
            Accepts: <span style={{ fontFamily:'var(--font-mono)', color:'var(--text-secondary)' }}>500000</span> or abbreviations: <span style={{ fontFamily:'var(--font-mono)', color:'var(--text-secondary)' }}>500K · 2.5M · 1B</span> (preview always ₹M / ₹B / ₹T)
          </div>

          {/* From / To */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
            <div>
              <div style={{ ...sectionLabel, marginBottom:6 }}>From</div>
              <input value={fromRaw} onChange={e => { setFromRaw(e.target.value); setFromErr(''); }}
                placeholder="e.g. 500M" style={{ ...inputStyle, border: fromErr ? '1px solid var(--accent-red)' : '1px solid var(--border)' }} />
              {fromVal !== null && !fromErr && (
                <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:3, fontFamily:'var(--font-mono)' }}>{formatMarketCap(fromVal)}</div>
              )}
              {fromErr && <div style={{ fontSize:10, color:'var(--accent-red)', marginTop:3 }}>{fromErr}</div>}
            </div>
            <div>
              <div style={{ ...sectionLabel, marginBottom:6 }}>To</div>
              <input value={toRaw} onChange={e => { setToRaw(e.target.value); setToErr(''); }}
                placeholder="e.g. 50B" style={{ ...inputStyle, border: toErr ? '1px solid var(--accent-red)' : '1px solid var(--border)' }} />
              {toVal !== null && !toErr && (
                <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:3, fontFamily:'var(--font-mono)' }}>{formatMarketCap(toVal)}</div>
              )}
              {toErr && <div style={{ fontSize:10, color:'var(--accent-red)', marginTop:3 }}>{toErr}</div>}
            </div>
          </div>

          {/* Legend */}
          <div style={{ fontSize:11, color:'var(--text-muted)', display:'flex', flexDirection:'column', gap:2 }}>
            <span>• <b>From</b> only → market cap ≥ From value</span>
            <span>• <b>To</b> only → market cap ≤ To value</span>
            <span>• <b>Both</b> → market cap within range</span>
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