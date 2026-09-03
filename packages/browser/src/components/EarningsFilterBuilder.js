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
  { value: 'current_trading_day', label: 'Current trading day' },
  { value: 'previous_day', label: 'Previous day' },
  { value: 'previous_5_days', label: 'Previous 5 days' },
  { value: 'next_day', label: 'Next day' },
  { value: 'next_5_days', label: 'Next 5 days' },
  { value: 'this_week', label: 'This week (Monday to Sunday)' },
  { value: 'prev_week', label: 'Previous week (Monday to Sunday)' },
  { value: 'next_week', label: 'Next week (Monday to Sunday)' },
  { value: 'month_range', label: 'Month range' },
];

const WINDOW_CHIP_LABELS = {
  current_trading_day: 'Current trading day',
  previous_day: 'Previous day',
  previous_5_days: 'Previous 5 days',
  next_day: 'Next day',
  next_5_days: 'Next 5 days',
  this_week: 'This week',
  prev_week: 'Prev week',
  next_week: 'Next week',
  today: 'Current trading day',
  yesterday: 'Previous day',
  today_yesterday: 'Current trading day',
  today_and_yesterday: 'Current trading day',
};

const REPORTED_WINDOWS = new Set([
  'current_trading_day',
  'previous_day',
  'previous_5_days',
  'this_week',
  'prev_week',
  'month_range',
]);

const UPCOMING_WINDOWS = new Set([
  'current_trading_day',
  'next_day',
  'next_5_days',
  'this_week',
  'next_week',
  'month_range',
]);

function normalizeWindowKey(raw) {
  const k = String(raw || '').trim().toLowerCase();
  if (k === 'today' || k === 'today_yesterday' || k === 'today_and_yesterday') return 'current_trading_day';
  if (k === 'yesterday') return 'previous_day';
  if (k === 'previous_week') return 'prev_week';
  return k || 'month_range';
}

const SCOPE_OPTIONS = [
  { value: 'reported', label: 'Reported', chip: 'Reported' },
  { value: 'upcoming', label: 'Upcoming', chip: 'Upcoming' },
  { value: 'both', label: 'Both', chip: 'Reported + upcoming' },
];

const SCOPE_HELP = {
  reported: 'Stocks that already reported in this window, matched on release date.',
  upcoming: 'Stocks scheduled to report in this window, matched on next release date.',
  both: 'Stocks that reported or are scheduled to report in this window.',
};

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
  const scope = def.earnings_scope || 'reported';
  if (scope !== 'reported') {
    parts.push(SCOPE_OPTIONS.find(o => o.value === scope)?.chip || scope);
  }
  const rw = normalizeWindowKey(def.report_window || 'month_range');
  if (WINDOW_CHIP_LABELS[rw]) parts.push(WINDOW_CHIP_LABELS[rw]);
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

  const [scope, setScope] = useState(init.earnings_scope || 'reported');
  const [reportWindow, setReportWindow] = useState(normalizeWindowKey(init.report_window || 'month_range'));
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

  // Reported earnings cannot land in a future month; upcoming ones only do.
  const allowsFutureMonths = scope !== 'reported';
  const boundMonth = allowsFutureMonths ? 12 : maxMonth;
  const surpriseEnabled = scope !== 'upcoming';

  function handleScopeChange(next) {
    setScope(next);
    if (next === 'reported') {
      setFromMonth(m => clampMonthForYear(fromYear, m, maxYear, maxMonth));
      setToMonth(m => clampMonthForYear(toYear, m, maxYear, maxMonth));
    }
    const allowed = next === 'upcoming' ? UPCOMING_WINDOWS
      : next === 'reported' ? REPORTED_WINDOWS
      : new Set([...REPORTED_WINDOWS, ...UPCOMING_WINDOWS]);
    if (!allowed.has(reportWindow)) {
      setReportWindow('current_trading_day');
    }
  }

  const windowOptions = useMemo(() => {
    if (scope === 'upcoming') {
      return WINDOW_OPTIONS.filter(o => UPCOMING_WINDOWS.has(o.value));
    }
    if (scope === 'reported') {
      return WINDOW_OPTIONS.filter(o => REPORTED_WINDOWS.has(o.value));
    }
    // both: all TV windows + month range
    return WINDOW_OPTIONS;
  }, [scope]);

  function validate() {
    setFormErr('');
    if (reportWindow === 'month_range') {
      if (fromYear > toYear || (fromYear === toYear && fromMonth > toMonth)) {
        setFormErr('From month must not be after To month');
        return false;
      }
    }
    if (!surpriseEnabled) return true;
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
      earnings_scope: scope,
      report_window: reportWindow,
      eps_surprise_min: surpriseEnabled && surpriseBoundIsSet(epsMin) ? parseSurprisePct(epsMin) : null,
      eps_surprise_max: surpriseEnabled && surpriseBoundIsSet(epsMax) ? parseSurprisePct(epsMax) : null,
      revenue_surprise_min: surpriseEnabled && surpriseBoundIsSet(revMin) ? parseSurprisePct(revMin) : null,
      revenue_surprise_max: surpriseEnabled && surpriseBoundIsSet(revMax) ? parseSurprisePct(revMax) : null,
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
    earnings_scope: scope,
    report_window: reportWindow,
    from_year: fromYear,
    from_month: fromMonth,
    to_year: toYear,
    to_month: toMonth,
    eps_surprise_min: surpriseEnabled && surpriseBoundIsSet(epsMin) ? parseSurprisePct(epsMin) : null,
    eps_surprise_max: surpriseEnabled && surpriseBoundIsSet(epsMax) ? parseSurprisePct(epsMax) : null,
    revenue_surprise_min: surpriseEnabled && surpriseBoundIsSet(revMin) ? parseSurprisePct(revMin) : null,
    revenue_surprise_max: surpriseEnabled && surpriseBoundIsSet(revMax) ? parseSurprisePct(revMax) : null,
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
            {SCOPE_HELP[scope]}
            {surpriseEnabled && ' Surprise % uses the same rules as the Earnings tab (0 = met estimate).'}
          </div>

          <div>
            <div style={sectionLabel}>Scope</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
              {SCOPE_OPTIONS.map(o => {
                const active = scope === o.value;
                return (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => handleScopeChange(o.value)}
                    style={{
                      padding: '6px 8px',
                      borderRadius: 4,
                      fontSize: 12,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      backgroundColor: active ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                      border: `1px solid ${active ? 'var(--accent-blue)' : 'var(--border)'}`,
                      color: active ? '#fff' : 'var(--text-secondary)',
                      fontWeight: active ? 600 : 400,
                    }}
                  >
                    {o.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div style={sectionLabel}>Period</div>
            <select value={reportWindow} onChange={e => setReportWindow(e.target.value)} style={selectStyle}>
              {windowOptions.map(o => (
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
                    {renderMonthOptions(fromYear, maxYear, boundMonth)}
                  </select>
                  <select
                    value={fromYear}
                    onChange={e => {
                      const y = Number(e.target.value);
                      setFromYear(y);
                      setFromMonth(m => clampMonthForYear(y, m, maxYear, boundMonth));
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
                    {renderMonthOptions(toYear, maxYear, boundMonth)}
                  </select>
                  <select
                    value={toYear}
                    onChange={e => {
                      const y = Number(e.target.value);
                      setToYear(y);
                      setToMonth(m => clampMonthForYear(y, m, maxYear, boundMonth));
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

          <div style={{ opacity: surpriseEnabled ? 1 : 0.5 }}>
            <div style={sectionLabel}>Surprise % (optional)</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>EPS min</div>
                <input value={epsMin} onChange={e => setEpsMin(e.target.value)} disabled={!surpriseEnabled} placeholder="—" style={inputStyle} title="Minimum EPS surprise % (≥). 0 = met or beat." />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>EPS max</div>
                <input value={epsMax} onChange={e => setEpsMax(e.target.value)} disabled={!surpriseEnabled} placeholder="—" style={inputStyle} />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>Rev min</div>
                <input value={revMin} onChange={e => setRevMin(e.target.value)} disabled={!surpriseEnabled} placeholder="—" style={inputStyle} title="Minimum revenue surprise % (≥). 0 = met or beat." />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>Rev max</div>
                <input value={revMax} onChange={e => setRevMax(e.target.value)} disabled={!surpriseEnabled} placeholder="—" style={inputStyle} />
              </div>
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6, lineHeight: 1.4 }}>
              {scope === 'upcoming' && 'Surprise % needs a published result, so it is off for upcoming.'}
              {scope === 'both' && 'Applies to the reported half only; upcoming names are never dropped by these bounds.'}
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
