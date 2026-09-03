import React, { useCallback, useEffect, useState } from 'react';
import api from '../api/http';

const BROKER_OPTIONS = [
  { value: 'zerodha', label: 'Zerodha' },
  { value: 'paytm', label: 'Paytm' },
  { value: 'manual', label: 'Manual' },
];

function brokerLabel(value) {
  const v = String(value || '').toLowerCase();
  const hit = BROKER_OPTIONS.find((o) => o.value === v);
  return hit ? hit.label : '—';
}

function detailMessage(err) {
  const status = err?.response?.status;
  const d = err?.response?.data?.detail;
  let msg = '';
  if (typeof d === 'string' && d.trim()) msg = d;
  else if (Array.isArray(d) && d[0]?.msg) msg = String(d[0].msg);
  else if (err?.message) msg = String(err.message);
  else msg = 'Could not save broker';
  if (status && !String(msg).includes(String(status))) {
    return `${status}: ${msg}`;
  }
  return msg;
}

/**
 * Broker picker for one lot, or for every open lot under a symbol (mode="symbol").
 * Uses POST-only APIs (PATCH is blocked by showcase CORS / some proxies).
 */
export default function PnLBrokerCell({
  positionId,
  symbol,
  mode = 'lot',
  broker,
  mixed = false,
  isPlaceholder,
  readOnly,
  onSaved,
}) {
  const propValue = String(broker || 'manual').toLowerCase();
  const [draft, setDraft] = useState(mixed ? '' : propValue);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setDraft(mixed ? '' : propValue);
    setError('');
  }, [propValue, mixed, positionId, symbol]);

  const save = useCallback(async (next) => {
    if (isPlaceholder || readOnly) return;
    if (!next) return;
    if (mode === 'lot' && !positionId) return;
    if (mode === 'symbol' && !symbol) return;
    if (!mixed && next === propValue) return;

    setDraft(next);
    setError('');
    setSaving(true);
    try {
      if (mode === 'symbol') {
        await api.post('/api/pnl/broker/symbol', {
          symbol,
          broker: next,
          scope: 'open',
        });
      } else {
        await api.post('/api/pnl/broker/position', {
          position_id: positionId,
          broker: next,
        });
      }
      onSaved?.();
    } catch (err) {
      setDraft(mixed ? '' : propValue);
      setError(detailMessage(err));
    } finally {
      setSaving(false);
    }
  }, [
    isPlaceholder,
    readOnly,
    mode,
    positionId,
    symbol,
    mixed,
    propValue,
    onSaved,
  ]);

  const stopRow = (e) => e.stopPropagation();

  if (isPlaceholder || readOnly) {
    return (
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
        {mixed ? 'Mixed' : brokerLabel(broker)}
      </span>
    );
  }

  if (mode === 'lot' && !positionId) {
    return (
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
        {brokerLabel(broker)}
      </span>
    );
  }

  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', maxWidth: 92 }} title={error || undefined}>
      <select
        value={draft}
        disabled={saving}
        onMouseDown={stopRow}
        onClick={stopRow}
        onChange={(e) => {
          stopRow(e);
          save(e.target.value);
        }}
        aria-label={mode === 'symbol' ? `Broker for all ${symbol} lots` : 'Broker'}
        style={{
          maxWidth: 88,
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          color: error ? 'var(--accent-red)' : 'var(--text-primary)',
          background: 'var(--bg-secondary)',
          border: `1px solid ${error ? 'var(--accent-red)' : 'var(--border)'}`,
          borderRadius: 3,
          padding: '1px 2px',
          cursor: saving ? 'wait' : 'pointer',
        }}
      >
        {mixed && (
          <option value="" disabled>
            Mixed
          </option>
        )}
        {BROKER_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {error ? (
        <span style={{ fontSize: 9, color: 'var(--accent-red)', lineHeight: 1.1, marginTop: 1 }}>
          {error}
        </span>
      ) : null}
    </span>
  );
}

export function groupBrokerLabel(lots) {
  if (!lots || !lots.length) return '—';
  const tags = [...new Set(lots.map((l) => String(l.broker || 'manual').toLowerCase()))];
  if (tags.length === 1) return brokerLabel(tags[0]);
  return 'Mixed';
}

export function groupBrokerTags(lots) {
  if (!lots || !lots.length) return [];
  return [...new Set(lots.map((l) => String(l.broker || 'manual').toLowerCase()))];
}

export { BROKER_OPTIONS, brokerLabel };
