import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';

const API = '';

/** Dispatched after a successful save so other mounted icons for the same key can refresh. */
export const INSTRUMENT_NOTE_SAVED_EVENT = 'nse-pulse:instrument-note-saved';

const PANEL_MIN = { w: 240, h: 120 };
const Z_PANEL = 300000;

function loadSavedSize() {
  try {
    const raw = localStorage.getItem('instrument-notes-panel-size');
    if (raw) {
      const j = JSON.parse(raw);
      if (j && typeof j.w === 'number' && typeof j.h === 'number') {
        return {
          w: Math.max(PANEL_MIN.w, Math.min(j.w, typeof window !== 'undefined' ? window.innerWidth - 24 : 1200)),
          h: Math.max(PANEL_MIN.h, Math.min(j.h, typeof window !== 'undefined' ? window.innerHeight - 24 : 800)),
        };
      }
    }
  } catch (_) {}
  return { w: 320, h: 220 };
}

/**
 * Notes icon next to priced rows. Persists via API keyed by (symbol, instrumentType).
 */
export default function InstrumentNotesIcon({ symbol, instrumentType = 'stock' }) {
  const anchorRef = useRef(null);
  const panelRef = useRef(null);
  const resizeRef = useRef({ active: false, sx: 0, sy: 0, sw: 0, sh: 0 });

  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [dirty, setDirty] = useState(false);
  const [hasNote, setHasNote] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pos, setPos] = useState({ left: 40, top: 40 });
  const [size, setSize] = useState(() => loadSavedSize());
  const latestSizeRef = useRef({ w: 320, h: 220 });
  useEffect(() => {
    latestSizeRef.current = size;
  }, [size]);

  const symEnc = encodeURIComponent(symbol || '');
  const apiType = instrumentType === 'index' ? 'index' : 'stock';

  const fetchPresence = useCallback(async () => {
    if (!symbol) return;
    try {
      const r = await axios.get(`${API}/api/instrument-notes/${symEnc}`, {
        params: { type: apiType, exists_only: 1 },
      });
      setHasNote(!!r.data?.has_note);
    } catch (_) {}
  }, [symbol, symEnc, apiType]);

  const fetchNote = useCallback(async () => {
    if (!symbol) return;
    try {
      const r = await axios.get(`${API}/api/instrument-notes/${symEnc}`, { params: { type: apiType } });
      const body = r.data?.note ?? '';
      setText(body);
      setDirty(false);
      setHasNote(!!r.data?.has_note || !!(body && String(body).trim()));
    } catch (_) {}
  }, [symbol, symEnc, apiType]);

  useEffect(() => {
    setText('');
    setDirty(false);
    setHasNote(false);
  }, [symbol, apiType]);

  useEffect(() => {
    fetchPresence();
  }, [fetchPresence]);

  useEffect(() => {
    function onSaved(ev) {
      const d = ev.detail;
      if (!d || d.symbol !== symbol || d.instrument_type !== apiType) return;
      if (open) fetchNote();
      else fetchPresence();
    }
    window.addEventListener(INSTRUMENT_NOTE_SAVED_EVENT, onSaved);
    return () => window.removeEventListener(INSTRUMENT_NOTE_SAVED_EVENT, onSaved);
  }, [symbol, apiType, fetchNote, fetchPresence, open]);

  useEffect(() => {
    if (!open) return;
    fetchNote();
  }, [open, fetchNote]);

  useEffect(() => {
    if (!open) return;
    function onDocDown(e) {
      const a = anchorRef.current;
      const p = panelRef.current;
      if (a && a.contains(e.target)) return;
      if (p && p.contains(e.target)) return;
      setOpen(false);
    }
    document.addEventListener('mousedown', onDocDown);
    return () => document.removeEventListener('mousedown', onDocDown);
  }, [open]);

  function placePanel() {
    if (!anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    const w = size.w;
    const h = size.h;
    let left = rect.left;
    let top = rect.bottom + 6;
    if (left + w > window.innerWidth - 8) left = Math.max(8, window.innerWidth - w - 8);
    if (top + h > window.innerHeight - 8) top = Math.max(8, rect.top - h - 6);
    setPos({ left, top });
  }

  function toggleOpen(e) {
    e.stopPropagation();
    if (!open) {
      placePanel();
      setOpen(true);
    } else {
      setOpen(false);
    }
  }

  async function save(e) {
    if (e) e.stopPropagation();
    setSaving(true);
    try {
      await axios.put(`${API}/api/instrument-notes/${symEnc}`, {
        instrument_type: apiType,
        note: text,
      });
      setDirty(false);
      setHasNote(!!(text && text.trim()));
      window.dispatchEvent(
        new CustomEvent(INSTRUMENT_NOTE_SAVED_EVENT, {
          detail: { symbol, instrument_type: apiType },
        })
      );
    } finally {
      setSaving(false);
    }
  }

  function onResizeMove(e) {
    const r = resizeRef.current;
    if (!r.active) return;
    const dw = e.clientX - r.sx;
    const dh = e.clientY - r.sy;
    let nw = Math.max(PANEL_MIN.w, r.sw + dw);
    let nh = Math.max(PANEL_MIN.h, r.sh + dh);
    nw = Math.min(nw, window.innerWidth - pos.left - 8);
    nh = Math.min(nh, window.innerHeight - pos.top - 8);
    const next = { w: nw, h: nh };
    latestSizeRef.current = next;
    setSize(next);
  }

  function onResizeUp() {
    const r = resizeRef.current;
    if (!r.active) return;
    r.active = false;
    document.removeEventListener('mousemove', onResizeMove);
    document.removeEventListener('mouseup', onResizeUp);
    try {
      localStorage.setItem(
        'instrument-notes-panel-size',
        JSON.stringify(latestSizeRef.current)
      );
    } catch (_) {}
  }

  function onResizeStart(e) {
    e.stopPropagation();
    e.preventDefault();
    resizeRef.current = {
      active: true,
      sx: e.clientX,
      sy: e.clientY,
      sw: size.w,
      sh: size.h,
    };
    document.addEventListener('mousemove', onResizeMove);
    document.addEventListener('mouseup', onResizeUp);
  }

  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', onResizeMove);
      document.removeEventListener('mouseup', onResizeUp);
    };
  }, []);

  const noteTitle = apiType === 'index' ? 'Index note' : 'Stock note';

  return (
    <>
      <button
        type="button"
        ref={anchorRef}
        title={`${noteTitle}${hasNote ? ' (saved)' : ''}`}
        onClick={toggleOpen}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 26,
          height: 22,
          padding: 0,
          flexShrink: 0,
          border: `1px solid ${hasNote ? 'var(--accent-blue)' : 'var(--border)'}`,
          borderRadius: 4,
          backgroundColor: hasNote ? 'rgba(56,139,253,0.12)' : 'var(--bg-tertiary)',
          color: hasNote ? 'var(--accent-blue)' : 'var(--text-muted)',
          cursor: 'pointer',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          <path d="M8 7h8M8 11h8M8 15h5" strokeLinecap="round" />
        </svg>
      </button>

      {open &&
        createPortal(
          <div
            ref={panelRef}
            style={{
              position: 'fixed',
              left: pos.left,
              top: pos.top,
              width: size.w,
              height: size.h,
              zIndex: Z_PANEL,
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              boxShadow: '0 12px 40px rgba(0,0,0,0.55)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                flexShrink: 0,
                padding: '8px 10px',
                borderBottom: '1px solid var(--border-light)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {noteTitle} · {symbol}
              </span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setOpen(false);
                }}
                style={{
                  flexShrink: 0,
                  width: 26,
                  height: 26,
                  padding: 0,
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  background: 'var(--bg-tertiary)',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: 16,
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setDirty(true);
              }}
              onClick={(e) => e.stopPropagation()}
              placeholder="Private note for this instrument…"
              spellCheck
              style={{
                flex: 1,
                minHeight: 0,
                margin: 0,
                padding: 10,
                resize: 'none',
                border: 'none',
                outline: 'none',
                fontSize: 12,
                fontFamily: 'inherit',
                color: 'var(--text-primary)',
                backgroundColor: 'var(--bg-primary)',
              }}
            />
            <div
              style={{
                flexShrink: 0,
                padding: '8px 10px',
                borderTop: '1px solid var(--border-light)',
                display: 'flex',
                justifyContent: 'flex-end',
                gap: 8,
                alignItems: 'center',
              }}
            >
              {dirty && (
                <span style={{ fontSize: 11, color: 'var(--text-muted)', marginRight: 'auto' }}>
                  Unsaved changes
                </span>
              )}
              <button
                type="button"
                disabled={saving || !dirty}
                onClick={save}
                style={{
                  padding: '6px 14px',
                  fontSize: 12,
                  fontWeight: 600,
                  borderRadius: 5,
                  border: '1px solid var(--accent-blue)',
                  backgroundColor: dirty ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                  color: dirty ? '#fff' : 'var(--text-muted)',
                  cursor: dirty && !saving ? 'pointer' : 'default',
                }}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
            <div
              role="presentation"
              onMouseDown={onResizeStart}
              title="Resize"
              style={{
                position: 'absolute',
                right: 0,
                bottom: 0,
                width: 18,
                height: 18,
                cursor: 'nwse-resize',
                background: 'linear-gradient(135deg, transparent 50%, var(--border) 50%)',
              }}
            />
          </div>,
          document.body
        )}
    </>
  );
}
