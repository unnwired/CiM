import React from 'react';
import supportUpiQr from '../assets/support-upi-qr.png';

export default function SupportQrModalBody({ open }) {
  if (!open) return null;

  return (
    <>
      <img
        src={supportUpiQr}
        alt="UPI QR code for Sandeep Balachandran — sandeep.balachandran-2@okaxis"
        style={{ width: '100%', maxWidth: 360, height: 'auto', borderRadius: 6, display: 'block' }}
      />
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
        Scan with any UPI app (Google Pay, PhonePe, Paytm, etc.)
      </div>
    </>
  );
}
