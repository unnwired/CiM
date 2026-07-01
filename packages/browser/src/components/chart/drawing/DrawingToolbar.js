import React, { useState } from 'react';
import { DRAWING_TOOLS } from './drawingTypes';

const COLORS = ['#58a6ff', '#3fb950', '#f85149', '#d2a8ff', '#ffa657', '#ffffff', '#8b949e'];
const WIDTHS = [1, 2, 3, 4];

const STRIP_W = 14;
const PANEL_W = 34;

const pillStyle = {
  position: 'absolute',
  left: Math.max(0, (STRIP_W - 12) / 2),
  width: 12,
  minHeight: 44,
  padding: '6px 0',
  borderRadius: 6,
  border: 'none',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  backgroundColor: 'var(--accent-blue)',
  color: '#fff',
  fontSize: 13,
  fontWeight: 700,
  lineHeight: 1,
  boxShadow: '0 2px 8px rgba(0,0,0,0.35)',
  zIndex: 2,
};

const btn = (active, w = 28) => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: w,
  height: 24,
  padding: 0,
  margin: 0,
  border: 'none',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: 11,
  fontWeight: 600,
  flexShrink: 0,
  backgroundColor: active ? 'var(--accent-blue)' : 'transparent',
  color: active ? '#fff' : 'var(--text-secondary)',
});

export function DrawingToolbarInner({
  collapsed,
  onCollapsedChange,
  activeTool,
  onToolChange,
  lineColor,
  onLineColor,
  lineWidth,
  onLineWidth,
  favorites,
  onToggleFavorite,
  floatOpen,
  onFloatOpenChange,
  linesExpanded,
  onLinesExpandedChange,
  mirrorAvailable,
  mirrorEnabled,
  onMirrorChange,
  onClearAll,
  onDeleteSelected,
  hasSelection,
}) {
  const [confirmClear, setConfirmClear] = useState(false);

  if (collapsed) {
    return (
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: STRIP_W,
          flexShrink: 0,
          backgroundColor: 'rgba(22,27,34,0.92)',
          borderRight: '1px solid var(--border)',
          zIndex: 40,
          pointerEvents: 'auto',
        }}
      >
        <button
          type="button"
          title="Show drawing tools"
          onClick={() => onCollapsedChange(false)}
          style={{ ...pillStyle, bottom: 10, top: 'auto' }}
        >
          {'>'}
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: PANEL_W,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        backgroundColor: 'rgba(22,27,34,0.96)',
        borderRight: '1px solid var(--border)',
        padding: '6px 0 52px',
        gap: 4,
        zIndex: 40,
        pointerEvents: 'auto',
        overflow: 'hidden',
        boxSizing: 'border-box',
      }}
    >
      <button type="button" title="Favorites palette" onClick={() => onFloatOpenChange(!floatOpen)}
        style={{ ...btn(floatOpen, 26), height: 22, fontSize: 10, marginBottom: 2 }}>
        {'\u2605'}
      </button>

      <button type="button" title="Select / move" onClick={() => onToolChange(activeTool === 'select' ? null : 'select')}
        style={{ ...btn(activeTool === 'select', 28) }}>⤧</button>

      <button
        type="button"
        title={linesExpanded ? 'Collapse line tools' : 'Expand line tools'}
        onClick={() => onLinesExpandedChange(!linesExpanded)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          width: 28, height: 22, padding: '0 4px', margin: 0, border: 'none', borderRadius: 4,
          cursor: 'pointer', fontSize: 9, fontWeight: 700, color: 'var(--text-muted)',
          backgroundColor: 'var(--bg-tertiary)', flexShrink: 0,
        }}
      >
        <span style={{ letterSpacing: '-0.02em' }}>Ln</span>
        <span style={{ fontSize: 10, color: 'var(--accent-blue)' }}>{linesExpanded ? '\u2228' : '>'}</span>
      </button>

      {linesExpanded && DRAWING_TOOLS.map((t) => (
        <div key={t.id} style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>
          <button type="button" title={t.label} onClick={() => onToolChange(activeTool === t.id ? null : t.id)}
            style={{ ...btn(activeTool === t.id, 28) }}>
            {t.short}
          </button>
          <button type="button" title={favorites.includes(t.id) ? 'Unfavorite' : 'Favorite'}
            onClick={(e) => { e.stopPropagation(); onToggleFavorite(t.id); }}
            style={{
              position: 'absolute', right: 0, top: -1, width: 12, height: 12, padding: 0, border: 'none',
              borderRadius: 2, cursor: 'pointer', fontSize: 8, lineHeight: 1,
              backgroundColor: 'var(--bg-secondary)', color: favorites.includes(t.id) ? 'var(--accent-blue)' : 'var(--text-muted)',
            }}>★</button>
        </div>
      ))}

      <div style={{ width: 24, height: 1, backgroundColor: 'var(--border)', margin: '2px 0', flexShrink: 0 }} />

      <div style={{ display: 'grid', gridTemplateColumns: '12px 12px', gap: 3, justifyContent: 'center', width: '100%' }}>
        {COLORS.map((c) => (
          <button key={c} type="button" title={c} onClick={() => onLineColor(c)}
            style={{
              width: 12, height: 12, borderRadius: 2,
              border: lineColor === c ? '2px solid #fff' : '1px solid var(--border)',
              backgroundColor: c, padding: 0, cursor: 'pointer',
            }} />
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, width: 28, flexShrink: 0 }}>
        {WIDTHS.map((w) => (
          <button key={w} type="button" onClick={() => onLineWidth(w)}
            style={{ ...btn(lineWidth === w, 28), height: 20, fontSize: 10, fontFamily: 'var(--font-mono)' }}>{w}</button>
        ))}
      </div>

      {hasSelection && (
        <button type="button" title="Delete selected" onClick={onDeleteSelected}
          style={{ ...btn(false, 28), height: 22, fontSize: 10, marginTop: 2, color: 'var(--accent-red)' }}>⌫</button>
      )}

      {!confirmClear ? (
        <button type="button" title="Clear all on focused chart" onClick={() => setConfirmClear(true)}
          style={{ ...btn(false, 28), height: 20, fontSize: 8, marginTop: 2, color: 'var(--text-muted)' }}>CLR</button>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, width: 28 }}>
          <button type="button" onClick={() => { setConfirmClear(false); onClearAll && onClearAll(); }}
            style={{ ...btn(true, 28), height: 18, fontSize: 8 }}>OK</button>
          <button type="button" onClick={() => setConfirmClear(false)}
            style={{ ...btn(false, 28), height: 16, fontSize: 8 }}>No</button>
        </div>
      )}

      {mirrorAvailable && onMirrorChange && (
        <label style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, marginTop: 4, width: 28,
          fontSize: 8, color: 'var(--text-muted)', cursor: 'pointer', userSelect: 'none',
        }} title="Mirror drawings across split charts">
          <input type="checkbox" checked={mirrorEnabled} onChange={(e) => onMirrorChange(e.target.checked)} style={{ margin: 0 }} />
          <span style={{ textAlign: 'center', lineHeight: 1.1 }}>Mir</span>
        </label>
      )}

      <div style={{ flex: 1, minHeight: 4 }} />

      <button
        type="button"
        title="Hide drawing tools"
        onClick={() => onCollapsedChange(true)}
        style={{ ...pillStyle, bottom: 10, top: 'auto' }}
      >
        {'<'}
      </button>
    </div>
  );
}

/** Renders the single toolbar using workspace + mirror context */
export function DrawingToolbarConnected() {
  return null;
}

export function DrawingFloatPaletteConnected() {
  return null;
}

export function DrawingFloatPalette({
  open,
  onClose,
  favorites,
  activeTool,
  onToolChange,
}) {
  if (!open) return null;
  const favSet = new Set(favorites);
  const tools = DRAWING_TOOLS.filter((t) => favSet.has(t.id));
  if (tools.length === 0) return null;

  return (
    <div style={{
      position: 'fixed', bottom: 20, left: 20, zIndex: 200010,
      display: 'flex', gap: 4, padding: '6px 8px',
      backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)',
      borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
    }}>
      {tools.map((t) => (
        <button key={t.id} type="button" title={t.label} onClick={() => onToolChange(activeTool === t.id ? null : t.id)}
          style={{
            width: 32, height: 30, borderRadius: 6, border: 'none', cursor: 'pointer',
            fontSize: 12, fontWeight: 600,
            backgroundColor: activeTool === t.id ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
            color: activeTool === t.id ? '#fff' : 'var(--text-secondary)',
          }}>{t.short}</button>
      ))}
      <button type="button" title="Close" onClick={onClose}
        style={{ width: 24, border: 'none', borderRadius: 4, cursor: 'pointer', background: 'transparent', color: 'var(--text-muted)' }}>×</button>
    </div>
  );
}
