import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import ExternalFinancialsLinks from '../components/ExternalFinancialsLinks';
import EarningsQuarterlyPanel from '../components/EarningsQuarterlyPanel';
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

const API = '';
const MIN_YEAR = 2024;
const FILTERS_STORAGE_KEY = isDistributionProfile
  ? 'cim.earningsBeats.filters.distribution'
  : 'cim.earningsBeats.filters';
const DIST_FILTERS_DEFAULTS_VERSION_KEY = 'cim.earningsBeats.filters.distribution.version';
const DIST_FILTERS_DEFAULTS_VERSION = 'v1-clean';
const FILTER_INPUT_CLASS = 'earnings-filter-input';
const BEAT_HINT = '* Empty = no bound. Min 0 = met or beat estimates (0% included). Values match the table (computed when needed).';

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

const PERIOD_OPTIONS = [
  { value: 'this_month', label: 'This month' },
  { value: 'next_month', label: 'Next month' },
  { value: 'month_after', label: 'Month after' },
  { value: 'coming_week', label: 'Coming week' },
];

const EARNINGS_PLUS_FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'only', label: 'Earnings+ only' },
  { value: 'exclude', label: 'Exclude Earnings+' },
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

function fmtPct(val) {
  const n = Number(val);
  if (!Number.isFinite(n)) return '—';
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

function fmtEps(val) {
  const n = Number(val);
  if (!Number.isFinite(n)) return '—';
  return n.toFixed(2);
}

function fmtPrice(val) {
  if (val == null || val === '') return '—';
  const n = Number(val);
  if (!Number.isFinite(n) || n <= 0) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function chgPctColor(val) {
  const n = Number(val);
  if (!Number.isFinite(n)) return 'var(--text-muted)';
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
  if (key === 'symbol') {
    return String(a.symbol || '').localeCompare(String(b.symbol || ''));
  }
  const dateKeys = new Set(['earnings_release_date', 'earnings_release_next_date']);
  if (dateKeys.has(key)) {
    return String(a[key] || '').localeCompare(String(b[key] || ''));
  }
  const na = Number(a[key]);
  const nb = Number(b[key]);
  const aOk = Number.isFinite(na);
  const bOk = Number.isFinite(nb);
  if (!aOk && !bOk) return 0;
  if (!aOk) return 1;
  if (!bOk) return -1;
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

/** Fixed column widths so row 1 and row 2 controls line up vertically. */
const FILTER_COL = {
  earnings: 118,
  year: 84,
  month: 108,
  mcapMin: 112,
  mcapMax: 96,
};

const filterGridCols = `${FILTER_COL.earnings}px ${FILTER_COL.year}px ${FILTER_COL.month}px ${FILTER_COL.mcapMin}px ${FILTER_COL.mcapMax}px minmax(140px, 1fr)`;

const filterGridStyle = {
  display: 'grid',
  gridTemplateColumns: filterGridCols,
  columnGap: 10,
  rowGap: 5,
  alignItems: 'end',
  width: '100%',
};

const filterLabelStyle = {
  fontSize: 10,
  color: 'var(--text-muted)',
  lineHeight: 1.2,
  textAlign: 'left',
  width: '100%',
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
      <div style={{ width: '100%' }}>{children}</div>
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
  'symbol', 'market_cap_basic', 'price', 'change_1d_pct', 'change_2w_pct',
  'earnings_release_date',
  'eps_actual', 'eps_estimate', 'eps_surprise_pct',
  'revenue_actual', 'revenue_estimate', 'revenue_surprise_pct',
]);

const UPCOMING_SORT_KEYS = new Set([
  'symbol', 'market_cap_basic', 'price', 'change_1d_pct', 'change_2w_pct',
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
    const period = PERIOD_OPTIONS.some(o => o.value === p.period) ? p.period : 'this_month';
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

function shiftCalendarMonth(year, month, delta) {
  let idx = year * 12 + (month - 1) + delta;
  return { year: Math.floor(idx / 12), month: (idx % 12) + 1 };
}

/** Period shown beside page title (e.g. May 2026, Coming week). */
function headerPeriodLabel(mode, month, year, period) {
  if (mode === 'upcoming') {
    if (period === 'coming_week') {
      return PERIOD_OPTIONS.find(o => o.value === period)?.label || 'Coming week';
    }
    const delta = period === 'this_month' ? 0 : period === 'next_month' ? 1 : 2;
    const now = new Date();
    const { year: y, month: m } = shiftCalendarMonth(now.getFullYear(), now.getMonth() + 1, delta);
    const name = MONTH_OPTIONS.find(o => o.value === m)?.label;
    return name ? `${name} ${y}` : String(y);
  }
  if (month === 0) return `${year} (all months)`;
  const name = MONTH_OPTIONS.find(o => o.value === month)?.label;
  return name ? `${name} ${year}` : String(year);
}

function statusSummary(mode, month, year, period) {
  const periodLabel = headerPeriodLabel(mode, month, year, period);
  return mode === 'upcoming' ? `Upcoming · ${periodLabel}` : `Reported · ${periodLabel}`;
}

export default function EarningsBeatsPage({
  onOpenChart,
  isActive,
  onContextMenuRequest,
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
  const [expandedSymbol, setExpandedSymbol] = useState(null);
  const [symbolSearch, setSymbolSearch] = useState('');
  const [sortKey, setSortKey] = useState(initialSort.key);
  const [sortDir, setSortDir] = useState(initialSort.dir);
  const [isEarningsPlusReloading, setIsEarningsPlusReloading] = useState(false);
  const [warmStatus, setWarmStatus] = useState(null);

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
      mode, month, year, period, mcapMin, mcapMax,
      epsSurpriseMin, epsSurpriseMax, revenueSurpriseMin, revenueSurpriseMax,
      earningsPlusFilter,
      sortByMode,
    });
  }, [mode, month, year, period, mcapMin, mcapMax, epsSurpriseMin, epsSurpriseMax, revenueSurpriseMin, revenueSurpriseMax, earningsPlusFilter, sortByMode]);

  useEffect(() => {
    const next = normalizeSortEntry(sortByMode[mode], mode);
    setSortKey(next.key);
    setSortDir(next.dir);
  }, [mode, sortByMode]);

  useEffect(() => {
    setExpandedSymbol(null);
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
      params.year = year;
      params.month = month;
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
      setRows(data.rows || []);
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
  }, [mode, month, year, period, mcapDebounced.min, mcapDebounced.max, surpriseDebounced, earningsPlusFilter]);

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
    const q = symbolSearch.trim().toUpperCase();
    if (!q) return sortedRows;
    return sortedRows.filter(row => {
      const sym = String(row.symbol || '').toUpperCase();
      const name = String(row.name || '').toUpperCase();
      return sym.includes(q) || name.includes(q);
    });
  }, [sortedRows, symbolSearch]);

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

  const headerPeriod = headerPeriodLabel(mode, month, year, period);
  const statusLine = statusSummary(mode, month, year, period);

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
              gap: 4,
              paddingTop: 0,
              paddingBottom: 0,
              minWidth: 0,
            }}
          >
            <div style={filterGridStyle}>
              <FilterField label="Earnings" width={FILTER_COL.earnings}>
                <select value={mode} onChange={e => setMode(e.target.value)} style={selectFullStyle}>
                  <option value="reported">Reported</option>
                  <option value="upcoming">Upcoming</option>
                </select>
              </FilterField>
              <FilterField label="Year" width={FILTER_COL.year} disabled={mode === 'upcoming'}>
                <select
                  value={year}
                  onChange={e => {
                    const y = Number(e.target.value);
                    setYear(y);
                    if (!isReportedMonthSelectable(y, month)) {
                      setMonth(clampReportedMonth(y, month));
                    }
                  }}
                  disabled={mode === 'upcoming'}
                  title={mode === 'upcoming' ? 'Year applies to Reported earnings only' : undefined}
                  style={controlStyle(selectFullStyle, mode === 'upcoming')}
                >
                  {years.map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </FilterField>
              <FilterField label={mode === 'upcoming' ? 'Period' : 'Month'} width={FILTER_COL.month}>
                {mode === 'upcoming' ? (
                  <select
                    value={period}
                    onChange={e => setPeriod(e.target.value)}
                    style={selectFullStyle}
                  >
                    {PERIOD_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                ) : (
                  <select
                    value={month}
                    onChange={e => setMonth(Number(e.target.value))}
                    style={selectFullStyle}
                    title="Future months in the selected year are disabled until earnings are reported"
                  >
                    {MONTH_OPTIONS.map(o => {
                      const disabled = !isReportedMonthSelectable(year, o.value);
                      return (
                        <option key={o.value} value={o.value} disabled={disabled}>
                          {o.label}
                        </option>
                      );
                    })}
                  </select>
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
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                paddingBottom: 1,
                flexWrap: 'nowrap',
              }}
              >
                <span style={{ fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>M · B · T</span>
                <button
                  type="button"
                  onClick={() => load(true)}
                  disabled={loading}
                  title="Bypass cache and pull fresh data from TradingView"
                  style={{
                    padding: '6px 12px',
                    borderRadius: 5,
                    border: '1px solid var(--accent-blue)',
                    backgroundColor: loading ? 'var(--bg-tertiary)' : 'rgba(56,139,253,0.12)',
                    color: loading ? 'var(--text-muted)' : 'var(--accent-blue)',
                    fontSize: 12,
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                    cursor: loading ? 'wait' : 'pointer',
                  }}
                >
                  {loading ? 'Fetching…' : 'Fetch latest data'}
                </button>
                {mode === 'reported' && onRefreshEarningsPlusCache && (
                  <>
                    <button
                      type="button"
                      onClick={() => onRefreshEarningsPlusCache({ year, month })}
                      disabled={earningsPlusRefreshRunning || isEarningsPlusReloading}
                      title="Refresh missing or stale Earnings+ cache rows for this month (uses DB quarterly data when available)."
                      style={{
                        padding: '6px 12px',
                        borderRadius: 5,
                        border: '1px solid #d29922',
                        backgroundColor: (earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'var(--bg-tertiary)' : 'rgba(210,153,34,0.14)',
                        color: (earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'var(--text-muted)' : '#d29922',
                        fontSize: 12,
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        cursor: (earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'wait' : 'pointer',
                      }}
                    >
                      {(earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'Refreshing Earnings+…' : 'Refresh Earnings+ cache'}
                    </button>
                    <button
                      type="button"
                      onClick={() => onRefreshEarningsPlusCache({ year, month, onlyIncomplete: true })}
                      disabled={earningsPlusRefreshRunning || isEarningsPlusReloading}
                      title="Retry symbols with no cache row or insufficient_data only."
                      style={{
                        padding: '6px 12px',
                        borderRadius: 5,
                        border: '1px solid var(--border-light)',
                        backgroundColor: 'var(--bg-secondary)',
                        color: 'var(--text-secondary)',
                        fontSize: 12,
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
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
                        padding: '6px 12px',
                        borderRadius: 5,
                        border: '1px solid var(--border-light)',
                        backgroundColor: 'var(--bg-secondary)',
                        color: 'var(--text-muted)',
                        fontSize: 12,
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        cursor: (earningsPlusRefreshRunning || isEarningsPlusReloading) ? 'wait' : 'pointer',
                      }}
                    >
                      Force all
                    </button>
                  </>
                )}
              </div>
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
                  title={mode === 'upcoming' ? 'Surprise % filters apply to Reported earnings only' : 'Minimum EPS surprise % (≥). Use 0 to include met estimates (0%). Empty = no floor.'}
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
                  title={mode === 'upcoming' ? 'Surprise % filters apply to Reported earnings only' : 'Minimum revenue surprise % (≥). Use 0 to include met estimates (0%). Empty = no floor.'}
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
              <FilterField label="Earnings+" disabled={mode === 'upcoming'}>
                <select
                  value={earningsPlusFilter}
                  onChange={e => setEarningsPlusFilter(e.target.value)}
                  disabled={mode === 'upcoming'}
                  aria-label="Earnings+ filter"
                  title={mode === 'upcoming' ? 'Earnings+ applies to Reported earnings only' : 'Filter reported rows by the Screener-derived Earnings+ quality badge'}
                  style={controlStyle(selectFullStyle, mode === 'upcoming')}
                >
                  {EARNINGS_PLUS_FILTER_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </FilterField>
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
            width: 200,
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
              placeholder="Search symbol or name…"
              title="Filter loaded earnings rows by NSE symbol or company name"
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
                  <SortableTh label="MCap" sortKey="market_cap_basic" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Price" sortKey="price" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="1D %" sortKey="change_1d_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="2W %" sortKey="change_2w_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
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
                  <SortableTh label="MCap" sortKey="market_cap_basic" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Price" sortKey="price" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="1D %" sortKey="change_1d_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="2W %" sortKey="change_2w_pct" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Upcoming" sortKey="earnings_release_next_date" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="EPS est" sortKey="eps_estimate" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  <SortableTh label="Rev est" sortKey="revenue_estimate" activeKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {filteredRows.map(row => {
              const sym = row.symbol;
              const isSel = sym === selectedSymbol;
              const isExpanded = sym === expandedSymbol;
              const columnCount = mode === 'reported'
                ? EARNINGS_REPORTED_COLUMN_COUNT
                : EARNINGS_UPCOMING_COLUMN_COUNT;
              const epsBeat = Number(row.eps_surprise_pct);
              const revBeat = Number(row.revenue_surprise_pct);
              return (
                <React.Fragment key={sym}>
                <tr
                  onClick={() => setSelectedSymbol(sym)}
                  onDoubleClick={(e) => {
                    e.preventDefault();
                    if (isExpanded) {
                      setExpandedSymbol(null);
                    } else {
                      setExpandedSymbol(sym);
                      setSelectedSymbol(sym);
                    }
                  }}
                  title="Double-click row to show or hide Screener quarterly results"
                  onContextMenu={(e) => {
                    e.preventDefault();
                    if (onContextMenuRequest) {
                      onContextMenuRequest({
                        x: e.clientX,
                        y: e.clientY,
                        symbol: sym,
                        type: 'stock',
                        sourcePage: 'earnings-beats',
                      });
                    }
                  }}
                  style={{
                    cursor: 'pointer',
                    backgroundColor: isSel ? 'rgba(56,139,253,0.12)' : 'transparent',
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
                    {sym}
                  </td>
                  <td style={tdStyle}>{formatMarketCap(row.market_cap_basic)}</td>
                  <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)' }}>{fmtPrice(row.price)}</td>
                  <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)', color: chgPctColor(row.change_1d_pct), fontWeight: 600 }}>
                    {fmtPct(row.change_1d_pct)}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)', color: chgPctColor(row.change_2w_pct), fontWeight: 600 }}>
                    {fmtPct(row.change_2w_pct)}
                  </td>
                  {mode === 'reported' ? (
                    <>
                      <td style={tdStyle}>{row.earnings_release_date || '—'}</td>
                      <td style={tdStyle}>{fmtEps(row.eps_actual)}</td>
                      <td style={tdStyle}>{fmtEps(row.eps_estimate)}</td>
                      <td style={{ ...tdStyle, color: epsBeat >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 600 }}>
                        {fmtPct(row.eps_surprise_pct)}
                      </td>
                      <td style={tdStyle}>{formatMarketCap(row.revenue_actual)}</td>
                      <td style={tdStyle}>{formatMarketCap(row.revenue_estimate)}</td>
                      <td style={{ ...tdStyle, color: revBeat >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 600 }}>
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
                    <EarningsQuarterlyPanel symbol={sym} columnCount={columnCount} />
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
            </span>
            <div style={{ width: 1, height: 22, backgroundColor: 'var(--border)', flexShrink: 0 }} />
            <ExternalFinancialsLinks
              symbol={selectedSymbol}
              height={28}
              layout="inline"
              includeTvEarnings
              onOpenChart={onOpenChart || null}
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
