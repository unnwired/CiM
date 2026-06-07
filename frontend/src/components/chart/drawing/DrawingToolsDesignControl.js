import React, { useEffect, useMemo, useState } from 'react';
import { useDrawingWorkspace } from './DrawingWorkspaceContext';
import { CHART_DRAWINGS_ENABLED } from './drawingFeature';

const PANEL_Z_INDEX = 200010;

const LINE_DRAWING_TOOLS = [
  { key: 'trendline', label: 'Trendline', glyph: '／' },
  { key: 'h_line', label: 'Horizontal Line', glyph: '—' },
  { key: 'h_ray', label: 'Horizontal Ray', glyph: '⟶' },
  { key: 'v_line', label: 'Vertical Line', glyph: '|' },
  { key: 'cross', label: 'Cross Line', glyph: '+' },
  { key: 'channel', label: 'Parallel Channel', glyph: '∥' },
  { key: 'ray', label: 'Ray', glyph: '›' },
];

const FIBONACCI_TOOLS = [
  { key: 'fib', label: 'Fibonacci Retracement', glyph: 'ƒ' },
];

const RANGE_TOOLS = [
  { key: 'price_range', label: 'Price Range', glyph: '⎺↕⎽' },
];

const TOOL_MAP = {
  trendline: 'trendline',
  horizontal_line: 'h_line',
  horizontal_ray: 'h_ray',
  vertical_line: 'v_line',
  cross_line: 'cross',
  parallel_channel: 'channel',
  fib_retracement: 'fib',
  fib_extension: 'fib',
  fib_time: 'fib',
  price_range: 'price_range',
};

const buttonBaseStyle = {
  display: 'inline-flex',
  alignItems: 'stretch',
  height: 28,
  border: '1px solid var(--border)',
  borderRadius: 5,
  backgroundColor: 'var(--bg-tertiary)',
  overflow: 'hidden',
  cursor: 'pointer',
  flexShrink: 0,
  padding: 0,
};

function ToolIconButton({ tool, activeTool, onPickTool }) {
  const mapped = TOOL_MAP[tool.key] || null;
  const isActive = mapped ? activeTool === mapped : false;
  return (
    <button
      type="button"
      title={tool.label}
      aria-label={tool.label}
      onClick={() => {
        if (!mapped) return;
        const nextTool = isActive ? null : mapped;
        if (typeof onPickTool === 'function') onPickTool(nextTool);
        window.dispatchEvent(new CustomEvent('flowx-drawing-set-tool', { detail: { tool: nextTool } }));
      }}
      style={{
        width: 30,
        height: 28,
        border: '1px solid var(--border)',
        borderRadius: 4,
        backgroundColor: isActive ? 'rgba(56,139,253,0.18)' : 'var(--bg-tertiary)',
        color: isActive ? 'var(--accent-blue)' : 'var(--text-secondary)',
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        cursor: 'pointer',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}
    >
      {tool.glyph}
    </button>
  );
}

export default function DrawingToolsDesignControl({ panelOffsetX = 0, panelOffsetY = 0 }) {
  const dw = useDrawingWorkspace();
  const [localActiveTool, setLocalActiveTool] = useState(null);
  useEffect(() => {
    const handler = (e) => {
      const tool = e?.detail?.tool;
      setLocalActiveTool(typeof tool === 'string' ? tool : null);
    };
    window.addEventListener('flowx-drawing-set-tool', handler);
    return () => window.removeEventListener('flowx-drawing-set-tool', handler);
  }, []);
  const activeTool = dw?.activeTool || localActiveTool || null;
  const [enabled, setEnabled] = useState(false);
  const [open, setOpen] = useState(false);
  const [panelPos, setPanelPos] = useState({
    x: Math.max(24, 120 + panelOffsetX),
    y: Math.max(92, 92 + panelOffsetY),
  });
  const allGroups = useMemo(
    () => [
      { title: 'Line Drawing', tools: LINE_DRAWING_TOOLS },
      { title: 'Fibonacci', tools: FIBONACCI_TOOLS },
      { title: 'Range', tools: RANGE_TOOLS },
    ],
    []
  );

  const handleToggle = () => {
    setEnabled((prev) => {
      const next = !prev;
      setOpen(next);
      return next;
    });
  };

  if (!CHART_DRAWINGS_ENABLED) return null;

  return (
    <>
      <div style={buttonBaseStyle}>
        <button
          type="button"
          onClick={() => {
            if (!enabled) return;
            setOpen((prev) => !prev);
          }}
          style={{
            border: 'none',
            borderRight: '1px solid var(--border)',
            backgroundColor: enabled ? 'rgba(56,139,253,0.10)' : 'transparent',
            color: enabled ? 'var(--accent-blue)' : 'var(--text-secondary)',
            fontSize: 12,
            fontWeight: 500,
            padding: '0 10px',
            fontFamily: 'var(--font-mono)',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            whiteSpace: 'nowrap',
          }}
          title="Drawing Tools"
        >
          Drawing Tools
        </button>
        <button
          type="button"
          onClick={handleToggle}
          title={enabled ? 'Disable Drawing Tools' : 'Enable Drawing Tools'}
          style={{
            border: 'none',
            backgroundColor: 'transparent',
            width: 24,
            padding: 0,
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              backgroundColor: enabled ? 'var(--accent-blue)' : 'var(--text-muted)',
              opacity: enabled ? 1 : 0.72,
            }}
          />
        </button>
      </div>

      {enabled && open && (
        <div
          style={{
            position: 'fixed',
            left: panelPos.x,
            top: panelPos.y,
            width: 236,
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            boxShadow: '0 12px 28px rgba(0,0,0,0.45)',
            zIndex: PANEL_Z_INDEX,
            overflow: 'hidden',
          }}
        >
          <div
            role="presentation"
            onMouseDown={(evt) => {
              if (evt.button !== 0) return;
              const startX = evt.clientX;
              const startY = evt.clientY;
              const originX = panelPos.x;
              const originY = panelPos.y;
              const onMove = (moveEvt) => {
                const nextX = originX + (moveEvt.clientX - startX);
                const nextY = originY + (moveEvt.clientY - startY);
                setPanelPos({
                  x: Math.max(8, nextX),
                  y: Math.max(52, nextY),
                });
              };
              const onUp = () => {
                window.removeEventListener('mousemove', onMove);
                window.removeEventListener('mouseup', onUp);
              };
              window.addEventListener('mousemove', onMove);
              window.addEventListener('mouseup', onUp);
            }}
            style={{
              height: 34,
              borderBottom: '1px solid var(--border)',
              backgroundColor: 'var(--bg-tertiary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 10px',
              cursor: 'move',
              userSelect: 'none',
            }}
          >
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                color: 'var(--text-primary)',
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
                fontWeight: 600,
              }}
            >
              Drawing Tools
              <span aria-hidden="true">✎</span>
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              title="Close"
              style={{
                width: 18,
                height: 18,
                border: 'none',
                background: 'transparent',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                fontSize: 14,
                lineHeight: '18px',
                padding: 0,
              }}
            >
              ×
            </button>
          </div>

          <div style={{ padding: '10px 10px 12px', display: 'grid', gap: 10 }}>
            {allGroups.map((group) => (
              <div key={group.title} style={{ display: 'grid', gap: 7 }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    color: 'var(--text-muted)',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                  }}
                >
                  <span>{group.title}</span>
                  <span style={{ flex: 1, borderBottom: '1px dashed var(--border)' }} />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  {group.tools.map((tool) => (
                    <ToolIconButton
                      key={tool.key}
                      tool={tool}
                      activeTool={activeTool}
                      onPickTool={dw?.setActiveTool || (() => {})}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
