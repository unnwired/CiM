import React, { useState, useEffect } from 'react';
import { loadSecureSupportQrObjectUrl } from '../utils/supportQrSecure';

export default function SupportQrModalBody({ open }) {
  const [src, setSrc] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    let objectUrl = null;
    let cancelled = false;

    async function load() {
      try {
        objectUrl = await loadSecureSupportQrObjectUrl();
        if (!cancelled) {
          setSrc(objectUrl);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setSrc(null);
          setError(e?.message || 'Unable to verify support QR.');
        }
      }
    }

    setSrc(null);
    setError(null);
    load();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [open]);

  if (error) {
    return (
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center', padding: '8px 0', maxWidth: 360 }}>
        {error}
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
          This package may have been modified. The support QR is hidden.
        </div>
      </div>
    );
  }

  if (!src) {
    return (
      <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '24px 0' }}>Loading…</div>
    );
  }

  return (
    <>
      <img
        src={src}
        alt="UPI QR code for Sandeep Balachandran — sandeep.balachandran-2@okaxis"
        style={{ width: '100%', maxWidth: 360, height: 'auto', borderRadius: 6, display: 'block' }}
      />
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
        Scan with any UPI app (Google Pay, PhonePe, Paytm, etc.)
      </div>
    </>
  );
}
