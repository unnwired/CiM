import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { todayCalendarDateIst } from './PnLDateSelect';

const API = '';

function formatQtyDisplay(val) {
  if (val == null || !Number.isFinite(Number(val))) return '';
  return String(Math.trunc(Number(val)));
}

function parseQtyInput(raw) {
  const s = String(raw ?? '').trim().replace(/,/g, '');
  if (!s) return null;
  const n = Number(s);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) return undefined;
  return n;
}

export default function PnLQtyCell({ positionId, entryPrice, qty, isPlaceholder, onSaved }) {
  const inputRef = useRef(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!editing) setDraft(formatQtyDisplay(qty));
  }, [qty, editing]);

  const save = useCallback(async () => {
    const parsed = parseQtyInput(draft);
    if (parsed === undefined) {
      setDraft(formatQtyDisplay(qty));
      setEditing(false);
      return;
    }
    const prev = qty != null ? Number(qty) : null;
    if (parsed === prev && !isPlaceholder) {
      setEditing(false);
      return;
    }
    if (isPlaceholder && parsed == null) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const body = { qty: parsed };
      if (isPlaceholder) {
        if (entryPrice != null) body.entry_price = entryPrice;
        if (body.entry_price != null) body.entry_date = todayCalendarDateIst();
      }
      const res = await axios.patch(
        `${API}/api/pnl/positions/${encodeURIComponent(positionId)}`,
        body,
      );
      onSaved?.(res.data?.position);
      setEditing(false);
    } catch {
      setDraft(formatQtyDisplay(qty));
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }, [draft, entryPrice, qty, isPlaceholder, onSaved, positionId]);

  const stopRow = (e) => e.stopPropagation();

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        inputMode="numeric"
        autoFocus
        disabled={saving}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onMouseDown={stopRow}
        onClick={stopRow}
        onBlur={() => { save(); }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); save(); }
          else if (e.key === 'Escape') {
            e.preventDefault();
            setDraft(formatQtyDisplay(qty));
            setEditing(false);
          }
        }}
        style={{
          width: '100%',
          maxWidth: 56,
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--text-primary)',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--accent-blue)',
          borderRadius: 3,
          padding: '2px 4px',
          outline: 'none',
        }}
      />
    );
  }

  const hasQty = qty != null && Number.isFinite(Number(qty));
  return (
    <button
      type="button"
      onMouseDown={stopRow}
      onClick={(e) => { stopRow(e); setEditing(true); }}
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: hasQty ? 'var(--text-primary)' : 'var(--text-muted)',
        background: 'transparent',
        border: 'none',
        padding: 0,
        cursor: 'pointer',
        textAlign: 'left',
      }}
    >
      {hasQty ? formatQtyDisplay(qty) : '—'}
    </button>
  );
}
