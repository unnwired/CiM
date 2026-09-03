import React, { useState } from 'react';
import MACDFilterPreview from './MACDFilterPreview';
import MACDHistChainPreview from './MACDHistChainPreview';
import {
  HISTOGRAM_CHAIN_MODE_OPTIONS,
  HISTOGRAM_SIDE_OPTIONS,
  buildMacdCombinedFilterLabel,
  isHistChainEnabled,
  macdFilterInitialValues,
  normalizeChainMode,
  normalizeHistogramSide,
  parseAllowCrossZero,
} from '../utils/macdHistogramFilter';

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

const SOURCE_PLOTS = [
  { key: 'macd',   label: 'Level',  desc: 'MACD line'  },
  { key: 'signal', label: 'Signal', desc: 'Signal line' },
];

const TARGET_PLOTS = [
  { key: 'value',  label: 'Value',  desc: 'Fixed number' },
  { key: 'macd',   label: 'Level',  desc: 'MACD line'    },
  { key: 'signal', label: 'Signal', desc: 'Signal line'  },
];

const TIMEFRAME_GROUPS = {
  D: ['30m','4H','1D','2D','3D','4D','5D','6D','7D'],
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
  backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)',
  borderRadius: 4, padding: '4px 8px', color: 'var(--text-primary)',
  fontSize: 12, fontFamily: 'var(--font-mono)',
};

const sectionLabel = {
  fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
  textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8,
};

function RadioChip({ item, isSelected, disabled, onSelect }) {
  return (
    <div
      onClick={() => !disabled && onSelect(item.key)}
      style={{
        display: 'flex', flexDirection: 'column',
        padding: '6px 12px', borderRadius: 5,
        cursor: disabled ? 'not-allowed' : 'pointer',
        backgroundColor: isSelected ? 'rgba(56,139,253,0.15)' : disabled ? 'var(--bg-primary)' : 'var(--bg-tertiary)',
        border: `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border)'}`,
        opacity: disabled ? 0.4 : 1,
        userSelect: 'none', minWidth: 80,
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

function validateHistogramFields({
  barsToCompare,
  allowedStragglers,
  allowCrossZero,
  crossZeroBars,
  crossZeroStragglers,
}) {
  const bars = parseInt(barsToCompare, 10);
  const stragglers = parseInt(allowedStragglers, 10);
  const czBars = parseInt(crossZeroBars, 10);
  const czStragglers = parseInt(crossZeroStragglers, 10);
  if (Number.isNaN(bars) || bars < 2) {
    alert('Bars to compare must be at least 2');
    return null;
  }
  if (Number.isNaN(stragglers) || stragglers < 0) {
    alert('Allowed stragglers must be 0 or greater');
    return null;
  }
  if (allowCrossZero) {
    if (Number.isNaN(czBars) || czBars < 1) {
      alert('Cross-zero bars must be at least 1');
      return null;
    }
    if (Number.isNaN(czStragglers) || czStragglers < 0) {
      alert('Cross-zero stragglers must be 0 or greater');
      return null;
    }
  }
  return {
    bars_to_compare: bars,
    allowed_stragglers: stragglers,
    ...(allowCrossZero
      ? { cross_zero_bars: czBars, cross_zero_stragglers: czStragglers }
      : {}),
  };
}

export default function MACDFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = macdFilterInitialValues(initialValues);

  const [source, setSource] = useState(init.source === 'signal' ? 'signal' : 'macd');
  const [tfGroup, setTfGroup] = useState(getTFGroupKey(init.timeframe || '1D'));
  const [timeframe, setTimeframe] = useState(init.timeframe || '1D');
  const [condition, setCondition] = useState(init.condition || 'above');
  const [pctValue, setPctValue] = useState(init.pct_value != null && init.pct_value !== 0 ? String(init.pct_value) : '');
  const [target, setTarget] = useState(init.target || 'value');
  const [targetVal, setTargetVal] = useState(init.target_value != null ? String(init.target_value) : '0');

  const [histChainEnabled, setHistChainEnabled] = useState(isHistChainEnabled(init));
  const [barsToCompare, setBarsToCompare] = useState(String(init.bars_to_compare ?? 4));
  const [allowedStragglers, setAllowedStragglers] = useState(String(init.allowed_stragglers ?? 0));
  const [histogramSide, setHistogramSide] = useState(normalizeHistogramSide(init.histogram_side));
  const [chainMode, setChainMode] = useState(normalizeChainMode(init.chain_mode));
  const [allowCrossZero, setAllowCrossZero] = useState(parseAllowCrossZero(init.allow_cross_zero));
  const [crossZeroBars, setCrossZeroBars] = useState(String(init.cross_zero_bars ?? 3));
  const [crossZeroStragglers, setCrossZeroStragglers] = useState(String(init.cross_zero_stragglers ?? 0));

  const isEditMode = !!initialValues;
  const showPct = condition === 'above_pct' || condition === 'below_pct';
  const showValIn = target === 'value';
  const isIncreasing = chainMode === 'increasing';
  const crossBarsLabel = isIncreasing ? 'Bars before cross' : 'Bars after cross';
  const oppositeSide = histogramSide === 'positive' ? 'negative' : 'positive';

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
    const histFields = histChainEnabled
      ? validateHistogramFields({
        barsToCompare,
        allowedStragglers,
        allowCrossZero,
        crossZeroBars,
        crossZeroStragglers,
      })
      : null;
    if (histChainEnabled && !histFields) return;

    if (showPct && (!pctValue || isNaN(parseFloat(pctValue)))) {
      alert('Please enter a valid % value');
      return;
    }
    if (showValIn && (targetVal === '' || isNaN(parseFloat(targetVal)))) {
      alert('Please enter a valid target value');
      return;
    }

    onApply({
      filter_type: 'macd',
      source,
      timeframe,
      condition,
      pct_value: showPct ? parseFloat(pctValue) : 0,
      target,
      target_value: showValIn ? parseFloat(targetVal) : 0,
      hist_chain_enabled: histChainEnabled === true,
      ...(histChainEnabled
        ? {
          chain_mode: chainMode,
          histogram_side: histogramSide,
          allow_cross_zero: allowCrossZero === true,
          ...histFields,
        }
        : {}),
    });
  }

  function previewFilterDef() {
    return {
      source,
      timeframe,
      condition,
      pct_value: showPct ? parseFloat(pctValue) : 0,
      target,
      target_value: showValIn ? parseFloat(targetVal) : 0,
      hist_chain_enabled: histChainEnabled,
      chain_mode: chainMode,
      histogram_side: histogramSide,
      bars_to_compare: barsToCompare,
      allowed_stragglers: allowedStragglers,
      allow_cross_zero: allowCrossZero,
      cross_zero_bars: crossZeroBars,
      cross_zero_stragglers: crossZeroStragglers,
    };
  }

  const crossZeroSectionStyle = {
    opacity: allowCrossZero ? 1 : 0.5,
    pointerEvents: allowCrossZero ? 'auto' : 'none',
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8, width: 520, boxShadow: '0 16px 48px rgba(0,0,0,0.6)', overflow: 'hidden' }}>

        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              {isEditMode ? 'Edit MACD Filter' : 'MACD Filter'}
            </span>
            <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', backgroundColor: 'var(--bg-active)', padding: '2px 8px', borderRadius: 3 }}>12 / 26 / 9</span>
          </div>
          <button onClick={onCancel} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18 }}>×</button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 18, maxHeight: 'calc(90vh - 52px)', overflowY: 'auto' }}>

          <div>
            <div style={sectionLabel}>MACD Plot — Source</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {SOURCE_PLOTS.map(item => (
                <RadioChip key={item.key} item={item} isSelected={source === item.key} disabled={false} onSelect={handleSetSource} />
              ))}
            </div>
          </div>

          <div>
            <div style={sectionLabel}>Timeframe</div>
            <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'nowrap', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
              {Object.keys(TIMEFRAME_GROUPS).map(g => (
                <button key={g}
                  onClick={() => { setTfGroup(g); setTimeframe(tfForGroup(g)); }}
                  style={{
                    flexShrink: 0,
                    padding: '4px 14px', borderRadius: 4, cursor: 'pointer', fontSize: 12,
                    fontFamily: 'var(--font-mono)', fontWeight: 600,
                    backgroundColor: tfGroup === g ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                    border: `1px solid ${tfGroup === g ? 'var(--accent-blue)' : 'var(--border)'}`,
                    color: tfGroup === g ? '#fff' : 'var(--text-secondary)',
                  }}
                >{g}</button>
              ))}
            </div>
            <div style={{ display: 'flex', flexWrap: 'nowrap', gap: 4, overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
              {TIMEFRAME_GROUPS[tfGroup].map(tf => (
                <button key={tf}
                  onClick={() => setTimeframe(tf)}
                  style={{
                    flexShrink: 0,
                    padding: '3px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 11,
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
            <div style={sectionLabel}>Condition</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {CONDITIONS.map(item => (
                <ConditionChip key={item.key} item={item} isSelected={condition === item.key} onSelect={setCondition} />
              ))}
            </div>
            {showPct && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>% Value</span>
                <input
                  type="number" min="0" step="0.1"
                  value={pctValue}
                  onChange={e => setPctValue(e.target.value)}
                  placeholder="e.g. 5"
                  style={{ ...inputStyle, width: 90 }}
                />
              </div>
            )}
          </div>

          <div>
            <div style={sectionLabel}>Target Value</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {TARGET_PLOTS.map(item => (
                <RadioChip
                  key={item.key} item={item}
                  isSelected={target === item.key}
                  disabled={isTargetDisabled(item.key)}
                  onSelect={handleSetTarget}
                />
              ))}
            </div>
            {showValIn && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Value</span>
                <input
                  type="number" step="0.01"
                  value={targetVal}
                  onChange={e => setTargetVal(e.target.value)}
                  placeholder="0"
                  style={{ ...inputStyle, width: 100 }}
                />
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>0 = histogram baseline</span>
              </div>
            )}
          </div>

          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer', userSelect: 'none', marginBottom: histChainEnabled ? 14 : 0 }}>
              <input
                type="checkbox"
                checked={histChainEnabled}
                onChange={e => setHistChainEnabled(e.target.checked)}
              />
              <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                Also require histogram bar chain
                <span style={{ display: 'block', fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                  Same timeframe — stock must match Level/Signal above and the histogram pattern below.
                </span>
              </span>
            </label>

            {histChainEnabled && (
              <>
                <div style={{ marginBottom: 14 }}>
                  <div style={sectionLabel}>Histogram Side</div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {HISTOGRAM_SIDE_OPTIONS.map(item => (
                      <RadioChip key={item.key} item={item} isSelected={histogramSide === item.key} onSelect={setHistogramSide} />
                    ))}
                  </div>
                </div>

                <div style={{ marginBottom: 14 }}>
                  <div style={sectionLabel}>Bar Motion (vs zero)</div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {HISTOGRAM_CHAIN_MODE_OPTIONS.map(item => (
                      <RadioChip key={item.key} item={item} isSelected={chainMode === item.key} onSelect={setChainMode} />
                    ))}
                  </div>
                </div>

                <div style={{ marginBottom: 14 }}>
                  <div style={sectionLabel}>Main leg ({histogramSide})</div>
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
                </div>

                <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer', userSelect: 'none', marginBottom: 14 }}>
                  <input
                    type="checkbox"
                    checked={allowCrossZero}
                    onChange={e => setAllowCrossZero(e.target.checked)}
                  />
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                    Allow Cross-Zero Chain
                    <span style={{ display: 'block', fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                      {isIncreasing
                        ? `Opposite-side (${oppositeSide}) bars recede toward zero before cross; selected-side bars then increase away from zero.`
                        : `Selected-side bars recede toward zero; opposite-side (${oppositeSide}) bars then increase away from zero after cross.`}
                    </span>
                  </span>
                </label>

                <div style={{ ...crossZeroSectionStyle, marginBottom: 14 }}>
                  <div style={sectionLabel}>Cross-zero leg ({oppositeSide})</div>
                  <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 12, color: allowCrossZero ? 'var(--text-secondary)' : 'var(--text-muted)' }}>{crossBarsLabel}</span>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={crossZeroBars}
                        disabled={!allowCrossZero}
                        onChange={e => setCrossZeroBars(e.target.value)}
                        style={{ ...inputStyle, width: 80, opacity: allowCrossZero ? 1 : 0.7 }}
                      />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 12, color: allowCrossZero ? 'var(--text-secondary)' : 'var(--text-muted)' }}>Allowed stragglers</span>
                      <input
                        type="number"
                        min="0"
                        step="1"
                        value={crossZeroStragglers}
                        disabled={!allowCrossZero}
                        onChange={e => setCrossZeroStragglers(e.target.value)}
                        style={{ ...inputStyle, width: 80, opacity: allowCrossZero ? 1 : 0.7 }}
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <div style={sectionLabel}>Histogram Example</div>
                  <MACDHistChainPreview
                    chainMode={chainMode}
                    histogramSide={histogramSide}
                    allowCrossZero={allowCrossZero}
                    barsToCompare={barsToCompare}
                    crossZeroBars={crossZeroBars}
                  />
                </div>
              </>
            )}
          </div>

          <div>
            <div style={sectionLabel}>Level / Signal Example</div>
            <MACDFilterPreview
              source={source}
              condition={condition}
              target={target}
              targetValue={targetVal}
              pctValue={pctValue}
            />
          </div>

          <div style={{ backgroundColor: 'var(--bg-tertiary)', borderRadius: 5, padding: '8px 12px', border: '1px solid var(--border)', fontSize: 12, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)' }}>
            Filter: {buildMacdCombinedFilterLabel(previewFilterDef())}
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={onCancel}
              style={{ padding: '7px 16px', borderRadius: 5, fontSize: 12, cursor: 'pointer', backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
              Cancel
            </button>
            <button onClick={handleApply}
              style={{ padding: '7px 16px', borderRadius: 5, fontSize: 12, cursor: 'pointer', backgroundColor: 'var(--accent-blue)', border: 'none', color: '#fff', fontWeight: 600 }}>
              {isEditMode ? 'Update Filter' : 'Apply Filter'}
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
