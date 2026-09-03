import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import {
  PnlFormDialog,
  PnlDialogButton,
  pnlFormFieldLabelStyle,
  pnlFormFooterSplitStyle,
  PNL_FORM_DIALOG_WIDTH_WIDE,
  PNL_FORM_GAP,
} from './pnlFormDialogChrome';

const API = '';

const hintStyle = { fontSize: 9, color: 'var(--text-muted)', lineHeight: 1.45, marginTop: 4 };

const previewPanelStyle = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  lineHeight: 1.5,
  padding: '6px 8px',
  background: 'var(--bg-tertiary)',
  borderRadius: 4,
  border: '1px solid var(--border-light)',
};

const TAX_ACCEPT =
  '.csv,.txt,.xlsx,.xls,.xlsm,text/csv,text/tab-separated-values,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

function isExcelName(name) {
  const n = String(name || '').toLowerCase();
  return n.endsWith('.xlsx') || n.endsWith('.xls') || n.endsWith('.xlsm');
}

function arrayBufferToBase64(buf) {
  const bytes = new Uint8Array(buf);
  const chunk = 0x8000;
  let binary = '';
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function fmtInr(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return '—';
  const sign = v > 0 ? '+' : '';
  return `${sign}₹${v.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

function formatTaxPreview(preview) {
  if (!preview) return [];
  const lines = [];
  lines.push(`Parsed closed rows: ${preview.parsed_closed ?? 0}`);
  if (preview.parsed_open) lines.push(`Open rows in file: ${preview.parsed_open}`);
  if (preview.excel_sheet) lines.push(`Excel sheet used: ${preview.excel_sheet}`);
  if (preview.closed_replaced != null) {
    lines.push(`Will remove ${preview.closed_replaced} existing Zerodha closed trade(s)`);
  }
  if (preview.open_replaced != null) {
    lines.push(`Will remove ${preview.open_replaced} existing Zerodha open lot(s)`);
  }
  lines.push(`Will add ${preview.closed_added ?? 0} Tax P&L close(s)`);
  lines.push(`Will rebuild ${preview.open_synced ?? 0} Zerodha open lot(s) from the file`);
  if (preview.realized_total != null) {
    lines.push(`Tax P&L realized total: ${fmtInr(preview.realized_total)}`);
  }
  if (preview.holdings_parsed) {
    lines.push(`Holdings rows: ${preview.holdings_parsed}`);
  }
  if (preview.holdings_reconcile?.reconciled?.length) {
    lines.push(`Holdings sync: ${preview.holdings_reconcile.reconciled.length} symbol(s)`);
  }
  if (preview.symbols?.length) {
    lines.push(`Symbols: ${preview.symbols.join(', ')}`);
  }
  return lines;
}

function hasTaxUpload(tax) {
  if (!tax) return false;
  if (tax.kind === 'excel') return Boolean(tax.base64);
  return Boolean(String(tax.text || '').trim());
}

function detailMessage(detail, fallback) {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0];
    if (typeof first === 'string') return first;
    if (first && typeof first === 'object') {
      return first.message || first.msg || fallback;
    }
  }
  if (detail && typeof detail === 'object') {
    return detail.message || detail.msg || fallback;
  }
  return fallback;
}

export default function PnLImportTaxPnlDialog({ open, onClose, onImported }) {
  const taxRef = useRef(null);
  const holdingsRef = useRef(null);
  const busyRef = useRef(false);
  const previewSeqRef = useRef(0);
  const taxReadSeqRef = useRef(0);
  const holdingsReadSeqRef = useRef(0);

  const [taxName, setTaxName] = useState('');
  const [holdingsName, setHoldingsName] = useState('');
  const [taxUpload, setTaxUpload] = useState(null);
  const [holdingsText, setHoldingsText] = useState('');
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [reconcileHoldings, setReconcileHoldings] = useState(true);
  const [confirmReplace, setConfirmReplace] = useState(false);

  const reset = useCallback(() => {
    setTaxName('');
    setHoldingsName('');
    setTaxUpload(null);
    setHoldingsText('');
    setPreview(null);
    setError('');
    setReconcileHoldings(true);
    setConfirmReplace(false);
    setPreviewBusy(false);
    busyRef.current = false;
    setBusy(false);
    if (taxRef.current) taxRef.current.value = '';
    if (holdingsRef.current) holdingsRef.current.value = '';
  }, []);

  const handleClose = useCallback(() => {
    if (busyRef.current) return;
    reset();
    onClose();
  }, [onClose, reset]);

  const readTaxFile = useCallback((file) => {
    setConfirmReplace(false);
    const seq = ++taxReadSeqRef.current;
    if (!file) {
      setTaxUpload(null);
      setTaxName('');
      return;
    }
    const name = file.name || 'file';
    setTaxName(name);
    setError('');
    if (isExcelName(name)) {
      const reader = new FileReader();
      reader.onload = () => {
        if (seq !== taxReadSeqRef.current) return;
        try {
          const base64 = arrayBufferToBase64(reader.result);
          setTaxUpload({ kind: 'excel', base64, filename: name });
        } catch (err) {
          setError(err?.message || 'Could not encode Excel file');
          setTaxUpload(null);
        }
      };
      reader.onerror = () => {
        if (seq !== taxReadSeqRef.current) return;
        setError('Could not read Excel file');
        setTaxUpload(null);
      };
      reader.readAsArrayBuffer(file);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (seq !== taxReadSeqRef.current) return;
      setTaxUpload({ kind: 'csv', text: String(reader.result || ''), filename: name });
    };
    reader.onerror = () => {
      if (seq !== taxReadSeqRef.current) return;
      setError('Could not read file');
      setTaxUpload(null);
    };
    reader.readAsText(file);
  }, []);

  const readHoldingsFile = useCallback((file) => {
    const seq = ++holdingsReadSeqRef.current;
    if (!file) {
      setHoldingsText('');
      setHoldingsName('');
      return;
    }
    setHoldingsName(file.name || 'file');
    const reader = new FileReader();
    reader.onload = () => {
      if (seq !== holdingsReadSeqRef.current) return;
      setHoldingsText(String(reader.result || ''));
    };
    reader.onerror = () => {
      if (seq !== holdingsReadSeqRef.current) return;
      setError('Could not read holdings file');
      setHoldingsText('');
    };
    reader.readAsText(file);
  }, []);

  const buildPayload = useCallback((tax, hText, flags) => {
    const base = {
      holdings_csv: hText.trim() || undefined,
      confirm_broker_replace: 'zerodha',
      reconcile_holdings: Boolean(hText.trim()) && flags.reconcileHoldings,
    };
    if (tax?.kind === 'excel') {
      return {
        ...base,
        excel_base64: tax.base64,
        filename: tax.filename || 'tax_pnl.xlsx',
      };
    }
    return {
      ...base,
      csv: tax?.text || '',
    };
  }, []);

  const runPreview = useCallback(async (tax, hText, flags) => {
    const seq = ++previewSeqRef.current;
    setError('');
    setPreview(null);
    if (!hasTaxUpload(tax)) {
      setPreviewBusy(false);
      return;
    }
    setPreviewBusy(true);
    try {
      const res = await axios.post(
        `${API}/api/pnl/import/zerodha/tax-pnl/preview`,
        buildPayload(tax, hText, flags),
      );
      if (seq !== previewSeqRef.current) return;
      const data = res.data || {};
      setPreview(data);
      if (!data.ok) {
        const err = data.errors?.[0] || data.parse_errors?.[0];
        setError(err?.message || (typeof err === 'string' ? err : 'Preview failed'));
      }
    } catch (e) {
      if (seq !== previewSeqRef.current) return;
      const detail = e?.response?.data?.detail;
      setError(detailMessage(detail, e.message || 'Preview failed'));
    } finally {
      if (seq === previewSeqRef.current) setPreviewBusy(false);
    }
  }, [buildPayload]);

  useEffect(() => {
    if (!open) return undefined;
    const t = setTimeout(() => {
      runPreview(taxUpload, holdingsText, { reconcileHoldings });
    }, 280);
    return () => clearTimeout(t);
  }, [open, taxUpload, holdingsText, reconcileHoldings, runPreview]);

  const handleApply = useCallback(async () => {
    if (!hasTaxUpload(taxUpload) || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      const res = await axios.post(
        `${API}/api/pnl/import/zerodha/tax-pnl`,
        buildPayload(taxUpload, holdingsText, { reconcileHoldings }),
      );
      const data = res.data || {};
      if (data.status !== 'ok' && data.ok === false) {
        setError(data.errors?.[0]?.message || 'Import failed');
        return;
      }
      onImported?.(data);
      busyRef.current = false;
      setBusy(false);
      reset();
      onClose();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setError(detailMessage(detail, e.message || 'Import failed'));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [
    taxUpload,
    holdingsText,
    reconcileHoldings,
    buildPayload,
    onImported,
    onClose,
    reset,
  ]);

  if (!open) return null;

  const canApply = hasTaxUpload(taxUpload) && preview?.ok && confirmReplace && !busy && !previewBusy;
  const compareRows = (preview?.compare || []).slice(0, 20);
  const parseErrs = preview?.parse_errors || preview?.errors || [];
  const needsHoldingsHint = Boolean(preview && preview.open_replaced > 0 && !preview.ok);

  return createPortal(
    <PnlFormDialog
      title="Replace Zerodha P&L"
      titleId="pnl-import-tax-pnl-title"
      onClose={handleClose}
      width={PNL_FORM_DIALOG_WIDTH_WIDE}
      error={error || undefined}
      footerStyle={pnlFormFooterSplitStyle}
      footer={
        <>
          <div style={{ fontSize: 9, color: 'var(--text-muted)', maxWidth: 280, lineHeight: 1.4 }}>
            Replaces Zerodha only. Paytm, Groww, and Manual records stay unchanged.
          </div>
          <div style={{ display: 'flex', gap: PNL_FORM_GAP, flexShrink: 0 }}>
            <PnlDialogButton onClick={handleClose} disabled={busy}>
              Cancel
            </PnlDialogButton>
            <PnlDialogButton variant="primary" onClick={handleApply} disabled={!canApply}>
              {busy ? 'Replacing…' : 'Replace Zerodha P&L'}
            </PnlDialogButton>
          </div>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: PNL_FORM_GAP }}>
        <div
          style={{
            ...previewPanelStyle,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Broker</span>
          <span style={{ fontWeight: 700, color: 'var(--accent-blue)' }}>Zerodha · locked</span>
        </div>

        <div>
          <div style={pnlFormFieldLabelStyle} id="pnl-tax-file-label">
            Tax P&L / Capital gains (CSV or Excel)
          </div>
          <input
            ref={taxRef}
            id="pnl-tax-file"
            aria-labelledby="pnl-tax-file-label"
            type="file"
            accept={TAX_ACCEPT}
            disabled={busy}
            onChange={(e) => readTaxFile(e.target.files?.[0])}
            style={{ fontSize: 11, width: '100%' }}
          />
          {taxName ? (
            <div style={hintStyle}>
              {taxName}
              {taxUpload?.kind === 'excel' ? ' · Excel (server converts to table)' : ''}
            </div>
          ) : null}
          <div style={hintStyle}>
            Console → Reports → Tax P&L → download capital gains / Tax P&L (.xlsx or .csv).
            Also accepts Console P&L realised exports.
          </div>
        </div>

        <div>
          <div style={pnlFormFieldLabelStyle} id="pnl-holdings-file-label">
            Holdings CSV {needsHoldingsHint ? '(required for open lots)' : '(optional — open qty)'}
          </div>
          <input
            ref={holdingsRef}
            id="pnl-holdings-file"
            aria-labelledby="pnl-holdings-file-label"
            type="file"
            accept=".csv,.txt,text/csv,text/tab-separated-values"
            disabled={busy}
            onChange={(e) => readHoldingsFile(e.target.files?.[0])}
            style={{ fontSize: 11, width: '100%' }}
          />
          {holdingsName ? <div style={hintStyle}>{holdingsName}</div> : null}
          <div style={hintStyle}>
            Required when CiM already has Zerodha open lots and the Tax P&L file has no open section.
            When attached with Sync holdings, this becomes the final Zerodha open snapshot.
          </div>
        </div>

        <label
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            fontSize: 10,
            cursor: holdingsText.trim() && !busy ? 'pointer' : 'not-allowed',
            opacity: holdingsText.trim() ? 1 : 0.55,
          }}
        >
          <input
            type="checkbox"
            checked={reconcileHoldings && Boolean(holdingsText.trim())}
            disabled={!holdingsText.trim() || busy}
            onChange={(e) => setReconcileHoldings(e.target.checked)}
            style={{ marginTop: 2 }}
          />
          <span>
            <strong>Sync holdings</strong> — set open qty/avg from holdings CSV (Zerodha lots only).
          </span>
        </label>

        <div style={{ ...previewPanelStyle, borderColor: 'var(--accent-amber, #b8860b)' }}>
          This is a full broker replacement. All existing Zerodha open lots and closed
          trades will be removed, then rebuilt from this upload. A holdings CSV, when
          supplied, becomes the final Zerodha open-position snapshot.
        </div>

        {previewBusy ? (
          <div style={previewPanelStyle}>Loading preview…</div>
        ) : null}

        {preview ? (
          <div style={previewPanelStyle}>
            {formatTaxPreview(preview).map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        ) : null}

        {compareRows.length ? (
          <div style={previewPanelStyle}>
            <div style={{ fontWeight: 600, marginBottom: 4, color: 'var(--text-primary)' }}>
              CiM vs Tax P&L (Zerodha realized by symbol)
            </div>
            {compareRows.map((r) => (
              <div key={r.symbol}>
                {r.symbol}: CiM {fmtInr(r.cim_realized)} → Tax {fmtInr(r.tax_realized)}
                {r.delta ? ` (Δ ${fmtInr(r.delta)})` : ''}
              </div>
            ))}
            {(preview?.compare?.length || 0) > 20 ? (
              <div style={hintStyle}>…and {(preview.compare.length - 20)} more</div>
            ) : null}
          </div>
        ) : null}

        {parseErrs.length ? (
          <div style={{ ...previewPanelStyle, borderColor: 'var(--accent-amber, #b8860b)' }}>
            {parseErrs.slice(0, 6).map((e, i) => (
              <div key={i}>
                {e.symbol ? `${e.symbol}: ` : ''}
                {e.message || String(e)}
              </div>
            ))}
          </div>
        ) : null}

        <label
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            fontSize: 10,
            cursor: 'pointer',
          }}
        >
          <input
            type="checkbox"
            checked={confirmReplace}
            disabled={busy}
            onChange={(e) => setConfirmReplace(e.target.checked)}
            style={{ marginTop: 2 }}
          />
          <span>
            I confirm this upload is the complete Zerodha source of truth. Replace all
            Zerodha P&amp;L without changing Paytm, Groww, or Manual records.
          </span>
        </label>
      </div>
    </PnlFormDialog>,
    document.body,
  );
}
