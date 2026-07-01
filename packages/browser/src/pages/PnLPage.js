import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { APP_DATA_REFRESH_EVENT, PNL_REFRESH_EVENT } from '../chartEvents';
import StockListColumnHeader from '../components/StockListColumnHeader';
import StockListGridCell from '../components/StockListGridCell';
import PnLEntryCell from '../components/PnLEntryCell';
import PnLQtyCell from '../components/PnLQtyCell';
import PnLBookDialog from '../components/PnLBookDialog';
import PnlSymbolCell from '../components/PnlSymbolCell';
import PnLPeriodPanel from '../components/PnLPeriodPanel';
import { useStockListColumnWidths } from '../hooks/useStockListColumnWidths';
import { columnWidthKey } from '../hooks/stockListColumnStorage';
import { applySavedOrder, insertionGapFromRowHover, reorderByGap } from '../utils/listOrder';
import { DropInsetLine, setListDragImage } from '../utils/listDnD';
import {
  STOCK_LIST_ROW_HEIGHT,
  stockListCellPad,
  stockListGridCellStyle,
  stockListGridTrackStyle,
  stockListHeaderStripStyle,
  stockListRowSelectShadow,
} from '../components/stockTableChrome';
import { formatMarketCap } from '../utils/formatMarketCap';
import { formatPnLAmount, formatPnLHeaderTotal } from '../utils/formatPnLAmount';
import { formatPlPct, plPctColor } from '../utils/portfolioEntry';
import {
  buildGroupDisplayList,
  buildSymbolGroups,
  groupSortValue,
  sectionTotalFromTrades,
} from '../utils/groupPnlClosed';
import {
  buildOpenGroupDisplayList,
  buildOpenSymbolGroups,
  openGroupSortValue,
  pnlOpenGroupKey,
  reconcilePnlGroupOrder,
} from '../utils/groupPnlOpen';
import PnLDateSelect, { istTodayParts, toCalendarDate } from '../components/PnLDateSelect';
import {
  PnlFormDialog,
  PnlDialogButton,
  PnlGridActionButton,
  PnlToolbarButton,
  pnlFormFieldRowStyle,
  pnlFormFieldStyle,
  pnlFormMonoFieldStyle,
  pnlFormPickListStyle,
} from '../components/pnlFormDialogChrome';
import { searchUniverse } from '../api/client';
import { useIntradayPatchOptional } from '../intraday/useIntradayPatch';
import { usePageLive } from '../intraday/pageLiveContext';
import { usePatchOverlay } from '../intraday/usePatchOverlay';

const API = '';
const PNL_PAGE_ID = 'pnl';

const PNL_OPEN_SORT_KEY = 'cim.pnl.openSort.v1';
const PNL_CLOSED_SORT_KEY = 'cim.pnl.closedSort.v1';
const PNL_OPEN_ROW_ORDER_KEY = 'cim.pnl.openRowOrder.v1';
const PNL_MANUAL_ROW_ORDER_KEY = 'cim.pnl.useManualRowOrder.v1';
const PNL_OPEN_EXPANDED_KEY = 'cim.pnl.openExpanded.v1';
const PNL_PERIOD_PANE_WIDTH_KEY = 'cim.pnl.periodPaneWidth.v1';
const PNL_PERIOD_PANE_MIN = 580;
const PNL_OPEN_PANE_MIN = 900;
const PNL_PERIOD_PANE_DEFAULT = 580;

function readPeriodPaneWidth() {
  try {
    const n = Number(window.localStorage.getItem(PNL_PERIOD_PANE_WIDTH_KEY));
    if (Number.isFinite(n) && n >= PNL_PERIOD_PANE_MIN) return Math.round(n);
  } catch { /* ignore */ }
  return PNL_PERIOD_PANE_DEFAULT;
}

function writePeriodPaneWidth(w) {
  try {
    window.localStorage.setItem(PNL_PERIOD_PANE_WIDTH_KEY, String(Math.round(w)));
  } catch { /* ignore */ }
}

const PNL_OPEN_COLS = [
  { key: 'symbol', widthKey: 'pnl_open_symbol', label: 'Symbol', width: 96, sortable: true },
  { key: 'entry_date', widthKey: 'pnl_open_bought', label: 'Bought', width: 88, sortable: true },
  { key: 'market_cap', widthKey: 'pnl_open_market_cap', label: 'Mkt Cap', width: 100, sortable: true },
  { key: 'price', widthKey: 'pnl_open_price', label: 'Price', width: 80, sortable: true },
  { key: 'entry', widthKey: 'pnl_open_entry', label: 'Entry', width: 88, sortable: true },
  { key: 'qty', widthKey: 'pnl_open_qty', label: 'Qty', width: 56, sortable: true },
  { key: 'invested', widthKey: 'pnl_open_invested', label: 'Invested', width: 92, sortable: true },
  { key: 'pl_pct', widthKey: 'pnl_open_pl_pct', label: 'P/L %', width: 72, sortable: true },
  { key: 'change_1d', widthKey: 'pnl_open_change_1d', label: '1D Chg %', width: 76, sortable: true },
  { key: 'change_1m', widthKey: 'pnl_open_change_1m', label: '1M Chg %', width: 76, sortable: true },
  { key: 'unrealized_pl', widthKey: 'pnl_open_unrealized', label: 'Unreal. P/L', width: 96, sortable: true },
  { key: 'book', widthKey: 'pnl_open_book', label: 'Book', width: 56, sortable: false },
];

const PNL_CLOSED_COLS = [
  { key: 'symbol', widthKey: 'pnl_closed_symbol', label: 'Symbol', width: 96, sortable: true },
  { key: 'market_cap', widthKey: 'pnl_closed_market_cap', label: 'Mkt Cap', width: 100, sortable: true },
  { key: 'entry', widthKey: 'pnl_closed_entry', label: 'Entry', width: 80, sortable: true },
  { key: 'exit', widthKey: 'pnl_closed_exit', label: 'Exit', width: 80, sortable: true },
  { key: 'qty_bought', widthKey: 'pnl_closed_qty_bought', label: 'Bought', width: 64, sortable: true },
  { key: 'qty_sold', widthKey: 'pnl_closed_qty_sold', label: 'Lot sold', width: 64, sortable: true },
  { key: 'realized_pl', widthKey: 'pnl_closed_pl', label: 'P/L', width: 96, sortable: true },
  { key: 'realized_pl_pct', widthKey: 'pnl_closed_pl_pct', label: 'P/L %', width: 72, sortable: true },
  { key: 'sale_date', widthKey: 'pnl_closed_date', label: 'Date', width: 88, sortable: true },
];

function readStoredSort(storageKey, fallback) {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return fallback;
    const sortBy = String(parsed.sortBy || fallback.sortBy);
    const sortDir = parsed.sortDir === 'asc' ? 'asc' : 'desc';
    return { sortBy, sortDir };
  } catch {
    return fallback;
  }
}

function writeStoredSort(storageKey, sortBy, sortDir) {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify({ sortBy, sortDir }));
  } catch { /* ignore */ }
}

function readStoredRowOrder() {
  try {
    const raw = window.localStorage.getItem(PNL_OPEN_ROW_ORDER_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function writeStoredRowOrder(keys) {
  try {
    window.localStorage.setItem(PNL_OPEN_ROW_ORDER_KEY, JSON.stringify(keys));
  } catch { /* ignore */ }
}

function readStoredManualRowOrder() {
  try {
    const v = window.localStorage.getItem(PNL_MANUAL_ROW_ORDER_KEY);
    if (v === null) return true;
    return v === '1';
  } catch {
    return true;
  }
}

function writeStoredManualRowOrder(enabled) {
  try {
    window.localStorage.setItem(PNL_MANUAL_ROW_ORDER_KEY, enabled ? '1' : '0');
  } catch { /* ignore */ }
}

function readStoredExpanded() {
  try {
    const raw = window.localStorage.getItem(PNL_OPEN_EXPANDED_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeStoredExpanded(expanded) {
  try {
    window.localStorage.setItem(PNL_OPEN_EXPANDED_KEY, JSON.stringify(expanded));
  } catch { /* ignore */ }
}

function fmtSaleDate(sd) {
  if (!sd) return '—';
  try {
    const d = new Date(`${sd}T12:00:00`);
    if (Number.isNaN(d.getTime())) return String(sd);
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return String(sd);
  }
}

function fmtClosedPl(v, isLoss) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  const n = isLoss ? Math.abs(Number(v)) : Number(v);
  return formatPnLAmount(n);
}

function compareSortValues(a, b, sortDir) {
  const dir = sortDir === 'asc' ? 1 : -1;
  const aNull = a == null || a === '' || (typeof a === 'number' && !Number.isFinite(a));
  const bNull = b == null || b === '' || (typeof b === 'number' && !Number.isFinite(b));
  if (aNull && bNull) return 0;
  if (aNull) return 1;
  if (bNull) return -1;
  if (typeof a === 'string' || typeof b === 'string') {
    return dir * String(a).localeCompare(String(b), undefined, { sensitivity: 'base' });
  }
  const na = Number(a);
  const nb = Number(b);
  if (na < nb) return -dir;
  if (na > nb) return dir;
  return 0;
}

function sortRows(rows, sortBy, sortDir, valueFn) {
  if (!sortBy || !rows.length) return rows;
  return [...rows].sort((a, b) => compareSortValues(valueFn(a, sortBy), valueFn(b, sortBy), sortDir));
}

function toggleSort(sortBy, sortDir, colKey) {
  if (sortBy === colKey) {
    return { sortBy: colKey, sortDir: sortDir === 'asc' ? 'desc' : 'asc' };
  }
  return { sortBy: colKey, sortDir: 'desc' };
}

function fmtPrice(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  return Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  const n = Number(v);
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function fmtPlRupee(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  return formatPnLAmount(Number(v));
}

function OpenGrid({
  groups,
  selectedKey,
  onSelectGroup,
  onBook,
  onPositionSaved,
  sortBy,
  sortDir,
  onSort,
  rowDrag,
  draggingIdx,
  dropGap,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}) {
  const { startResize, resizingKey, gridTemplateColumns } = useStockListColumnWidths(PNL_OPEN_COLS);
  const [expanded, setExpanded] = useState(() => readStoredExpanded());

  const displayList = useMemo(
    () => buildOpenGroupDisplayList(groups, expanded),
    [groups, expanded],
  );

  const toggleExpanded = useCallback((symbol) => {
    setExpanded((prev) => {
      const next = { ...prev, [symbol]: prev[symbol] !== true };
      writeStoredExpanded(next);
      return next;
    });
  }, []);

  const renderLotCell = (key, lot) => {
    switch (key) {
      case 'symbol':
        return <PnlSymbolCell variant="child" />;
      case 'entry_date':
        return fmtSaleDate(lot.entry_date);
      case 'market_cap':
        return '—';
      case 'price':
        return fmtPrice(lot.price);
      case 'entry':
        return (
          <PnLEntryCell
            positionId={lot.id}
            entryPrice={lot.entry_price}
            qty={lot.qty}
            isPlaceholder={lot.is_placeholder}
            onSaved={() => onPositionSaved?.()}
          />
        );
      case 'qty':
        return (
          <PnLQtyCell
            positionId={lot.id}
            entryPrice={lot.entry_price}
            qty={lot.qty}
            isPlaceholder={lot.is_placeholder}
            onSaved={() => onPositionSaved?.()}
          />
        );
      case 'invested':
        return lot.invested != null ? formatPnLAmount(lot.invested) : '—';
      case 'pl_pct':
        return (
          <span style={{ color: plPctColor(lot.pl_pct), fontFamily: 'var(--font-mono)' }}>
            {formatPlPct(lot.pl_pct)}
          </span>
        );
      case 'change_1d':
        return fmtPct(lot.change_1d);
      case 'change_1m':
        return fmtPct(lot.change_1m);
      case 'unrealized_pl':
        return (
          <span style={{ color: plPctColor(lot.unrealized_pl), fontFamily: 'var(--font-mono)' }}>
            {fmtPlRupee(lot.unrealized_pl)}
          </span>
        );
      case 'book':
        return '';
      default:
        return '—';
    }
  };

  const renderParentCell = (key, group, multiLot, gIdx) => {
    const t = group.totals;
    const lot = group.lots[0];
    const data = multiLot ? t : lot;
    switch (key) {
      case 'symbol':
        return (
          <PnlSymbolCell
            symbol={group.symbol}
            showDrag={rowDrag}
            onDragStart={(e) => { e.stopPropagation(); onDragStart(e, gIdx); }}
            onDragEnd={(e) => { e.stopPropagation(); onDragEnd(); }}
            showExpand={multiLot}
            expanded={expanded[group.symbol] === true}
          />
        );
      case 'entry_date':
        if (multiLot) return fmtSaleDate(t.min_entry_date) || '—';
        return fmtSaleDate(lot?.entry_date);
      case 'market_cap':
        return formatMarketCap(data?.market_cap ?? lot?.market_cap);
      case 'price':
        return fmtPrice(data?.price ?? lot?.price);
      case 'entry':
        if (multiLot) {
          return data?.entry_price != null ? `₹${fmtPrice(data.entry_price)}` : '—';
        }
        return (
          <PnLEntryCell
            positionId={lot.id}
            entryPrice={lot.entry_price}
            qty={lot.qty}
            isPlaceholder={lot.is_placeholder}
            onSaved={() => onPositionSaved?.()}
          />
        );
      case 'qty':
        if (multiLot) return data?.qty ?? '—';
        return (
          <PnLQtyCell
            positionId={lot.id}
            entryPrice={lot.entry_price}
            qty={lot.qty}
            isPlaceholder={lot.is_placeholder}
            onSaved={() => onPositionSaved?.()}
          />
        );
      case 'invested':
        return data?.invested != null ? formatPnLAmount(data.invested) : '—';
      case 'pl_pct':
        return (
          <span style={{ color: plPctColor(data?.pl_pct ?? lot?.pl_pct), fontFamily: 'var(--font-mono)' }}>
            {formatPlPct(data?.pl_pct ?? lot?.pl_pct)}
          </span>
        );
      case 'change_1d':
        return fmtPct(lot?.change_1d);
      case 'change_1m':
        return fmtPct(lot?.change_1m);
      case 'unrealized_pl':
        return (
          <span style={{ color: plPctColor(data?.unrealized_pl ?? lot?.unrealized_pl), fontFamily: 'var(--font-mono)' }}>
            {fmtPlRupee(data?.unrealized_pl ?? lot?.unrealized_pl)}
          </span>
        );
      case 'book':
        return (
          <PnlGridActionButton
            disabled={group.isPlaceholder || !data?.qty}
            onClick={(e) => {
              e.stopPropagation();
              onBook(group);
            }}
          >
            Book
          </PnlGridActionButton>
        );
      default:
        return '—';
    }
  };

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ ...stockListHeaderStripStyle, overflowX: 'auto', flexShrink: 0 }}>
        <div style={stockListGridTrackStyle(gridTemplateColumns)}>
          {PNL_OPEN_COLS.map((col, colIdx) => {
            const sortable = col.sortable !== false;
            const activeSort = sortable && sortBy === col.key;
            return (
              <StockListColumnHeader
                key={col.key}
                colKey={col.key}
                isLast={colIdx === PNL_OPEN_COLS.length - 1}
                widthKey={columnWidthKey(col)}
                resizingKey={resizingKey}
                onResizeStart={(e) => startResize(col, e)}
                sortable={sortable}
                onClick={sortable && onSort ? () => onSort(col.key) : undefined}
              >
                <span style={{ color: activeSort ? 'var(--accent-blue)' : 'var(--text-secondary)' }}>
                  {col.label}
                  {activeSort && (
                    <span style={{ marginLeft: 3, fontSize: 9 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>
                  )}
                </span>
              </StockListColumnHeader>
            );
          })}
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        {groups.length === 0 ? (
          <div style={{ padding: 16, fontSize: 12, color: 'var(--text-muted)' }}>
            Add stock to track P&amp;L here.
          </div>
        ) : (
          <>
            {rowDrag && draggingIdx !== null && dropGap === 0 ? <DropInsetLine /> : null}
            {displayList.map((item) => {
              if (item.type === 'parent') {
                const { group, multiLot } = item;
                const gKey = pnlOpenGroupKey(group);
                const gIdx = groups.findIndex((g) => pnlOpenGroupKey(g) === gKey);
                const selected = selectedKey === gKey;
                return (
                  <React.Fragment key={gKey}>
                    <div
                      onClick={() => {
                        if (multiLot) toggleExpanded(group.symbol);
                        onSelectGroup(group);
                      }}
                      onDragOver={rowDrag ? (e) => onDragOver(e, gIdx) : undefined}
                      onDrop={rowDrag ? onDrop : undefined}
                      style={{
                        ...stockListGridTrackStyle(gridTemplateColumns),
                        alignItems: 'center',
                        height: STOCK_LIST_ROW_HEIGHT,
                        borderBottom: '1px solid var(--border-light)',
                        cursor: 'pointer',
                        backgroundColor: selected ? 'var(--bg-hover)' : 'transparent',
                        ...stockListRowSelectShadow(selected ? '2px solid var(--accent-blue)' : '2px solid transparent'),
                        opacity: draggingIdx === gIdx ? 0.45 : 1,
                      }}
                    >
                      {PNL_OPEN_COLS.map((col, colIdx) => {
                        if (col.key === 'symbol') {
                          return (
                            <StockListGridCell
                              key={col.key}
                              colKey="symbol"
                              compact={rowDrag}
                              isLast={colIdx === PNL_OPEN_COLS.length - 1}
                            >
                              {renderParentCell('symbol', group, multiLot, gIdx)}
                            </StockListGridCell>
                          );
                        }
                        return (
                          <div
                            key={col.key}
                            style={{
                              ...stockListGridCellStyle({ isLast: colIdx === PNL_OPEN_COLS.length - 1 }),
                              padding: stockListCellPad(col.key),
                              fontSize: 11,
                            }}
                          >
                            {renderParentCell(col.key, group, multiLot, gIdx)}
                          </div>
                        );
                      })}
                    </div>
                    {rowDrag && draggingIdx !== null && dropGap === gIdx + 1 ? <DropInsetLine /> : null}
                  </React.Fragment>
                );
              }
              const { group, lot } = item;
              return (
                <div
                  key={lot.id}
                  onClick={() => onSelectGroup(group)}
                  style={{
                    ...stockListGridTrackStyle(gridTemplateColumns),
                    alignItems: 'center',
                    height: STOCK_LIST_ROW_HEIGHT,
                    borderBottom: '1px solid var(--border-light)',
                    backgroundColor: 'var(--bg-primary)',
                  }}
                >
                  {PNL_OPEN_COLS.map((col, colIdx) => {
                    if (col.key === 'symbol') {
                      return (
                        <StockListGridCell
                          key={col.key}
                          colKey="symbol"
                          compact={rowDrag}
                          isLast={colIdx === PNL_OPEN_COLS.length - 1}
                        >
                          {renderLotCell('symbol', lot)}
                        </StockListGridCell>
                      );
                    }
                    return (
                    <div
                      key={col.key}
                      style={{
                        ...stockListGridCellStyle({ isLast: colIdx === PNL_OPEN_COLS.length - 1 }),
                        padding: stockListCellPad(col.key),
                        fontSize: 11,
                        color: col.key === 'symbol' ? 'var(--text-muted)' : 'var(--text-primary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {renderLotCell(col.key, lot)}
                    </div>
                    );
                  })}
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}

function ClosedGrid({
  title,
  titleColor,
  rows,
  isLoss,
  widthKeyPrefix,
  sortBy,
  sortDir,
  onSort,
}) {
  const cols = useMemo(
    () => PNL_CLOSED_COLS.map((c) => ({ ...c, widthKey: c.widthKey.replace('pnl_closed_', widthKeyPrefix) })),
    [widthKeyPrefix],
  );
  const { startResize, resizingKey, gridTemplateColumns } = useStockListColumnWidths(cols);
  const [expanded, setExpanded] = useState({});

  const sectionTotal = useMemo(() => sectionTotalFromTrades(rows, isLoss), [rows, isLoss]);

  const sortedGroups = useMemo(() => {
    const groups = buildSymbolGroups(rows);
    return sortRows(groups, sortBy, sortDir, groupSortValue);
  }, [rows, sortBy, sortDir]);

  const displayList = useMemo(
    () => buildGroupDisplayList(sortedGroups, expanded),
    [sortedGroups, expanded],
  );

  const toggleExpanded = useCallback((symbol) => {
    setExpanded((prev) => ({ ...prev, [symbol]: prev[symbol] !== true }));
  }, []);

  const plColor = isLoss ? 'var(--accent-red)' : 'var(--accent-green)';

  const renderParentCell = (key, group) => {
    const t = group.totals;
    const multiTrade = group.trades.length > 1;
    switch (key) {
      case 'symbol':
        return (
          <PnlSymbolCell
            symbol={group.symbol}
            showExpand={multiTrade}
            expanded={expanded[group.symbol] === true}
          />
        );
      case 'market_cap':
        return formatMarketCap(t.market_cap);
      case 'entry':
        return t.entry_price != null ? `₹${fmtPrice(t.entry_price)}` : '—';
      case 'exit':
        return t.exit_price != null ? `₹${fmtPrice(t.exit_price)}` : '—';
      case 'qty_bought':
        return t.qty_bought || '—';
      case 'qty_sold':
        return t.qty_sold || '—';
      case 'realized_pl':
        return (
          <span style={{ color: plColor, fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
            {fmtClosedPl(t.realized_pl, isLoss)}
          </span>
        );
      case 'realized_pl_pct':
        return t.realized_pl_pct != null ? (
          <span style={{ color: plColor, fontFamily: 'var(--font-mono)' }}>
            {formatPlPct(isLoss ? Math.abs(t.realized_pl_pct) : t.realized_pl_pct)}
          </span>
        ) : '—';
      case 'sale_date':
        return '—';
      default:
        return '—';
    }
  };

  const renderChildCell = (key, trade) => {
    switch (key) {
      case 'symbol':
        return <PnlSymbolCell variant="child" />;
      case 'market_cap':
        return '—';
      case 'entry':
        return trade.entry_price != null ? `₹${fmtPrice(trade.entry_price)}` : '—';
      case 'exit':
        return trade.exit_price != null ? `₹${fmtPrice(trade.exit_price)}` : '—';
      case 'qty_bought':
        return trade.qty_bought ?? '—';
      case 'qty_sold':
        return trade.qty_sold ?? '—';
      case 'realized_pl':
        return (
          <span style={{ color: plColor, fontFamily: 'var(--font-mono)' }}>
            {fmtClosedPl(trade.realized_pl, isLoss)}
          </span>
        );
      case 'realized_pl_pct':
        return trade.realized_pl_pct != null ? (
          <span style={{ color: plColor, fontFamily: 'var(--font-mono)' }}>
            {formatPlPct(isLoss ? Math.abs(trade.realized_pl_pct) : trade.realized_pl_pct)}
          </span>
        ) : '—';
      case 'sale_date':
        return fmtSaleDate(trade.sale_date);
      default:
        return '—';
    }
  };

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRight: '1px solid var(--border)' }}>
      <div
        style={{
          padding: '6px 10px',
          fontSize: 11,
          fontWeight: 600,
          color: titleColor,
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span>{title}</span>
        <span style={{ fontFamily: 'var(--font-mono)' }}>{formatPnLHeaderTotal(sectionTotal)}</span>
      </div>
      <div style={{ ...stockListHeaderStripStyle, overflowX: 'auto', flexShrink: 0 }}>
        <div style={stockListGridTrackStyle(gridTemplateColumns)}>
          {cols.map((col, colIdx) => {
            const sortable = col.sortable !== false;
            const activeSort = sortable && sortBy === col.key;
            return (
              <StockListColumnHeader
                key={col.key}
                colKey={col.key}
                isLast={colIdx === cols.length - 1}
                widthKey={columnWidthKey(col)}
                resizingKey={resizingKey}
                onResizeStart={(e) => startResize(col, e)}
                sortable={sortable}
                onClick={sortable && onSort ? () => onSort(col.key) : undefined}
              >
                <span style={{ color: activeSort ? 'var(--accent-blue)' : 'var(--text-secondary)' }}>
                  {col.label}
                  {activeSort && (
                    <span style={{ marginLeft: 3, fontSize: 9 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>
                  )}
                </span>
              </StockListColumnHeader>
            );
          })}
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        {rows.length === 0 ? (
          <div style={{ padding: 16, fontSize: 12, color: 'var(--text-muted)' }}>No booked trades</div>
        ) : (
          displayList.map((item, idx) => {
            if (item.type === 'divider') {
              return (
                <div
                  key={`div-${item.group.symbol}-${item.trade.id}-${idx}`}
                  style={{
                    padding: '4px 12px 4px 28px',
                    fontSize: 10,
                    color: 'var(--text-muted)',
                    borderBottom: '1px solid var(--border-light)',
                    background: 'var(--bg-tertiary)',
                  }}
                >
                  — {item.label} —
                </div>
              );
            }
            if (item.type === 'parent') {
              return (
                <div
                  key={item.group.id}
                  onClick={() => toggleExpanded(item.group.symbol)}
                  style={{
                    ...stockListGridTrackStyle(gridTemplateColumns),
                    alignItems: 'center',
                    height: STOCK_LIST_ROW_HEIGHT,
                    borderBottom: '1px solid var(--border-light)',
                    cursor: 'pointer',
                    backgroundColor: 'var(--bg-secondary)',
                  }}
                >
                  {cols.map((col, colIdx) => {
                    if (col.key === 'symbol') {
                      return (
                        <StockListGridCell
                          key={col.key}
                          colKey="symbol"
                          isLast={colIdx === cols.length - 1}
                        >
                          {renderParentCell(col.key, item.group)}
                        </StockListGridCell>
                      );
                    }
                    return (
                    <div
                      key={col.key}
                      style={{
                        ...stockListGridCellStyle({ isLast: colIdx === cols.length - 1 }),
                        padding: stockListCellPad(col.key),
                        fontSize: 11,
                        fontFamily: col.key === 'symbol' ? 'var(--font-mono)' : undefined,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {renderParentCell(col.key, item.group)}
                    </div>
                    );
                  })}
                </div>
              );
            }
            const trade = item.trade;
            return (
              <div
                key={trade.id}
                style={{
                  ...stockListGridTrackStyle(gridTemplateColumns),
                  alignItems: 'center',
                  height: STOCK_LIST_ROW_HEIGHT,
                  borderBottom: '1px solid var(--border-light)',
                  backgroundColor: 'transparent',
                }}
              >
                {cols.map((col, colIdx) => {
                  if (col.key === 'symbol') {
                    return (
                      <StockListGridCell
                        key={col.key}
                        colKey="symbol"
                        isLast={colIdx === cols.length - 1}
                      >
                        {renderChildCell(col.key, trade)}
                      </StockListGridCell>
                    );
                  }
                  return (
                  <div
                    key={col.key}
                    style={{
                      ...stockListGridCellStyle({ isLast: colIdx === cols.length - 1 }),
                      padding: stockListCellPad(col.key),
                      fontSize: 11,
                      color: col.key === 'symbol' ? 'var(--text-muted)' : 'var(--text-primary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {renderChildCell(col.key, trade)}
                  </div>
                  );
                })}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function AddStockDialog({ onClose, onAdded }) {
  const [search, setSearch] = useState('');
  const [picks, setPicks] = useState([]);
  const [symbol, setSymbol] = useState('');
  const [entry, setEntry] = useState('');
  const [qty, setQty] = useState('');
  const [year, setYear] = useState(() => istTodayParts().year);
  const [month, setMonth] = useState(() => istTodayParts().month);
  const [day, setDay] = useState(() => istTodayParts().day);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const pickTimerRef = useRef(null);

  useEffect(() => {
    if (pickTimerRef.current) clearTimeout(pickTimerRef.current);
    const q = search.trim();
    if (q.length < 1) {
      setPicks([]);
      return undefined;
    }
    pickTimerRef.current = setTimeout(async () => {
      try {
        const d = await searchUniverse(q);
        setPicks((d.stocks || []).slice(0, 12));
      } catch {
        setPicks([]);
      }
    }, 220);
    return () => { if (pickTimerRef.current) clearTimeout(pickTimerRef.current); };
  }, [search]);

  const submit = async () => {
    const sym = String(symbol || search).trim().toUpperCase();
    const ep = Number(entry);
    const q = Number(qty);
    if (!sym) { setError('Symbol required'); return; }
    if (!Number.isFinite(ep) || ep <= 0) { setError('Valid entry required'); return; }
    if (!Number.isInteger(q) || q <= 0) { setError('Valid qty required'); return; }
    const entryDate = toCalendarDate(year, month, day);
    if (!entryDate) { setError('Valid buy date required'); return; }
    setSaving(true);
    setError('');
    try {
      await axios.post(`${API}/api/pnl/add-stock`, {
        symbol: sym,
        entry_price: ep,
        qty: q,
        entry_date: entryDate,
      });
      window.dispatchEvent(new CustomEvent('portfolio-updated'));
      onAdded?.();
      onClose?.();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <PnlFormDialog
      title="Add stock"
      titleId="pnl-add-stock-title"
      onClose={onClose}
      error={error || null}
      footer={(
        <>
          <PnlDialogButton onClick={onClose} disabled={saving}>Cancel</PnlDialogButton>
          <PnlDialogButton variant="primary" onClick={submit} disabled={saving}>
            {saving ? 'Adding…' : 'Add'}
          </PnlDialogButton>
        </>
      )}
    >
      <input
        placeholder="Symbol"
        value={search}
        onChange={(e) => { setSearch(e.target.value); setSymbol(''); }}
        style={pnlFormFieldStyle}
        autoComplete="off"
      />
      {picks.length > 0 && (
        <div style={pnlFormPickListStyle}>
          {picks.map((p) => (
            <button
              key={p.Symbol || p.symbol}
              type="button"
              onClick={() => {
                const s = String(p.Symbol || p.symbol).toUpperCase();
                setSymbol(s);
                setSearch(s);
                setPicks([]);
              }}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '5px 8px',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                border: 'none',
                background: 'transparent',
                color: 'var(--text-primary)',
                cursor: 'pointer',
              }}
            >
              {p.Symbol || p.symbol}
            </button>
          ))}
        </div>
      )}
      <div style={pnlFormFieldRowStyle}>
        <input
          placeholder="Entry"
          value={entry}
          onChange={(e) => setEntry(e.target.value)}
          style={pnlFormMonoFieldStyle}
          inputMode="decimal"
        />
        <input
          placeholder="Qty"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          style={pnlFormMonoFieldStyle}
          inputMode="numeric"
        />
      </div>
      <PnLDateSelect
        label="Buy date"
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

function AddLotDialog({ portfolioStocks, onClose, onAdded }) {
  const [symbol, setSymbol] = useState(portfolioStocks[0] || '');
  const [entry, setEntry] = useState('');
  const [qty, setQty] = useState('');
  const [year, setYear] = useState(() => istTodayParts().year);
  const [month, setMonth] = useState(() => istTodayParts().month);
  const [day, setDay] = useState(() => istTodayParts().day);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const ep = Number(entry);
    const q = Number(qty);
    if (!symbol) { setError('Symbol required'); return; }
    if (!Number.isFinite(ep) || ep <= 0) { setError('Valid entry required'); return; }
    if (!Number.isInteger(q) || q <= 0) { setError('Valid qty required'); return; }
    const entryDate = toCalendarDate(year, month, day);
    if (!entryDate) { setError('Valid buy date required'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/api/pnl/positions`, {
        symbol,
        entry_price: ep,
        qty: q,
        entry_date: entryDate,
      });
      onAdded?.();
      onClose?.();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed');
    } finally {
      setSaving(false);
    }
  };

  if (!portfolioStocks.length) return null;

  return (
    <PnlFormDialog
      title="Add lot"
      titleId="pnl-add-lot-title"
      onClose={onClose}
      error={error || null}
      footer={(
        <>
          <PnlDialogButton onClick={onClose} disabled={saving}>Cancel</PnlDialogButton>
          <PnlDialogButton variant="primary" onClick={submit} disabled={saving}>
            {saving ? 'Adding…' : 'Add'}
          </PnlDialogButton>
        </>
      )}
    >
      <select
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        style={{ ...pnlFormFieldStyle, fontFamily: 'var(--font-mono)' }}
      >
        {portfolioStocks.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <div style={pnlFormFieldRowStyle}>
        <input
          placeholder="Entry"
          value={entry}
          onChange={(e) => setEntry(e.target.value)}
          style={pnlFormMonoFieldStyle}
          inputMode="decimal"
        />
        <input
          placeholder="Qty"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          style={pnlFormMonoFieldStyle}
          inputMode="numeric"
        />
      </div>
      <PnLDateSelect
        label="Buy date"
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

export default function PnLPage({ onOpenChart }) {
  const [openRows, setOpenRows] = useState([]);
  const [profitRows, setProfitRows] = useState([]);
  const [lossRows, setLossRows] = useState([]);
  const [asOfDate, setAsOfDate] = useState(null);
  const [availableCash, setAvailableCash] = useState(0);
  const [selectedKey, setSelectedKey] = useState(null);
  const [bookTarget, setBookTarget] = useState(null);
  const [addLotOpen, setAddLotOpen] = useState(false);
  const [addStockOpen, setAddStockOpen] = useState(false);
  const [portfolioStocks, setPortfolioStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openSortBy, setOpenSortBy] = useState(() => readStoredSort(PNL_OPEN_SORT_KEY, { sortBy: 'symbol', sortDir: 'asc' }).sortBy);
  const [openSortDir, setOpenSortDir] = useState(() => readStoredSort(PNL_OPEN_SORT_KEY, { sortBy: 'symbol', sortDir: 'asc' }).sortDir);
  const [profitSortBy, setProfitSortBy] = useState(() => readStoredSort(`${PNL_CLOSED_SORT_KEY}.profit`, { sortBy: 'sale_date', sortDir: 'desc' }).sortBy);
  const [profitSortDir, setProfitSortDir] = useState(() => readStoredSort(`${PNL_CLOSED_SORT_KEY}.profit`, { sortBy: 'sale_date', sortDir: 'desc' }).sortDir);
  const [lossSortBy, setLossSortBy] = useState(() => readStoredSort(`${PNL_CLOSED_SORT_KEY}.loss`, { sortBy: 'sale_date', sortDir: 'desc' }).sortBy);
  const [lossSortDir, setLossSortDir] = useState(() => readStoredSort(`${PNL_CLOSED_SORT_KEY}.loss`, { sortBy: 'sale_date', sortDir: 'desc' }).sortDir);
  const [openRowOrder, setOpenRowOrder] = useState(() => readStoredRowOrder());
  const [useManualRowOrder, setUseManualRowOrder] = useState(() => readStoredManualRowOrder());
  const [openDraggingIdx, setOpenDraggingIdx] = useState(null);
  const [openDropGap, setOpenDropGap] = useState(null);
  const openDragIdxRef = useRef(null);
  const openDropGapRef = useRef(null);
  const displayOpenGroupsRef = useRef([]);
  const openRowsRef = useRef([]);
  const openRowOrderRef = useRef(openRowOrder);
  const useManualRowOrderRef = useRef(useManualRowOrder);
  openRowOrderRef.current = openRowOrder;
  useManualRowOrderRef.current = useManualRowOrder;
  const topSplitRef = useRef(null);
  const periodDragRef = useRef(false);
  const periodStartXRef = useRef(0);
  const periodStartWidthRef = useRef(0);
  const [periodPaneWidth, setPeriodPaneWidth] = useState(() => readPeriodPaneWidth());

  const intraday = useIntradayPatchOptional();
  const { setPageLive, liveActive } = usePageLive(PNL_PAGE_ID);
  const { overlayPnlRows, refreshTick } = usePatchOverlay(PNL_PAGE_ID);
  const [priceRefreshBusy, setPriceRefreshBusy] = useState(false);
  const [priceRefreshNote, setPriceRefreshNote] = useState('');

  const displayOpenGroups = useMemo(() => {
    const patched = overlayPnlRows(openRows);
    let groups = buildOpenSymbolGroups(patched);
    if (useManualRowOrder && openRowOrder.length) {
      groups = applySavedOrder(groups, openRowOrder, pnlOpenGroupKey);
    } else {
      groups = sortRows(groups, openSortBy, openSortDir, openGroupSortValue);
    }
    return groups;
  }, [openRows, openRowOrder, useManualRowOrder, openSortBy, openSortDir, overlayPnlRows, refreshTick]);

  openRowsRef.current = openRows;
  displayOpenGroupsRef.current = displayOpenGroups;

  const periodOpenRows = useMemo(
    () => overlayPnlRows(openRows),
    [openRows, overlayPnlRows, refreshTick],
  );

  const closedTradesAll = useMemo(
    () => [...profitRows, ...lossRows],
    [profitRows, lossRows],
  );

  const onPeriodDividerMouseDown = useCallback((e) => {
    e.preventDefault();
    periodDragRef.current = true;
    periodStartXRef.current = e.clientX;
    periodStartWidthRef.current = periodPaneWidth;
    function onMouseMove(ev) {
      if (!periodDragRef.current) return;
      const total = topSplitRef.current?.clientWidth || 1200;
      const maxW = Math.max(PNL_PERIOD_PANE_MIN, total - PNL_OPEN_PANE_MIN - 4);
      const next = periodStartWidthRef.current - (ev.clientX - periodStartXRef.current);
      setPeriodPaneWidth(Math.max(PNL_PERIOD_PANE_MIN, Math.min(maxW, next)));
    }
    function onMouseUp() {
      periodDragRef.current = false;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      setPeriodPaneWidth((w) => {
        writePeriodPaneWidth(w);
        return w;
      });
    }
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, [periodPaneWidth]);

  const clearOpenDnD = useCallback(() => {
    openDragIdxRef.current = null;
    openDropGapRef.current = null;
    setOpenDropGap(null);
    setOpenDraggingIdx(null);
  }, []);

  const handleOpenDragStart = useCallback((e, idx) => {
    openDragIdxRef.current = idx;
    setOpenDraggingIdx(idx);
    const group = displayOpenGroupsRef.current[idx];
    if (!group) return;
    setListDragImage(e.dataTransfer, group.symbol, null);
  }, []);

  const handleOpenDragOver = useCallback((e, idx) => {
    if (openDragIdxRef.current === null) return;
    e.preventDefault();
    const gap = insertionGapFromRowHover(e.clientY, e.currentTarget, idx, displayOpenGroupsRef.current.length);
    openDropGapRef.current = gap;
    setOpenDropGap(gap);
  }, []);

  const handleOpenDrop = useCallback((e) => {
    e.preventDefault();
    const from = openDragIdxRef.current;
    const gap = openDropGapRef.current;
    clearOpenDnD();
    if (from === null || gap === null || gap === undefined) return;
    const list = displayOpenGroupsRef.current;
    const keys = list.map(pnlOpenGroupKey);
    const nextKeys = reorderByGap(keys, from, gap);
    if (JSON.stringify(nextKeys) === JSON.stringify(keys)) return;
    setOpenRowOrder(nextKeys);
    setUseManualRowOrder(true);
    writeStoredRowOrder(nextKeys);
    writeStoredManualRowOrder(true);
  }, [clearOpenDnD]);

  const handleOpenDragEnd = useCallback(() => {
    clearOpenDnD();
  }, [clearOpenDnD]);

  const handleOpenSort = useCallback((colKey) => {
    const next = toggleSort(openSortBy, openSortDir, colKey);
    setOpenSortBy(next.sortBy);
    setOpenSortDir(next.sortDir);
    writeStoredSort(PNL_OPEN_SORT_KEY, next.sortBy, next.sortDir);
    setUseManualRowOrder(false);
    writeStoredManualRowOrder(false);
  }, [openSortBy, openSortDir]);

  const handleProfitSort = useCallback((colKey) => {
    const next = toggleSort(profitSortBy, profitSortDir, colKey);
    setProfitSortBy(next.sortBy);
    setProfitSortDir(next.sortDir);
    writeStoredSort(`${PNL_CLOSED_SORT_KEY}.profit`, next.sortBy, next.sortDir);
  }, [profitSortBy, profitSortDir]);

  const handleLossSort = useCallback((colKey) => {
    const next = toggleSort(lossSortBy, lossSortDir, colKey);
    setLossSortBy(next.sortBy);
    setLossSortDir(next.sortDir);
    writeStoredSort(`${PNL_CLOSED_SORT_KEY}.loss`, next.sortBy, next.sortDir);
  }, [lossSortBy, lossSortDir]);

  const load = useCallback(async ({ preserveRowOrder = false } = {}) => {
    const prevGroups = preserveRowOrder ? [...displayOpenGroupsRef.current] : [];
    const prevKeys = preserveRowOrder
      ? (openRowOrderRef.current.length ? openRowOrderRef.current : prevGroups.map(pnlOpenGroupKey))
      : [];
    try {
      const [openRes, closedRes, pfRes] = await Promise.all([
        axios.get(`${API}/api/pnl/open`),
        axios.get(`${API}/api/pnl/closed`),
        axios.get(`${API}/api/portfolio`),
      ]);
      const newRows = openRes.data?.data || [];
      setOpenRows(newRows);
      setAsOfDate(openRes.data?.as_of_date || null);
      setAvailableCash(Number(openRes.data?.available_cash) || 0);
      setProfitRows(closedRes.data?.profit || []);
      setLossRows(closedRes.data?.loss || []);
      const stocks = (pfRes.data?.items || [])
        .filter((it) => it.type === 'stock')
        .map((it) => String(it.symbol).toUpperCase());
      setPortfolioStocks(stocks);

      if (preserveRowOrder && prevKeys.length > 0 && newRows.length > 0) {
        const newGroups = buildOpenSymbolGroups(newRows);
        const nextOrder = reconcilePnlGroupOrder(prevKeys, newGroups, prevGroups);
        setOpenRowOrder(nextOrder);
        writeStoredRowOrder(nextOrder);
        if (useManualRowOrderRef.current) {
          setUseManualRowOrder(true);
          writeStoredManualRowOrder(true);
        }
      } else if (newRows.length > 0 && !readStoredRowOrder().length) {
        const initial = buildOpenSymbolGroups(newRows).map(pnlOpenGroupKey);
        setOpenRowOrder(initial);
        writeStoredRowOrder(initial);
        setUseManualRowOrder(true);
        writeStoredManualRowOrder(true);
      }
    } catch {
      setOpenRows([]);
      setProfitRows([]);
      setLossRows([]);
      setAvailableCash(0);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleCashChanged = useCallback((bal) => {
    if (bal != null && Number.isFinite(Number(bal))) {
      setAvailableCash(Number(bal));
    } else {
      load({ preserveRowOrder: true });
    }
  }, [load]);

  const handlePositionSaved = useCallback(() => {
    load({ preserveRowOrder: true });
  }, [load]);

  const handleBooked = useCallback(() => {
    load({ preserveRowOrder: true });
  }, [load]);

  const handleStockAdded = useCallback(() => {
    load({ preserveRowOrder: true });
  }, [load]);

  const handleLotAdded = useCallback(() => {
    load({ preserveRowOrder: true });
  }, [load]);

  const refreshSessionPrices = useCallback(async () => {
    const symbols = [...new Set(
      (openRowsRef.current || [])
        .map((r) => String(r.symbol || '').trim().toUpperCase())
        .filter(Boolean),
    )];
    if (!symbols.length) {
      setPriceRefreshNote('No open positions to refresh');
      return;
    }
    if (!intraday?.enabled || !intraday.refreshPatch) {
      setPriceRefreshNote('');
      await load({ preserveRowOrder: true });
      return;
    }
    setPriceRefreshBusy(true);
    setPriceRefreshNote('');
    try {
      const result = await intraday.refreshPatch(symbols);
      if (result?.ok && (result.count ?? 0) > 0) {
        setPageLive?.(PNL_PAGE_ID);
        setPriceRefreshNote('');
      } else if (result?.nseError) {
        setPriceRefreshNote(String(result.nseError));
      } else {
        setPriceRefreshNote('No prices returned');
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setPriceRefreshNote(typeof detail === 'string' ? detail : 'Price refresh failed');
    } finally {
      setPriceRefreshBusy(false);
    }
  }, [intraday, setPageLive, load]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onRefresh = () => { load({ preserveRowOrder: true }); };
    const onPnlRefresh = () => { refreshSessionPrices(); };
    window.addEventListener(APP_DATA_REFRESH_EVENT, onRefresh);
    window.addEventListener(PNL_REFRESH_EVENT, onPnlRefresh);
    window.addEventListener('portfolio-updated', onRefresh);
    return () => {
      window.removeEventListener(APP_DATA_REFRESH_EVENT, onRefresh);
      window.removeEventListener(PNL_REFRESH_EVENT, onPnlRefresh);
      window.removeEventListener('portfolio-updated', onRefresh);
    };
  }, [load, refreshSessionPrices]);

  const selectedSymbol = useMemo(() => {
    if (!selectedKey) return null;
    const g = displayOpenGroups.find((gr) => pnlOpenGroupKey(gr) === selectedKey);
    return g?.symbol ?? null;
  }, [selectedKey, displayOpenGroups]);

  const handleSelectGroup = useCallback((group) => {
    setSelectedKey(pnlOpenGroupKey(group));
  }, []);

  const handleBookGroup = useCallback((group) => {
    setBookTarget({
      symbol: group.symbol,
      totalQty: group.totals?.qty,
      isPlaceholder: group.isPlaceholder,
      lots: group.lots ?? [],
    });
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div
        style={{
          height: 40,
          flexShrink: 0,
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'var(--bg-secondary)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 12px',
          gap: 8,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>P&amp;L</span>
        {priceRefreshBusy && (
          <span style={{ fontSize: 11, color: 'var(--accent-blue)' }}>Refreshing prices…</span>
        )}
        {!priceRefreshBusy && liveActive && (
          <span style={{ fontSize: 11, color: 'var(--accent-green)' }}>Session prices</span>
        )}
        {!priceRefreshBusy && !liveActive && asOfDate && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            Prices as of {asOfDate}
          </span>
        )}
        {priceRefreshNote && (
          <span style={{ fontSize: 11, color: 'var(--accent-red)' }}>{priceRefreshNote}</span>
        )}
        {useManualRowOrder && displayOpenGroups.length > 1 && (
          <span style={{ fontSize: 11, color: 'var(--accent-blue)' }}>
            Manual order
          </span>
        )}
        <div style={{ flex: 1 }} />
        <PnlToolbarButton onClick={() => setAddStockOpen(true)}>
          Add stock
        </PnlToolbarButton>
        <PnlToolbarButton onClick={() => setAddLotOpen(true)} disabled={!portfolioStocks.length}>
          Add lot
        </PnlToolbarButton>
        {selectedSymbol && (
          <PnlToolbarButton onClick={() => onOpenChart && onOpenChart(selectedSymbol)}>
            Open Full Chart ↗
          </PnlToolbarButton>
        )}
      </div>

      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div
          ref={topSplitRef}
          style={{
            flex: 1,
            minHeight: 0,
            display: 'flex',
            flexDirection: 'row',
            borderBottom: '2px solid var(--border)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              flex: '1 1 0',
              minWidth: PNL_OPEN_PANE_MIN,
              minHeight: 0,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {loading ? (
              <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>Loading…</div>
            ) : (
              <OpenGrid
                groups={displayOpenGroups}
                selectedKey={selectedKey}
                onSelectGroup={handleSelectGroup}
                onBook={handleBookGroup}
                onPositionSaved={handlePositionSaved}
                sortBy={openSortBy}
                sortDir={openSortDir}
                onSort={handleOpenSort}
                rowDrag={displayOpenGroups.length > 1}
                draggingIdx={openDraggingIdx}
                dropGap={openDropGap}
                onDragStart={handleOpenDragStart}
                onDragOver={handleOpenDragOver}
                onDrop={handleOpenDrop}
                onDragEnd={handleOpenDragEnd}
              />
            )}
          </div>
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize period panel"
            onMouseDown={onPeriodDividerMouseDown}
            style={{
              width: 4,
              flexShrink: 0,
              backgroundColor: 'var(--border)',
              cursor: 'col-resize',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--accent-blue)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'var(--border)'; }}
          />
          <div
            style={{
              width: periodPaneWidth,
              minWidth: PNL_PERIOD_PANE_MIN,
              flexShrink: 0,
              minHeight: 0,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              borderLeft: '1px solid var(--border-light)',
            }}
          >
            {loading ? (
              <div style={{ padding: 12, fontSize: 11, color: 'var(--text-muted)' }}>Loading…</div>
            ) : (
              <PnLPeriodPanel
                openRows={periodOpenRows}
                closedTrades={closedTradesAll}
                availableCash={availableCash}
                onImported={handlePositionSaved}
                onCashChanged={handleCashChanged}
              />
            )}
          </div>
        </div>
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          <ClosedGrid
            title="Profit"
            titleColor="var(--accent-green)"
            rows={profitRows}
            isLoss={false}
            widthKeyPrefix="pnl_profit_"
            sortBy={profitSortBy}
            sortDir={profitSortDir}
            onSort={handleProfitSort}
          />
          <ClosedGrid
            title="Loss"
            titleColor="var(--accent-red)"
            rows={lossRows}
            isLoss
            widthKeyPrefix="pnl_loss_"
            sortBy={lossSortBy}
            sortDir={lossSortDir}
            onSort={handleLossSort}
          />
        </div>
      </div>

      {bookTarget && (
        <PnLBookDialog
          bookTarget={bookTarget}
          onClose={() => setBookTarget(null)}
          onBooked={handleBooked}
        />
      )}
      {addStockOpen && (
        <AddStockDialog
          onClose={() => setAddStockOpen(false)}
          onAdded={handleStockAdded}
        />
      )}
      {addLotOpen && (
        <AddLotDialog
          portfolioStocks={portfolioStocks}
          onClose={() => setAddLotOpen(false)}
          onAdded={handleLotAdded}
        />
      )}
    </div>
  );
}
