import React, { useMemo } from 'react';
import {
  disabledFieldOpacity,
  fieldInputStyle,
  fieldLabelStyle,
  FIELD_HEIGHT,
} from './schedulerFieldStyles';

function parse24(value) {
  const parts = String(value || '00:00').split(':');
  let h = parseInt(parts[0], 10);
  let m = parseInt(parts[1], 10);
  if (!Number.isFinite(h)) h = 0;
  if (!Number.isFinite(m)) m = 0;
  h = Math.max(0, Math.min(23, h));
  m = Math.max(0, Math.min(59, m));
  return { h, m };
}

export function formatIstTime24(h24, minute) {
  return `${String(h24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

/** 24-hour IST time picker: two fields (HH 00–23 : MM 00–59), no AM/PM. */
export default function IstTimeInput({ value = '00:00', onChange, disabled = false, hideLabel = false }) {
  const { h, m } = useMemo(() => parse24(value), [value]);

  function emit(nextH, nextM) {
    const hh = Math.max(0, Math.min(23, Number(nextH) || 0));
    const mm = Math.max(0, Math.min(59, Number(nextM) || 0));
    onChange?.(formatIstTime24(hh, mm));
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
      {!hideLabel && (
        <span style={{ ...fieldLabelStyle, width: 84, flexShrink: 0 }}>Time (IST · 24h)</span>
      )}
      <input
        type="number"
        min={0}
        max={23}
        value={h}
        disabled={disabled}
        onChange={(e) => emit(e.target.value, m)}
        style={{ ...fieldInputStyle, width: 52 }}
        aria-label="Hour (0-23, 24-hour)"
      />
      <span style={{ fontSize: 13, color: 'var(--text-secondary)', flexShrink: 0 }}>:</span>
      <input
        type="number"
        min={0}
        max={59}
        value={String(m).padStart(2, '0')}
        disabled={disabled}
        onChange={(e) => emit(h, e.target.value)}
        style={{ ...fieldInputStyle, width: 52 }}
        aria-label="Minute (0-59)"
      />
      <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>IST</span>
    </div>
  );
}
