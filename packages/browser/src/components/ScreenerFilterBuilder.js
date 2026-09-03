import React, { useState } from 'react';

const sectionLabel = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 8,
};

const inputStyle = {
  backgroundColor: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  padding: '6px 10px',
  color: 'var(--text-primary)',
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
  width: '100%',
  outline: 'none',
};

const SCREENER_SCREEN_RE = /^https?:\/\/(?:www\.)?screener\.in\/screens\/\d+/i;

function validateScreenUrl(raw) {
  const text = String(raw || '').trim();
  if (!text) return 'Paste your saved Screener screen URL';
  if (!SCREENER_SCREEN_RE.test(text)) {
    return 'Use a saved screen link like https://www.screener.in/screens/123456/my-screen/';
  }
  return '';
}

export function buildScreenerFilterLabel(def) {
  const name = String(def?.screen_name || '').trim();
  const url = String(def?.screen_url || '').trim();
  if (name) return `Screener · ${name}`;
  if (url) {
    const parts = url.replace(/\/+$/, '').split('/');
    const slug = parts[parts.length - 1];
    if (slug && !/^\d+$/.test(slug)) {
      return `Screener · ${decodeURIComponent(slug).replace(/-/g, ' ')}`;
    }
  }
  return 'Screener';
}

export default function ScreenerFilterBuilder({ onApply, onCancel, initialValues }) {
  const init = initialValues || {};
  const isEditMode = !!initialValues;

  const [screenUrl, setScreenUrl] = useState(init.screen_url || '');
  const [screenName, setScreenName] = useState(init.screen_name || '');
  const [forceRefresh, setForceRefresh] = useState(!!init.force_refresh);
  const [urlErr, setUrlErr] = useState('');

  function handleApply() {
    const err = validateScreenUrl(screenUrl);
    if (err) {
      setUrlErr(err);
      return;
    }
    onApply({
      filter_type: 'screener',
      screen_url: screenUrl.trim(),
      screen_name: screenName.trim() || null,
      force_refresh: forceRefresh,
    });
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.5)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          width: 480,
          maxWidth: 'calc(100vw - 32px)',
          boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '12px 16px',
            borderBottom: '1px solid var(--border)',
            backgroundColor: 'var(--bg-tertiary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {isEditMode ? 'Edit Screener Filter' : 'Screener Filter'}
          </span>
          <button type="button" onClick={onCancel} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18 }}>×</button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div
            style={{
              fontSize: 11,
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-tertiary)',
              borderRadius: 4,
              padding: '8px 10px',
              border: '1px solid var(--border)',
              lineHeight: 1.45,
            }}
          >
            Open your saved screen on screener.in, copy the address bar URL, and paste it here.
            CiM fetches the matching symbols and you can stack MACD, EMA, and other filters on top.
          </div>

          <div>
            <div style={sectionLabel}>Screen URL</div>
            <input
              value={screenUrl}
              onChange={(e) => { setScreenUrl(e.target.value); setUrlErr(''); }}
              placeholder="https://www.screener.in/screens/…"
              style={{
                ...inputStyle,
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                border: urlErr ? '1px solid var(--accent-red)' : '1px solid var(--border)',
              }}
            />
            {urlErr && (
              <div style={{ fontSize: 11, color: 'var(--accent-red)', marginTop: 4 }}>{urlErr}</div>
            )}
          </div>

          <div>
            <div style={sectionLabel}>Label (optional)</div>
            <input
              value={screenName}
              onChange={(e) => setScreenName(e.target.value)}
              placeholder="e.g. Quality Q"
              style={inputStyle}
            />
          </div>

          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 12,
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              userSelect: 'none',
            }}
          >
            <input
              type="checkbox"
              checked={forceRefresh}
              onChange={(e) => setForceRefresh(e.target.checked)}
            />
            Refresh from Screener now (ignore cache)
          </label>

          <div
            style={{
              fontSize: 12,
              color: 'var(--text-muted)',
              padding: '8px 10px',
              borderRadius: 4,
              backgroundColor: 'var(--bg-tertiary)',
              border: '1px solid var(--border)',
            }}
          >
            Preview: <span style={{ color: 'var(--accent-blue)' }}>{buildScreenerFilterLabel({ screen_url: screenUrl, screen_name: screenName })}</span>
          </div>
        </div>

        <div
          style={{
            padding: '12px 16px',
            borderTop: '1px solid var(--border)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            backgroundColor: 'var(--bg-tertiary)',
          }}
        >
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '6px 14px',
              borderRadius: 5,
              border: '1px solid var(--border)',
              background: 'transparent',
              color: 'var(--text-secondary)',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleApply}
            style={{
              padding: '6px 14px',
              borderRadius: 5,
              border: 'none',
              background: 'var(--accent-blue)',
              color: '#fff',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Apply filter
          </button>
        </div>
      </div>
    </div>
  );
}
