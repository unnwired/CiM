import React, { useEffect, useMemo } from 'react';
import { PNL_FORM_INNER_GAP, pnlFormFieldLabelStyle } from './pnlFormDialogChrome';

export const MONTHS = [
  { v: 1, label: 'Jan' },
  { v: 2, label: 'Feb' },
  { v: 3, label: 'Mar' },
  { v: 4, label: 'Apr' },
  { v: 5, label: 'May' },
  { v: 6, label: 'Jun' },
  { v: 7, label: 'Jul' },
  { v: 8, label: 'Aug' },
  { v: 9, label: 'Sep' },
  { v: 10, label: 'Oct' },
  { v: 11, label: 'Nov' },
  { v: 12, label: 'Dec' },
];

export function istTodayParts() {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  }).formatToParts(new Date());
  const get = (type) => Number(parts.find((p) => p.type === type)?.value);
  return { year: get('year'), month: get('month'), day: get('day') };
}

export function daysInMonth(year, month) {
  return new Date(year, month, 0).getDate();
}

export function toCalendarDate(year, month, day) {
  const y = Number(year);
  const m = Number(month);
  const d = Number(day);
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null;
  const maxDay = daysInMonth(y, m);
  if (d < 1 || d > maxDay) return null;
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

export function todayCalendarDateIst() {
  const { year, month, day } = istTodayParts();
  return toCalendarDate(year, month, day);
}

export const PERIOD_YEAR_MIN = 2022;

export const YEAR_OPTIONS = (() => {
  const cur = istTodayParts().year;
  const out = [];
  for (let y = cur - 10; y <= cur + 1; y += 1) out.push(y);
  return out;
})();

export const PERIOD_YEAR_OPTIONS = (() => {
  const cur = istTodayParts().year;
  const out = [];
  for (let y = PERIOD_YEAR_MIN; y <= cur + 1; y += 1) out.push(y);
  return out;
})();

const selectBase = {
  padding: '5px 4px',
  fontSize: 11,
  background: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  flexShrink: 0,
};

export default function PnLDateSelect({
  label = 'Date',
  year,
  month,
  day,
  onYearChange,
  onMonthChange,
  onDayChange,
  hideLabel = false,
  allowAllDays = false,
  allowAllMonths = false,
  yearOptions = YEAR_OPTIONS,
  minMonth = 0,
  minDay = 0,
  inline = false,
}) {
  const monthAll = allowAllMonths && month === 0;
  const effectiveMonth = monthAll ? 1 : month;
  const maxDay = daysInMonth(year, effectiveMonth);
  const monthChoices = useMemo(() => {
    const list = allowAllMonths ? [{ v: 0, label: 'All' }] : [];
    for (const m of MONTHS) {
      if (minMonth > 0 && m.v < minMonth) continue;
      list.push(m);
    }
    return list;
  }, [allowAllMonths, minMonth]);
  const dayOptions = useMemo(() => {
    const start = minDay > 0 ? minDay : 1;
    const out = [];
    for (let d = start; d <= maxDay; d += 1) out.push(d);
    return out;
  }, [maxDay, minDay]);

  useEffect(() => {
    if (monthAll) {
      if (day !== 0) onDayChange(0);
      return;
    }
    if (minMonth > 0 && month > 0 && month < minMonth) onMonthChange(minMonth);
  }, [month, minMonth, monthAll, onMonthChange]);

  useEffect(() => {
    if (monthAll) return;
    if (allowAllDays && day === 0) return;
    if (minDay > 0 && day > 0 && day < minDay) onDayChange(minDay);
    if (day > maxDay) onDayChange(maxDay);
  }, [day, maxDay, monthAll, onDayChange, allowAllDays, minDay]);

  const controls = (
    <div style={{ display: 'flex', gap: PNL_FORM_INNER_GAP, alignItems: 'center', flexWrap: 'nowrap' }}>
      <select
        aria-label={`${label} year`}
        value={year}
        onChange={(e) => onYearChange(Number(e.target.value))}
        style={{ ...selectBase, width: 72 }}
      >
        {yearOptions.map((y) => (
          <option key={y} value={y}>{y}</option>
        ))}
      </select>
      <select
        aria-label={`${label} month`}
        value={month}
        onChange={(e) => onMonthChange(Number(e.target.value))}
        style={{ ...selectBase, width: allowAllMonths ? 48 : 54 }}
      >
        {monthChoices.map((m) => (
          <option key={m.v} value={m.v}>{m.label}</option>
        ))}
      </select>
      <select
        aria-label={`${label} day`}
        value={day}
        onChange={(e) => onDayChange(Number(e.target.value))}
        style={{ ...selectBase, width: allowAllDays || monthAll ? 48 : 40 }}
        disabled={monthAll}
      >
        {(allowAllDays || monthAll) ? <option value={0}>All</option> : null}
        {!monthAll && dayOptions.map((d) => (
          <option key={d} value={d}>{d}</option>
        ))}
      </select>
    </div>
  );

  if (inline) return controls;

  return (
    <div>
      {!hideLabel ? <div style={pnlFormFieldLabelStyle}>{label}</div> : null}
      {controls}
    </div>
  );
}
