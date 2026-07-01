import React, { useState } from 'react';

export default function SchedulerLogPanel({ logTail = [] }) {
  const [open, setOpen] = useState(false);
  const lines = Array.isArray(logTail) ? logTail : [];

  return (
    <div style={{
      backgroundColor: 'var(--bg-tertiary)',
      borderRadius: 6,
      padding: open ? '8px 10px' : '6px 10px',
      border: '1px solid var(--border)',
      flexShrink: 0,
    }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex',
          width: '100%',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          color: 'var(--text-primary)',
          fontSize: 11,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}
      >
        <span>Scheduler log{!open && lines.length ? ` (${lines.length})` : ''}</span>
        <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <pre style={{
          margin: '6px 0 0',
          padding: 6,
          fontSize: 10,
          lineHeight: 1.4,
          maxHeight: 144,
          overflow: 'auto',
          backgroundColor: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          borderRadius: 5,
          color: 'var(--text-muted)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
        >
          {lines.length ? lines.slice(-16).join('\n') : 'No log entries yet.'}
        </pre>
      )}
    </div>
  );
}
