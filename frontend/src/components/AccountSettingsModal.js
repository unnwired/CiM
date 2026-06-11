import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import {
  fetchLicenseStatus,
  logout,
  recoveryRegenerate,
  totpConfirm,
  totpDisable,
  totpEnroll,
} from '../api/auth';

export default function AccountSettingsModal({ open, onClose, licenseStatus, onSignedOut }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [enroll, setEnroll] = useState(null);
  const [confirmCode, setConfirmCode] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState(null);

  if (!open) return null;

  const email = licenseStatus?.email || '—';
  const offline = licenseStatus?.offline_cached;

  async function handleEnroll() {
    setBusy(true);
    setMessage('');
    try {
      const data = await totpEnroll();
      setEnroll(data);
    } catch (e) {
      setMessage(e.response?.data?.detail || e.message || 'Enroll failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirmTotp() {
    setBusy(true);
    setMessage('');
    try {
      await totpConfirm(confirmCode);
      setEnroll(null);
      setConfirmCode('');
      setMessage('Two-factor authentication enabled.');
      await fetchLicenseStatus();
    } catch (e) {
      setMessage(e.response?.data?.detail || e.message || 'Invalid code');
    } finally {
      setBusy(false);
    }
  }

  async function handleDisableTotp() {
    setBusy(true);
    setMessage('');
    try {
      await totpDisable(password, totpCode);
      setPassword('');
      setTotpCode('');
      setMessage('Two-factor authentication disabled.');
    } catch (e) {
      setMessage(e.response?.data?.detail || e.message || 'Could not disable 2FA');
    } finally {
      setBusy(false);
    }
  }

  async function handleRegenCodes() {
    setBusy(true);
    setMessage('');
    try {
      const data = await recoveryRegenerate(password, totpCode || undefined);
      setRecoveryCodes(data.recovery_codes || []);
      setPassword('');
      setTotpCode('');
    } catch (e) {
      setMessage(e.response?.data?.detail || e.message || 'Could not regenerate codes');
    } finally {
      setBusy(false);
    }
  }

  async function handleSignOut() {
    setBusy(true);
    try {
      await logout();
      onSignedOut?.();
      if (window.cimDesktop?.restartBackend) {
        await window.cimDesktop.restartBackend();
        window.location.reload();
      } else {
        window.location.reload();
      }
    } catch (e) {
      setMessage(e.response?.data?.detail || e.message || 'Sign out failed');
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 300000,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 'min(480px, 100%)', maxHeight: '90vh', overflow: 'auto',
          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 8, padding: 20,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: '0 0 8px', fontSize: 16 }}>Account</h2>
        <p style={{ margin: '0 0 16px', fontSize: 12, color: 'var(--text-muted)' }}>
          Signed in as <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>
          {offline ? ' · offline mode (cached session)' : ''}
        </p>
        {licenseStatus?.offline_grace_until && (
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
            Offline grace until {String(licenseStatus.offline_grace_until).slice(0, 19).replace('T', ' ')}
          </p>
        )}

        {!enroll ? (
          <button type="button" disabled={busy} onClick={handleEnroll} style={btnBlockStyle}>
            Enable authenticator (2FA)
          </button>
        ) : (
          <div style={{ marginBottom: 12, fontSize: 12 }}>
            <p style={{ margin: '0 0 10px' }}>Scan this QR code in Google Authenticator (or similar):</p>
            {enroll.otpauth_uri ? (
              <div
                style={{
                  display: 'inline-block',
                  padding: 12,
                  borderRadius: 8,
                  background: '#fff',
                  border: '1px solid var(--border)',
                  marginBottom: 10,
                }}
              >
                <QRCodeSVG value={enroll.otpauth_uri} size={180} level="M" includeMargin={false} />
              </div>
            ) : (
              <p style={{ color: 'var(--text-muted)' }}>QR data unavailable. Use manual key below.</p>
            )}
            {enroll.secret_base32 && (
              <p style={{ margin: '0 0 8px', color: 'var(--text-muted)', fontSize: 11 }}>
                Can&apos;t scan? Enter key manually:{' '}
                <code style={{ wordBreak: 'break-all', color: 'var(--text-primary)' }}>
                  {enroll.secret_base32}
                </code>
              </p>
            )}
            <input
              value={confirmCode}
              onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="6-digit code"
              maxLength={6}
              inputMode="numeric"
              autoComplete="one-time-code"
              style={inputStyle}
            />
            <button type="button" disabled={busy} onClick={handleConfirmTotp} style={btnBlockStyle}>
              Confirm 2FA
            </button>
          </div>
        )}

        <div style={{ marginTop: 16, fontSize: 12 }}>
          <p style={{ color: 'var(--text-muted)', marginBottom: 8 }}>Disable 2FA or regenerate recovery codes (password required)</p>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" style={inputStyle} />
          <input type="text" value={totpCode} onChange={(e) => setTotpCode(e.target.value)} placeholder="TOTP code (if 2FA on)" style={inputStyle} />
          <button type="button" disabled={busy} onClick={handleDisableTotp} style={btnBlockStyle}>Disable 2FA</button>
          <button type="button" disabled={busy} onClick={handleRegenCodes} style={btnBlockStyle}>Regenerate recovery codes</button>
        </div>

        {recoveryCodes && (
          <pre style={{ fontSize: 11, background: 'var(--bg-primary)', padding: 10, borderRadius: 6, marginTop: 12 }}>
            {recoveryCodes.join('\n')}
          </pre>
        )}

        {message && <p style={{ fontSize: 12, marginTop: 12, color: 'var(--text-primary)' }}>{message}</p>}

        <div style={{ display: 'flex', gap: 8, marginTop: 20, justifyContent: 'flex-end' }}>
          <button
            type="button"
            disabled={busy}
            onClick={handleSignOut}
            style={{ ...btnCompactStyle, background: '#f85149', color: '#fff', borderColor: '#f85149' }}
          >
            Sign out
          </button>
          <button type="button" onClick={onClose} style={btnCompactStyle}>Close</button>
        </div>
      </div>
    </div>
  );
}

const btnBlockStyle = {
  display: 'block',
  width: '100%',
  marginTop: 8,
  padding: '8px 12px',
  border: '1px solid var(--border)',
  borderRadius: 6,
  background: 'var(--bg-hover)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
  fontSize: 12,
  textAlign: 'left',
};

const btnCompactStyle = {
  display: 'inline-block',
  width: 'auto',
  marginTop: 0,
  padding: '6px 14px',
  border: '1px solid var(--border)',
  borderRadius: 6,
  background: 'var(--bg-hover)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
  fontSize: 12,
  textAlign: 'center',
  whiteSpace: 'nowrap',
};

const inputStyle = {
  display: 'block',
  width: '100%',
  marginTop: 6,
  padding: '8px 10px',
  borderRadius: 6,
  border: '1px solid var(--border)',
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  fontSize: 12,
};
