import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import {
  PnlFormDialog,
  PnlDialogButton,
  pnlFormFieldLabelStyle,
  PNL_FORM_DIALOG_WIDTH_WIDE,
  PNL_FORM_GAP,
} from './pnlFormDialogChrome';

const API = '';

const previewPanelStyle = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  lineHeight: 1.5,
  padding: '6px 8px',
  background: 'var(--bg-tertiary)',
  borderRadius: 4,
  border: '1px solid var(--border-light)',
};

export default function PnLSyncHoldingsDialog({ open, onClose, onSynced }) {
  const fileRef = useRef(null);
  const [fileName, setFileName] = useState('');
  const [holdingsText, setHoldingsText] = useState('');
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const reset = useCallback(() => {
    setFileName('');
    setHoldingsText('');
    setPreview(null);
    setError('');
    if (fileRef.current) fileRef.current.value = '';
  }, []);

  const handleClose = useCallback(() => {
    reset();
    onClose();
  }, [onClose, reset]);

  const runPreview = useCallback(async (text) => {
    setError('');
    setPreview(null);
    try {
      const res = await axios.post(`${API}/api/pnl/import/zerodha/holdings/preview`, {
        holdings_csv: text,
      });
      setPreview(res.data || {});
    } catch (e) {
      setError(e?.response?.data?.detail || 'Preview failed');
    }
  }, []);

  useEffect(() => {
    if (holdingsText.trim()) runPreview(holdingsText);
  }, [holdingsText, runPreview]);

  const onFileChange = useCallback((e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = () => setHoldingsText(String(reader.result || ''));
    reader.readAsText(file);
  }, []);

  const handleSync = useCallback(async () => {
    if (!holdingsText.trim()) {
      setError('Choose a holdings CSV first');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await axios.post(`${API}/api/pnl/import/zerodha/holdings`, { holdings_csv: holdingsText });
      onSynced?.();
      handleClose();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Sync failed');
    } finally {
      setBusy(false);
    }
  }, [holdingsText, onSynced, handleClose]);

  if (!open) return null;

  const mismatches = preview?.holdings_mismatches || [];
  const reconciled = preview?.holdings_reconcile?.reconciled || [];
  const canSync = holdingsText.trim() && preview?.ok !== false && !busy;

  return createPortal(
    <PnlFormDialog
      title="Sync holdings"
      titleId="pnl-sync-holdings-title"
      onClose={handleClose}
      width={PNL_FORM_DIALOG_WIDTH_WIDE}
      error={error || undefined}
      footer={
        <>
          <PnlDialogButton onClick={handleClose} disabled={busy}>
            Cancel
          </PnlDialogButton>
          <PnlDialogButton variant="primary" onClick={handleSync} disabled={!canSync}>
            {busy ? 'Syncing…' : 'Sync open lots'}
          </PnlDialogButton>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: PNL_FORM_GAP }}>
        <div>
          <div style={pnlFormFieldLabelStyle}>Holdings CSV (Kite / Console export)</div>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.txt,text/csv,text/tab-separated-values"
            onChange={onFileChange}
            style={{ fontSize: 11, width: '100%' }}
          />
          {fileName ? (
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>{fileName}</div>
          ) : null}
        </div>
        <div style={{ fontSize: 9, color: 'var(--text-muted)', lineHeight: 1.45 }}>
          Updates open qty and average entry only — does not re-import tradebook or change closed trades.
        </div>
        {mismatches.length ? (
          <div style={previewPanelStyle}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Mismatches ({mismatches.length})</div>
            {mismatches.map((m) => (
              <div key={m.symbol}>
                {m.symbol}: {m.ledger_qty} → {m.holdings_qty}
                {m.holdings_avg_price != null ? ` @ ₹${Number(m.holdings_avg_price).toFixed(2)}` : ''}
              </div>
            ))}
          </div>
        ) : preview && holdingsText.trim() ? (
          <div style={previewPanelStyle}>No mismatches — ledger already matches holdings.</div>
        ) : null}
        {reconciled.length ? (
          <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
            Will reconcile: {reconciled.map((r) => r.symbol).join(', ')}
          </div>
        ) : null}
      </div>
    </PnlFormDialog>,
    document.body,
  );
}
