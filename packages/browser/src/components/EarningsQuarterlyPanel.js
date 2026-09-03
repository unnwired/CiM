import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { formatINRFromCrores, formatMarketCap } from '../utils/formatMarketCap';
import { screenerFinancialsUrl } from '../utils/externalFinancialsLinks';
import { openExternalUrl } from '../utils/openExternalUrl';
import ScreenerProfileSidebar from './ScreenerProfileSidebar';
import { isLoopbackHost } from '../config/operatorMode';

/** Match quarterly table block height so the profile column scrolls independently. */
const TABLE_HEAD_ROW_PX = 34;
const TABLE_BODY_ROW_PX = 29;
function quarterlyTableBlockHeight(rowCount) {
  return TABLE_HEAD_ROW_PX + Math.max(1, rowCount) * TABLE_BODY_ROW_PX;
}

const API = '';

const HOST_ONLY_REFRESH_MSG =
  'Manual refresh from Screener is only available on the showcase host (loopback operator).';
const MONTH_INDEX = {
  jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
  jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
  january: 0, february: 1, march: 2, april: 3, june: 5,
  july: 6, august: 7, september: 8, october: 9, november: 10, december: 11,
};

/** Blue / gold / purple — latest quarter, 1Y ago, 2Y ago (idle + hover). */
const ROLE_BG = {
  latest: 'rgba(56, 139, 253, 0.14)',
  yoy1: 'rgba(210, 153, 34, 0.14)',
  yoy2: 'rgba(163, 113, 247, 0.12)',
};
const ROLE_BG_HOVER = {
  latest: 'rgba(56, 139, 253, 0.28)',
  yoy1: 'rgba(210, 153, 34, 0.28)',
  yoy2: 'rgba(163, 113, 247, 0.26)',
};
const ROLE_HEADER_COLOR = {
  latest: 'var(--accent-blue)',
  yoy1: '#d29922',
  yoy2: '#a371f7',
};

function fmtEps(val) {
  const n = Number(String(val).replace(/,/g, ''));
  if (!Number.isFinite(n)) return val ?? '—';
  return n.toFixed(2);
}

function fmtPct(val) {
  const s = String(val ?? '').trim();
  if (!s) return '—';
  if (s.endsWith('%')) return s;
  const n = Number(s.replace(/,/g, ''));
  if (!Number.isFinite(n)) return s;
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

const SCREENER_SITE = 'https://www.screener.in';

function normalizeScreenerPdfUrl(url) {
  const u = String(url || '').trim();
  if (!u) return null;
  if (u.startsWith('//')) return `https:${u}`;
  if (u.startsWith('/')) return `${SCREENER_SITE}${u}`;
  return u;
}

function QuarterPdfLink({ href }) {
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={e => e.stopPropagation()}
      style={{
        fontSize: 10,
        fontWeight: 500,
        color: 'var(--accent-blue)',
        textDecoration: 'none',
      }}
    >
      PDF
    </a>
  );
}

/** Metric rows + TV overlay before Raw PDF (Screener layout: PDF below EPS). */
function buildDisplayRows(rows, periods, tvRows = []) {
  const metrics = (rows || []).filter(r => !(r.is_pdf || r.slug === 'raw_pdf'));
  const tv = (tvRows || []).filter(r => r && r.source === 'tradingview');
  const existing = (rows || []).find(r => r.is_pdf || r.slug === 'raw_pdf');
  const beforePdf = [...metrics, ...tv];
  if (existing) {
    return [...beforePdf, existing];
  }
  const pdfValues = (periods || []).map(p => p.pdf_url ?? null);
  return [
    ...beforePdf,
    { label: 'Raw PDF', slug: 'raw_pdf', values: pdfValues, is_pdf: true },
  ];
}

function formatCell(row, raw) {
  if (row.is_pdf) {
    const href = normalizeScreenerPdfUrl(raw);
    return href ? <QuarterPdfLink href={href} /> : '—';
  }
  if (raw == null || raw === '') return '—';
  // TradingView overlay: EPS as ₹ decimals; revenue as full INR (M/B/T).
  if (row.source === 'tradingview') {
    if (row.value_kind === 'eps' || String(row.slug || '').includes('eps')) {
      return `₹${fmtEps(raw)}`;
    }
    if (row.value_kind === 'revenue' || String(row.slug || '').includes('rev')) {
      return formatMarketCap(raw);
    }
  }
  const label = (row.label || '').toLowerCase();
  if (label.includes('eps')) return `₹${fmtEps(raw)}`;
  if (label.includes('%') || label.includes('opm') || label.includes('tax')) return fmtPct(raw);
  const n = Number(String(raw).replace(/,/g, ''));
  if (Number.isFinite(n)) return formatINRFromCrores(n);
  return String(raw);
}

function isBoldRow(label) {
  const l = (label || '').toLowerCase();
  return l.includes('operating profit') || l.includes('profit before tax') || l.includes('net profit');
}

/** Parse Screener headers like "Sep 2024" or "Mar 2025". */
function parsePeriodLabel(label) {
  const s = String(label || '').trim();
  const m = s.match(/^([A-Za-z]+)\s+(\d{4})$/);
  if (!m) return null;
  const monthKey = m[1].toLowerCase();
  const month =
    MONTH_INDEX[monthKey] ??
    MONTH_INDEX[monthKey.slice(0, 3)] ??
    null;
  const year = Number(m[2]);
  if (month == null || !Number.isFinite(year)) return null;
  return { month, year, label: s };
}

/**
 * Mark latest quarter + same fiscal quarter 1Y and 2Y ago (for column tint + hover group).
 */
function buildYoYColumnMeta(periods) {
  if (!periods?.length) return [];
  const parsed = periods.map((p, index) => ({
    index,
    parsed: parsePeriodLabel(p.period),
  }));
  const latestIdx = periods.length - 1;
  const latest = parsed[latestIdx]?.parsed;
  if (!latest) {
    return periods.map((p) => {
      const parsed = parsePeriodLabel(p.period);
      return { role: null, month: parsed?.month ?? null };
    });
  }

  const findSameQuarterYear = (yearDelta) => {
    const targetYear = latest.year - yearDelta;
    for (let i = parsed.length - 1; i >= 0; i -= 1) {
      const p = parsed[i].parsed;
      if (p && p.month === latest.month && p.year === targetYear) return i;
    }
    return -1;
  };

  const yoy1Idx = findSameQuarterYear(1);
  const yoy2Idx = findSameQuarterYear(2);

  return periods.map((p, i) => {
    const parsed = parsePeriodLabel(p.period);
    const month = parsed?.month ?? null;
    let role = null;
    if (i === latestIdx) role = 'latest';
    else if (i === yoy1Idx) role = 'yoy1';
    else if (i === yoy2Idx) role = 'yoy2';
    return { role, month };
  });
}

/**
 * For a hovered month family: blue = newest year, gold = 1Y before that, purple = 2Y before.
 * Roles are fixed by calendar — not by which column the pointer is on.
 */
function buildMonthFamilyRoles(periods, hoveredMonth) {
  const rolesByCol = {};
  if (hoveredMonth == null || !periods?.length) return rolesByCol;

  const sameMonth = [];
  periods.forEach((p, colIdx) => {
    const parsed = parsePeriodLabel(p.period);
    if (parsed && parsed.month === hoveredMonth) {
      sameMonth.push({ colIdx, year: parsed.year });
    }
  });
  if (!sameMonth.length) return rolesByCol;

  const newestYear = Math.max(...sameMonth.map(x => x.year));
  const assign = (yearDelta, role) => {
    const targetYear = newestYear - yearDelta;
    const hit = sameMonth.find(x => x.year === targetYear);
    if (hit) rolesByCol[hit.colIdx] = role;
  };
  assign(0, 'latest');
  assign(1, 'yoy1');
  assign(2, 'yoy2');
  return rolesByCol;
}

function effectiveColumnRole(meta, colIdx, hoveredMonth, hoverRolesByCol) {
  if (hoveredMonth != null) return hoverRolesByCol[colIdx] || null;
  if (meta?.role) return meta.role;
  return null;
}

function columnBackground(meta, colIdx, hoveredMonth, hoverRolesByCol) {
  const role = effectiveColumnRole(meta, colIdx, hoveredMonth, hoverRolesByCol);
  if (!role) return undefined;
  const palette = hoveredMonth != null ? ROLE_BG_HOVER : ROLE_BG;
  return palette[role];
}

function metricCellBackground(rowIdx, colMeta, colIdx, hoveredMonth, hoverRolesByCol) {
  const stripe = rowIdx % 2 === 0 ? 'var(--bg-secondary)' : 'var(--bg-primary)';
  const tint = columnBackground(colMeta, colIdx, hoveredMonth, hoverRolesByCol);
  return tint || stripe;
}

function headerColor(meta, colIdx, hoveredMonth, hoverRolesByCol) {
  const role = effectiveColumnRole(meta, colIdx, hoveredMonth, hoverRolesByCol);
  if (role) return ROLE_HEADER_COLOR[role];
  return 'var(--text-secondary)';
}

/** Quarterly table + Screener company profile (reused in Earnings table row and Portfolio modal). */
export function EarningsQuarterlyPanelContent({
  symbol,
  profileWidthPx,
  scrollTableToLatest = true,
  onBasisChange = null,
}) {
  const showRefreshButton = isLoopbackHost();
  const [basis, setBasis] = useState('consolidated');
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  /** Month family (0–11) under pointer — shows fixed blue/gold/purple YoY trio for that month. */
  const [hoveredMonth, setHoveredMonth] = useState(null);

  useEffect(() => {
    if (typeof onBasisChange === 'function') onBasisChange(basis);
  }, [basis, onBasisChange]);

  const load = useCallback(async ({ refresh = false } = {}) => {
    if (!symbol) return;
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const r = refresh
        ? await axios.post(`${API}/api/screener-quarters/${encodeURIComponent(symbol)}/refresh`, null, {
            params: { basis },
          })
        : await axios.get(`${API}/api/screener-quarters/${encodeURIComponent(symbol)}`, {
            params: { basis, fetch_if_missing: true },
          });
      setData(r.data?.data ?? null);
      setStatus(r.data?.status ?? null);
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;
      const hostOnly = status === 403
        && String(detail || '').toLowerCase().includes('host-only');

      if (hostOnly && refresh) {
        setError(HOST_ONLY_REFRESH_MSG);
      } else {
        const msg = detail || err.message || 'Failed to load quarterly data';
        setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
        if (!refresh) setData(null);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [symbol, basis]);

  useEffect(() => {
    setData(null);
    setStatus(null);
    setError(null);
    setHoveredMonth(null);
    if (symbol) load();
  }, [symbol, basis, load]);

  const periods = useMemo(() => data?.periods ?? [], [data]);
  const rows = data?.rows ?? [];
  const tvRows = data?.tv_rows ?? [];
  const displayRows = useMemo(
    () => buildDisplayRows(rows, periods, tvRows),
    [rows, periods, tvRows],
  );
  const columnMeta = useMemo(() => buildYoYColumnMeta(periods), [periods]);
  const hoverRolesByCol = useMemo(
    () => buildMonthFamilyRoles(periods, hoveredMonth),
    [periods, hoveredMonth],
  );
  const hasYoYHighlight = columnMeta.some(m => m.role);
  const screenerHref = screenerFinancialsUrl(symbol, basis);

  const onColumnEnter = useCallback((colIdx) => (e) => {
    e.stopPropagation();
    const parsed = parsePeriodLabel(periods[colIdx]?.period);
    if (parsed?.month != null) setHoveredMonth(parsed.month);
  }, [periods]);

  const clearColumnHover = useCallback((e) => {
    e.stopPropagation();
    setHoveredMonth(null);
  }, []);

  const tableBlockHeight = quarterlyTableBlockHeight(displayRows.length);
  const tableWrapRef = useRef(null);
  const [profileMaxHeight, setProfileMaxHeight] = useState(null);

  const scrollTableToEnd = useCallback(() => {
    const el = tableWrapRef.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    if (max > 0) el.scrollLeft = max;
  }, []);

  useLayoutEffect(() => {
    const el = tableWrapRef.current;
    if (!el) return;
    const sync = () => {
      setProfileMaxHeight(el.offsetHeight);
      if (scrollTableToLatest) scrollTableToEnd();
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, [displayRows.length, periods.length, data, loading, scrollTableToLatest, scrollTableToEnd]);

  useLayoutEffect(() => {
    if (!scrollTableToLatest || loading || !data || !displayRows.length) return;
    scrollTableToEnd();
    const id = requestAnimationFrame(() => {
      requestAnimationFrame(scrollTableToEnd);
    });
    return () => cancelAnimationFrame(id);
  }, [scrollTableToLatest, loading, data, displayRows.length, periods.length, basis, scrollTableToEnd]);

  return (
      <div
        style={{
          width: '100%',
          maxWidth: '100%',
          boxSizing: 'border-box',
          padding: '10px 12px 12px',
          borderLeft: '3px solid var(--accent-blue)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)' }}>
            Quarterly Results (Screener)
          </span>
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
            {data?.unit_note || 'Figures in ₹ Crores'}
          </span>
          {hasYoYHighlight && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: ROLE_BG.latest }} />
                Latest
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: ROLE_BG.yoy1 }} />
                1Y ago
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: ROLE_BG.yoy2 }} />
                2Y ago
              </span>
              <span style={{ color: 'var(--text-muted)' }}>· hover a month: blue = newest, gold / purple = 1Y / 2Y earlier</span>
            </span>
          )}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={e => { e.stopPropagation(); setBasis('consolidated'); }}
              style={{
                fontSize: 10,
                padding: '3px 8px',
                borderRadius: 4,
                border: '1px solid var(--border)',
                backgroundColor: basis === 'consolidated' ? 'var(--bg-active)' : 'var(--bg-tertiary)',
                color: basis === 'consolidated' ? 'var(--text-primary)' : 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              Consolidated
            </button>
            <button
              type="button"
              onClick={e => { e.stopPropagation(); setBasis('standalone'); }}
              style={{
                fontSize: 10,
                padding: '3px 8px',
                borderRadius: 4,
                border: '1px solid var(--border)',
                backgroundColor: basis === 'standalone' ? 'var(--bg-active)' : 'var(--bg-tertiary)',
                color: basis === 'standalone' ? 'var(--text-primary)' : 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              Standalone
            </button>
            {showRefreshButton && (
              <button
                type="button"
                disabled={refreshing || loading}
                onClick={e => { e.stopPropagation(); load({ refresh: true }); }}
                title="Refresh this symbol from Screener"
                style={{
                  fontSize: 10,
                  padding: '3px 10px',
                  borderRadius: 4,
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-tertiary)',
                  color: 'var(--text-secondary)',
                  cursor: refreshing || loading ? 'wait' : 'pointer',
                }}
              >
                {refreshing ? 'Refreshing…' : 'Refresh'}
              </button>
            )}
            {screenerHref && (
              <a
                href={screenerHref}
                target="_blank"
                rel="noopener noreferrer"
                title={basis === 'standalone'
                  ? `Screener.in standalone — ${symbol}`
                  : `Screener.in consolidated — ${symbol}`}
                onClick={e => { e.stopPropagation(); openExternalUrl(screenerHref, e); }}
                style={{
                  fontSize: 10,
                  padding: '3px 8px',
                  borderRadius: 4,
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-tertiary)',
                  color: 'var(--accent-blue)',
                  cursor: 'pointer',
                  textDecoration: 'none',
                  display: 'inline-flex',
                  alignItems: 'center',
                }}
              >
                Screener ↗
              </a>
            )}
          </div>
        </div>

        {data?.fetched_at && (
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6 }}>
            Last updated {data.fetched_at}
            {status === 'cache_stale' && data.refresh_error
              ? ` · refresh failed (${data.refresh_error})`
              : ''}
            {status === 'fetched' ? ' · just loaded from Screener' : ''}
          </div>
        )}

        {loading && !data && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '8px 0' }}>
            Loading quarterly data from Screener…
          </div>
        )}

        {error && (
          <div style={{ fontSize: 11, color: 'var(--accent-red)', padding: '4px 0 8px', whiteSpace: 'pre-wrap' }}>
            {error}
          </div>
        )}

        {!loading && data && displayRows.length > 0 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              width: '100%',
            }}
          >
            <div
              ref={tableWrapRef}
              style={{
                flex: '1 1 0',
                minWidth: 0,
                overflowX: 'auto',
                border: '1px solid var(--border-light)',
                borderRadius: 6,
                backgroundColor: 'var(--bg-secondary)',
              }}
              onMouseLeave={clearColumnHover}
            >
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, minWidth: 520 }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border)' }}>
                  <th style={{
                    padding: '6px 10px',
                    textAlign: 'left',
                    color: 'var(--text-secondary)',
                    fontWeight: 600,
                    position: 'sticky',
                    left: 0,
                    backgroundColor: 'var(--bg-tertiary)',
                    zIndex: 2,
                  }}
                  >
                    Metric
                  </th>
                  {periods.map((p, colIdx) => {
                    const meta = columnMeta[colIdx] || { role: null, month: null };
                    const canHover = meta.month != null;
                    const role = effectiveColumnRole(meta, colIdx, hoveredMonth, hoverRolesByCol);
                    return (
                      <th
                        key={p.period}
                        onMouseEnter={canHover ? onColumnEnter(colIdx) : undefined}
                        style={{
                          padding: '6px 10px',
                          textAlign: 'right',
                          color: headerColor(meta, colIdx, hoveredMonth, hoverRolesByCol),
                          fontWeight: 600,
                          whiteSpace: 'nowrap',
                          backgroundColor: columnBackground(meta, colIdx, hoveredMonth, hoverRolesByCol) || 'var(--bg-tertiary)',
                          transition: 'background-color 0.12s ease',
                          cursor: canHover ? 'default' : undefined,
                          boxShadow: role ? `inset 0 -2px 0 ${ROLE_HEADER_COLOR[role]}` : 'none',
                        }}
                      >
                        {p.period}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {displayRows.map((row, rowIdx) => (
                  <tr
                    key={row.slug || row.label}
                    style={{ borderBottom: '1px solid var(--border-light)' }}
                  >
                    <td style={{
                      padding: '5px 10px',
                      color: isBoldRow(row.label) ? 'var(--text-primary)' : 'var(--text-secondary)',
                      fontWeight: isBoldRow(row.label) ? 600 : 400,
                      position: 'sticky',
                      left: 0,
                      backgroundColor: rowIdx % 2 === 0 ? 'var(--bg-secondary)' : 'var(--bg-primary)',
                      whiteSpace: 'nowrap',
                      zIndex: 1,
                    }}
                    >
                      {row.label}
                    </td>
                    {row.values.map((val, colIdx) => {
                      const meta = columnMeta[colIdx] || { role: null, month: null };
                      const canHover = meta.month != null;
                      return (
                        <td
                          key={`${row.slug}-${colIdx}`}
                          onMouseEnter={canHover ? onColumnEnter(colIdx) : undefined}
                          style={{
                            padding: '5px 10px',
                            textAlign: 'right',
                            fontFamily: 'var(--font-mono)',
                            color: 'var(--text-primary)',
                            fontWeight: isBoldRow(row.label) ? 600 : 400,
                            backgroundColor: metricCellBackground(rowIdx, meta, colIdx, hoveredMonth, hoverRolesByCol),
                            transition: 'background-color 0.12s ease',
                          }}
                        >
                          {formatCell(row, val)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <ScreenerProfileSidebar
              data={data}
              maxHeight={profileMaxHeight ?? tableBlockHeight}
              widthPx={profileWidthPx}
            />
          </div>
        )}
      </div>
  );
}

export default function EarningsQuarterlyPanel({ symbol, columnCount, onBasisChange = null }) {
  return (
    <td colSpan={columnCount} style={{ padding: 0, borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-primary)' }}>
      <EarningsQuarterlyPanelContent symbol={symbol} onBasisChange={onBasisChange} />
    </td>
  );
}
