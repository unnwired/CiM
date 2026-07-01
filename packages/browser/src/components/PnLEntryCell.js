import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { todayCalendarDateIst } from './PnLDateSelect';

const API = '';

function formatEntryDisplay(val) {
  if (val == null || !Number.isFinite(Number(val))) return '';
  return Number(val).toFixed(2);
}

function parseEntryInput(raw) {
  const s = String(raw ?? '').trim().replace(/,/g, '');
  if (!s) return null;
  const n = Number(s);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.round(n * 100) / 100;
}

export default function PnLEntryCell({ positionId, entryPrice, qty, isPlaceholder, onSaved }) {
  const inputRef = useRef(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!editing) setDraft(formatEntryDisplay(entryPrice));
  }, [entryPrice, editing]);

  const save = useCallback(async () => {
    const parsed = parseEntryInput(draft);
    if (parsed === undefined) {
      setDraft(formatEntryDisplay(entryPrice));
      setEditing(false);
      return;
    }
    const prev = entryPrice != null ? Number(entryPrice) : null;
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
      const body = { entry_price: parsed };
      if (isPlaceholder) {
        if (qty != null) body.qty = qty;
        if (body.qty != null) body.entry_date = todayCalendarDateIst();
      }
      const res = await axios.patch(
        `${API}/api/pnl/positions/${encodeURIComponent(positionId)}`,
        body,
      );
      onSaved?.(res.data?.position);
      setEditing(false);
    } catch {
      setDraft(formatEntryDisplay(entryPrice));
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
        inputMode="decimal"
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
            setDraft(formatEntryDisplay(entryPrice));
            setEditing(false);
          }
        }}
        style={{
          width: '100%',
          maxWidth: 76,
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

  const hasEntry = entryPrice != null && Number.isFinite(Number(entryPrice));
  return (
    <button
      type="button"
      onMouseDown={stopRow}
      onClick={(e) => { stopRow(e); setEditing(true); }}
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: hasEntry ? 'var(--text-primary)' : 'var(--text-muted)',
        background: 'transparent',
        border: 'none',
        padding: 0,
        cursor: 'pointer',
        textAlign: 'left',
      }}
    >
      {hasEntry ? `₹${formatEntryDisplay(entryPrice)}` : '—'}
    </button>
  );
}
