import React, { useEffect, useState } from 'react';
import {
  getCachedSecureSupportQrUrl,
  prefetchSecureSupportQr,
} from '../utils/supportQrSecure';
import SupportQrLoadingSkeleton from './SupportQrLoadingSkeleton';

export default function SupportQrModalBody({ open }) {
  const [src, setSrc] = useState(() => getCachedSecureSupportQrUrl());
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;

    const cached = getCachedSecureSupportQrUrl();
    if (cached) {
      setSrc(cached);
      setError(null);
      return undefined;
    }

    setError(null);

    prefetchSecureSupportQr()
      .then((url) => {
        if (!cancelled) {
          setSrc(url);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setSrc(null);
          setError(e?.message || 'Unable to verify support QR.');
        }
      });

    return () => { cancelled = true; };
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
    return <SupportQrLoadingSkeleton />;
  }

  return (
    <>
      <img
        src={src}
        alt="UPI QR code for Sandeep Balachandran — sandeep.balachandran-2@okaxis"
        decoding="async"
        style={{ width: '100%', maxWidth: 360, height: 'auto', borderRadius: 6, display: 'block' }}
      />
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
        Scan with any UPI app (Google Pay, PhonePe, Paytm, etc.)
      </div>
    </>
  );
}
