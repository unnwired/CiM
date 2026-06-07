import React, { useRef } from 'react';

export default function PanelResizeHandle({ onResize }) {
  const startY     = useRef(0);
  const dragging   = useRef(false);

  function onMouseDown(e) {
    e.preventDefault();
    dragging.current = true;
    startY.current   = e.clientY;

    function onMouseMove(ev) {
      if (!dragging.current) return;
      const delta = ev.clientY - startY.current;
      startY.current = ev.clientY;
      onResize(delta);
    }

    function onMouseUp() {
      dragging.current = false;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
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
        zIndex:          10,
        transition:      'background 0.15s',
      }}
      onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--accent-blue)'}
      onMouseLeave={e => e.currentTarget.style.backgroundColor = 'var(--border)'}
    />
  );
}