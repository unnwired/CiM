import React, { useMemo } from 'react';
import {
  disabledFieldOpacity,
  fieldInputStyle,
  fieldLabelStyle,
  fieldSelectStyle,
  FIELD_HEIGHT,
} from './schedulerFieldStyles';

function parse24(value) {
  const parts = String(value || '12:00').split(':');
  let h = parseInt(parts[0], 10);
  let m = parseInt(parts[1], 10);
  if (!Number.isFinite(h)) h = 12;
  if (!Number.isFinite(m)) m = 0;
  h = Math.max(0, Math.min(23, h));
  m = Math.max(0, Math.min(59, m));
  return { h, m };
}

function to12(h24) {
  const isPm = h24 >= 12;
  let h12 = h24 % 12;
  if (h12 === 0) h12 = 12;
  return { h12, isPm };
}

function to24(h12, isPm) {
  let h = Math.max(1, Math.min(12, Number(h12) || 12));
  if (isPm) return h === 12 ? 12 : h + 12;
  return h === 12 ? 0 : h;
}

export function formatIstTime24(h24, minute) {
  return `${String(h24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

export default function IstTimeInput({ value = '12:00', onChange, disabled = false }) {
  const parsed = useMemo(() => {
    const { h, m } = parse24(value);
    const { h12, isPm } = to12(h);
    return { h12, m, isPm };
  }, [value]);

  function emit(h12, minute, isPm) {
    const h24 = to24(h12, isPm);
    const m = Math.max(0, Math.min(59, Number(minute) || 0));
    onChange?.(formatIstTime24(h24, m));
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'nowrap',
      height: FIELD_HEIGHT,
      opacity: disabledFieldOpacity(disabled),
    }}
    >
      <span style={{ ...fieldLabelStyle, width: 56, flexShrink: 0 }}>Time (IST)</span>
      <input
        type="number"
        min={1}
        max={12}
        value={parsed.h12}
        disabled={disabled}
        onChange={(e) => emit(e.target.value, parsed.m, parsed.isPm)}
        style={fieldInputStyle}
        aria-label="Hour"
      />
      <span style={{ fontSize: 13, color: 'var(--text-secondary)', flexShrink: 0 }}>:</span>
      <input
        type="number"
        min={0}
        max={59}
        value={String(parsed.m).padStart(2, '0')}
        disabled={disabled}
        onChange={(e) => emit(parsed.h12, e.target.value, parsed.isPm)}
        style={fieldInputStyle}
        aria-label="Minute"
      />
      <select
        value={parsed.isPm ? 'PM' : 'AM'}
        disabled={disabled}
        onChange={(e) => emit(parsed.h12, parsed.m, e.target.value === 'PM')}
        style={{ ...fieldSelectStyle, flexShrink: 0 }}
        aria-label="AM or PM"
      >
        <option value="AM">AM</option>
        <option value="PM">PM</option>
      </select>
    </div>
  );
}
