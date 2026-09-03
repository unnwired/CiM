import React, { useState, useEffect, useLayoutEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import BasketToolbarButton from '../components/Basket';
import { startBasketSymbolDrag } from '../utils/basketDnD';
import ExternalFinancialsLinks from '../components/ExternalFinancialsLinks';
import EarningsQuarterlyPanel from '../components/EarningsQuarterlyPanel';
import EarningsPlusInlineMark from '../components/EarningsPlusInlineMark';
import {
  EARNINGS_REPORTED_COLUMN_COUNT,
  EARNINGS_UPCOMING_COLUMN_COUNT,
  REPORTED_COLGROUP,
  UPCOMING_COLGROUP,
  earningsTableMinWidthPx,
} from '../config/earningsTableLayout';
import { formatMarketCap, parseMarketCapInput } from '../utils/formatMarketCap';
import { CHART_DATA_UPDATED_EVENT } from '../chartEvents';
import { isDistributionProfile } from '../config/exportProfile';
import { usePageLive } from '../intraday/pageLiveContext';
import { usePatchOverlay } from '../intraday/usePatchOverlay';
import { useRegisterIntradaySymbols } from '../intraday/useRegisterIntradaySymbols';
import { useRegisterFocusedSymbol } from '../intraday/useRegisterFocusedSymbol';
import { attachEarningsMonthRefClose } from '../intraday/patchOverlay';

const API = '';
const MIN_YEAR = 2024;
const FILTERS_STORAGE_KEY = isDistributionProfile
  ? 'cim.earningsBeats.filters.distribution'
  : 'cim.earningsBeats.filters';
const DIST_FILTERS_DEFAULTS_VERSION_KEY = 'cim.earningsBeats.filters.distribution.version';
const DIST_FILTERS_DEFAULTS_VERSION = 'v1-clean';
const FILTER_INPUT_CLASS = 'earnings-filter-input';
const EARNINGS_NOTIFY_KEY = isDistributionProfile
  ? 'cim.earningsBeats.notifications.distribution'
  : 'cim.earningsBeats.notifications';
const BEAT_HINT = '* Empty = no bound. Min 0 = met or beat (0% included). If EPS beat is missing (—) but revenue beat exists for the quarter (or vice versa), the row is kept.';

/** Short search tokens → canonical Market Sector tag (uppercase). */
const EARNINGS_SECTOR_SEARCH_ALIASES = {
  OIL: 'OIL & GAS',
  IT: 'IT',
  AUTO: 'AUTO',
  FMCG: 'FMCG',
  PHARMA: 'PHARMA',
  BANK: 'BANK',
  BANKS: 'BANK',
  DEFENCE: 'DEFENCE',
  DEFENSE: 'DEFENCE',
  TELECOM: 'TELECOM',
  CHEM: 'CHEMICALS',
  CHEMICAL: 'CHEMICALS',
  CONSUMER: 'CONSUMPTION',
  FIN: 'FINANCIAL SERVICES',
  FINANCIALS: 'FINANCIAL SERVICES',
};

function earningsSectorTags(row) {
  if (Array.isArray(row?.market_sectors) && row.market_sectors.length) {
    return row.market_sectors.map((s) => String(s || '').trim()).filter(Boolean);
  }
  return String(row?.market_sector || '')
    .split('·')
    .map((s) => s.trim())
    .filter(Boolean);
}

function tokenMatchesSectorTag(tok, tag) {
  const k = String(tok || '').trim().toUpperCase();
  const t = String(tag || '').trim().toUpperCase();
  if (!k || !t) return false;
  if (t === k) return true;
  // Prefix on whole tag: "FIN" → "FINANCIAL SERVICES" (never mid-word: "IT" ⊂ "COMMODITIES")
  if (t.startsWith(`${k} `) || t.startsWith(`${k}&`) || t.startsWith(`${k}-`)) return true;
  const parts = t.split(/[\s&/\-·•|/]+/).filter(Boolean);
  return parts.some((p) => p === k || (k.length >= 3 && p.startsWith(k)));
}

/** True if this search token matches the row (sector tags and/or symbol/name). */
function tokenMatchesEarningsRow(tok, sym, name, tags) {
  const k = String(tok || '').trim().toUpperCase();
  if (!k) return false;
  const aliased = EARNINGS_SECTOR_SEARCH_ALIASES[k];
  // Known short sector codes: exact tag only (IT → IT, never COMMODITIES / ITC).
  if (aliased) {
    return tags.some((tag) => String(tag || '').trim().toUpperCase() === aliased);
  }
  if (tags.some((tag) => tokenMatchesSectorTag(k, tag))) return true;
  if (sym === k || sym.startsWith(k)) return true;
  if (k.length <= 2) {
    return new RegExp(`(?:^|[^A-Z0-9])${k}(?:[^A-Z0-9]|$)`).test(name);
  }
  return sym.includes(k) || name.includes(k);
}

const MONTH_OPTIONS = [
  { value: 0, label: 'All months' },
  { value: 1, label: 'January' },
  { value: 2, label: 'February' },
  { value: 3, label: 'March' },
  { value: 4, label: 'April' },
  { value: 5, label: 'May' },
  { value: 6, label: 'June' },
  { value: 7, label: 'July' },
  { value: 8, label: 'August' },
  { value: 9, label: 'September' },
  { value: 10, label: 'October' },
  { value: 11, label: 'November' },
  { value: 12, label: 'December' },
];

/** Upcoming: TradingView-aligned date windows + existing month / coming-week extras. */
const PERIOD_OPTIONS = [
  { value: 'current_trading_day', label: 'Current trading day' },
  { value: 'next_day', label: 'Next day' },
  { value: 'next_5_days', label: 'Next 5 days' },
  { value: 'this_week', label: 'This week' },
  { value: 'next_week', label: 'Next week' },
  { value: 'this_month', label: 'This month' },
  { value: 'next_month', label: 'Next month' },
  { value: 'month_after', label: 'Month after' },
  { value: 'coming_week', label: 'Coming week' },
];

/** Reported: TV Recent windows (CTD spans Fri→weekend on Sat/Sun). */
const REPORTED_FRESHNESS_OPTIONS = [
  { value: 'current_trading_day', label: 'Current trading day' },
  { value: 'previous_day', label: 'Previous day' },
  { value: 'previous_5_days', label: 'Previous 5 days' },
  { value: 'this_week', label: 'This week' },
  { value: 'prev_week', label: 'Previous week' },
];
const REPORTED_FRESHNESS_VALUES = new Set(REPORTED_FRESHNESS_OPTIONS.map(o => o.value));

const LEGACY_PERIOD_ALIASES = {
  today: 'current_trading_day',
};
const LEGACY_REPORT_WINDOW_ALIASES = {
  today: 'current_trading_day',
  yesterday: 'previous_day',
  today_yesterday: 'current_trading_day',
  today_and_yesterday: 'current_trading_day',
  previous_week: 'prev_week',
};

function migratePeriod(raw) {
  const v = LEGACY_PERIOD_ALIASES[raw] || raw;
  return PERIOD_OPTIONS.some(o => o.value === v) ? v : 'this_month';
}

function migrateReportWindow(raw) {
  const v = LEGACY_REPORT_WINDOW_ALIASES[raw] || raw;
  return REPORTED_FRESHNESS_VALUES.has(v) ? v : 'month';
}

const UPCOMING_NAMED_PERIODS = new Set([
  'current_trading_day',
  'next_day',
  'next_5_days',
  'this_week',
  'next_week',
  'coming_week',
]);

const EARNINGS_PLUS_FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'only', label: 'Earnings+ only' },
  { value: 'exclude', label: 'Exclude Earnings+' },
  { value: 'tv_eps_rev_beat', label: 'TV EPS plus revenue beat' },
];

function availableYears() {
  const max = new Date().getFullYear();
  const years = [];
  for (let y = max; y >= MIN_YEAR; y -= 1) years.push(y);
  return years;
}

function defaultMonth() {
  return new Date().getMonth() + 1;
}

function defaultYear() {
  return new Date().getFullYear();
}

function currentCalendar() {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

/** Reported earnings: future months in the selected year are not selectable (no data yet). */
function isReportedMonthSelectable(year, monthValue) {
  if (monthValue === 0) return true;
  const { year: yNow, month: mNow } = currentCalendar();
  const y = Number(year);
  const m = Number(monthValue);
  if (!Number.isFinite(y) || !Number.isFinite(m) || m < 1 || m > 12) return false;
  if (y < yNow) return true;
  if (y > yNow) return false;
  return m <= mNow;
}

function clampReportedMonth(year, monthValue) {
  if (isReportedMonthSelectable(year, monthValue)) return monthValue;
  const { year: yNow, month: mNow } = currentCalendar();
  if (Number(year) === yNow) return mNow;
  return 0;
}

/** Parse a numeric cell; null/undefined/'' stay missing (Number(null) is 0 — never treat as 0%). */
function toFiniteNumber(val) {
  if (val == null || val === '') return null;
  const n = Number(val);
  return Number.isFinite(n) ? n : null;
}

function fmtPct(val) {
  const n = toFiniteNumber(val);
  if (n == null) return '—';
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

function fmtEps(val) {
  const n = toFiniteNumber(val);
  if (n == null) return '—';
  return n.toFixed(2);
}

function fmtPrice(val) {
  if (val == null || val === '') return '—';
  const n = Number(val);
  if (!Number.isFinite(n) || n <= 0) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPe(val) {
  const n = toFiniteNumber(val);
  if (n == null) return '—';
  return n.toFixed(1);
}

function chgPctColor(val) {
  const n = toFiniteNumber(val);
  if (n == null) return 'var(--text-muted)';
  if (n > 0) return 'var(--accent-green)';
  if (n < 0) return 'var(--accent-red)';
  return 'var(--text-secondary)';
}

/** True when user entered a bound (including 0). Empty field = no bound. */
function surpriseBoundIsSet(raw) {
  return String(raw ?? '').trim() !== '';
}

/** Parse surprise % filter; empty = no bound, NaN = invalid. 0 is valid (meet or beat). */
function parseSurprisePct(raw) {
  if (!surpriseBoundIsSet(raw)) return undefined;
  const n = Number(String(raw).trim());
  if (!Number.isFinite(n)) return NaN;
  return n;
}

function compareValues(a, b, key) {
  if (key === 'symbol' || key === 'market_sector') {
    return String(a[key] || '').localeCompare(String(b[key] || ''));
  }
  const dateKeys = new Set(['earnings_release_date', 'earnings_release_next_date']);
  if (dateKeys.has(key)) {
    return String(a[key] || '').localeCompare(String(b[key] || ''));
  }
  const na = toFiniteNumber(a[key]);
  const nb = toFiniteNumber(b[key]);
  if (na == null && nb == null) return 0;
  if (na == null) return 1;
  if (nb == null) return -1;
  return na - nb;
}

const thStyle = {
  textAlign: 'left',
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  padding: '8px 10px',
  borderBottom: '1px solid var(--border)',
  whiteSpace: 'nowrap',
  cursor: 'pointer',
  userSelect: 'none',
};

const tdStyle = {
  padding: '8px 10px',
  fontSize: 12,
  borderBottom: '1px solid var(--border-light)',
  whiteSpace: 'nowrap',
};

const selectStyle = {
  padding: '5px 8px',
  borderRadius: 5,
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-tertiary)',
  color: 'var(--text-secondary)',
  fontSize: 12,
  colorScheme: 'dark',
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '5px 8px',
  borderRadius: 5,
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-tertiary)',
  color: 'var(--text-secondary)',
  fontSize: 12,
};

const selectFullStyle = {
  ...selectStyle,
  width: '100%',
  boxSizing: 'border-box',
  marginLeft: 0,
};

/** Fixed column widths so row 1 and row 2 field controls line up vertically. */
const FILTER_COL = {
  earnings: 118,
  year: 84,
  month: 168,
  mcapMin: 112,
  mcapMax: 96,
};

/** Fixed field columns + auto action column (buttons stay beside Max, not far right). */
const filterGridCols = `${FILTER_COL.earnings}px ${FILTER_COL.year}px ${FILTER_COL.month}px ${FILTER_COL.mcapMin}px ${FILTER_COL.mcapMax}px auto`;

const filterGridStyle = {
  display: 'grid',
  gridTemplateColumns: filterGridCols,
  columnGap: 10,
  alignItems: 'end',
  justifyContent: 'start',
  width: 'max-content',
  maxWidth: '100%',
};

const filterStackGap = 5;

const filterLabelStyle = {
  fontSize: 10,
  color: 'var(--text-muted)',
  lineHeight: 1.2,
  textAlign: 'left',
  width: '100%',
};

const actionBtnBase = {
  padding: '6px 12px',
  borderRadius: 5,
  fontSize: 12,
  fontWeight: 600,
  whiteSpace: 'nowrap',
};

function FilterField({ label, children, width, disabled = false }) {
  return (
    <div style={{
      width: width ?? '100%',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'flex-start',
      gap: 3,
      minWidth: 0,
      opacity: disabled ? 0.45 : 1,
    }}
    >
      <span style={filterLabelStyle}>{label}</span>
      <div style={{ width: '100%', minWidth: 0 }}>{children}</div>
    </div>
  );
}

/**
 * Themed select with marquee label when text overflows.
 * Custom listbox (not native popup) so the open menu matches CiM dark chrome.
 */
function OverflowMarqueeSelect({
  value,
  onChange,
  options,
  disabled = false,
  style,
  title,
  'aria-label': ariaLabel,
}) {
  const rootRef = useRef(null);
  const viewportRef = useRef(null);
  const textRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [travelPx, setTravelPx] = useState(0);
  const selected = options.find((o) => o.value === value);
  const label = selected?.label || String(value || '');

  const measure = useCallback(() => {
    const vp = viewportRef.current;
    const tx = textRef.current;
    if (!vp || !tx) {
      setTravelPx(0);
      return;
    }
    const overflow = Math.ceil(tx.scrollWidth - vp.clientWidth);
    setTravelPx(overflow > 1 ? overflow : 0);
  }, []);

  useLayoutEffect(() => {
    measure();
  }, [label, style, disabled, measure]);

  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => measure());
    ro.observe(vp);
    return () => ro.disconnect();
  }, [measure]);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const overflows = travelPx > 0;
  const faceStyle = {
    ...style,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    width: '100%',
    boxSizing: 'border-box',
    minHeight: 28,
    color: disabled ? 'var(--text-muted)' : (style?.color || 'var(--text-secondary)'),
    cursor: disabled ? 'not-allowed' : 'pointer',
    textAlign: 'left',
    appearance: 'none',
    WebkitAppearance: 'none',
  };

  const pick = (next) => {
    setOpen(false);
    if (next === value) return;
    onChange({ target: { value: next } });
  };

  return (
    <div ref={rootRef} style={{ position: 'relative', width: '100%', minWidth: 0 }}>
      <button
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={title}
        onClick={() => {
          if (!disabled) setOpen((v) => !v);
        }}
        style={faceStyle}
      >
        <div
          ref={viewportRef}
          style={{
            flex: 1,
            minWidth: 0,
            overflow: 'hidden',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <span
            ref={textRef}
            className={overflows ? 'cim-select-marquee' : undefined}
            style={{
              display: 'inline-block',
              whiteSpace: 'nowrap',
              fontSize: 12,
              lineHeight: 1.2,
              color: 'inherit',
              ...(overflows
                ? { '--cim-marquee-travel': `${travelPx}px` }
                : {}),
            }}
          >
            {label}
          </span>
        </div>
        <span
          aria-hidden
          style={{
            flex: '0 0 auto',
            width: 0,
            height: 0,
            borderLeft: '4px solid transparent',
            borderRight: '4px solid transparent',
            borderTop: `5px solid ${disabled ? 'var(--text-muted)' : 'var(--text-secondary)'}`,
            opacity: 0.85,
            marginRight: 2,
          }}
        />
      </button>
      {open && !disabled && (
        <div
          role="listbox"
          aria-label={ariaLabel}
          style={{
            position: 'absolute',
            left: 0,
            top: '100%',
            marginTop: 4,
            zIndex: 40,
            minWidth: '100%',
            width: 'max-content',
            maxWidth: 320,
            maxHeight: 240,
            overflowY: 'auto',
            backgroundColor: 'var(--bg-secondary, #161b22)',
            border: '1px solid var(--border, #30363d)',
            borderRadius: 6,
            boxShadow: '0 10px 28px rgba(0,0,0,0.55)',
            padding: 4,
            color: 'var(--text-secondary, #8b949e)',
          }}
        >
          {options.map((option) => {
            if (option.disabled) {
              return (
                <div
                  key={option.value}
                  aria-hidden
                  style={{
                    padding: '5px 10px',
                    fontSize: 11,
                    color: 'var(--text-muted, #484f58)',
                    cursor: 'default',
                    userSelect: 'none',
                  }}
                >
                  {option.label}
                </div>
              );
            }
            const active = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => pick(option.value)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '7px 10px',
                  borderRadius: 4,
                  border: 'none',
                  backgroundColor: active ? 'var(--bg-active, #2d333b)' : 'transparent',
                  color: active ? 'var(--text-primary, #e6edf3)' : 'var(--text-secondary, #8b949e)',
                  fontSize: 12,
                  fontWeight: active ? 600 : 400,
                  whiteSpace: 'nowrap',
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => {
                  if (!active) e.currentTarget.style.backgroundColor = 'var(--bg-hover, #21262d)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = active ? 'var(--bg-active, #2d333b)' : 'transparent';
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function controlStyle(base, disabled) {
  if (!disabled) return base;
  return { ...base, opacity: 0.85, cursor: 'not-allowed' };
}

function SortableTh({ label, sortKey, activeKey, sortDir, onSort, style }) {
  const active = activeKey === sortKey;
  const arrow = active ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';
  return (
    <th
      style={{ ...thStyle, ...style, cursor: 'pointer' }}
      onClick={() => onSort(sortKey)}
      title="Click to sort"
    >
      {label}
      {arrow}
    </th>
  );
}

const REPORTED_SORT_KEYS = new Set([
  'symbol', 'market_sector', 'market_cap_basic', 'price', 'price_earnings_ttm', 'change_1d_pct', 'change_1m_pct',
  'earnings_release_date',
  'eps_actual', 'eps_estimate', 'eps_surprise_pct',
  'revenue_actual', 'revenue_estimate', 'revenue_surprise_pct',
]);

const UPCOMING_SORT_KEYS = new Set([
  'symbol', 'market_sector', 'market_cap_basic', 'price', 'price_earnings_ttm', 'change_1d_pct', 'change_1m_pct',
  'earnings_release_next_date',
  'eps_estimate', 'revenue_estimate',
]);

function defaultSort(mode) {
  return mode === 'upcoming'
    ? { key: 'earnings_release_next_date', dir: 'asc' }
    : { key: 'revenue_surprise_pct', dir: 'desc' };
}

function normalizeSortEntry(entry, mode) {
  const valid = mode === 'upcoming' ? UPCOMING_SORT_KEYS : REPORTED_SORT_KEYS;
  if (
    entry?.key
    && valid.has(entry.key)
    && (entry.dir === 'asc' || entry.dir === 'desc')
  ) {
    return { key: entry.key, dir: entry.dir };
  }
  return defaultSort(mode);
}

function loadPersistedFilters() {
  if (typeof window === 'undefined') return null;
  try {
    if (isDistributionProfile) {
      const migrated = window.localStorage.getItem(DIST_FILTERS_DEFAULTS_VERSION_KEY);
      if (migrated !== DIST_FILTERS_DEFAULTS_VERSION) {
        window.localStorage.removeItem(FILTERS_STORAGE_KEY);
        window.localStorage.setItem(DIST_FILTERS_DEFAULTS_VERSION_KEY, DIST_FILTERS_DEFAULTS_VERSION);
        return null;
      }
    }
    const raw = window.localStorage.getItem(FILTERS_STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    const mode = p.mode === 'upcoming' ? 'upcoming' : 'reported';
    const month = Number(p.month);
    const year = Number(p.year);
    const maxYear = new Date().getFullYear();
    const period = migratePeriod(p.period);
    const reportWindow = migrateReportWindow(p.reportWindow);
    const sortByMode = {};
    if (p.sortByMode && typeof p.sortByMode === 'object') {
      if (p.sortByMode.reported) {
        sortByMode.reported = normalizeSortEntry(p.sortByMode.reported, 'reported');
      }
      if (p.sortByMode.upcoming) {
        sortByMode.upcoming = normalizeSortEntry(p.sortByMode.upcoming, 'upcoming');
      }
    }
    return {
      mode,
      month: Number.isFinite(month) && month >= 0 && month <= 12 ? month : defaultMonth(),
      year: Number.isFinite(year) && year >= MIN_YEAR && year <= maxYear ? year : defaultYear(),
      period,
      reportWindow,
      mcapMin: typeof p.mcapMin === 'string' ? p.mcapMin : '',
      mcapMax: typeof p.mcapMax === 'string' ? p.mcapMax : '',
      epsSurpriseMin: typeof p.epsSurpriseMin === 'string' ? p.epsSurpriseMin : '',
      epsSurpriseMax: typeof p.epsSurpriseMax === 'string' ? p.epsSurpriseMax : '',
      revenueSurpriseMin: typeof p.revenueSurpriseMin === 'string' ? p.revenueSurpriseMin : '',
      revenueSurpriseMax: typeof p.revenueSurpriseMax === 'string' ? p.revenueSurpriseMax : '',
      earningsPlusFilter: EARNINGS_PLUS_FILTER_OPTIONS.some(option => option.value === p.earningsPlusFilter)
        ? p.earningsPlusFilter
        : 'all',
      sortByMode,
    };
  } catch {
    return null;
  }
}

function persistFilters(filters) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(filters));
  } catch {
    // ignore quota / private mode
  }
}

function loadEarningsNotifyEnabled() {
  try {
    return window.localStorage.getItem(EARNINGS_NOTIFY_KEY) === '1';
  } catch {
    return false;
  }
}

function persistEarningsNotifyEnabled(on) {
  try {
    window.localStorage.setItem(EARNINGS_NOTIFY_KEY, on ? '1' : '0');
  } catch {
    // ignore
  }
}

function shiftCalendarMonth(year, month, delta) {
  let idx = year * 12 + (month - 1) + delta;
  return { year: Math.floor(idx / 12), month: (idx % 12) + 1 };
}

/** Period shown beside page title (e.g. May 2026, Coming week). */
function headerPeriodLabel(mode, month, year, period, reportWindow = 'month') {
  if (mode === 'upcoming') {
    const named = migratePeriod(period);
    if (UPCOMING_NAMED_PERIODS.has(named)) {
      return PERIOD_OPTIONS.find(o => o.value === named)?.label || named;
    }
    const delta = named === 'this_month' ? 0 : named === 'next_month' ? 1 : 2;
    const now = new Date();
    const { year: y, month: m } = shiftCalendarMonth(now.getFullYear(), now.getMonth() + 1, delta);
    const name = MONTH_OPTIONS.find(o => o.value === m)?.label;
    return name ? `${name} ${y}` : String(y);
  }
  const rw = migrateReportWindow(reportWindow);
  if (REPORTED_FRESHNESS_VALUES.has(rw)) {
    return REPORTED_FRESHNESS_OPTIONS.find(o => o.value === rw)?.label || rw;
  }
  if (month === 0) return `${year} (all months)`;
  const name = MONTH_OPTIONS.find(o => o.value === month)?.label;
  return name ? `${name} ${year}` : String(year);
}

function statusSummary(mode, month, year, period, reportWindow = 'month') {
  const periodLabel = headerPeriodLabel(mode, month, year, period, reportWindow);
  return mode === 'upcoming' ? `Upcoming · ${periodLabel}` : `Reported · ${periodLabel}`;
}

export default function EarningsBeatsPage({
  onOpenChart,
  isActive,
  onContextMenuRequest,
  onAddStocksToWatchlist,
  watchlists = [],
  onGoToWatchlist,
  onRefreshEarningsPlusCache,
  earningsPlusRefreshRunning = false,
}) {
  const saved = useMemo(() => loadPersistedFilters(), []);
  const initialMode = saved?.mode ?? 'reported';
  const initialSort = saved?.sortByMode?.[initialMode] ?? defaultSort(initialMode);

  const [mode, setMode] = useState(initialMode);
  const [month, setMonth] = useState(saved?.month ?? defaultMonth());
  const [year, setYear] = useState(saved?.year ?? defaultYear());
  const [period, setPeriod] = useState(saved?.period ?? 'this_month');
  const [reportWindow, setReportWindow] = useState(saved?.reportWindow ?? 'month');
  const [mcapMin, setMcapMin] = useState(saved?.mcapMin ?? '');
  const [mcapMax, setMcapMax] = useState(saved?.mcapMax ?? '');
  const [mcapDebounced, setMcapDebounced] = useState({
    min: saved?.mcapMin ?? '',
    max: saved?.mcapMax ?? '',
  });
  const [epsSurpriseMin, setEpsSurpriseMin] = useState(saved?.epsSurpriseMin ?? '');
  const [epsSurpriseMax, setEpsSurpriseMax] = useState(saved?.epsSurpriseMax ?? '');
  const [revenueSurpriseMin, setRevenueSurpriseMin] = useState(saved?.revenueSurpriseMin ?? '');
  const [revenueSurpriseMax, setRevenueSurpriseMax] = useState(saved?.revenueSurpriseMax ?? '');
  const [earningsPlusFilter, setEarningsPlusFilter] = useState(saved?.earningsPlusFilter ?? 'all');
  const [surpriseDebounced, setSurpriseDebounced] = useState({
    epsMin: saved?.epsSurpriseMin ?? '',
    epsMax: saved?.epsSurpriseMax ?? '',
    revMin: saved?.revenueSurpriseMin ?? '',
    revMax: saved?.revenueSurpriseMax ?? '',
  });
  const [sortByMode, setSortByMode] = useState(saved?.sortByMode ?? {
    [initialMode]: initialSort,
  });
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [selectedSymbols, setSelectedSymbols] = useState(() => new Set());
  const [lastSelectedIndex, setLastSelectedIndex] = useState(null);
  const [expandedSymbol, setExpandedSymbol] = useState(null);
  /** Screener basis from the open quarterly sheet — drives footer Screener URL. */
  const [screenerBasisBySymbol, setScreenerBasisBySymbol] = useState({});
  const [wlPickOpen, setWlPickOpen] = useState(false);
  const [addMenuMode, setAddMenuMode] = useState(null);
  const wlPickWrapRef = useRef(null);
  const [symbolSearch, setSymbolSearch] = useState('');
  const [sortKey, setSortKey] = useState(initialSort.key);
  const [sortDir, setSortDir] = useState(initialSort.dir);
  const [isEarningsPlusReloading, setIsEarningsPlusReloading] = useState(false);
  const [warmStatus, setWarmStatus] = useState(null);
  const [notificationsEnabled, setNotificationsEnabled] = useState(() => loadEarningsNotifyEnabled());
  const [upcomingWatchSymbols, setUpcomingWatchSymbols] = useState(() => new Set());
  const [upcomingWatchBusy, setUpcomingWatchBusy] = useState(null); // symbol being toggled

  useEffect(() => {
    const t = setTimeout(() => {
      setMcapDebounced({ min: mcapMin, max: mcapMax });
    }, 400);
    return () => clearTimeout(t);
  }, [mcapMin, mcapMax]);

  useEffect(() => {
    const t = setTimeout(() => {
      setSurpriseDebounced({
        epsMin: epsSurpriseMin,
        epsMax: epsSurpriseMax,
        revMin: revenueSurpriseMin,
        revMax: revenueSurpriseMax,
      });
    }, 400);
    return () => clearTimeout(t);
  }, [epsSurpriseMin, epsSurpriseMax, revenueSurpriseMin, revenueSurpriseMax]);

  useEffect(() => {
    persistFilters({
      mode, month, year, period, reportWindow, mcapMin, mcapMax,
      epsSurpriseMin, epsSurpriseMax, revenueSurpriseMin, revenueSurpriseMax,
      earningsPlusFilter,
      sortByMode,
    });
  }, [mode, month, year, period, reportWindow, mcapMin, mcapMax, epsSurpriseMin, epsSurpriseMax, revenueSurpriseMin, revenueSurpriseMax, earningsPlusFilter, sortByMode]);

  // Push Earnings notification toggle + filter snapshot to the server evaluator.
  // Alerts always use Reported + current IST month server-side; snapshot still
  // carries surprise/mcap/Earnings+ so browsing another month/upcoming is safe.
  useEffect(() => {
    persistEarningsNotifyEnabled(notificationsEnabled);
    const nowIst = new Date(
      new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }),
    );
    const snapshot = {
      mode: 'reported',
      month: nowIst.getMonth() + 1,
      year: nowIst.getFullYear(),
      period,
      earnings_plus: earningsPlusFilter,
      earningsPlusFilter,
    };
    const minRaw = String(mcapDebounced.min || '').trim();
    const maxRaw = String(mcapDebounced.max || '').trim();
    const parsedMin = minRaw ? parseMarketCapInput(minRaw) : null;
    const parsedMax = maxRaw ? parseMarketCapInput(maxRaw) : null;
    if (Number.isFinite(parsedMin)) {
      snapshot.mcapMin = parsedMin;
      snapshot.mcap_min = parsedMin;
    }
    if (Number.isFinite(parsedMax)) {
      snapshot.mcapMax = parsedMax;
      snapshot.mcap_max = parsedMax;
    }
    const eMin = parseSurprisePct(surpriseDebounced.epsMin);
    const eMax = parseSurprisePct(surpriseDebounced.epsMax);
    const rMin = parseSurprisePct(surpriseDebounced.revMin);
    const rMax = parseSurprisePct(surpriseDebounced.revMax);
    if (surpriseBoundIsSet(surpriseDebounced.epsMin) && Number.isFinite(eMin)) {
      snapshot.epsSurpriseMin = eMin;
      snapshot.eps_surprise_min = eMin;
    }
    if (surpriseBoundIsSet(surpriseDebounced.epsMax) && Number.isFinite(eMax)) {
      snapshot.epsSurpriseMax = eMax;
      snapshot.eps_surprise_max = eMax;
    }
    if (surpriseBoundIsSet(surpriseDebounced.revMin) && Number.isFinite(rMin)) {
      snapshot.revenueSurpriseMin = rMin;
      snapshot.revenue_surprise_min = rMin;
    }
    if (surpriseBoundIsSet(surpriseDebounced.revMax) && Number.isFinite(rMax)) {
      snapshot.revenueSurpriseMax = rMax;
      snapshot.revenue_surprise_max = rMax;
    }

    const t = setTimeout(() => {
      axios.put(`${API}/api/alert-settings`, {
        earnings_notifications_enabled: notificationsEnabled,
        earnings_filter_snapshot: notificationsEnabled ? snapshot : null,
      }).catch(() => {});
    }, 500);
    return () => clearTimeout(t);
  }, [
    notificationsEnabled, mode, month, year, period, reportWindow, mcapMin, mcapMax,
    mcapDebounced, surpriseDebounced, earningsPlusFilter,
    epsSurpriseMin, epsSurpriseMax, revenueSurpriseMin, revenueSurpriseMax,
  ]);

  // Load per-symbol upcoming earnings bells.
  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/api/alert-settings`).then((r) => {
      if (cancelled) return;
      const watches = Array.isArray(r.data?.upcoming_earnings_watches)
        ? r.data.upcoming_earnings_watches
        : [];
      const next = new Set(
        watches
          .filter((w) => w && w.enabled !== false)
          .map((w) => String(w.symbol || '').toUpperCase())
          .filter(Boolean),
      );
      setUpcomingWatchSymbols(next);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const toggleUpcomingWatch = useCallback(async (sym, releaseDate) => {
    const symbol = String(sym || '').toUpperCase();
    const rel = String(releaseDate || '').trim().slice(0, 10);
    if (!symbol) return;
    const currentlyOn = upcomingWatchSymbols.has(symbol);
    const enabled = !currentlyOn;
    if (enabled && !rel) return;
    setUpcomingWatchBusy(symbol);
    // Optimistic UI
    setUpcomingWatchSymbols((prev) => {
      const next = new Set(prev);
      if (enabled) next.add(symbol);
      else next.delete(symbol);
      return next;
    });
    try {
      const r = await axios.put(`${API}/api/alert-settings/upcoming-watch`, {
        symbol,
        release_date: rel,
        enabled,
      });
      const watches = Array.isArray(r.data?.upcoming_earnings_watches)
        ? r.data.upcoming_earnings_watches
        : [];
      setUpcomingWatchSymbols(new Set(
        watches
          .filter((w) => w && w.enabled !== false)
          .map((w) => String(w.symbol || '').toUpperCase())
          .filter(Boolean),
      ));
    } catch (_) {
      // Revert optimistic toggle
      setUpcomingWatchSymbols((prev) => {
        const next = new Set(prev);
        if (currentlyOn) next.add(symbol);
        else next.delete(symbol);
        return next;
      });
    } finally {
      setUpcomingWatchBusy(null);
    }
  }, [upcomingWatchSymbols]);

  useEffect(() => {
    const next = normalizeSortEntry(sortByMode[mode], mode);
    setSortKey(next.key);
    setSortDir(next.dir);
  }, [mode, sortByMode]);

  useEffect(() => {
    setExpandedSymbol(null);
    setSelectedSymbols(new Set());
    setLastSelectedIndex(null);
    setSelectedSymbol(null);
  }, [mode]);

  useEffect(() => {
    if (mode !== 'reported') return;
    if (!isReportedMonthSelectable(year, month)) {
      setMonth(clampReportedMonth(year, month));
    }
  }, [mode, year, month]);

  const years = useMemo(() => {
    const fromApi = meta?.available_years;
    if (Array.isArray(fromApi) && fromApi.length) return [...fromApi].reverse();
    return availableYears();
  }, [meta?.available_years]);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    const params = {
      mode,
      limit: 2000,
      refresh: refresh ? 1 : 0,
    };
    if (mode === 'reported') {
      if (REPORTED_FRESHNESS_VALUES.has(reportWindow)) {
        params.report_window = reportWindow;
      } else {
        params.year = year;
        params.month = month;
      }
      const eMin = parseSurprisePct(surpriseDebounced.epsMin);
      const eMax = parseSurprisePct(surpriseDebounced.epsMax);
      const rMin = parseSurprisePct(surpriseDebounced.revMin);
      const rMax = parseSurprisePct(surpriseDebounced.revMax);
      if (surpriseBoundIsSet(surpriseDebounced.epsMin) && !Number.isFinite(eMin)) {
        setError('EPS beat min % must be a number (e.g. 0, 1, or -1)');
        setLoading(false);
        return;
      }
      if (surpriseBoundIsSet(surpriseDebounced.epsMax) && !Number.isFinite(eMax)) {
        setError('EPS beat max % must be a number (e.g. 0, 1, or -1)');
        setLoading(false);
        return;
      }
      if (surpriseBoundIsSet(surpriseDebounced.revMin) && !Number.isFinite(rMin)) {
        setError('Revenue beat min % must be a number (e.g. 0, 1, or -1)');
        setLoading(false);
        return;
      }
      if (surpriseBoundIsSet(surpriseDebounced.revMax) && !Number.isFinite(rMax)) {
        setError('Revenue beat max % must be a number (e.g. 0, 1, or -1)');
        setLoading(false);
        return;
      }
      if (surpriseBoundIsSet(surpriseDebounced.epsMin)) params.eps_surprise_min = eMin;
      if (surpriseBoundIsSet(surpriseDebounced.epsMax)) params.eps_surprise_max = eMax;
      if (surpriseBoundIsSet(surpriseDebounced.revMin)) params.revenue_surprise_min = rMin;
      if (surpriseBoundIsSet(surpriseDebounced.revMax)) params.revenue_surprise_max = rMax;
      if (earningsPlusFilter !== 'all') params.earnings_plus = earningsPlusFilter;
    } else {
      params.period = period;
    }
    const minRaw = mcapDebounced.min.trim();
    const maxRaw = mcapDebounced.max.trim();
    const parsedMin = minRaw ? parseMarketCapInput(minRaw) : null;
    const parsedMax = maxRaw ? parseMarketCapInput(maxRaw) : null;
    if (minRaw && !Number.isFinite(parsedMin)) {
      setError('Min market cap: use suffix M, B, or T (e.g. 500M, 50B, 5T)');
      setLoading(false);
      return;
    }
    if (maxRaw && !Number.isFinite(parsedMax)) {
      setError('Max market cap: use suffix M, B, or T (e.g. 500M, 50B, 5T)');
      setLoading(false);
      return;
    }
    if (parsedMin != null && Number.isFinite(parsedMin)) params.mcap_min = parsedMin;
    if (parsedMax != null && Number.isFinite(parsedMax)) params.mcap_max = parsedMax;

    try {
      const r = await axios.get(`${API}/api/earnings-beats`, {
        params,
        timeout: 120000,
      });
      const data = r.data || {};
      setRows((data.rows || []).map(attachEarningsMonthRefClose));
      setMeta(data);
      setSelectedSymbol(prev => (
        prev && (data.rows || []).some(row => row.symbol === prev) ? prev : null
      ));
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Failed to load earnings data');
      setRows([]);
      setMeta(null);
    }
    setLoading(false);
  }, [mode, month, year, period, reportWindow, mcapDebounced.min, mcapDebounced.max, surpriseDebounced, earningsPlusFilter]);

  useEffect(() => {
    if (!isActive) return;
    load(false);
  }, [isActive, load]);

  const loadWarmStatus = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/admin/earnings-plus-warm-status`);
      setWarmStatus(r.data && typeof r.data === 'object' ? r.data : null);
    } catch {
      setWarmStatus(null);
    }
  }, []);

  useEffect(() => {
    if (!isActive || mode !== 'reported') return undefined;
    loadWarmStatus();
    const id = setInterval(loadWarmStatus, 60000);
    return () => clearInterval(id);
  }, [isActive, mode, earningsPlusRefreshRunning, loadWarmStatus]);

  useEffect(() => {
    if (!isActive) return undefined;
    const onChartDataUpdated = (event) => {
      const job = event?.detail?.job;
      if (job !== 'earnings_plus_cache') return;
      if (mode !== 'reported') return;
      if (Number(event?.detail?.year) !== Number(year)) return;
      if (Number(event?.detail?.month) !== Number(month)) return;
      setIsEarningsPlusReloading(true);
      Promise.resolve(load(false))
        .finally(() => {
          setIsEarningsPlusReloading(false);
          loadWarmStatus();
        });
    };
    window.addEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
    return () => window.removeEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
  }, [isActive, load, loadWarmStatus, mode, year, month]);

  const handleSort = useCallback((key) => {
    const nextDir = sortKey === key ? (sortDir === 'asc' ? 'desc' : 'asc') : 'asc';
    setSortKey(key);
    setSortDir(nextDir);
    setSortByMode(prev => ({ ...prev, [mode]: { key, dir: nextDir } }));
  }, [mode, sortKey, sortDir]);

  const sortedRows = useMemo(() => {
    const list = [...rows];
    const dir = sortDir === 'asc' ? 1 : -1;
    list.sort((a, b) => compareValues(a, b, sortKey) * dir);
    return list;
  }, [rows, sortKey, sortDir]);

  const filteredRows = useMemo(() => {
    const raw = symbolSearch.trim();
    if (!raw) return sortedRows;
    const tokens = raw
      .split(',')
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
    if (!tokens.length) return sortedRows;
    return sortedRows.filter((row) => {
      const sym = String(row.symbol || '').toUpperCase();
      const name = String(row.name || '').toUpperCase();
      const tags = earningsSectorTags(row);
      return tokens.some((tok) => tokenMatchesEarningsRow(tok, sym, name, tags));
    });
  }, [sortedRows, symbolSearch]);

  // Live ON: Upstox LTPC overlays price + 1D%; 1M% derived from fetch-time month_ref_close.
  usePageLive('earnings-beats');
  const { overlayEarningsRows } = usePatchOverlay('earnings-beats');
  const displayRows = useMemo(
    () => overlayEarningsRows(filteredRows) || filteredRows,
    [filteredRows, overlayEarningsRows],
  );
  useRegisterFocusedSymbol(
    'earnings-beats',
    useMemo(() => (selectedSymbol ? [selectedSymbol] : []), [selectedSymbol]),
  );
  useRegisterIntradaySymbols(
    'earnings-beats',
    useMemo(
      () => filteredRows
        .map((r) => String(r.symbol || '').trim().toUpperCase())
        .filter(Boolean)
        .slice(0, 200),
      [filteredRows],
    ),
  );

  useEffect(() => {
    if (!filteredRows.length) return;
    const visible = new Set(filteredRows.map((r) => String(r.symbol || '').toUpperCase()).filter(Boolean));
    setSelectedSymbols((prev) => {
      if (!prev.size) return prev;
      const next = new Set([...prev].filter((s) => visible.has(s)));
      return next.size === prev.size ? prev : next;
    });
  }, [filteredRows]);

  useEffect(() => {
    if (!wlPickOpen) return undefined;
    function handleDoc(e) {
      if (wlPickWrapRef.current?.contains(e.target)) return;
      setWlPickOpen(false);
      setAddMenuMode(null);
    }
    document.addEventListener('mousedown', handleDoc);
    return () => document.removeEventListener('mousedown', handleDoc);
  }, [wlPickOpen]);

  function handleRowSelect(sym, idx, e) {
    if (e.shiftKey && lastSelectedIndex !== null) {
      const start = Math.min(lastSelectedIndex, idx);
      const end = Math.max(lastSelectedIndex, idx);
      const rangeSymbols = filteredRows.slice(start, end + 1).map((r) => String(r.symbol || '').toUpperCase());
      setSelectedSymbols((prev) => {
        const next = new Set(prev);
        for (const s of rangeSymbols) {
          if (s) next.add(s);
        }
        return next;
      });
    } else if (e.ctrlKey || e.metaKey) {
      setSelectedSymbols((prev) => {
        const next = new Set(prev);
        if (next.has(sym)) next.delete(sym);
        else next.add(sym);
        return next;
      });
      setLastSelectedIndex(idx);
    } else {
      setSelectedSymbols(new Set([sym]));
      setLastSelectedIndex(idx);
    }
    setSelectedSymbol(sym);
  }

  function openEarningsContextMenu(e, sym) {
    e.preventDefault();
    if (!onContextMenuRequest) return;
    let items;
    if (selectedSymbols.has(sym) && selectedSymbols.size > 1) {
      items = [...selectedSymbols].map((s) => ({ symbol: s, type: 'stock' }));
    } else {
      items = [{ symbol: sym, type: 'stock' }];
      if (!selectedSymbols.has(sym) || selectedSymbols.size !== 1) {
        setSelectedSymbols(new Set([sym]));
        setSelectedSymbol(sym);
      }
    }
    const allVisibleItems = filteredRows
      .map((r) => String(r.symbol || '').trim().toUpperCase())
      .filter(Boolean)
      .map((s) => ({ symbol: s, type: 'stock' }));
    onContextMenuRequest({
      x: e.clientX,
      y: e.clientY,
      symbol: sym,
      type: 'stock',
      sourcePage: 'earnings-beats',
      items,
      allVisibleItems,
    });
  }

  async function addSymbolsToWatchlist(symbols, watchlistName) {
    if (!onAddStocksToWatchlist || !symbols?.length || !watchlistName) return;
    try {
      await onAddStocksToWatchlist(symbols, watchlistName);
      setWlPickOpen(false);
      setAddMenuMode(null);
    } catch {
      /* parent alerts */
    }
  }

  const searchActive = symbolSearch.trim().length > 0;

  const fetchedLabel = meta?.fetched_at
    ? new Date((meta.fetched_at || 0) * 1000).toLocaleString('en-IN')
    : null;
  const earningsPlusCache = meta?.earnings_plus_cache || null;
  const earningsPlusCacheLabel = mode === 'reported' && earningsPlusCache
    ? [
        earningsPlusCache.missing_symbols > 0 ? `${earningsPlusCache.missing_symbols} uncached` : null,
        earningsPlusCache.stale_symbols > 0 ? `${earningsPlusCache.stale_symbols} stale` : null,
      ].filter(Boolean).join(', ')
    : '';
  const warmStatusLabel = (() => {
    if (mode !== 'reported' || !warmStatus) return '';
    const when = warmStatus.finished_at || warmStatus.started_at;
    if (!when) return '';
    const bits = [when];
    if (warmStatus.trigger) bits.push(String(warmStatus.trigger));
    if (warmStatus.success === true) bits.push('ok');
    if (warmStatus.success === false) bits.push('failed');
    if (warmStatus.refreshed != null) bits.push(`${warmStatus.refreshed} updated`);
    if (warmStatus.skipped != null) bits.push(`${warmStatus.skipped} skipped`);
    return bits.join(' · ');
  })();

  const headerPeriod = headerPeriodLabel(mode, month, year, period, reportWindow);
  const statusLine = statusSummary(mode, month, year, period, reportWindow);

  const emptyMessage = mode === 'reported'
    ? 'No symbols matched your period, market cap, or surprise % filters.'
    : 'No upcoming earnings matched your filters.';

  const tableEmptyMessage = searchActive
    ? `No symbols match “${symbolSearch.trim()}”.`
    : (
      mode === 'reported'
      && earningsPlusFilter !== 'all'
      && (earningsPlusCache?.missing_symbols || 0) > 0
        ? `${emptyMessage} Earnings+ cache is incomplete for ${earningsPlusCache.missing_symbols} symbol(s); refresh the cache for complete results.`
        : emptyMessage
    );

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      width: '100%',
      overflow: 'hidden',
      backgroundColor: 'var(--bg-primary)',
    }}
    >
      <div style={{
        flexShrink: 0,
        padding: '12px 16px',
        borderBottom: '1px solid var(--border)',
        backgroundColor: 'var(--bg-secondary)',
      }}
      >
        <div style={{
          display: 'flex',
          alignItems: 'stretch',
          gap: 0,
          minHeight: 52,
        }}
        >
          <div style={{
            flexShrink: 0,
            paddingRight: 20,
            paddingTop: 2,
            paddingBottom: 2,
            minWidth: 200,
            maxWidth: 420,
          }}
          >
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flexWrap: 'nowrap',
            }}
            >
              <span style={{
                fontSize: 14,
                fontWeight: 700,
                color: 'var(--text-primary)',
                whiteSpace: 'nowrap',
              }}
              >
                Earnings
              </span>
              <BasketToolbarButton />
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>|</span>
              <span style={{
                fontSize: 14,
                fontWeight: 600,
                color: 'var(--text-secondary)',
                whiteSpace: 'nowrap',
              }}
              >
                NSE
              </span>
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>|</span>
              <span style={{
                fontSize: 14,
                fontWeight: 600,
                color: 'var(--text-secondary)',
                whiteSpace: 'nowrap',
              }}
              >
                {headerPeriod}
              </span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, lineHeight: 1.45 }}>
              <span style={{ fontSize: 10, opacity: mode === 'reported' ? 0.9 : 0.4 }}>{BEAT_HINT}</span>
            </div>
            <label
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 8,
                fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer', userSelect: 'none',
              }}
              title="Alerts only for Reported earnings in the current month that match your filters (not Upcoming, not past months)"
            >
              <input
                type="checkbox"
                checked={notificationsEnabled}
                onChange={e => setNotificationsEnabled(e.target.checked)}
              />
              Notifications {notificationsEnabled ? 'ON' : 'OFF'}
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                (reported · this month)
              </span>
            </label>
          </div>

          <div
            role="separator"
            style={{
              width: 1,
              alignSelf: 'stretch',
              backgroundColor: 'var(--border)',
              margin: '2px 20px',
              flexShrink: 0,
            }}
          />

          <div
            className="earnings-filters-panel"
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              gap: filterStackGap,
              paddingTop: 0,
              paddingBottom: 0,
              minWidth: 0,
            }}
          >
            <div style={filterGridStyle}>
              <FilterField label="Earnings" width={FILTER_COL.earnings}>
                <OverflowMarqueeSelect
                  value={mode}
                  onChange={e => setMode(e.target.value)}
                  style={selectFullStyle}
                  aria-label="Earnings mode"
                  options={[
                    { value: 'reported', label: 'Reported' },
                    { value: 'upcoming', label: 'Upcoming' },
                  ]}
                />
              </FilterField>
              <FilterField
                label="Year"
                width={FILTER_COL.year}
                disabled={mode === 'upcoming' || (mode === 'reported' && REPORTED_FRESHNESS_VALUES.has(reportWindow))}
              >
                <OverflowMarqueeSelect
                  value={String(year)}
                  onChange={e => {
                    const y = Number(e.target.value);
                    setYear(y);
                    if (!isReportedMonthSelectable(y, month)) {
                      setMonth(clampReportedMonth(y, month));
                    }
                  }}
                  disabled={mode === 'upcoming' || (mode === 'reported' && REPORTED_FRESHNESS_VALUES.has(reportWindow))}
                  title={
                    mode === 'upcoming'
                      ? 'Year applies to Reported earnings only'
                      : (REPORTED_FRESHNESS_VALUES.has(reportWindow) ? 'Year applies when Period is a calendar month' : undefined)
                  }
                  style={controlStyle(
                    selectFullStyle,
                    mode === 'upcoming' || (mode === 'reported' && REPORTED_FRESHNESS_VALUES.has(reportWindow)),
                  )}
                  aria-label="Year"
                  options={years.map(y => ({ value: String(y), label: String(y) }))}
                />
              </FilterField>
              <FilterField label="Period" width={FILTER_COL.month}>
                {mode === 'upcoming' ? (
                  <OverflowMarqueeSelect
                    value={period}
                    onChange={e => setPeriod(e.target.value)}
                    style={selectFullStyle}
                    aria-label="Period"
                    options={PERIOD_OPTIONS}
                  />
                ) : (
                  <OverflowMarqueeSelect
                    value={REPORTED_FRESHNESS_VALUES.has(reportWindow) ? reportWindow : String(month)}
                    onChange={e => {
                      const v = e.target.value;
                      if (REPORTED_FRESHNESS_VALUES.has(v)) {
                        setReportWindow(v);
                        return;
                      }
                      setReportWindow('month');
                      setMonth(Number(v));
                    }}
                    style={selectFullStyle}
                    title="Current trading day spans last session→today on weekends. Months use the Year control."
                    aria-label="Period"
                    options={[
                      ...REPORTED_FRESHNESS_OPTIONS,
                      { value: '__sep__', label: '────────', disabled: true },
                      ...MONTH_OPTIONS.map(o => ({
                        value: String(o.value),
                        label: o.label,
                        disabled: !isReportedMonthSelectable(year, o.value),
                      })),
                    ]}
                  />
                )}
              </FilterField>
              <FilterField label="MCap min" width={FILTER_COL.mcapMin}>
                <input
                  type="text"
                  className={FILTER_INPUT_CLASS}
                  value={mcapMin}
                  onChange={e => setMcapMin(e.target.value)}
                  placeholder="—"
                  title="Empty = no minimum. Suffix M, B, or T (e.g. 500M, 50B, 5T) in INR."
                  style={inputStyle}
                />
              </FilterField>
              <FilterField label="Max" width={FILTER_COL.mcapMax}>
                <input
                  type="text"
                  className={FILTER_INPUT_CLASS}
                  value={mcapMax}
                  onChange={e => setMcapMax(e.target.value)}
                  placeholder="—"
                  title="Empty = no maximum. Suffix M, B, or T (e.g. 500M, 50B, 5T) in INR."
                  style={inputStyle}
                />
              </FilterField>
              <FilterField label="M · B · T">
                <div style={{ display: 'flex', gap: 10, flexWrap: 'nowrap' }}>
                  <button
                    type="button"
                    onClick={() => load(true)}
                    disabled={loading}
                    title="Bypass cache and pull fresh data from TradingView"
                    style={{
                      ...actionBtnBase,
                      border: '1px solid var(--accent-blue)',
                      backgroundColor: loading ? 'var(--bg-tertiary)' : 'rgba(56,139,253,0.12)',
                      color: loading ? 'var(--text-muted)' : 'var(--accent-blue)',
                      cursor: loading ? 'wait' : 'pointer',
                    }}
                  >
                    {loading ? 'Fetching…' : 'Fetch latest data'}
                  </button>
                  {mode === 'reported' && onRefreshEarningsPlusCache && (
                    <button
                      type="button"
                      onClick={() => onRefreshEarningsPlusCache({ year, month })}
                      disabled={earningsPlusRefreshRunning || isEarningsPlusReloading}
                      title="Refresh missing or stale Earnings+ cache rows for this month (uses DB quarterly data when available)."
                      style={{
                        ...actionBtnBase,
                        border: '1px solid #d29922',
                        backgroundColor: (earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'var(--bg-tertiary)' : 'rgba(210,153,34,0.14)',
                        color: (earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'var(--text-muted)' : '#d29922',
                        cursor: (earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'wait' : 'pointer',
                      }}
                    >
                      {(earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'Refreshing Earnings+…' : 'Refresh Earnings+ cache'}
                    </button>
                  )}
                </div>
              </FilterField>
            </div>
            <div style={filterGridStyle}>
              <FilterField label="EPS beat min %" width={FILTER_COL.earnings} disabled={mode === 'upcoming'}>
                <input
                  type="text"
                  className={FILTER_INPUT_CLASS}
                  value={epsSurpriseMin}
                  onChange={e => setEpsSurpriseMin(e.target.value)}
                  disabled={mode === 'upcoming'}
                  placeholder="—"
                  title={mode === 'upcoming' ? 'Surprise % filters apply to Reported earnings only' : 'Minimum EPS surprise % (≥). Use 0 for met/beat. If EPS is missing (—) but revenue surprise exists for the quarter, the row is still kept.'}
                  style={controlStyle(inputStyle, mode === 'upcoming')}
                />
              </FilterField>
              <FilterField label="Max %" width={FILTER_COL.year} disabled={mode === 'upcoming'}>
                <input
                  type="text"
                  className={FILTER_INPUT_CLASS}
                  value={epsSurpriseMax}
                  onChange={e => setEpsSurpriseMax(e.target.value)}
                  disabled={mode === 'upcoming'}
                  placeholder="—"
                  title={mode === 'upcoming' ? 'Surprise % filters apply to Reported earnings only' : 'Maximum EPS surprise % (≤). Empty = no ceiling.'}
                  style={controlStyle(inputStyle, mode === 'upcoming')}
                />
              </FilterField>
              <FilterField label="Rev beat min %" width={FILTER_COL.month} disabled={mode === 'upcoming'}>
                <input
                  type="text"
                  className={FILTER_INPUT_CLASS}
                  value={revenueSurpriseMin}
                  onChange={e => setRevenueSurpriseMin(e.target.value)}
                  disabled={mode === 'upcoming'}
                  placeholder="—"
                  title={mode === 'upcoming' ? 'Surprise % filters apply to Reported earnings only' : 'Minimum revenue surprise % (≥). Use 0 for met/beat. If revenue is missing (—) but EPS surprise exists for the quarter, the row is still kept.'}
                  style={controlStyle(inputStyle, mode === 'upcoming')}
                />
              </FilterField>
              <FilterField label="Max %" width={FILTER_COL.mcapMin} disabled={mode === 'upcoming'}>
                <input
                  type="text"
                  className={FILTER_INPUT_CLASS}
                  value={revenueSurpriseMax}
                  onChange={e => setRevenueSurpriseMax(e.target.value)}
                  disabled={mode === 'upcoming'}
                  placeholder="—"
                  title={mode === 'upcoming' ? 'Surprise % filters apply to Reported earnings only' : 'Maximum revenue surprise % (≤). Empty = no ceiling.'}
                  style={controlStyle(inputStyle, mode === 'upcoming')}
                />
              </FilterField>
              <FilterField label="Earnings+" width={FILTER_COL.mcapMax} disabled={mode === 'upcoming'}>
                <OverflowMarqueeSelect
                  value={earningsPlusFilter}
                  onChange={e => setEarningsPlusFilter(e.target.value)}
                  disabled={mode === 'upcoming'}
                  aria-label="Earnings+ filter"
                  title={mode === 'upcoming'
                    ? 'Earnings+ applies to Reported earnings only'
                    : 'All / Earnings+ Screener quality / TV EPS plus revenue beat (reported EPS > est and reported revenue > est)'}
                  style={controlStyle(selectFullStyle, mode === 'upcoming')}
                  options={EARNINGS_PLUS_FILTER_OPTIONS}
                />
              </FilterField>
              {mode === 'reported' && onRefreshEarningsPlusCache ? (
                <FilterField label={'\u00a0'}>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'nowrap' }}>
                    <button
                      type="button"
                      onClick={() => onRefreshEarningsPlusCache({ year, month, onlyIncomplete: true })}
                      disabled={earningsPlusRefreshRunning || isEarningsPlusReloading}
                      title="Retry symbols with no cache row or insufficient_data only."
                      style={{
                        ...actionBtnBase,
                        border: '1px solid var(--border-light)',
                        backgroundColor: 'var(--bg-secondary)',
                        color: 'var(--text-secondary)',
                        cursor: (earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'wait' : 'pointer',
                      }}
                    >
                      Retry incomplete
                    </button>
                    <button
                      type="button"
                      onClick={() => onRefreshEarningsPlusCache({ year, month, force: true })}
                      disabled={earningsPlusRefreshRunning || isEarningsPlusReloading}
                      title="Force refresh all reported symbols (slow; may re-scrape Screener)."
                      style={{
                        ...actionBtnBase,
                        border: '1px solid var(--border-light)',
                        backgroundColor: 'var(--bg-secondary)',
                        color: 'var(--text-muted)',
                        cursor: (earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'wait' : 'pointer',
                      }}
                    >
                      Force all
                    </button>
                  </div>
                </FilterField>
              ) : (
                <div aria-hidden />
              )}
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div style={{ padding: '12px 14px', color: 'var(--accent-red)', fontSize: 12 }}>
          {error}
        </div>
      )}

      {!error && meta && (
        <div style={{
          padding: '6px 14px',
          fontSize: 11,
          color: 'var(--text-muted)',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
        }}
        >
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            backgroundColor: 'var(--bg-tertiary)',
            border: '1px solid var(--border)',
            borderRadius: 5,
            padding: '0 10px',
            height: 28,
            width: 300,
            flexShrink: 0,
          }}
          >
            <svg width="11" height="11" viewBox="0 0 16 16" fill="var(--text-muted)" aria-hidden>
              <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z" />
            </svg>
            <input
              type="text"
              value={symbolSearch}
              onChange={e => setSymbolSearch(e.target.value)}
              placeholder="Symbol, name, or sector (comma-separated)…"
              title="Filter by symbol, company name, or sector. Use commas for multiple terms (OR), e.g. Auto, Energy or INFY, TCS"
              style={{
                background: 'transparent',
                color: 'var(--text-primary)',
                flex: 1,
                fontSize: 12,
                border: 'none',
                outline: 'none',
                minWidth: 0,
              }}
            />
            {searchActive && (
              <button
                type="button"
                onClick={() => setSymbolSearch('')}
                title="Clear search"
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  fontSize: 14,
                  cursor: 'pointer',
                  padding: 0,
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            )}
          </div>
          {onAddStocksToWatchlist && filteredRows.length > 0 && (
            <div ref={wlPickWrapRef} style={{ position: 'relative', flexShrink: 0 }}>
              <button
                type="button"
                onClick={() => {
                  if (!watchlists?.length) {
                    if (window.confirm('You don\'t have any watchlists yet.\n\nOpen the Watchlist tab to create one?')) {
                      onGoToWatchlist && onGoToWatchlist();
                    }
                    return;
                  }
                  setAddMenuMode(null);
                  setWlPickOpen((o) => !o);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 11,
                  color: 'var(--text-secondary)',
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border)',
                  borderRadius: 5,
                  cursor: 'pointer',
                  padding: '2px 8px',
                  height: 28,
                  whiteSpace: 'nowrap',
                }}
                title="Add selected or all visible symbols to a watchlist"
              >
                Watchlist
                {selectedSymbols.size > 1 ? ` (${selectedSymbols.size})` : ''}
                <svg width="7" height="4" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6 }}><path d="M0 0l4 5 4-5z" /></svg>
              </button>
              {wlPickOpen && watchlists.length > 0 && (
                <div
                  style={{
                    position: 'absolute',
                    top: 'calc(100% + 4px)',
                    left: 0,
                    zIndex: 40,
                    width: 240,
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border)',
                    borderRadius: 6,
                    boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    role="menuitem"
                    onClick={() => setAddMenuMode((m) => (m === 'selected' ? null : 'selected'))}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '9px 12px',
                      cursor: selectedSymbols.size ? 'pointer' : 'default',
                      fontSize: 12,
                      color: selectedSymbols.size ? 'var(--text-primary)' : 'var(--text-muted)',
                      borderBottom: '1px solid var(--border-light)',
                      opacity: selectedSymbols.size ? 1 : 0.55,
                    }}
                  >
                    <span>{`Add selected (${selectedSymbols.size || 0})…`}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', opacity: 0.8 }}>{'>'}</span>
                  </div>
                  {addMenuMode === 'selected' && selectedSymbols.size > 0 && (
                    <div style={{ borderBottom: '1px solid var(--border-light)', maxHeight: 200, overflowY: 'auto' }}>
                      {watchlists.map((w) => (
                        <div
                          key={`sel-${w.name}`}
                          role="menuitem"
                          onClick={() => addSymbolsToWatchlist([...selectedSymbols], w.name)}
                          style={{ padding: '8px 16px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)' }}
                          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                        >
                          {w.name}
                        </div>
                      ))}
                    </div>
                  )}
                  <div
                    role="menuitem"
                    onClick={() => setAddMenuMode((m) => (m === 'all' ? null : 'all'))}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '9px 12px',
                      cursor: 'pointer',
                      fontSize: 12,
                      color: 'var(--text-primary)',
                      borderBottom: addMenuMode === 'all' ? '1px solid var(--border-light)' : 'none',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                  >
                    <span>{`Add all visible (${filteredRows.length})…`}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', opacity: 0.8 }}>{'>'}</span>
                  </div>
                  {addMenuMode === 'all' && (
                    <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                      {watchlists.map((w) => (
                        <div
                          key={`all-${w.name}`}
                          role="menuitem"
                          onClick={() => {
                            const symbols = filteredRows
                              .map((r) => String(r.symbol || '').trim().toUpperCase())
                              .filter(Boolean);
                            addSymbolsToWatchlist(symbols, w.name);
                          }}
                          style={{ padding: '8px 16px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)' }}
                          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                        >
                          {w.name}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          <div
            role="status"
            aria-live="polite"
            style={{
            flex: 1,
            minWidth: 200,
            textAlign: 'right',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            }}
          >
            {statusLine}
            {' · '}
            {searchActive
              ? `${filteredRows.length} of ${sortedRows.length} stocks`
              : `${meta.count ?? rows.length} stocks`}
            {!searchActive && meta.truncated && meta.matched_symbols != null
              ? ` (showing ${meta.count} of ${meta.matched_symbols} symbols)`
              : ''}
            {meta.scanner_total != null ? ` · TV listings ${meta.scanner_total}` : ''}
            {meta.cached ? ' · cached' : ''}
            {fetchedLabel ? ` · ${fetchedLabel}` : ''}
            {earningsPlusCacheLabel ? ` · Earnings+ cache ${earningsPlusCacheLabel}` : ''}
            {warmStatusLabel ? ` · Last background warm: ${warmStatusLabel}` : ''}
          </div>
        </div>
      )}

      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }} aria-busy={loading}>
        <table
          style={{
            width: '100%',
            minWidth: earningsTableMinWidthPx(mode),
            tableLayout: 'fixed',
            borderCollapse: 'collapse',
          }}
        >
          <colgroup>
            {(mode === 'reported' ? REPORTED_COLGROUP : UPCOMING_COLGROUP).map((w, i) => (
              <col key={`${mode}-col-${i}`} style={{ width: w }} />
            ))}
          </colgroup>
          <thead style={{ position: 'sticky', top: 0, backgroundColor: 'var(--bg-secondary)', zIndex: 1 }}>
            <tr>
              {mode === 'reported' ? (
                <>
                  <SortableTh label="Symbol" sortKey="symbol" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Sector" sortKey="market_sector" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="MCap" sortKey="market_cap_basic" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Price" sortKey="price" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="P/E" sortKey="price_earnings_ttm" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="1D %" sortKey="change_1d_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="1M %" sortKey="change_1m_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Reported" sortKey="earnings_release_date" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="EPS act" sortKey="eps_actual" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="EPS est" sortKey="eps_estimate" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="EPS beat" sortKey="eps_surprise_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Rev act" sortKey="revenue_actual" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Rev est" sortKey="revenue_estimate" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Rev beat" sortKey="revenue_surprise_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                </>
              ) : (
                <>
                  <SortableTh label="Symbol" sortKey="symbol" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Sector" sortKey="market_sector" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="MCap" sortKey="market_cap_basic" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Price" sortKey="price" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="P/E" sortKey="price_earnings_ttm" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="1D %" sortKey="change_1d_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="1M %" sortKey="change_1m_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Upcoming" sortKey="earnings_release_next_date" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="EPS est" sortKey="eps_estimate" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Rev est" sortKey="revenue_estimate" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, idx) => {
              const sym = String(row.symbol || '').toUpperCase();
              const isSel = sym === selectedSymbol;
              const isMultiSel = selectedSymbols.has(sym);
              const isExpanded = sym === expandedSymbol;
              const columnCount = mode === 'reported'
                ? EARNINGS_REPORTED_COLUMN_COUNT
                : EARNINGS_UPCOMING_COLUMN_COUNT;
              const epsBeat = toFiniteNumber(row.eps_surprise_pct);
              const revBeat = toFiniteNumber(row.revenue_surprise_pct);
              return (
                <React.Fragment key={sym}>
                <tr
                  onClick={(e) => handleRowSelect(sym, idx, e)}
                  onDoubleClick={(e) => {
                    if (e.shiftKey || e.ctrlKey || e.metaKey) return;
                    e.preventDefault();
                    if (isExpanded) {
                      setExpandedSymbol(null);
                    } else {
                      setExpandedSymbol(sym);
                      setSelectedSymbol(sym);
                    }
                  }}
                  title="Click to select · Ctrl/Cmd multi-select · Shift range · Double-click for quarterly results"
                  onContextMenu={(e) => openEarningsContextMenu(e, sym)}
                  style={{
                    cursor: 'pointer',
                    backgroundColor: isSel
                      ? 'rgba(56,139,253,0.12)'
                      : isMultiSel
                        ? 'rgba(56,139,253,0.06)'
                        : 'transparent',
                    boxShadow: isSel
                      ? 'inset 2px 0 0 var(--accent-blue)'
                      : isMultiSel
                        ? 'inset 2px 0 0 rgba(56,139,253,0.45)'
                        : 'none',
                  }}
                >
                  <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)' }}>
                    <button
                      type="button"
                      aria-expanded={isExpanded}
                      aria-label={isExpanded ? `Collapse quarterly results for ${sym}` : `Expand quarterly results for ${sym}`}
                      title={isExpanded ? 'Hide quarterly results' : 'Show Screener quarterly results'}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (isExpanded) {
                          setExpandedSymbol(null);
                        } else {
                          setExpandedSymbol(sym);
                          setSelectedSymbol(sym);
                          setSelectedSymbols(new Set([sym]));
                          setLastSelectedIndex(idx);
                        }
                      }}
                      onDoubleClick={e => e.stopPropagation()}
                      style={{
                        marginRight: 6,
                        padding: '0 4px',
                        border: 'none',
                        background: 'transparent',
                        color: 'var(--text-muted)',
                        cursor: 'pointer',
                        fontSize: 10,
                        lineHeight: 1,
                        verticalAlign: 'middle',
                      }}
                    >
                      {isExpanded ? '▼' : '▶'}
                    </button>
                    <span
                      draggable
                      onDragStart={(e) => {
                        e.stopPropagation();
                        startBasketSymbolDrag(e, sym, 'stock');
                      }}
                      title={`${sym} — drag to Basket`}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 4, verticalAlign: 'middle', cursor: 'grab' }}
                    >
                      {sym}
                      {mode === 'reported' && row.earnings_plus ? (
                        <EarningsPlusInlineMark
                          title={row.earnings_plus_note || 'Earnings+ for this release quarter'}
                        />
                      ) : null}
                      {mode === 'upcoming' ? (
                        <button
                          type="button"
                          aria-label={
                            upcomingWatchSymbols.has(sym)
                              ? `Turn off upcoming earnings alert for ${sym}`
                              : `Alert me when ${sym} reports`
                          }
                          title={
                            upcomingWatchSymbols.has(sym)
                              ? 'Alert ON — notify day before & day of report (click to turn off)'
                              : 'Alert OFF — click to notify day before & day of this report'
                          }
                          disabled={upcomingWatchBusy === sym || !row.earnings_release_next_date}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleUpcomingWatch(sym, row.earnings_release_next_date);
                          }}
                          onDoubleClick={(e) => e.stopPropagation()}
                          style={{
                            marginLeft: 2,
                            padding: '0 2px',
                            border: 'none',
                            background: 'transparent',
                            cursor: upcomingWatchBusy === sym ? 'wait' : 'pointer',
                            fontSize: 12,
                            lineHeight: 1,
                            opacity: upcomingWatchSymbols.has(sym) ? 1 : 0.45,
                            color: upcomingWatchSymbols.has(sym)
                              ? 'var(--accent-blue)'
                              : 'var(--text-muted)',
                          }}
                        >
                          🔔
                        </button>
                      ) : null}
                    </span>
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      color: 'var(--text-secondary)',
                      maxWidth: 140,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={
                      (Array.isArray(row.market_sectors) && row.market_sectors.length)
                        ? row.market_sectors.join(' · ')
                        : (row.market_sector || undefined)
                    }
                  >
                    {row.market_sector || '—'}
                  </td>
                  <td style={tdStyle}>{formatMarketCap(row.market_cap_basic)}</td>
                  <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)' }}>{fmtPrice(row.price)}</td>
                  <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)' }} title="TradingView P/E (TTM)">
                    {fmtPe(row.price_earnings_ttm)}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)', color: chgPctColor(row.change_1d_pct), fontWeight: 600 }}>
                    {fmtPct(row.change_1d_pct)}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)', color: chgPctColor(row.change_1m_pct), fontWeight: 600 }}>
                    {fmtPct(row.change_1m_pct)}
                  </td>
                  {mode === 'reported' ? (
                    <>
                      <td style={tdStyle}>{row.earnings_release_date || '—'}</td>
                      <td style={tdStyle}>{fmtEps(row.eps_actual)}</td>
                      <td style={tdStyle}>{fmtEps(row.eps_estimate)}</td>
                      <td style={{ ...tdStyle, color: chgPctColor(epsBeat), fontWeight: 600 }}>
                        {fmtPct(row.eps_surprise_pct)}
                      </td>
                      <td style={tdStyle}>{formatMarketCap(row.revenue_actual)}</td>
                      <td style={tdStyle}>{formatMarketCap(row.revenue_estimate)}</td>
                      <td style={{ ...tdStyle, color: chgPctColor(revBeat), fontWeight: 600 }}>
                        {fmtPct(row.revenue_surprise_pct)}
                      </td>
                    </>
                  ) : (
                    <>
                      <td style={tdStyle}>{row.earnings_release_next_date || '—'}</td>
                      <td style={tdStyle}>{fmtEps(row.eps_estimate)}</td>
                      <td style={tdStyle}>{formatMarketCap(row.revenue_estimate)}</td>
                    </>
                  )}
                </tr>
                {isExpanded && (
                  <tr>
                    <EarningsQuarterlyPanel
                      symbol={sym}
                      columnCount={columnCount}
                      onBasisChange={(nextBasis) => {
                        setScreenerBasisBySymbol((prev) => (
                          prev[sym] === nextBasis ? prev : { ...prev, [sym]: nextBasis }
                        ));
                      }}
                    />
                  </tr>
                )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
        {!loading && filteredRows.length === 0 && !error && (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
            {tableEmptyMessage}
          </div>
        )}
      </div>

      <div style={{
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 14px',
        borderTop: '1px solid var(--border)',
        backgroundColor: 'var(--bg-secondary)',
        minHeight: 46,
      }}
      >
        {selectedSymbol ? (
          <>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              fontSize: 13,
              color: 'var(--text-primary)',
              flexShrink: 0,
            }}
            >
              {selectedSymbol}
              {selectedSymbols.size > 1 ? (
                <span style={{ fontWeight: 500, color: 'var(--text-muted)', marginLeft: 8 }}>
                  +{selectedSymbols.size - 1} more selected
                </span>
              ) : null}
            </span>
            <div style={{ width: 1, height: 22, backgroundColor: 'var(--border)', flexShrink: 0 }} />
            <ExternalFinancialsLinks
              symbol={selectedSymbol}
              height={28}
              layout="inline"
              includeTvEarnings
              onOpenChart={onOpenChart || null}
              basis={screenerBasisBySymbol[selectedSymbol] || 'consolidated'}
              screenerLabel="Screener ↗"
              tradingViewLabel="TV Overview ↗"
            />
          </>
        ) : (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            Select a symbol in the table above to show Chart, Screener, TV Overview, and TV Earnings links.
          </span>
        )}
      </div>
    </div>
  );
}
