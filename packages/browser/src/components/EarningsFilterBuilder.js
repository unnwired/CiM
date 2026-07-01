import React, { useMemo, useState } from 'react';

const MONTH_OPTIONS = [
  { value: 1, label: 'January' },
  { value: 2, label: 'February' },
  { value: 3, label: 'March' },
  { value: 4, label: 'April' },
  { value: 5, label: 'May' },
  { value: 6, label: 'June' },
  { value: 7, label: 'July' },
  { value: 8, label: 'August' },
  { value: 9, label: 'September' },
  { value: 10, label: 'October' },
  { value: 11, label: 'November' },
  { value: 12, label: 'December' },
];

const WINDOW_OPTIONS = [
  { value: 'this_week', label: 'This week (Monday to Sunday)' },
  { value: 'prev_week', label: 'Previous week (Monday to Sunday)' },
  { value: 'month_range', label: 'Month range' },
];

const sectionLabel = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 6,
};

const inputStyle = {
  backgroundColor: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  padding: '5px 8px',
  color: 'var(--text-primary)',
  fontSize: 12,
  fontFamily: 'var(--font-mono)',
  width: '100%',
  boxSizing: 'border-box',
  outline: 'none',
};

const selectStyle = {
  ...inputStyle,
  fontFamily: 'var(--font-sans)',
  cursor: 'pointer',
};

function surpriseBoundIsSet(raw) {
  return String(raw ?? '').trim() !== '';
}

function parseSurprisePct(raw) {
  if (!surpriseBoundIsSet(raw)) return undefined;
  const n = Number(String(raw).trim());
  if (!Number.isFinite(n)) return NaN;
  return n;
}

function currentYearMonth() {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: 'numeric',
  }).formatToParts(new Date());
  return {
    year: Number(parts.find(p => p.type === 'year')?.value),
    month: Number(parts.find(p => p.type === 'month')?.value),
  };
}

function clampMonthForYear(year, month, maxYear, maxMonth) {
  if (year > maxYear) return maxMonth;
  if (year === maxYear && month > maxMonth) return maxMonth;
  return month;
}

function isMonthDisabled(year, monthValue, maxYear, maxMonth) {
  return year === maxYear && monthValue > maxMonth;
}

function monthLabel(month, year) {
  const name = MONTH_OPTIONS.find(o => o.value === month)?.label;
  return name ? `${name} ${year}` : `${year}-${month}`;
}

function buildChipLabel(def) {
  const parts = ['Earnings'];
  const rw = def.report_window || 'month_range';
  if (rw === 'this_week') parts.push('This week');
  else if (rw === 'prev_week') parts.push('Prev week');
  else {
    parts.push(`${monthLabel(def.from_month, def.from_year)} – ${monthLabel(def.to_month, def.to_year)}`);
  }
  const bounds = [];
  if (def.eps_surprise_min != null) bounds.push(`EPS ≥ ${def.eps_surprise_min}%`);
  if (def.eps_surprise_max != null) bounds.push(`EPS ≤ ${def.eps_surprise_max}%`);
  if (def.revenue_surprise_min != null) bounds.push(`Rev ≥ ${def.revenue_surprise_min}%`);
  if (def.revenue_surprise_max != null) bounds.push(`Rev ≤ ${def.revenue_surprise_max}%`);
  if (bounds.length) parts.push(bounds.join(', '));
  return parts.join(' · ');
}

function renderMonthOptions(year, maxYear, maxMonth) {
  return MONTH_OPTIONS.map(o => (
    <option
      key={o.value}
      value={o.value}
      disabled={isMonthDisabled(year, o.value, maxYear, maxMonth)}
    >
      {o.label}
    </option>
  ));
}

export default function EarningsFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = initialValues || {};
  const { year: maxYear, month: maxMonth } = currentYearMonth();
  const minYear = 2024;

  const [reportWindow, setReportWindow] = useState(init.report_window || 'month_range');
  const [fromYear, setFromYear] = useState(init.from_year ?? maxYear);
  const [fromMonth, setFromMonth] = useState(
    clampMonthForYear(init.from_year ?? maxYear, init.from_month ?? maxMonth, maxYear, maxMonth),
  );
  const [toYear, setToYear] = useState(init.to_year ?? maxYear);
  const [toMonth, setToMonth] = useState(
    clampMonthForYear(init.to_year ?? maxYear, init.to_month ?? maxMonth, maxYear, maxMonth),
  );
  const [epsMin, setEpsMin] = useState(init.eps_surprise_min != null ? String(init.eps_surprise_min) : '');
  const [epsMax, setEpsMax] = useState(init.eps_surprise_max != null ? String(init.eps_surprise_max) : '');
  const [revMin, setRevMin] = useState(init.revenue_surprise_min != null ? String(init.revenue_surprise_min) : '');
  const [revMax, setRevMax] = useState(init.revenue_surprise_max != null ? String(init.revenue_surprise_max) : '');
  const [formErr, setFormErr] = useState('');

  const years = useMemo(() => {
    const list = [];
    for (let y = maxYear; y >= minYear; y -= 1) list.push(y);
    return list;
  }, [maxYear]);

  const isEditMode = !!initialValues;

  function validate() {
    setFormErr('');
    if (reportWindow === 'month_range') {
      if (fromYear > toYear || (fromYear === toYear && fromMonth > toMonth)) {
        setFormErr('From month must not be after To month');
        return false;
      }
    }
    const fields = [
      { raw: epsMin, label: 'EPS min %' },
      { raw: epsMax, label: 'EPS max %' },
      { raw: revMin, label: 'Revenue min %' },
      { raw: revMax, label: 'Revenue max %' },
    ];
    for (const f of fields) {
      if (surpriseBoundIsSet(f.raw) && !Number.isFinite(parseSurprisePct(f.raw))) {
        setFormErr(`${f.label} must be a number (e.g. 0 or 1)`);
        return false;
      }
    }
    return true;
  }

  function handleApply() {
    if (!validate()) return;
    const def = {
      filter_type: 'earnings',
      report_window: reportWindow,
      eps_surprise_min: surpriseBoundIsSet(epsMin) ? parseSurprisePct(epsMin) : null,
      eps_surprise_max: surpriseBoundIsSet(epsMax) ? parseSurprisePct(epsMax) : null,
      revenue_surprise_min: surpriseBoundIsSet(revMin) ? parseSurprisePct(revMin) : null,
      revenue_surprise_max: surpriseBoundIsSet(revMax) ? parseSurprisePct(revMax) : null,
    };
    if (reportWindow === 'month_range') {
      def.from_year = fromYear;
      def.from_month = fromMonth;
      def.to_year = toYear;
      def.to_month = toMonth;
    }
    onApply(def);
  }

  const preview = buildChipLabel({
    report_window: reportWindow,
    from_year: fromYear,
    from_month: fromMonth,
    to_year: toYear,
    to_month: toMonth,
    eps_surprise_min: surpriseBoundIsSet(epsMin) ? parseSurprisePct(epsMin) : null,
    eps_surprise_max: surpriseBoundIsSet(epsMax) ? parseSurprisePct(epsMax) : null,
    revenue_surprise_min: surpriseBoundIsSet(revMin) ? parseSurprisePct(revMin) : null,
    revenue_surprise_max: surpriseBoundIsSet(revMax) ? parseSurprisePct(revMax) : null,
  });

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
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div style={{
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        width: 460,
        maxHeight: '90vh',
        overflow: 'auto',
        boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
      }}
      >
        <div style={{
          padding: '12px 16px',
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'var(--bg-tertiary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
        >
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {isEditMode ? 'Edit Earnings Filter' : 'Earnings Filter'}
          </span>
          <button type="button" onClick={onCancel} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer' }}>×</button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{
            fontSize: 11,
            color: 'var(--text-muted)',
            backgroundColor: 'var(--bg-tertiary)',
            borderRadius: 4,
            padding: '6px 10px',
            border: '1px solid var(--border)',
            lineHeight: 1.45,
          }}
          >
            Reported earnings by release date. Surprise % uses the same rules as the Earnings tab (0 = met estimate).
          </div>

          <div>
            <div style={sectionLabel}>Period</div>
            <select value={reportWindow} onChange={e => setReportWindow(e.target.value)} style={selectStyle}>
              {WINDOW_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {reportWindow === 'month_range' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <div style={sectionLabel}>From</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <select value={fromMonth} onChange={e => setFromMonth(Number(e.target.value))} style={selectStyle}>
                    {renderMonthOptions(fromYear, maxYear, maxMonth)}
                  </select>
                  <select
                    value={fromYear}
                    onChange={e => {
                      const y = Number(e.target.value);
                      setFromYear(y);
                      setFromMonth(m => clampMonthForYear(y, m, maxYear, maxMonth));
                    }}
                    style={{ ...selectStyle, width: 88, flexShrink: 0 }}
                  >
                    {years.map(y => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <div style={sectionLabel}>To</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <select value={toMonth} onChange={e => setToMonth(Number(e.target.value))} style={selectStyle}>
                    {renderMonthOptions(toYear, maxYear, maxMonth)}
                  </select>
                  <select
                    value={toYear}
                    onChange={e => {
                      const y = Number(e.target.value);
                      setToYear(y);
                      setToMonth(m => clampMonthForYear(y, m, maxYear, maxMonth));
                    }}
                    style={{ ...selectStyle, width: 88, flexShrink: 0 }}
                  >
                    {years.map(y => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}

          <div>
            <div style={sectionLabel}>Surprise % (optional)</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>EPS min</div>
                <input value={epsMin} onChange={e => setEpsMin(e.target.value)} placeholder="—" style={inputStyle} title="Minimum EPS surprise % (≥). 0 = met or beat." />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>EPS max</div>
                <input value={epsMax} onChange={e => setEpsMax(e.target.value)} placeholder="—" style={inputStyle} />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>Rev min</div>
                <input value={revMin} onChange={e => setRevMin(e.target.value)} placeholder="—" style={inputStyle} title="Minimum revenue surprise % (≥). 0 = met or beat." />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>Rev max</div>
                <input value={revMax} onChange={e => setRevMax(e.target.value)} placeholder="—" style={inputStyle} />
              </div>
            </div>
          </div>

          {formErr && (
            <div style={{ fontSize: 11, color: 'var(--accent-red)' }}>{formErr}</div>
          )}

          <div style={{
            backgroundColor: 'var(--bg-tertiary)',
            borderRadius: 5,
            padding: '8px 12px',
            border: '1px solid var(--border)',
            fontSize: 12,
            color: 'var(--accent-blue)',
            fontFamily: 'var(--font-mono)',
          }}
          >
            {preview}
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
