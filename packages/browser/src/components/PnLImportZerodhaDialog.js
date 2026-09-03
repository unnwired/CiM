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

function hasActionableImport(text, hText, pText, flags) {
  if (String(text || '').trim()) return true;
  if (String(hText || '').trim() && flags.reconcileHoldings) return true;
  if (String(pText || '').trim() && flags.importTodaysPositions) return true;
  return false;
}

function formatPreviewSummary(preview) {
  if (!preview) return null;
  const lines = [];
  if (preview.tradebook_skipped) {
    lines.push('Tradebook: skipped (holdings / positions only)');
  } else if (preview.date_from && preview.date_to) {
    lines.push(`Dates: ${preview.date_from} → ${preview.date_to}`);
    lines.push(`Parsed: ${preview.parsed_rows} rows`);
  } else if (preview.parsed_rows) {
    lines.push(`Parsed: ${preview.parsed_rows} rows`);
  }
  if (preview.rebuild) {
    lines.push('Mode: Rebuild symbols in file (replay full trade history)');
    const strip = preview.rebuild_strip;
    if (strip) {
      lines.push(
        `Clears ${strip.positions_removed} open lot(s), ${strip.closed_removed} closed trade(s) for file symbols`,
      );
    }
  } else if (preview.skipped_duplicate) {
    lines.push(`Skipping ${preview.skipped_duplicate} already-imported trade(s)`);
  }
  if (preview.holdings_parsed) {
    lines.push(`Holdings rows: ${preview.holdings_parsed}`);
  }
  if (preview.holdings_reconcile?.reconciled?.length) {
    lines.push(`Holdings sync: ${preview.holdings_reconcile.reconciled.length} symbol(s)`);
  }
  if (preview.positions_parsed) {
    lines.push(`Positions rows: ${preview.positions_parsed}`);
  }
  if (preview.positions_buys_applied || preview.positions_sells_applied) {
    lines.push(
      `Today applied: ${preview.positions_buys_applied || 0} buy(s), ${preview.positions_sells_applied || 0} sell(s)`,
    );
  }
  lines.push(`New buys: ${preview.buys_applied} · New sells: ${preview.sells_applied}`);
  if (preview.open_qty_after && Object.keys(preview.open_qty_after).length) {
    const qtyLine = Object.entries(preview.open_qty_after)
      .map(([sym, q]) => `${sym}=${q}`)
      .join(', ');
    lines.push(`Open qty after: ${qtyLine}`);
  }
  if (preview.symbols?.length) {
    lines.push(`Symbols: ${preview.symbols.join(', ')}`);
  }
  if (preview.portfolio_symbols_added) {
    lines.push(`Portfolio symbols added: ${preview.portfolio_symbols_added}`);
  }
  if (preview.manual_lots_removed) {
    lines.push(`Manual lots replaced for import: ${preview.manual_lots_removed}`);
  }
  if (preview.manual_promoted_qty) {
    lines.push(`Manual lots promoted to Zerodha for sells: ${preview.manual_promoted_qty}`);
  }
  if (preview.gap_seed_qty) {
    lines.push(`Gap-seeded Zerodha shares (missing buys): ${preview.gap_seed_qty}`);
  }
  if (preview.lots_consolidated) {
    lines.push(`Lots consolidated after import: ${preview.lots_consolidated}`);
  }
  if (preview.warnings?.length) {
    preview.warnings.slice(0, 8).forEach((w) => {
      const sym = w.symbol ? `${w.symbol}: ` : '';
      lines.push(`Note: ${sym}${w.message || w}`);
    });
    if (preview.warnings.length > 8) {
      lines.push(`…and ${preview.warnings.length - 8} more note(s)`);
    }
  }
  return lines;
}

function formatMismatchLines(mismatches) {
  if (!mismatches?.length) return [];
  return mismatches.map((m) => (
    `${m.symbol}: tradebook ${m.ledger_qty} → holdings ${m.holdings_qty}`
    + (m.holdings_avg_price != null ? ` @ ₹${Number(m.holdings_avg_price).toFixed(2)}` : '')
  ));
}

function formatCorpActionLines(applied) {
  if (!applied?.length) return [];
  return applied.map((a) => {
    if (a.dry_run) {
      return `${a.symbol}: ${a.action_type || 'corp action'} (${a.record_date || 'pending'})`;
    }
    if (a.skipped) return `${a.symbol}: skipped (${a.reason || 'unchanged'})`;
    if (a.bonus_shares_added) {
      return `${a.symbol}: bonus +${a.bonus_shares_added} shares → open ${a.open_qty}`;
    }
    if (a.open_qty != null) {
      return `${a.symbol}: corp action applied → open ${a.open_qty}`;
    }
    return `${a.symbol}: corp action applied`;
  });
}

function formatPositionLines(preview) {
  const lines = [];
  (preview?.positions_today || []).forEach((p) => {
    const side = p.side === 'sell' ? 'sell' : 'buy';
    const pnl = p.broker_pnl != null ? ` · P&L ${p.broker_pnl}` : '';
    lines.push(`Today: ${p.symbol} ${side} ${p.qty} @ ${p.avg}${pnl}`);
  });
  if (preview?.positions_to_apply?.length) {
    lines.push(`To apply: ${preview.positions_to_apply.length} row(s)`);
  }
  if (preview?.positions_skipped?.length) {
    lines.push(`Skipped: ${preview.positions_skipped.length} row(s) (already booked or insufficient qty)`);
  }
  return lines;
}

const previewPanelStyle = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  lineHeight: 1.5,
  padding: '6px 8px',
  background: 'var(--bg-tertiary)',
  borderRadius: 4,
  border: '1px solid var(--border-light)',
};

const mismatchPanelStyle = {
  ...previewPanelStyle,
  borderColor: 'var(--accent-amber, #b8860b)',
  color: 'var(--text-primary)',
};


export default function PnLImportZerodhaDialog({ open, onClose, onImported }) {
  const tradebookRef = useRef(null);
  const holdingsRef = useRef(null);
  const positionsRef = useRef(null);

  const [tradebookName, setTradebookName] = useState('');
  const [holdingsName, setHoldingsName] = useState('');
  const [positionsName, setPositionsName] = useState('');
  const [csvText, setCsvText] = useState('');
  const [holdingsText, setHoldingsText] = useState('');
  const [positionsText, setPositionsText] = useState('');
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [repairBusy, setRepairBusy] = useState(false);
  const [repairMsg, setRepairMsg] = useState('');
  const [rebuild, setRebuild] = useState(false);
  const [reconcileHoldings, setReconcileHoldings] = useState(true);
  const [importTodaysPositions, setImportTodaysPositions] = useState(false);
  const [applyCorpActions, setApplyCorpActions] = useState(true);

  const reset = useCallback(() => {
    setTradebookName('');
    setHoldingsName('');
    setPositionsName('');
    setCsvText('');
    setHoldingsText('');
    setPositionsText('');
    setPreview(null);
    setError('');
    setRepairMsg('');
    setReconcileHoldings(true);
    setImportTodaysPositions(false);
    setApplyCorpActions(true);
    if (tradebookRef.current) tradebookRef.current.value = '';
    if (holdingsRef.current) holdingsRef.current.value = '';
    if (positionsRef.current) positionsRef.current.value = '';
  }, []);

  const handleClose = useCallback(() => {
    reset();
    onClose();
  }, [onClose, reset]);

  const buildPayload = useCallback((text, hText, pText, flags) => ({
    csv: text,
    rebuild: flags.rebuild,
    holdings_csv: hText.trim() || undefined,
    positions_csv: pText.trim() || undefined,
    reconcile_holdings: flags.reconcileHoldings,
    import_todays_positions: flags.importTodaysPositions,
    apply_corp_actions: flags.applyCorpActions,
    validate_positions_pnl: true,
  }), []);

  const runPreview = useCallback(async (text, hText, pText, flags) => {
    setError('');
    setPreview(null);
    try {
      const res = await axios.post(
        `${API}/api/pnl/import/zerodha/preview`,
        buildPayload(text, hText, pText, flags),
      );
      const data = res.data || {};
      if (!data.ok) {
        const err = data.errors?.[0] || data.parse_errors?.[0];
        setError(err?.message || 'Preview failed — check CSV format and open quantities.');
      }
      setPreview(data);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (Array.isArray(detail) && detail[0]?.message) {
        setError(detail[0].message);
      } else if (typeof detail === 'string') {
        setError(detail);
      } else {
        setError('Preview failed');
      }
      setPreview(null);
    }
  }, [buildPayload]);

  useEffect(() => {
    const flags = {
      rebuild,
      reconcileHoldings,
      importTodaysPositions,
      applyCorpActions,
    };
    if (hasActionableImport(csvText, holdingsText, positionsText, flags)) {
      runPreview(csvText, holdingsText, positionsText, flags);
    } else {
      setPreview(null);
    }
  }, [
    csvText,
    holdingsText,
    positionsText,
    rebuild,
    reconcileHoldings,
    importTodaysPositions,
    applyCorpActions,
    runPreview,
  ]);

  const readFile = useCallback((file, setter, nameSetter) => {
    if (!file) return;
    nameSetter(file.name);
    const reader = new FileReader();
    reader.onload = () => setter(String(reader.result || ''));
    reader.readAsText(file);
  }, []);

  const onPositionsFile = useCallback((e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPositionsName(file.name);
    setImportTodaysPositions(true);
    readFile(file, setPositionsText, setPositionsName);
  }, [readFile]);

  const onHoldingsFile = useCallback((e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setReconcileHoldings(true);
    readFile(file, setHoldingsText, setHoldingsName);
  }, [readFile]);

  const handleImport = useCallback(async () => {
    const flags = {
      rebuild,
      reconcileHoldings,
      importTodaysPositions,
      applyCorpActions,
    };
    if (!hasActionableImport(csvText, holdingsText, positionsText, flags)) {
      setError(
        'Attach a tradebook CSV, holdings (with sync enabled), or positions (with apply enabled).',
      );
      return;
    }
    if (preview && !preview.ok) {
      setError('Fix preview errors before importing');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await axios.post(
        `${API}/api/pnl/import/zerodha`,
        buildPayload(csvText, holdingsText, positionsText, {
          rebuild,
          reconcileHoldings,
          importTodaysPositions,
          applyCorpActions,
        }),
      );
      onImported?.();
      handleClose();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (Array.isArray(detail) && detail[0]?.message) {
        setError(`${detail[0].message} (row ${detail[0].row ?? '?'})`);
      } else if (typeof detail === 'string') {
        setError(detail);
      } else {
        setError('Import failed');
      }
    } finally {
      setBusy(false);
    }
  }, [
    csvText,
    holdingsText,
    positionsText,
    preview,
    onImported,
    handleClose,
    rebuild,
    reconcileHoldings,
    importTodaysPositions,
    applyCorpActions,
    buildPayload,
  ]);

  const handleConsolidateLots = useCallback(async () => {
    setRepairBusy(true);
    setError('');
    setRepairMsg('');
    try {
      const res = await axios.post(`${API}/api/pnl/repair/consolidate-lots`, {});
      const n = res.data?.lots_consolidated ?? 0;
      onImported?.();
      setRepairMsg(n > 0 ? `Merged ${n} duplicate open lot(s).` : 'No duplicate lots to merge.');
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not consolidate lots');
    } finally {
      setRepairBusy(false);
    }
  }, [onImported]);

  if (!open) return null;

  const previewLines = formatPreviewSummary(preview);
  const mismatchLines = formatMismatchLines(preview?.holdings_mismatches);
  const corpLines = formatCorpActionLines(preview?.corp_actions_applied);
  const positionLines = formatPositionLines(preview);
  const sameDayHints = preview?.same_day_sell_likely || [];
  const hasTradebook = Boolean(csvText.trim());
  const hasHoldings = Boolean(holdingsText.trim());
  const hasPositions = Boolean(positionsText.trim());
  const importFlags = { reconcileHoldings, importTodaysPositions };
  const canImport = hasActionableImport(csvText, holdingsText, positionsText, {
    ...importFlags,
    rebuild,
    applyCorpActions,
  }) && preview?.ok && !busy && !repairBusy;

  const footerBusy = busy || repairBusy;

  return createPortal(
    <PnlFormDialog
      title="Import Zerodha CSV"
      titleId="pnl-import-zerodha-title"
      onClose={handleClose}
      width={PNL_FORM_DIALOG_WIDTH_WIDE}
      error={error || undefined}
      footerStyle={pnlFormFooterSplitStyle}
      footer={
        <>
          <PnlDialogButton
            onClick={handleConsolidateLots}
            disabled={footerBusy}
            title="Merge open lots with the same symbol, entry date, and price"
          >
            {repairBusy ? 'Fixing…' : 'Fix lots'}
          </PnlDialogButton>
          <div style={{ display: 'flex', gap: PNL_FORM_GAP, flexShrink: 0 }}>
            <PnlDialogButton onClick={handleClose} disabled={footerBusy}>
              Cancel
            </PnlDialogButton>
            <PnlDialogButton variant="primary" onClick={handleImport} disabled={!canImport}>
              {busy ? 'Importing…' : rebuild ? 'Rebuild' : 'Import'}
            </PnlDialogButton>
          </div>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: PNL_FORM_GAP }}>
        <div>
          <div style={pnlFormFieldLabelStyle}>
            Tradebook CSV (optional — full history through yesterday)
          </div>
          <input
            ref={tradebookRef}
            type="file"
            accept=".csv,.txt,text/csv,text/tab-separated-values"
            onChange={(e) => readFile(e.target.files?.[0], setCsvText, setTradebookName)}
            style={{ fontSize: 11, width: '100%' }}
          />
          {tradebookName ? <div style={hintStyle}>{tradebookName}</div> : null}
          <div style={hintStyle}>
            Skip if you only need holdings sync or today&apos;s positions below.
          </div>
        </div>

        <div>
          <div style={pnlFormFieldLabelStyle}>Holdings CSV (optional — current open qty + avg)</div>
          <input
            ref={holdingsRef}
            type="file"
            accept=".csv,.txt,text/csv,text/tab-separated-values"
            onChange={onHoldingsFile}
            style={{ fontSize: 11, width: '100%' }}
          />
          {holdingsName ? <div style={hintStyle}>{holdingsName}</div> : null}
          <div style={hintStyle}>
            Fixes bonus/split drift (e.g. TRENT qty). Export from Console → Holdings.
          </div>
        </div>

        <div>
          <div style={pnlFormFieldLabelStyle}>Positions CSV (optional — today&apos;s session)</div>
          <input
            ref={positionsRef}
            type="file"
            accept=".csv,.txt,text/csv,text/tab-separated-values"
            onChange={onPositionsFile}
            style={{ fontSize: 11, width: '100%' }}
          />
          {positionsName ? <div style={hintStyle}>{positionsName}</div> : null}
          <div style={hintStyle}>
            Same-day sells missing from tradebook until tomorrow. Export Kite Positions tab today before import.
          </div>
        </div>

        <label
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            fontSize: 10,
            cursor: hasTradebook ? 'pointer' : 'not-allowed',
            opacity: hasTradebook ? 1 : 0.55,
          }}
        >
          <input
            type="checkbox"
            checked={rebuild && hasTradebook}
            disabled={!hasTradebook}
            onChange={(e) => setRebuild(e.target.checked)}
            style={{ marginTop: 2 }}
          />
          <span>
            <strong>Rebuild symbols in file</strong> — wipe and replay open + closed history for every symbol in
            the tradebook. Use full export to fix a bad prior import.
          </span>
        </label>

        <label
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            fontSize: 10,
            cursor: hasHoldings ? 'pointer' : 'not-allowed',
            opacity: hasHoldings ? 1 : 0.55,
          }}
        >
          <input
            type="checkbox"
            checked={reconcileHoldings && hasHoldings}
            disabled={!hasHoldings}
            onChange={(e) => setReconcileHoldings(e.target.checked)}
            style={{ marginTop: 2 }}
          />
          <span>
            <strong>Sync open to holdings</strong> — reconcile open qty and average entry from holdings file.
          </span>
        </label>

        <label
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            fontSize: 10,
            cursor: hasPositions ? 'pointer' : 'not-allowed',
            opacity: hasPositions ? 1 : 0.55,
          }}
        >
          <input
            type="checkbox"
            checked={importTodaysPositions && hasPositions}
            disabled={!hasPositions}
            onChange={(e) => setImportTodaysPositions(e.target.checked)}
            style={{ marginTop: 2 }}
          />
          <span>
            <strong>Apply today&apos;s positions</strong> — book today&apos;s buys/sells via FIFO (e.g. PARAS sell).
          </span>
        </label>

        <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 10, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={applyCorpActions}
            onChange={(e) => setApplyCorpActions(e.target.checked)}
            style={{ marginTop: 2 }}
          />
          <span>
            <strong>Apply corp actions</strong> — bonus/split from registry (e.g. TRENT 1:2) before holdings sync.
          </span>
        </label>

        {previewLines ? (
          <div style={previewPanelStyle}>
            {previewLines.map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        ) : null}

        {mismatchLines.length ? (
          <div style={mismatchPanelStyle}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Holdings mismatches</div>
            {mismatchLines.map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        ) : null}

        {corpLines.length ? (
          <div style={previewPanelStyle}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Corp actions</div>
            {corpLines.map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        ) : null}

        {positionLines.length ? (
          <div style={previewPanelStyle}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Today&apos;s positions</div>
            {positionLines.map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        ) : null}

        {sameDayHints.length ? (
          <div style={mismatchPanelStyle}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Same-day sell likely</div>
            {sameDayHints.map((h) => (
              <div key={h.symbol}>
                {h.symbol}: ledger {h.ledger_qty} &gt; holdings {h.holdings_qty} — attach Positions CSV?
              </div>
            ))}
          </div>
        ) : null}

        {repairMsg ? (
          <div style={{ fontSize: 10, color: 'var(--accent-green)' }}>{repairMsg}</div>
        ) : null}
      </div>
    </PnlFormDialog>,
    document.body,
  );
}
