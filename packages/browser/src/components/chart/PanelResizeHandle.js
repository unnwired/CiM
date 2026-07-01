import React, { useRef } from 'react';

/**
 * Coalesce mousemove deltas to one onResize call per animation frame.
 */
export function scheduleResizeDelta(pendingRef, rafRef, delta, onResize) {
  pendingRef.current += delta;
  if (rafRef.current != null) return;
  rafRef.current = window.requestAnimationFrame(() => {
    rafRef.current = null;
    const total = pendingRef.current;
    pendingRef.current = 0;
    if (total !== 0) onResize(total);
  });
}

export default function PanelResizeHandle({ onResize, onResizeStart, onResizeEnd }) {
  const startY     = useRef(0);
  const dragging   = useRef(false);
  const pendingDelta = useRef(0);
  const rafId      = useRef(null);

  function flushPending() {
    if (rafId.current != null) {
      window.cancelAnimationFrame(rafId.current);
      rafId.current = null;
    }
    const total = pendingDelta.current;
    pendingDelta.current = 0;
    if (total !== 0) onResize(total);
  }

  function onMouseDown(e) {
    e.preventDefault();
    dragging.current = true;
    startY.current   = e.clientY;
    pendingDelta.current = 0;
    if (onResizeStart) onResizeStart();

    function onMouseMove(ev) {
      if (!dragging.current) return;
      const delta = ev.clientY - startY.current;
      startY.current = ev.clientY;
      scheduleResizeDelta(pendingDelta, rafId, delta, onResize);
    }

    function onMouseUp() {
      dragging.current = false;
      flushPending();
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      if (onResizeEnd) onResizeEnd();
    }

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  return (
    <div
      onMouseDown={onMouseDown}
      style={{
        height:          '4px',
        backgroundColor: 'var(--border)',
        cursor:          'row-resize',
        flexShrink:      0,
        position:        'relative',
        zIndex:          30,
        transition:      'background 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--accent-blue)'; }}
      onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'var(--border)'; }}
    />
  );
}
