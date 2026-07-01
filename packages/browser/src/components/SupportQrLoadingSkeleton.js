import React from 'react';

/** Fixed-size placeholder so the support modal does not look empty while the QR loads. */
export default function SupportQrLoadingSkeleton() {
  return (
    <div
      style={{
        width: '100%',
        maxWidth: 360,
        aspectRatio: '1',
        minHeight: 200,
        borderRadius: 6,
        backgroundColor: 'var(--bg-tertiary)',
        border: '1px dashed var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      aria-busy="true"
      aria-label="Loading support QR code"
    >
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading QR…</span>
    </div>
  );
}
