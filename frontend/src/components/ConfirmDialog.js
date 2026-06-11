import React from 'react';

/**
 * In-app confirmation dialog (replaces window.confirm for admin actions).
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;

  return (
    <div
      className="cim-confirm-backdrop"
      role="presentation"
      onClick={onCancel}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.45)',
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="cim-confirm-title"
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--cim-panel-bg, #1e1e1e)',
          color: 'var(--cim-text, #eee)',
          borderRadius: 8,
          padding: '20px 24px',
          maxWidth: 420,
          width: '90%',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        }}
      >
        <h2 id="cim-confirm-title" style={{ margin: '0 0 12px', fontSize: '1.1rem' }}>
          {title}
        </h2>
        <p style={{ margin: '0 0 20px', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{message}</p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button type="button" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            style={danger ? { background: '#c0392b', color: '#fff' } : undefined}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Promise-based helper for confirm flows.
 */
export function askConfirm(setConfirmState, { title, message, confirmLabel, danger = false }) {
  return new Promise(resolve => {
    setConfirmState({
      title,
      message,
      confirmLabel,
      danger,
      onConfirm: () => {
        setConfirmState(null);
        resolve(true);
      },
      onCancel: () => {
        setConfirmState(null);
        resolve(false);
      },
    });
  });
}
