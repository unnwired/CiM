import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import PnLDateSelect, { istTodayParts, toCalendarDate } from './PnLDateSelect';
import {
  PnlFormDialog,
  PnlDialogButton,
  pnlFormFieldRowStyle,
  pnlFormInsetBoxStyle,
  pnlFormMonoFieldStyle,
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

function filterIntegerInput(raw) {
  return String(raw ?? '').replace(/\D/g, '');
}

function parsePrice(raw) {
  const s = String(raw ?? '').trim().replace(/,/g, '');
  if (!s) return undefined;
  const n = Number(s);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.round(n * 100) / 100;
}

function parseQty(raw) {
  const s = String(raw ?? '').trim();
  if (!s) return undefined;
  const n = Number(s);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) return undefined;
  return n;
}

function lotSortKey(lot) {
  const ed = String(lot.entry_date || '');
  const created = String(lot.created_at || '');
  if (ed) return `${ed}\0${created}`;
  return `z\0${created}`;
}

function computeFifoBookPreview(lots, qtySold, exitPrice) {
  if (!qtySold || !exitPrice || !Array.isArray(lots)) return null;

  const fifoLots = [...lots]
    .filter((lot) => lot && !lot.is_placeholder)
    .sort((a, b) => lotSortKey(a).localeCompare(lotSortKey(b)));

  let remaining = qtySold;
  let costBasis = 0;
  for (const lot of fifoLots) {
    if (remaining <= 0) break;
    const lotQty = Math.trunc(Number(lot.qty)) || 0;
    const entry = Number(lot.entry_price);
    if (!lotQty || !Number.isFinite(entry) || entry <= 0) continue;
    const take = Math.min(remaining, lotQty);
    costBasis += take * entry;
    remaining -= take;
  }
  if (remaining > 0) return null;

  const saleValue = Math.round(qtySold * exitPrice * 100) / 100;
  const costRounded = Math.round(costBasis * 100) / 100;
  const realizedPl = Math.round((saleValue - costRounded) * 100) / 100;
  return { saleValue, costBasis: costRounded, realizedPl };
}

function fmtRupee(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  return Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const bookPreviewLineStyle = {
  fontSize: 11,
  fontFamily: 'var(--font-mono)',
  lineHeight: 1.4,
};

export default function PnLBookDialog({ bookTarget, onClose, onBooked }) {
  const [exitDraft, setExitDraft] = useState('');
  const [qtyDraft, setQtyDraft] = useState('');
  const [year, setYear] = useState(() => istTodayParts().year);
  const [month, setMonth] = useState(() => istTodayParts().month);
  const [day, setDay] = useState(() => istTodayParts().day);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!bookTarget) return;
    const today = istTodayParts();
    setExitDraft('');
    setQtyDraft('');
    setYear(today.year);
    setMonth(today.month);
    setDay(today.day);
    setError('');
  }, [bookTarget]);

  const maxQty = bookTarget?.totalQty != null ? Math.trunc(Number(bookTarget.totalQty)) : 0;
  const isPlaceholder = bookTarget?.isPlaceholder;
  const bookDisabled = saving || isPlaceholder || maxQty <= 0;

  const preview = useMemo(() => {
    if (!bookTarget) return null;
    const exit = parsePrice(exitDraft);
    const qty = parseQty(qtyDraft);
    if (exit == null || qty == null || qty > maxQty) return null;
    return computeFifoBookPreview(bookTarget.lots, qty, exit);
  }, [bookTarget, exitDraft, qtyDraft, maxQty]);

  if (!bookTarget) return null;

  const submit = async () => {
    const exit = parsePrice(exitDraft);
    const qty = parseQty(qtyDraft);
    const saleDate = toCalendarDate(year, month, day);
    if (exit == null) {
      setError('Exit price required');
      return;
    }
    if (qty == null) {
      setError('Quantity required');
      return;
    }
    if (!saleDate) {
      setError('Valid sale date required');
      return;
    }
    if (qty > maxQty) {
      setError(`Max qty ${maxQty}`);
      return;
    }
    setSaving(true);
    setError('');
    try {
      await axios.post(`${API}/api/pnl/book`, {
        symbol: bookTarget.symbol,
        exit_price: exit,
        qty_sold: qty,
        sale_date: saleDate,
      });
      window.dispatchEvent(new CustomEvent('portfolio-updated'));
      onBooked?.();
      onClose?.();
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Book failed';
      setError(typeof msg === 'string' ? msg : 'Book failed');
    } finally {
      setSaving(false);
    }
  };

  const plColor = preview == null
    ? 'var(--text-muted)'
    : preview.realizedPl >= 0
      ? 'var(--accent-green)'
      : 'var(--accent-red)';

  return (
    <PnlFormDialog
      title={`Book — ${bookTarget.symbol}`}
      subtitle="Oldest lots sold first (FIFO)."
      titleId="pnl-book-title"
      onClose={onClose}
      error={error || null}
      footer={(
        <>
          <PnlDialogButton onClick={onClose} disabled={saving}>Cancel</PnlDialogButton>
          <PnlDialogButton variant="primary" onClick={submit} disabled={bookDisabled}>
            {saving ? 'Booking…' : 'Book'}
          </PnlDialogButton>
        </>
      )}
    >
      <div style={pnlFormFieldRowStyle}>
        <input
          type="text"
          placeholder="Exit price"
          inputMode="decimal"
          autoComplete="off"
          autoFocus
          aria-label="Exit price"
          value={exitDraft}
          onChange={(e) => setExitDraft(filterDecimalInput(e.target.value))}
          style={pnlFormMonoFieldStyle}
        />
        <input
          type="text"
          placeholder="Qty"
          inputMode="numeric"
          autoComplete="off"
          aria-label="Quantity"
          title={`Max ${maxQty}`}
          value={qtyDraft}
          onChange={(e) => setQtyDraft(filterIntegerInput(e.target.value))}
          style={pnlFormMonoFieldStyle}
        />
      </div>
      {preview ? (
        <div style={pnlFormInsetBoxStyle}>
          <div style={{ ...bookPreviewLineStyle, color: 'var(--text-secondary)' }}>
            <span style={{ color: 'var(--text-muted)', fontFamily: 'inherit' }}>Sale value </span>
            ₹{fmtRupee(preview.saleValue)}
          </div>
          <div style={{ ...bookPreviewLineStyle, color: plColor, fontWeight: 600 }}>
            {preview.realizedPl >= 0 ? 'Profit' : 'Loss'}
            {' '}
            {preview.realizedPl >= 0 ? '+' : '−'}
            ₹{fmtRupee(Math.abs(preview.realizedPl))}
          </div>
        </div>
      ) : null}
      <PnLDateSelect
        label="Sale date"
        year={year}
        month={month}
        day={day}
        onYearChange={setYear}
        onMonthChange={setMonth}
        onDayChange={setDay}
      />
    </PnlFormDialog>
  );
}
