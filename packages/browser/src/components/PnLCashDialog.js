import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  PnlFormDialog,
  PnlDialogButton,
  PNL_FORM_DIALOG_WIDTH_WIDE,
  pnlFormFieldRowStyle,
  pnlFormMonoFieldStyle,
  pnlFormFieldLabelStyle,
} from './pnlFormDialogChrome';

const API = '';

function filterDecimalInput(raw) {
  let s = String(raw ?? '').replace(/,/g, '').replace(/[^\d.]/g, '');
  const dot = s.indexOf('.');
  if (dot >= 0) {
    s = `${s.slice(0, dot + 1)}${s.slice(dot + 1).replace(/\./g, '')}`;
  }
  return s;
}

function parseAmount(raw) {
  const s = String(raw ?? '').trim().replace(/,/g, '');
  if (!s) return undefined;
  const n = Number(s);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.round(n * 100) / 100;
}

const TITLES = {
  deposit: 'Bank deposit',
  withdraw: 'Bank withdrawal',
};

const SUBTITLES = {
  deposit: 'Move cash from your bank into available cash for trading.',
  withdraw: 'Move cash from available cash back to your bank.',
};

export default function PnLCashDialog({ open, mode, onClose, onDone }) {
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setAmount('');
    setNote('');
    setError('');
    setBusy(false);
  }, [open, mode]);

  const handleSubmit = async () => {
    const amt = parseAmount(amount);
    if (amt == null) {
      setError('Enter a positive amount');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const path = mode === 'withdraw' ? '/api/pnl/cash/withdraw' : '/api/pnl/cash/deposit';
      const res = await axios.post(`${API}${path}`, {
        amount: amt,
        note: note.trim() || undefined,
      });
      onDone?.(res.data?.available_cash);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  if (!open || !mode) return null;

  return (
    <PnlFormDialog
      title={TITLES[mode] || 'Cash transfer'}
      subtitle={SUBTITLES[mode]}
      onClose={onClose}
      width={PNL_FORM_DIALOG_WIDTH_WIDE}
    >
      <div style={pnlFormFieldRowStyle}>
        <label style={pnlFormFieldLabelStyle} htmlFor="pnl-cash-amount">Amount (₹)</label>
        <input
          id="pnl-cash-amount"
          type="text"
          inputMode="decimal"
          autoFocus
          value={amount}
          onChange={(e) => setAmount(filterDecimalInput(e.target.value))}
          style={pnlFormMonoFieldStyle}
          disabled={busy}
        />
      </div>
      <div style={pnlFormFieldRowStyle}>
        <label style={pnlFormFieldLabelStyle} htmlFor="pnl-cash-note">Note (optional)</label>
        <input
          id="pnl-cash-note"
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          style={pnlFormMonoFieldStyle}
          disabled={busy}
          placeholder="e.g. HDFC transfer"
        />
      </div>
      {error ? (
        <div style={{ fontSize: 10, color: 'var(--accent-red)', lineHeight: 1.35 }}>{error}</div>
      ) : null}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
        <PnlDialogButton variant="ghost" onClick={onClose} disabled={busy}>Cancel</PnlDialogButton>
        <PnlDialogButton onClick={handleSubmit} disabled={busy}>
          {busy ? 'Saving…' : mode === 'withdraw' ? 'Withdraw' : 'Deposit'}
        </PnlDialogButton>
      </div>
    </PnlFormDialog>
  );
}
