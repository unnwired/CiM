import React from 'react';

/** 2px-tall accent bar showing where a list item will be inserted (between rows). */
export function DropInsetLine() {
  return (
    <div
      aria-hidden
      style={{
        height: 3,
        margin: '0 4px',
        borderRadius: 2,
        background: 'linear-gradient(90deg, transparent, var(--accent-blue), transparent)',
        boxShadow: '0 0 8px rgba(56,139,253,0.55)',
        flexShrink: 0,
      }}
    />
  );
}

/**
 * Custom drag image for list reorder (must stay in DOM until after dragstart returns).
 */
export function setListDragImage(dataTransfer, primary, secondary) {
  if (!dataTransfer || typeof document === 'undefined') return;
  const wrap = document.createElement('div');
  wrap.style.cssText = [
    'position:fixed',
    'left:-9999px',
    'top:0',
    'padding:8px 12px',
    'background:var(--bg-secondary)',
    'border:1px solid var(--accent-blue)',
    'border-radius:6px',
    'box-shadow:0 8px 24px rgba(0,0,0,0.45)',
    'max-width:280px',
    'font-family:var(--font-mono),monospace',
    'font-size:12px',
    'font-weight:600',
    'color:var(--text-primary)',
    'pointer-events:none',
    'z-index:2147483647',
  ].join(';');
  wrap.textContent = primary || '';
  if (secondary) {
    const sub = document.createElement('div');
    sub.textContent = secondary;
    sub.style.cssText = 'font-size:10px;font-weight:500;color:var(--text-muted);margin-top:4px;font-family:inherit;';
    wrap.appendChild(sub);
  }
  document.body.appendChild(wrap);
  try {
    dataTransfer.setDragImage(wrap, 24, 20);
    dataTransfer.effectAllowed = 'move';
  } finally {
    requestAnimationFrame(() => {
      document.body.removeChild(wrap);
    });
  }
}
