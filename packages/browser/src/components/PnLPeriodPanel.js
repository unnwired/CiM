import React, { useCallback, useMemo, useState } from 'react';
import axios from 'axios';
import { istTodayParts } from './PnLDateSelect';
import PnLPeriodRangeSelect from './PnLPeriodRangeSelect';
import StockListColumnHeader from './StockListColumnHeader';
import { useStockListColumnWidths } from '../hooks/useStockListColumnWidths';
import { useSyncedHeaderScroll } from '../hooks/useSyncedHeaderScroll';
import { columnWidthKey } from '../hooks/stockListColumnStorage';
import {
  STOCK_LIST_ROW_HEIGHT,
  stockListCellPad,
  stockListGridCellStyle,
  stockListGridTrackStyle,
  stockListHeaderStripStyle,
} from './stockTableChrome';
import { formatPnLAmount } from '../utils/formatPnLAmount';
import { formatPlPct, plPctColor } from '../utils/portfolioEntry';
import {
  PERIOD_DAY_ALL,
  PERIOD_MONTH_ALL,
  buildPnlPeriodReport,
  clampEndTripleForward,
  exportPeriodReportCsv,
  formatPeriodShowing,
} from '../utils/buildPnlPeriodReport';
import { PNL_FORM_GAP, PnlToolbarButton, pnlFormMonoFieldStyle } from './pnlFormDialogChrome';
import PnLImportZerodhaDialog from './PnLImportZerodhaDialog';
import PnLImportTaxPnlDialog from './PnLImportTaxPnlDialog';
import PnLSyncHoldingsDialog from './PnLSyncHoldingsDialog';
import PnLCashDialog from './PnLCashDialog';

const API = '';

const PNL_PERIOD_DATE_KEY = 'cim.pnl.periodDate.v2';
const PNL_PERIOD_DATE_KEY_V1 = 'cim.pnl.periodDate.v1';

const PNL_PERIOD_COLS = [
  { key: 'symbol', widthKey: 'pnl_period_symbol', label: 'Symbol', width: 72, sortable: true },
  { key: 'qty_bought', widthKey: 'pnl_period_bt', label: 'Bt', width: 36, sortable: true },
  { key: 'qty_sold', widthKey: 'pnl_period_sl', label: 'Sl', width: 36, sortable: true },
  { key: 'invested_period', widthKey: 'pnl_period_inv', label: 'Inv', width: 64, sortable: true },
  { key: 'realized_pl', widthKey: 'pnl_period_rpl', label: 'Real P/L', width: 72, sortable: true },
  { key: 'realized_pl_pct', widthKey: 'pnl_period_rpct', label: 'Real%', width: 52, sortable: true },
  { key: 'unrealized_pl', widthKey: 'pnl_period_upl', label: 'Unr P/L', width: 72, sortable: true },
  { key: 'unrealized_pl_pct', widthKey: 'pnl_period_upct', label: 'Unr%', width: 52, sortable: true },
  { key: 'open_qty', widthKey: 'pnl_period_oq', label: 'Open', width: 44, sortable: true },
];

function parseStoredMonth(v) {
  if (v === PERIOD_MONTH_ALL || v === 0 || v === '0') return PERIOD_MONTH_ALL;
  const n = Number(v);
  return Number.isFinite(n) && n >= 1 && n <= 12 ? n : PERIOD_MONTH_ALL;
}

function parseStoredDay(v) {
  if (v === PERIOD_DAY_ALL || v === 0 || v === '0') return PERIOD_DAY_ALL;
  const n = Number(v);
  return Number.isFinite(n) && n >= 1 ? n : PERIOD_DAY_ALL;
}

function copyTriple(t) {
  return { year: t.year, month: t.month, day: t.day };
}

function readStoredPeriodRange() {
  const today = istTodayParts();
  const fallbackStart = {
    year: today.year,
    month: today.month,
    day: PERIOD_DAY_ALL,
  };
  const parsePayload = (p) => {
    const start = {
      year: Number(p.sy ?? p.year) || today.year,
      month: parseStoredMonth(p.sm ?? p.month),
      day: parseStoredDay(p.sd ?? p.day),
    };
    const end = {
      year: Number(p.ey ?? p.year ?? start.year) || start.year,
      month: parseStoredMonth(p.em ?? p.month ?? start.month),
      day: parseStoredDay(p.ed ?? p.day ?? start.day),
    };
    const endLinked = p.endLinked !== false;
    return {
      start,
      end: endLinked ? copyTriple(start) : clampEndTripleForward(start, end),
      endLinked,
    };
  };
  try {
    const raw = window.localStorage.getItem(PNL_PERIOD_DATE_KEY);
    if (raw) return parsePayload(JSON.parse(raw));
  } catch { /* ignore */ }
  try {
    const rawV1 = window.localStorage.getItem(PNL_PERIOD_DATE_KEY_V1);
    if (rawV1) return parsePayload(JSON.parse(rawV1));
  } catch { /* ignore */ }
  return { start: fallbackStart, end: copyTriple(fallbackStart), endLinked: true };
}

function writeStoredPeriodRange(start, end, endLinked) {
  try {
    window.localStorage.setItem(PNL_PERIOD_DATE_KEY, JSON.stringify({
      sy: start.year,
      sm: start.month,
      sd: start.day,
      ey: end.year,
      em: end.month,
      ed: end.day,
      endLinked,
    }));
  } catch { /* ignore */ }
}

function sortPeriodRows(rows, sortBy, sortDir) {
  const list = [...rows];
  const dir = sortDir === 'asc' ? 1 : -1;
  list.sort((a, b) => {
    const av = a[sortBy];
    const bv = b[sortBy];
    if (sortBy === 'symbol') return dir * String(av || '').localeCompare(String(bv || ''));
    const an = Number(av);
    const bn = Number(bv);
    if (Number.isFinite(an) && Number.isFinite(bn)) return dir * (an - bn);
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return dir * String(av).localeCompare(String(bv));
  });
  return list;
}

function cellMonoStyle(color) {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    color: color || 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  };
}

const summaryRowStyle = {
  display: 'flex',
  alignItems: 'baseline',
  gap: 6,
  fontSize: 11,
  lineHeight: 1.4,
  minWidth: 0,
};

const summaryLabelStyle = {
  color: 'var(--text-secondary)',
  flexShrink: 0,
};

const summaryLeaderStyle = {
  flex: '1 1 0',
  minWidth: 6,
  alignSelf: 'flex-end',
  marginBottom: 3,
  borderBottom: '1px dotted var(--border)',
  opacity: 0.85,
};

function SummaryLine({ label, amount, pct }) {
  const amtColor = plPctColor(amount);
  const pctColor = pct != null ? plPctColor(pct) : 'var(--text-muted)';
  return (
    <div style={summaryRowStyle}>
      <span style={summaryLabelStyle}>{label}</span>
      <span style={summaryLeaderStyle} aria-hidden />
      <span style={{ ...cellMonoStyle(amtColor), fontWeight: 600, flexShrink: 0 }}>
        {formatPnLAmount(amount)}
      </span>
      <span style={{ ...cellMonoStyle(pctColor), width: 52, flexShrink: 0, textAlign: 'right' }}>
        {pct != null ? formatPlPct(pct) : '—'}
      </span>
    </div>
  );
}

function SummaryNeutral({ label, amount }) {
  return (
    <div style={summaryRowStyle}>
      <span style={summaryLabelStyle}>{label}</span>
      <span style={summaryLeaderStyle} aria-hidden />
      <span style={{ ...cellMonoStyle('var(--text-primary)'), flexShrink: 0 }}>
        {formatPnLAmount(amount)}
      </span>
    </div>
  );
}

function filterDecimalInput(raw) {
  let s = String(raw ?? '').replace(/,/g, '').replace(/[^\d.]/g, '');
  const dot = s.indexOf('.');
  if (dot >= 0) {
    s = `${s.slice(0, dot + 1)}${s.slice(dot + 1).replace(/\./g, '')}`;
  }
  return s;
}

function SummaryCashRow({ amount, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const startEdit = useCallback(() => {
    const n = Number(amount);
    setDraft(Number.isFinite(n) ? String(n) : '0');
    setEditing(true);
  }, [amount]);

  const cancelEdit = useCallback(() => {
    setEditing(false);
    setDraft('');
  }, []);

  const commitEdit = useCallback(async () => {
    const s = String(draft ?? '').trim().replace(/,/g, '');
    if (!s) {
      cancelEdit();
      return;
    }
    const n = Number(s);
    if (!Number.isFinite(n) || n < 0) {
      cancelEdit();
      return;
    }
    const rounded = Math.round(n * 100) / 100;
    const current = Math.round((Number(amount) || 0) * 100) / 100;
    if (rounded === current) {
      cancelEdit();
      return;
    }
    setBusy(true);
    try {
      const res = await axios.patch(`${API}/api/pnl/cash`, {
        available_cash: rounded,
        note: 'manual balance',
      });
      onSaved?.(res.data?.available_cash ?? rounded);
    } catch {
      /* keep prior value */
    } finally {
      setBusy(false);
      setEditing(false);
    }
  }, [amount, cancelEdit, draft, onSaved]);

  if (editing) {
    return (
      <div style={summaryRowStyle}>
        <span style={summaryLabelStyle}>Available cash</span>
        <span style={summaryLeaderStyle} aria-hidden />
        <input
          type="text"
          inputMode="decimal"
          autoFocus
          value={draft}
          disabled={busy}
          onChange={(e) => setDraft(filterDecimalInput(e.target.value))}
          onBlur={() => { if (!busy) commitEdit(); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              commitEdit();
            } else if (e.key === 'Escape') {
              e.preventDefault();
              cancelEdit();
            }
          }}
          style={{
            ...pnlFormMonoFieldStyle,
            width: 96,
            flexShrink: 0,
            fontSize: 11,
            padding: '2px 6px',
          }}
        />
      </div>
    );
  }

  return (
    <div style={summaryRowStyle}>
      <span style={summaryLabelStyle}>Available cash</span>
      <span style={summaryLeaderStyle} aria-hidden />
      <button
        type="button"
        onClick={startEdit}
        title="Click to set balance manually"
        style={{
          ...cellMonoStyle('var(--text-primary)'),
          flexShrink: 0,
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          textDecoration: 'underline dotted',
          textUnderlineOffset: 2,
        }}
      >
        {formatPnLAmount(amount)}
      </button>
    </div>
  );
}

function renderPeriodCell(key, row) {
  switch (key) {
    case 'symbol':
      return row.symbol;
    case 'qty_bought':
      return row.qty_bought > 0 ? row.qty_bought : '—';
    case 'qty_sold':
      return row.qty_sold > 0 ? row.qty_sold : '—';
    case 'invested_period':
      return row.invested_period > 0 ? formatPnLAmount(row.invested_period) : '—';
    case 'realized_pl':
      return row.qty_sold > 0 ? formatPnLAmount(row.realized_pl) : '—';
    case 'realized_pl_pct':
      return row.qty_sold > 0 && row.realized_pl_pct != null
        ? formatPlPct(row.realized_pl_pct)
        : '—';
    case 'unrealized_pl':
      return row.open_qty > 0 ? formatPnLAmount(row.unrealized_pl) : '—';
    case 'unrealized_pl_pct':
      return row.open_qty > 0 && row.unrealized_pl_pct != null
        ? formatPlPct(row.unrealized_pl_pct)
        : '—';
    case 'open_qty':
      return row.open_qty > 0 ? row.open_qty : '—';
    default:
      return '—';
  }
}

function periodCellColor(key, row) {
  if (key === 'realized_pl' || key === 'realized_pl_pct') {
    return row.qty_sold > 0 ? plPctColor(key === 'realized_pl_pct' ? row.realized_pl_pct : row.realized_pl) : undefined;
  }
  if (key === 'unrealized_pl' || key === 'unrealized_pl_pct') {
    return row.open_qty > 0 ? plPctColor(key === 'unrealized_pl_pct' ? row.unrealized_pl_pct : row.unrealized_pl) : undefined;
  }
  return undefined;
}

export default function PnLPeriodPanel({
  openRows,
  closedTrades,
  availableCash = 0,
  onImported,
  onCashChanged,
}) {
  const stored = useMemo(() => readStoredPeriodRange(), []);
  const [startYear, setStartYear] = useState(stored.start.year);
  const [startMonth, setStartMonth] = useState(stored.start.month);
  const [startDay, setStartDay] = useState(stored.start.day);
  const [endYear, setEndYear] = useState(stored.end.year);
  const [endMonth, setEndMonth] = useState(stored.end.month);
  const [endDay, setEndDay] = useState(stored.end.day);
  const [endLinked, setEndLinked] = useState(stored.endLinked);
  const [sortBy, setSortBy] = useState('symbol');
  const [sortDir, setSortDir] = useState('asc');
  const [importOpen, setImportOpen] = useState(false);
  const [taxPnlOpen, setTaxPnlOpen] = useState(false);
  const [syncOpen, setSyncOpen] = useState(false);
  const [cashDialog, setCashDialog] = useState(null);

  const handleCashDone = useCallback((bal) => {
    onCashChanged?.(bal);
    onImported?.();
  }, [onCashChanged, onImported]);

  const start = useMemo(
    () => ({ year: startYear, month: startMonth, day: startDay }),
    [startYear, startMonth, startDay],
  );
  const end = useMemo(
    () => ({ year: endYear, month: endMonth, day: endDay }),
    [endYear, endMonth, endDay],
  );

  const persistRange = useCallback((nextStart, nextEnd, linked) => {
    setEndLinked(linked);
    writeStoredPeriodRange(nextStart, nextEnd, linked);
  }, []);

  const applyStart = useCallback((patch) => {
    const nextStart = { ...start, ...patch };
    if (patch.month === PERIOD_MONTH_ALL) nextStart.day = PERIOD_DAY_ALL;
    const linked = endLinked;
    const nextEnd = linked
      ? copyTriple(nextStart)
      : clampEndTripleForward(nextStart, end);
    setStartYear(nextStart.year);
    setStartMonth(nextStart.month);
    setStartDay(nextStart.day);
    setEndYear(nextEnd.year);
    setEndMonth(nextEnd.month);
    setEndDay(nextEnd.day);
    persistRange(nextStart, nextEnd, linked);
  }, [start, end, endLinked, persistRange]);

  const applyEnd = useCallback((patch) => {
    let nextEnd = { ...end, ...patch };
    if (patch.month === PERIOD_MONTH_ALL) nextEnd.day = PERIOD_DAY_ALL;
    nextEnd = clampEndTripleForward(start, nextEnd);
    setEndYear(nextEnd.year);
    setEndMonth(nextEnd.month);
    setEndDay(nextEnd.day);
    persistRange(start, nextEnd, false);
  }, [start, end, persistRange]);

  const onStartYearChange = useCallback((y) => applyStart({ year: y }), [applyStart]);
  const onStartMonthChange = useCallback((m) => applyStart({ month: m }), [applyStart]);
  const onStartDayChange = useCallback((d) => applyStart({ day: d }), [applyStart]);
  const onEndYearChange = useCallback((y) => applyEnd({ year: y }), [applyEnd]);
  const onEndMonthChange = useCallback((m) => applyEnd({ month: m }), [applyEnd]);
  const onEndDayChange = useCallback((d) => applyEnd({ day: d }), [applyEnd]);

  const report = useMemo(
    () => buildPnlPeriodReport({ openRows, closedTrades, start, end }),
    [openRows, closedTrades, start, end],
  );

  const sortedRows = useMemo(
    () => sortPeriodRows(report.rows, sortBy, sortDir),
    [report.rows, sortBy, sortDir],
  );

  const { startResize, resizingKey, gridTemplateColumns } = useStockListColumnWidths(PNL_PERIOD_COLS);
  const { headerScrollRef, rowsScrollRef } = useSyncedHeaderScroll([gridTemplateColumns, sortedRows.length]);

  const handleSort = useCallback((key) => {
    setSortBy((prev) => {
      if (prev === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        return prev;
      }
      setSortDir('asc');
      return key;
    });
  }, []);

  const { summary } = report;

  const handleExport = useCallback(() => {
    exportPeriodReportCsv(report, { start, end, availableCash });
  }, [report, start, end, availableCash]);

  const canExport = report.rows.length > 0
    || summary.total_invested > 0
    || summary.portfolio_value > 0
    || summary.realized_pl !== 0
    || summary.unrealized_pl !== 0
    || Number(availableCash) !== 0;

  return (
    <div style={{ flex: 1, minHeight: 0, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ flexShrink: 0, padding: `8px 10px ${PNL_FORM_GAP}px`, borderBottom: '1px solid var(--border)' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            marginBottom: PNL_FORM_GAP,
          }}
        >
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', flexShrink: 0 }}>
            Period
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: PNL_FORM_GAP, flexShrink: 0 }}>
            <PnlToolbarButton onClick={() => setCashDialog('deposit')}>
              Deposit
            </PnlToolbarButton>
            <PnlToolbarButton onClick={() => setCashDialog('withdraw')}>
              Withdraw
            </PnlToolbarButton>
            <PnlToolbarButton onClick={() => setTaxPnlOpen(true)}>
              Tax P&L
            </PnlToolbarButton>
            <PnlToolbarButton onClick={() => setImportOpen(true)}>
              Import CSV
            </PnlToolbarButton>
            <PnlToolbarButton onClick={() => setSyncOpen(true)}>
              Sync holdings
            </PnlToolbarButton>
            <PnlToolbarButton onClick={handleExport} disabled={!canExport}>
              Export CSV
            </PnlToolbarButton>
          </div>
        </div>
        <PnLImportTaxPnlDialog
          open={taxPnlOpen}
          onClose={() => setTaxPnlOpen(false)}
          onImported={onImported}
        />
        <PnLImportZerodhaDialog
          open={importOpen}
          onClose={() => setImportOpen(false)}
          onImported={onImported}
        />
        <PnLSyncHoldingsDialog
          open={syncOpen}
          onClose={() => setSyncOpen(false)}
          onSynced={onImported}
        />
        <PnLCashDialog
          open={cashDialog != null}
          mode={cashDialog}
          onClose={() => setCashDialog(null)}
          onDone={handleCashDone}
        />
        <PnLPeriodRangeSelect
          startYear={startYear}
          startMonth={startMonth}
          startDay={startDay}
          endYear={endYear}
          endMonth={endMonth}
          endDay={endDay}
          endLinked={endLinked}
          onStartYearChange={onStartYearChange}
          onStartMonthChange={onStartMonthChange}
          onStartDayChange={onStartDayChange}
          onEndYearChange={onEndYearChange}
          onEndMonthChange={onEndMonthChange}
          onEndDayChange={onEndDayChange}
        />
        <div style={{ marginTop: PNL_FORM_GAP, fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
          <span style={{ color: 'var(--text-muted)' }}>Showing: </span>
          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
            {formatPeriodShowing(report.from, report.to)}
          </span>
          {endLinked ? (
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>
              Range end matches period — change the right side to customize.
            </div>
          ) : null}
        </div>
        <div style={{ marginTop: PNL_FORM_GAP, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <SummaryLine label="Realized P/L" amount={summary.realized_pl} pct={summary.realized_pl_pct} />
          <SummaryLine label="Unrealized P/L" amount={summary.unrealized_pl} pct={summary.unrealized_pl_pct} />
          <SummaryNeutral label="Total invested" amount={summary.total_invested} />
          <SummaryNeutral label="Portfolio value" amount={summary.portfolio_value} />
          <SummaryCashRow amount={availableCash} onSaved={handleCashDone} />
          <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>
            Portfolio value is current market value of open positions. Available cash updates on buys, sells, and bank transfers.
          </div>
        </div>
      </div>

      <div ref={headerScrollRef} style={{ ...stockListHeaderStripStyle, overflowX: 'hidden', overflowY: 'hidden', flexShrink: 0 }}>
        <div style={stockListGridTrackStyle(gridTemplateColumns)}>
          {PNL_PERIOD_COLS.map((col, colIdx) => {
            const sortable = col.sortable !== false;
            const activeSort = sortable && sortBy === col.key;
            return (
              <StockListColumnHeader
                key={col.key}
                colKey={col.key}
                isLast={colIdx === PNL_PERIOD_COLS.length - 1}
                widthKey={columnWidthKey(col)}
                resizingKey={resizingKey}
                onResizeStart={(e) => startResize(col, e)}
                sortable={sortable}
                onClick={sortable ? () => handleSort(col.key) : undefined}
              >
                <span style={{ color: activeSort ? 'var(--accent-blue)' : 'var(--text-secondary)' }}>
                  {col.label}
                  {activeSort && (
                    <span style={{ marginLeft: 2, fontSize: 9 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>
                  )}
                </span>
              </StockListColumnHeader>
            );
          })}
        </div>
      </div>

      <div ref={rowsScrollRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'auto' }}>
        {sortedRows.length === 0 ? (
          <div style={{ padding: 12, fontSize: 11, color: 'var(--text-muted)' }}>
            No trades in this period.
          </div>
        ) : (
          sortedRows.map((row) => (
            <div
              key={row.symbol}
              style={{
                ...stockListGridTrackStyle(gridTemplateColumns),
                alignItems: 'center',
                height: STOCK_LIST_ROW_HEIGHT,
                borderBottom: '1px solid var(--border-light)',
              }}
            >
              {PNL_PERIOD_COLS.map((col, colIdx) => (
                <div
                  key={col.key}
                  style={{
                    ...stockListGridCellStyle({ isLast: colIdx === PNL_PERIOD_COLS.length - 1 }),
                    padding: col.key === 'symbol' ? '0 8px' : stockListCellPad(col.key),
                    ...cellMonoStyle(periodCellColor(col.key, row)),
                  }}
                >
                  {renderPeriodCell(col.key, row)}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
