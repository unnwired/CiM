import React, { useEffect, useState } from 'react';
import { SUPPORT_QR_DEV_URL, prefetchDevSupportQr } from '../utils/supportQrDevAsset';
import SupportQrLoadingSkeleton from './SupportQrLoadingSkeleton';

export default function SupportQrModalBody({ open }) {
  const [imgReady, setImgReady] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setError(null);

    prefetchDevSupportQr()
      .then(() => {
        if (!cancelled) setImgReady(true);
      })
      .catch((e) => {
        if (!cancelled) {
          setImgReady(false);
          setError(e?.message || 'Support QR failed to load.');
        }
      });

    return () => { cancelled = true; };
  }, [open]);

  if (error) {
    return (
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center', padding: '8px 0', maxWidth: 360 }}>
        {error}
      </div>
    );
  }

  if (!imgReady) {
    return <SupportQrLoadingSkeleton />;
  }

  return (
    <>
      <img
        src={SUPPORT_QR_DEV_URL}
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
