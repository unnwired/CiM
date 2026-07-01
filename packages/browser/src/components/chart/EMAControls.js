import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { HexColorPicker } from 'react-colorful';
import { normalizeEmaSet } from '../../config/chartDefaults';

export default function EMAControls({ emas, onChange }) {
  const normalized = useMemo(() => normalizeEmaSet(emas), [emas]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [draft, setDraft] = useState(normalized);
  const [activeColorIdx, setActiveColorIdx] = useState(null);
  const [colorDraft, setColorDraft] = useState('#ffffff');
  const [menuRect, setMenuRect] = useState(null);
  const anchorRef = useRef(null);
  const lastVisibleRef = useRef(normalized.map((e) => e.visible));

  useEffect(() => {
    if (menuOpen) setDraft(normalized);
  }, [menuOpen, normalized]);

  useEffect(() => {
    if (!menuOpen) {
      setActiveColorIdx(null);
      setColorDraft('#ffffff');
    }
  }, [menuOpen]);

  useLayoutEffect(() => {
    if (!menuOpen) {
      setMenuRect(null);
      return;
    }
    const update = () => {
      const el = anchorRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const width = 250;
      const pad = 8;
      const left = Math.min(Math.max(pad, r.left), Math.max(pad, window.innerWidth - width - pad));
      setMenuRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [menuOpen]);

  function toggleMaster() {
    const anyEnabled = normalized.some((e) => e.visible);
    if (anyEnabled) {
      lastVisibleRef.current = normalized.map((e) => e.visible);
      onChange(normalized.map((e) => ({ ...e, visible: false })));
      return;
    }
    const restore = normalized.map((e, i) => ({ ...e, visible: lastVisibleRef.current[i] ?? true }));
    onChange(restore);
  }

  function setDraftField(idx, patch) {
    setDraft((prev) => prev.map((e, i) => (i === idx ? { ...e, ...patch } : e)));
  }

  function toggleColorEditor(idx) {
    setActiveColorIdx((prev) => {
      if (prev === idx) return null;
      setColorDraft((draft[idx]?.color || '#ffffff').toLowerCase());
      return idx;
    });
  }

  function closeColorEditor() {
    setActiveColorIdx(null);
  }

  function applyColorEditor() {
    if (activeColorIdx === null) return;
    const nextDraft = draft.map((e, i) => (
      i === activeColorIdx ? { ...e, color: colorDraft } : e
    ));
    setDraft(nextDraft);
    setActiveColorIdx(null);
    onChange(normalizeEmaSet(nextDraft));
  }

  function handlePeriodInput(idx, value) {
    const n = parseInt(value.replace(/[^\d]/g, ''), 10);
    if (Number.isNaN(n)) {
      setDraftField(idx, { period: '' });
      return;
    }
    setDraftField(idx, { period: Math.max(1, Math.min(500, n)) });
  }

  function commitDraftFromState(nextDraft) {
    const dedup = new Set();
    const next = nextDraft.map((e) => {
      let period = Number(e.period);
      if (!Number.isFinite(period) || period <= 0) period = 1;
      period = Math.min(500, period);
      while (dedup.has(period) && period < 500) period += 1;
      dedup.add(period);
      return { ...e, period };
    });
    onChange(normalizeEmaSet(next));
  }

  function commitDraft() {
    commitDraftFromState(draft);
    setMenuOpen(false);
  }

  function closeMenu(commitChanges = true) {
    if (commitChanges) {
      const next = normalizeEmaSet(draft);
      if (JSON.stringify(next) !== JSON.stringify(normalized)) {
        commitDraftFromState(draft);
      }
    }
    setMenuOpen(false);
  }

  function cancelDraft() {
    setDraft(normalized);
    setMenuOpen(false);
  }

  function toggleMenu() {
    if (menuOpen) {
      closeMenu(true);
      return;
    }
    setDraft(normalized);
    setMenuOpen(true);
  }

  function parseHexToRgb(hex) {
    const s = String(hex || '').replace('#', '');
    const n = s.length === 3 ? s.split('').map((c) => c + c).join('') : s;
    if (!/^[0-9a-fA-F]{6}$/.test(n)) return null;
    return {
      r: parseInt(n.slice(0, 2), 16),
      g: parseInt(n.slice(2, 4), 16),
      b: parseInt(n.slice(4, 6), 16),
    };
  }

  function rgbToHsl({ r, g, b }) {
    const rn = r / 255;
    const gn = g / 255;
    const bn = b / 255;
    const max = Math.max(rn, gn, bn);
    const min = Math.min(rn, gn, bn);
    const d = max - min;
    let h = 0;
    const l = (max + min) / 2;
    const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
    if (d !== 0) {
      if (max === rn) h = ((gn - bn) / d) % 6;
      else if (max === gn) h = (bn - rn) / d + 2;
      else h = (rn - gn) / d + 4;
      h = Math.round(h * 60);
      if (h < 0) h += 360;
    }
    return { h, s: Math.round(s * 100), l: Math.round(l * 100) };
  }

  const rgb = parseHexToRgb(colorDraft);
  const hsl = rgb ? rgbToHsl(rgb) : null;
  const rgbText = rgb ? `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})` : 'rgb(—, —, —)';
  const hslText = hsl ? `hsl(${hsl.h}, ${hsl.s}%, ${hsl.l}%)` : 'hsl(—, —%, —%)';

  async function copyText(val) {
    try { await navigator.clipboard.writeText(val); } catch {}
  }

  const masterOn = normalized.some((e) => e.visible);

  return (
    <div ref={anchorRef} style={{ position: 'relative', flexShrink: 0 }}>
      <button
        type="button"
        onClick={toggleMenu}
        style={{
          height: 28,
          minWidth: 82,
          borderRadius: 5,
          border: '1px solid var(--border)',
          backgroundColor: 'var(--bg-tertiary)',
          color: 'var(--text-secondary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          padding: '0 8px',
          fontSize: 11,
          fontWeight: 600,
        }}
      >
        <span>EMA</span>
        <span
          onClick={(e) => { e.stopPropagation(); toggleMaster(); }}
          title={masterOn ? 'Turn EMA off' : 'Turn EMA on'}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            width: 30,
            height: 24,
            marginTop: -2,
            marginBottom: -2,
            marginRight: -4,
            padding: '2px 6px 2px 6px',
            cursor: 'pointer',
          }}
        >
          <span
            style={{
              width: 9,
              height: 9,
              borderRadius: 999,
              border: '1px solid var(--border)',
              backgroundColor: masterOn ? '#ffffff' : '#707b8a',
              boxShadow: masterOn ? '0 0 5px rgba(255,255,255,0.75)' : 'none',
              display: 'inline-block',
              flexShrink: 0,
            }}
          />
        </span>
      </button>

      {menuOpen && menuRect && (
        <div
          style={{
            position: 'fixed',
            top: menuRect.top,
            left: menuRect.left,
            zIndex: 300000,
            width: menuRect.width,
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            padding: 10,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          {draft.map((ema, idx) => (
            <div key={idx} style={{ display: 'grid', gridTemplateColumns: '18px 1fr 34px', gap: 8, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={!!ema.visible}
                onChange={(e) => setDraftField(idx, { visible: e.target.checked })}
              />
              <input
                value={String(ema.period)}
                onChange={(e) => handlePeriodInput(idx, e.target.value)}
                style={{
                  height: 28,
                  borderRadius: 4,
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-tertiary)',
                  color: 'var(--text-primary)',
                  padding: '0 8px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                }}
              />
              <button
                type="button"
                onClick={() => toggleColorEditor(idx)}
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 4,
                  border: '1px solid var(--border)',
                  backgroundColor: ema.color || '#ffffff',
                  cursor: 'pointer',
                }}
              />
            </div>
          ))}

          {activeColorIdx !== null && draft[activeColorIdx] && (
            <div style={{
              border: '1px solid var(--border)',
              borderRadius: 6,
              backgroundColor: 'var(--bg-tertiary)',
              padding: 10,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>
                EMA {draft[activeColorIdx].period} color
              </div>
              <HexColorPicker
                color={colorDraft}
                onChange={(color) => setColorDraft(color)}
                style={{ width: '100%' }}
              />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 6, alignItems: 'center' }}>
                <input
                  value={colorDraft}
                  onChange={(e) => setColorDraft(e.target.value)}
                  style={{
                    height: 28,
                    borderRadius: 4,
                    border: '1px solid var(--border)',
                    backgroundColor: 'var(--bg-secondary)',
                    color: 'var(--text-primary)',
                    padding: '0 8px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                  }}
                />
                <button
                  type="button"
                  onClick={() => copyText(colorDraft)}
                  style={{
                    height: 28,
                    borderRadius: 4,
                    border: '1px solid var(--border)',
                    backgroundColor: 'var(--bg-secondary)',
                    color: 'var(--text-secondary)',
                    padding: '0 8px',
                    fontSize: 11,
                  }}
                >
                  Copy
                </button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 6, alignItems: 'center' }}>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{rgbText}</div>
                <button type="button" onClick={() => copyText(rgbText)} style={{ height: 24, borderRadius: 4, border: '1px solid var(--border)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-secondary)', padding: '0 8px', fontSize: 10 }}>Copy</button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 6, alignItems: 'center' }}>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{hslText}</div>
                <button type="button" onClick={() => copyText(hslText)} style={{ height: 24, borderRadius: 4, border: '1px solid var(--border)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-secondary)', padding: '0 8px', fontSize: 10 }}>Copy</button>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button
                  type="button"
                  onClick={closeColorEditor}
                  style={{
                    height: 28,
                    borderRadius: 4,
                    border: '1px solid var(--border)',
                    backgroundColor: 'var(--bg-secondary)',
                    color: 'var(--text-secondary)',
                    padding: '0 10px',
                    fontSize: 11,
                  }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={applyColorEditor}
                  style={{
                    height: 28,
                    borderRadius: 4,
                    border: '1px solid var(--accent-blue)',
                    backgroundColor: 'rgba(56,139,253,0.2)',
                    color: 'var(--accent-blue)',
                    padding: '0 10px',
                    fontSize: 11,
                    fontWeight: 600,
                  }}
                >
                  Apply
                </button>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
            <button
              type="button"
              onClick={cancelDraft}
              style={{
                height: 28,
                borderRadius: 4,
                border: '1px solid var(--border)',
                backgroundColor: 'var(--bg-tertiary)',
                color: 'var(--text-secondary)',
                padding: '0 10px',
                fontSize: 11,
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={commitDraft}
              style={{
                height: 28,
                borderRadius: 4,
                border: '1px solid var(--accent-blue)',
                backgroundColor: 'rgba(56,139,253,0.2)',
                color: 'var(--accent-blue)',
                padding: '0 10px',
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              OK
            </button>
          </div>
        </div>
      )}
    </div>
  );
}