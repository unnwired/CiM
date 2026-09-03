import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import axios from 'axios';
import { applySavedOrder, reorderByGap, insertionGapFromRowHover } from '../utils/listOrder';
import { setListDragImage, DropInsetLine } from '../utils/listDnD';
import { CHART_DATA_UPDATED_EVENT, MOVERS_REFRESH_EVENT } from '../chartEvents';
import { usePatchOverlay } from '../intraday/usePatchOverlay';
import { useRegisterFocusedSymbol } from '../intraday/useRegisterFocusedSymbol';
import { useRegisterIntradaySymbols } from '../intraday/useRegisterIntradaySymbols';
import { symbolsForMarketMap } from '../intraday/intradayRefreshScopes';
import {
  sortMarketMapConstituents,
  summarizeConstituentChanges,
} from '../utils/marketMapConstituents';
import MarketMapTreemap from '../components/MarketMapTreemap';
import MarketMapEarningsBadges from '../components/MarketMapEarningsBadges';
import StockListSplitBody from '../components/StockListSplitBody';
import { useChartPrefsContext } from '../chartPrefs/useChartPrefs';
import { loadChartPrefs } from '../chartPrefs/chartPrefsStore';
import {
  hydrateListOrderFields,
  LIST_ORDER_KEYS,
  persistLayoutOrderFields,
  syncListOrdersToServerIfNeeded,
} from '../layout/listOrderPersistence';
import {
  MM_TEXT_PRIMARY,
  MM_TEXT_SECONDARY,
  tileBackground,
  tilePctColor,
} from '../utils/marketMapTileStyle';

const API = '';

const PERIOD_TABS = [
  { id: '1D', label: '1D', enabled: true },
  { id: '5D', label: '5D', enabled: false },
  { id: '1M', label: '1M', enabled: false },
  { id: '3M', label: '3M', enabled: false },
  { id: '6M', label: '6M', enabled: false },
  { id: '1Y', label: '1Y', enabled: false },
  { id: 'YTD', label: 'YTD', enabled: false },
];

const MAGNITUDE_CHIPS = [
  { value: 5, label: '≥+5%' },
  { value: 3, label: '≥+3%' },
  { value: 1, label: '≥+1%' },
  { value: -1, label: '≤−1%' },
  { value: -3, label: '≤−3%' },
  { value: -5, label: '≤−5%' },
];

function formatPrice(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  return `₹${Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPct(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  const n = Number(v);
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function AdvanceDeclineBar({ advances, declines, total }) {
  const adv = Number(advances) || 0;
  const dec = Number(declines) || 0;
  const t = Number(total) || adv + dec || 1;
  const gPct = Math.round((adv / t) * 100);
  const rPct = 100 - gPct;
  return (
    <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', backgroundColor: 'var(--bg-tertiary)', marginTop: 4 }}>
      <div style={{ width: `${gPct}%`, backgroundColor: 'var(--accent-green)', minWidth: adv > 0 ? 2 : 0 }} />
      <div style={{ width: `${rPct}%`, backgroundColor: 'var(--accent-red)', minWidth: dec > 0 ? 2 : 0 }} />
    </div>
  );
}

function IndexRailRow({
  row,
  i,
  selected,
  onSelect,
  rowRefs,
  draggable,
  onDragStartRow,
  onDragOverRow,
  onDropRow,
  onDragEndRow,
  dragDimmed,
}) {
  const isSelected = selected?.symbol === row.symbol;
  const chg = row.index_change_pct;
  const chgColor = chg > 0 ? 'var(--accent-green)' : chg < 0 ? 'var(--accent-red)' : 'var(--text-muted)';
  const adv = row.advances;
  const dec = row.declines;
  const err = row.error;

  return (
    <div
      ref={el => { rowRefs.current[i] = el; }}
      onClick={() => onSelect(row)}
      onDragOver={e => onDragOverRow && onDragOverRow(e, i)}
      onDrop={e => onDropRow && onDropRow(e)}
      style={{
        display: 'flex',
        flexDirection: 'column',
        padding: '7px 10px',
        cursor: 'pointer',
        borderLeft: isSelected ? '2px solid var(--accent-blue)' : '2px solid transparent',
        backgroundColor: isSelected ? 'rgba(56,139,253,0.08)' : 'transparent',
        borderBottom: '1px solid var(--border-light)',
        opacity: dragDimmed ? 0.45 : 1,
      }}
      onMouseEnter={e => { if (!isSelected) e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
      onMouseLeave={e => { if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent'; }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 4, minWidth: 0 }}>
        {draggable ? (
          <span
            title="Drag to reorder"
            draggable
            onDragStart={e => { e.stopPropagation(); onDragStartRow(e, i); }}
            onDragEnd={e => { e.stopPropagation(); if (onDragEndRow) onDragEndRow(); }}
            onClick={e => e.stopPropagation()}
            style={{
              flexShrink: 0,
              width: 14,
              cursor: 'grab',
              color: 'var(--text-muted)',
              fontSize: 10,
              lineHeight: 1,
              userSelect: 'none',
              letterSpacing: '-0.12em',
              paddingTop: 2,
            }}
          >
            ⋮⋮
          </span>
        ) : null}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6, alignItems: 'center' }}>
            <span style={{
              fontSize: 11,
              fontWeight: 600,
              color: isSelected ? 'var(--accent-blue)' : MM_TEXT_PRIMARY,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            >
              {row.name}
            </span>
            {chg != null && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: chgColor, flexShrink: 0 }}>
                {formatPct(chg)}
              </span>
            )}
          </div>
          {err ? (
            <span style={{ fontSize: 10, color: 'var(--accent-red)', marginTop: 2 }}>Data unavailable</span>
          ) : (
            <>
              <AdvanceDeclineBar advances={adv} declines={dec} total={row.total} />
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3, fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                <span style={{ color: 'var(--accent-green)' }}>{adv ?? '—'} ↑</span>
                <span style={{ color: 'var(--accent-red)' }}>{dec ?? '—'} ↓</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function MarketMapPage({ onOpenChart, isActive }) {
  const chartPrefs = useChartPrefsContext();
  const [catalog, setCatalog] = useState([]);
  const [summary, setSummary] = useState([]);
  const [asOf, setAsOf] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [summaryError, setSummaryError] = useState(null);

  const [period, setPeriod] = useState('1D');
  const [viewMode, setViewMode] = useState('stocks');
  const [heatmapLayout, setHeatmapLayout] = useState('grid');
  const [sort, setSort] = useState('major');
  const [magnitude, setMagnitude] = useState(null);
  const [alphaDesc, setAlphaDesc] = useState(false);

  const [paneWidth, setPaneWidth] = useState(280);
  const [indexOrder, setIndexOrder] = useState(null);
  const wrapperRef = useRef(null);
  const rowRefs = useRef({});
  const dragIdxRef = useRef(null);
  const dropGapRef = useRef(null);
  const [dropGap, setDropGap] = useState(null);
  const [draggingIdx, setDraggingIdx] = useState(null);
  const draggingDivider = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  const summaryLenRef = useRef(0);
  summaryLenRef.current = summary.length;
  const detailRef = useRef(detail);
  detailRef.current = detail;

  const loadSummary = useCallback((force = false, opts = {}) => {
    const quiet = !!opts.quiet || summaryLenRef.current > 0;
    if (!quiet) setLoadingSummary(true);
    setSummaryError(null);
    return axios.get(`${API}/api/market-map/summary`, { params: { period, force } })
      .then(r => {
        setAsOf(r.data.as_of || null);
        const items = r.data.items || [];
        setSummary(items);
        setCatalog(prev => {
          if (prev.length) return prev;
          return items.map(it => ({ symbol: it.symbol, name: it.name }));
        });
        setSelected(prev => {
          if (prev && items.some(it => it.symbol === prev.symbol)) return prev;
          return items[0] || null;
        });
      })
      .catch(err => {
        setSummaryError(err.response?.data?.detail || 'Failed to load market map');
      })
      .finally(() => {
        if (!quiet) setLoadingSummary(false);
      });
  }, [period]);

  const loadDetail = useCallback((symbol, opts = {}) => {
    if (!symbol) return Promise.resolve();
    const quiet = !!opts.quiet || (
      detailRef.current?.index?.symbol === symbol
      && Array.isArray(detailRef.current?.constituents)
      && detailRef.current.constituents.length > 0
    );
    if (!quiet) setLoadingDetail(true);
    const params = {
      period,
      layout: 'equal',
      sort: sort === 'alpha' ? (alphaDesc ? 'alpha_desc' : 'alpha') : 'major',
    };
    if (magnitude != null) params.magnitude = magnitude;
    if (opts.force) params.force = true;
    return axios.get(`${API}/api/market-map/index/${encodeURIComponent(symbol)}`, { params })
      .then(r => setDetail(r.data))
      .catch(() => {
        if (!quiet) setDetail(null);
      })
      .finally(() => {
        if (!quiet) setLoadingDetail(false);
      });
  }, [period, sort, alphaDesc, magnitude]);

  useEffect(() => {
    axios.get(`${API}/api/market-map/catalog`).then(r => {
      const indices = r.data.indices || [];
      setCatalog(indices);
    }).catch(() => {});
    axios.get(`${API}/api/layout`).then(r => {
      const prefsOrders = chartPrefs?.email
        ? (loadChartPrefs(chartPrefs.email).listOrders || {})
        : {};
      const { orders, usedLocal, needsStarTagsServerSync } = hydrateListOrderFields(
        r.data || {},
        chartPrefs?.email,
        prefsOrders,
      );
      if (r.data?.marketMapPaneWidth) setPaneWidth(r.data.marketMapPaneWidth);
      const savedIndexOrder = orders[LIST_ORDER_KEYS.equityIndexSymbolOrder];
      if (Array.isArray(savedIndexOrder)) setIndexOrder(savedIndexOrder);
      if (r.data?.marketMapSelectedSymbol) {
        setSelected({ symbol: r.data.marketMapSelectedSymbol, name: '' });
      }
      if (usedLocal || needsStarTagsServerSync) {
        syncListOrdersToServerIfNeeded(chartPrefs?.email, orders, {
          usedLocal,
          needsStarTagsServerSync,
        });
      }
    }).catch(() => {
      const { orders } = hydrateListOrderFields({}, chartPrefs?.email);
      const savedIndexOrder = orders[LIST_ORDER_KEYS.equityIndexSymbolOrder];
      if (Array.isArray(savedIndexOrder)) setIndexOrder(savedIndexOrder);
    });
  }, [chartPrefs?.email]);

  const prevIsActiveRef = useRef(false);

  useEffect(() => {
    if (!isActive) return;
    // Keep prior summary visible on tab return; only force-rebuild via Refresh.
    if (summaryLenRef.current > 0) return;
    loadSummary(false);
  }, [isActive, loadSummary]);

  useEffect(() => {
    const becameActive = !prevIsActiveRef.current && !!isActive;
    prevIsActiveRef.current = !!isActive;
    if (!selected?.symbol || !isActive) return;
    const haveDetail = detailRef.current?.index?.symbol === selected.symbol
      && Array.isArray(detailRef.current?.constituents)
      && detailRef.current.constituents.length > 0;
    // Tab return with detail already in memory — do not clear/reload heatmap.
    if (becameActive && haveDetail) return;
    loadDetail(selected.symbol);
  }, [selected?.symbol, isActive, loadDetail]);

  useEffect(() => {
    function reload() {
      loadSummary(true);
      if (selected?.symbol) loadDetail(selected.symbol, { force: true });
    }
    window.addEventListener(CHART_DATA_UPDATED_EVENT, reload);
    window.addEventListener(MOVERS_REFRESH_EVENT, reload);
    return () => {
      window.removeEventListener(CHART_DATA_UPDATED_EVENT, reload);
      window.removeEventListener(MOVERS_REFRESH_EVENT, reload);
    };
  }, [loadSummary, loadDetail, selected?.symbol]);

  const orderedRows = useMemo(() => {
    const base = summary.length
      ? summary
      : catalog.map(c => ({ ...c, advances: null, declines: null, total: 0, index_change_pct: null }));
    return applySavedOrder(base, indexOrder, r => r.symbol);
  }, [summary, catalog, indexOrder]);

  const { overlayMapIndexSummary, overlayIndexRow, overlayMapStocks, refreshTick: patchRefreshTick, liveActive } = usePatchOverlay('market-map');
  const liveOrderedRows = useMemo(
    () => orderedRows.map((r) => overlayMapIndexSummary(r)),
    [orderedRows, overlayMapIndexSummary, patchRefreshTick],
  );
  const liveConstituents = useMemo(
    () => overlayMapStocks(detail?.constituents || []),
    [detail?.constituents, overlayMapStocks, patchRefreshTick],
  );
  const displayConstituents = useMemo(() => {
    if (!liveActive) return liveConstituents;
    return sortMarketMapConstituents(liveConstituents, sort, alphaDesc);
  }, [liveConstituents, liveActive, sort, alphaDesc]);
  const liveSummary = useMemo(() => {
    if (!liveActive || !displayConstituents.length) return null;
    return summarizeConstituentChanges(displayConstituents);
  }, [liveActive, displayConstituents]);
  const liveHeader = useMemo(() => {
    const h = detail?.index || {};
    const sym = h.symbol || selected?.symbol;
    if (!sym) return h;
    return overlayIndexRow({ ...h, symbol: sym });
  }, [detail?.index, selected?.symbol, overlayIndexRow, patchRefreshTick]);

  useRegisterFocusedSymbol('market-map', useMemo(
    () => (selected?.symbol ? [selected.symbol] : []),
    [selected?.symbol],
  ));
  useRegisterIntradaySymbols('market-map', useMemo(
    () => symbolsForMarketMap(selected, detail?.constituents),
    [selected, detail?.constituents],
  ));

  useEffect(() => {
    const sym = String(selected?.symbol || '').trim().toUpperCase();
    if (!sym || typeof window === 'undefined') return undefined;
    window.dispatchEvent(new CustomEvent('cim:chart-focus-symbol', {
      detail: {
        symbol: sym,
        source: 'market-map',
        constituentCount: Array.isArray(detail?.constituents) ? detail.constituents.length : 0,
      },
    }));
    return undefined;
  }, [selected?.symbol, detail?.constituents]);

  useEffect(() => {
    if (!liveOrderedRows.length) return;
    const match = liveOrderedRows.find(r => r.symbol === selected?.symbol);
    if (!match && liveOrderedRows[0]) setSelected(liveOrderedRows[0]);
    else if (match && match.name && selected?.name !== match.name) {
      setSelected(match);
    }
  }, [liveOrderedRows, selected?.symbol]);

  function persistIndexOrder(symbols) {
    setIndexOrder(symbols);
    persistLayoutOrderFields(chartPrefs?.email, {
      [LIST_ORDER_KEYS.equityIndexSymbolOrder]: symbols,
    });
  }

  function handleSaveLayout() {
    if (indexOrder?.length) {
      persistLayoutOrderFields(chartPrefs?.email, {
        [LIST_ORDER_KEYS.equityIndexSymbolOrder]: indexOrder,
      });
    }
    const payload = {
      marketMapPaneWidth: paneWidth,
      ...(selected?.symbol ? { marketMapSelectedSymbol: selected.symbol } : {}),
    };
    axios.post(`${API}/api/layout`, payload)
      .then(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Layout saved.' })))
      .catch(() => window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Failed to save layout.' })));
  }

  function onDividerMouseDown(e) {
    e.preventDefault();
    draggingDivider.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = paneWidth;
    function onMouseMove(ev) {
      if (!draggingDivider.current) return;
      const total = wrapperRef.current?.clientWidth || 1200;
      setPaneWidth(Math.max(200, Math.min(total - 400, startWidthRef.current + ev.clientX - startXRef.current)));
    }
    function onMouseUp() {
      draggingDivider.current = false;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    }
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  function clearDnD() {
    dragIdxRef.current = null;
    dropGapRef.current = null;
    setDropGap(null);
    setDraggingIdx(null);
  }

  function onDragStart(e, idx) {
    dragIdxRef.current = idx;
    setDraggingIdx(idx);
    const row = liveOrderedRows[idx];
    if (row) setListDragImage(e.dataTransfer, row.symbol, row.name);
  }

  function onDragOver(e, i) {
    if (dragIdxRef.current === null) return;
    e.preventDefault();
    const gap = insertionGapFromRowHover(e.clientY, e.currentTarget, i, liveOrderedRows.length);
    dropGapRef.current = gap;
    setDropGap(gap);
  }

  function onDrop(e) {
    e.preventDefault();
    const from = dragIdxRef.current;
    const gap = dropGapRef.current;
    clearDnD();
    if (from === null || gap == null) return;
    const syms = liveOrderedRows.map(r => r.symbol);
    const next = reorderByGap(syms, from, gap);
    if (JSON.stringify(next) === JSON.stringify(syms)) return;
    persistIndexOrder(next);
  }

  const constituents = displayConstituents;
  const header = liveHeader;
  const sum = liveSummary || detail?.summary || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', backgroundColor: 'var(--bg-primary)', overflow: 'hidden' }}>
      <div className="chart-app-toolbar" style={{
        height: 44,
        flexShrink: 0,
        backgroundColor: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        gap: 8,
        overflowX: 'auto',
      }}
      >
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', flexShrink: 0 }}>Market Map</span>
        <div style={{ width: 1, height: 20, backgroundColor: 'var(--border)', flexShrink: 0 }} />

        {PERIOD_TABS.map(tab => (
          <button
            key={tab.id}
            type="button"
            disabled={!tab.enabled}
            onClick={() => tab.enabled && setPeriod(tab.id)}
            title={tab.enabled ? '' : 'Coming soon'}
            style={{
              height: 26,
              padding: '0 10px',
              borderRadius: 4,
              border: `1px solid ${period === tab.id && tab.enabled ? 'var(--accent-blue)' : 'var(--border)'}`,
              backgroundColor: period === tab.id && tab.enabled ? 'rgba(56,139,253,0.12)' : 'var(--bg-tertiary)',
              color: tab.enabled
                ? (period === tab.id ? 'var(--accent-blue)' : 'var(--text-secondary)')
                : 'var(--text-muted)',
              fontSize: 11,
              fontWeight: period === tab.id && tab.enabled ? 600 : 400,
              cursor: tab.enabled ? 'pointer' : 'not-allowed',
              opacity: tab.enabled ? 1 : 0.45,
              flexShrink: 0,
            }}
          >
            {tab.label}
          </button>
        ))}

        <div style={{ width: 1, height: 20, backgroundColor: 'var(--border)', flexShrink: 0 }} />

        <button
          type="button"
          title="Equal-size tiles in a grid"
          onClick={() => setHeatmapLayout('grid')}
          style={tabBtnStyle(heatmapLayout === 'grid')}
        >
          Grid
        </button>
        <button
          type="button"
          title="Treemap: tile area = market cap, color = 1D %"
          onClick={() => setHeatmapLayout('treemap')}
          style={tabBtnStyle(heatmapLayout === 'treemap')}
        >
          Heatmap
        </button>

        <div style={{ width: 1, height: 20, backgroundColor: 'var(--border)', flexShrink: 0 }} />

        <button
          type="button"
          disabled={heatmapLayout !== 'treemap'}
          title={heatmapLayout === 'treemap' ? 'Flat treemap by market cap' : 'Switch to Heatmap layout'}
          onClick={() => heatmapLayout === 'treemap' && setViewMode('stocks')}
          style={{
            ...tabBtnStyle(viewMode === 'stocks'),
            opacity: heatmapLayout === 'treemap' ? 1 : 0.45,
            cursor: heatmapLayout === 'treemap' ? 'pointer' : 'not-allowed',
          }}
        >
          Stocks
        </button>
        <button
          type="button"
          disabled={heatmapLayout !== 'treemap'}
          title={heatmapLayout === 'treemap' ? 'Group treemap by NSE sector' : 'Switch to Heatmap layout'}
          onClick={() => heatmapLayout === 'treemap' && setViewMode('sectors')}
          style={{
            ...tabBtnStyle(viewMode === 'sectors'),
            opacity: heatmapLayout === 'treemap' ? 1 : 0.45,
            cursor: heatmapLayout === 'treemap' ? 'pointer' : 'not-allowed',
          }}
        >
          Sectors
        </button>

        <div style={{ width: 1, height: 20, backgroundColor: 'var(--border)', flexShrink: 0 }} />

        <button
          type="button"
          title="Sort by 1D %: highest gain first → deepest loss last (grid only)"
          disabled={heatmapLayout !== 'grid'}
          onClick={() => setSort('major')}
          style={{
            ...tabBtnStyle(sort === 'major'),
            opacity: heatmapLayout === 'grid' ? 1 : 0.45,
            cursor: heatmapLayout === 'grid' ? 'pointer' : 'not-allowed',
          }}
        >
          % high→low
        </button>

        <div style={{ flex: 1, minWidth: 8 }} />

        {asOf && (
          <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0, fontFamily: 'var(--font-mono)' }}>
            {asOf}
          </span>
        )}
        <button type="button" onClick={handleSaveLayout} style={toolBtnStyle()}>Save Layout</button>
      </div>

      <StockListSplitBody
        splitRef={wrapperRef}
        footer={(
          <>
            {loadingSummary ? 'Loading…' : `${liveOrderedRows.length} ${liveOrderedRows.length === 1 ? 'index' : 'indices'}`}
          </>
        )}
      >
        <div style={{
          width: paneWidth,
          minWidth: 200,
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
          borderRight: '1px solid var(--border)',
        }}
        >
          {loadingSummary && (
            <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>Loading indices…</div>
          )}
          {summaryError && (
            <div style={{ padding: 16, color: 'var(--accent-red)', fontSize: 12 }}>{summaryError}</div>
          )}
          {!loadingSummary && liveOrderedRows.length > 0 && (
            <>
              {draggingIdx !== null && dropGap === 0 ? <DropInsetLine /> : null}
              {liveOrderedRows.map((row, i) => (
                <React.Fragment key={row.symbol}>
                  <IndexRailRow
                    row={row}
                    i={i}
                    selected={selected}
                    onSelect={setSelected}
                    rowRefs={rowRefs}
                    draggable={liveOrderedRows.length > 1}
                    onDragStartRow={onDragStart}
                    onDragOverRow={onDragOver}
                    onDropRow={onDrop}
                    onDragEndRow={clearDnD}
                    dragDimmed={draggingIdx === i}
                  />
                  {draggingIdx !== null && dropGap === i + 1 ? <DropInsetLine /> : null}
                </React.Fragment>
              ))}
            </>
          )}
        </div>

        <div
          onMouseDown={onDividerMouseDown}
          style={{ width: 4, backgroundColor: 'var(--border)', cursor: 'col-resize', flexShrink: 0 }}
          onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--accent-blue)'; }}
          onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'var(--border)'; }}
        />

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 320 }}>
          {!selected ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              Select an index
            </div>
          ) : (
            <>
              <div style={{
                flexShrink: 0,
                padding: '10px 14px',
                borderBottom: '1px solid var(--border)',
                backgroundColor: 'var(--bg-secondary)',
              }}
              >
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: MM_TEXT_PRIMARY }}>
                    {header.name || selected.name}
                  </span>
                  {header.last_price != null && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: MM_TEXT_SECONDARY }}>
                      {formatPrice(header.last_price)}
                    </span>
                  )}
                  {header.change_pct != null && (
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 13,
                      fontWeight: 600,
                      color: header.change_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
                    }}
                    >
                      {formatPct(header.change_pct)}
                    </span>
                  )}
                </div>
                <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--accent-green)' }}>{sum.advances ?? '—'} advancing</span>
                  {' · '}
                  <span style={{ color: 'var(--accent-red)' }}>{sum.declines ?? '—'} declining</span>
                  {sum.pct_positive != null && (
                    <span>{' · '}{sum.pct_positive}% participation</span>
                  )}
                </div>
                {detail?.error && (
                  <div style={{ marginTop: 6, fontSize: 11, color: 'var(--accent-red)' }}>{detail.error}</div>
                )}

                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Filter</span>
                  {MAGNITUDE_CHIPS.map(chip => (
                    <button
                      key={chip.value}
                      type="button"
                      title={chip.value > 0 ? `Gainers with 1D % ≥ +${chip.value}` : `Losers with 1D % ≤ ${chip.value}%`}
                      onClick={() => setMagnitude(prev => (prev === chip.value ? null : chip.value))}
                      style={{
                        ...chipBtnStyle(),
                        borderColor: magnitude === chip.value ? 'var(--accent-blue)' : 'var(--border)',
                        color: magnitude === chip.value ? 'var(--accent-blue)' : 'var(--text-secondary)',
                        backgroundColor: magnitude === chip.value ? 'rgba(56,139,253,0.1)' : 'var(--bg-tertiary)',
                      }}
                    >
                      {chip.label}
                    </button>
                  ))}
                  <span style={{ width: 1, height: 16, backgroundColor: 'var(--border)', flexShrink: 0 }} />
                  <span style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Sort</span>
                  <button
                    type="button"
                    onClick={() => { setSort('alpha'); setAlphaDesc(false); }}
                    style={tabBtnStyle(sort === 'alpha' && !alphaDesc)}
                  >
                    A–Z
                  </button>
                  <button
                    type="button"
                    onClick={() => { setSort('alpha'); setAlphaDesc(true); }}
                    style={tabBtnStyle(sort === 'alpha' && alphaDesc)}
                  >
                    Z–A
                  </button>
                </div>
              </div>

              <div style={{
                flex: 1,
                overflow: heatmapLayout === 'grid' ? 'auto' : 'hidden',
                padding: heatmapLayout === 'grid' ? 10 : 0,
                display: 'flex',
                flexDirection: 'column',
                minHeight: 0,
              }}
              >
                {loadingDetail && (
                  <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 8 }}>Loading constituents…</div>
                )}
                {!loadingDetail && constituents.length === 0 && (
                  <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 8 }}>
                    No constituent data for this index.
                  </div>
                )}
                {!loadingDetail && constituents.length > 0 && heatmapLayout === 'treemap' && (
                  <MarketMapTreemap
                    constituents={constituents}
                    onOpenChart={onOpenChart}
                    groupBySector={viewMode === 'sectors'}
                  />
                )}
                {!loadingDetail && constituents.length > 0 && heatmapLayout === 'grid' && (
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(148px, 1fr))',
                    gap: 8,
                  }}
                  >
                    {constituents.map(stock => {
                      const pct = stock.change_pct;
                      const tileBg = tileBackground(pct);
                      return (
                        <button
                          key={stock.symbol}
                          type="button"
                          onClick={() => onOpenChart && onOpenChart(stock.symbol)}
                          style={{
                            position: 'relative',
                            minHeight: 72,
                            border: '1px solid var(--border)',
                            borderRadius: 6,
                            padding: '8px 10px',
                            textAlign: 'left',
                            cursor: 'pointer',
                            backgroundColor: tileBg,
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'space-between',
                            gap: 4,
                          }}
                        >
                          <MarketMapEarningsBadges
                            earningsBeat={stock.earnings_beat}
                            earningsPlus={stock.earnings_plus}
                          />
                          <span style={{ fontSize: 11, fontWeight: 600, color: MM_TEXT_PRIMARY, lineHeight: 1.2 }}>
                            {stock.symbol}
                          </span>
                          <span style={{ fontSize: 10, color: MM_TEXT_SECONDARY, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {stock.company_name}
                          </span>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 2 }}>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: MM_TEXT_SECONDARY }}>
                              {formatPrice(stock.last_price)}
                            </span>
                            <span style={{
                              fontFamily: 'var(--font-mono)',
                              fontSize: 11,
                              fontWeight: 600,
                              color: tilePctColor(pct, tileBg),
                            }}
                            >
                              {formatPct(pct)}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </StockListSplitBody>
    </div>
  );
}

function tabBtnStyle(active) {
  return {
    height: 26,
    padding: '0 10px',
    borderRadius: 4,
    border: `1px solid ${active ? 'var(--accent-blue)' : 'var(--border)'}`,
    backgroundColor: active ? 'rgba(56,139,253,0.12)' : 'var(--bg-tertiary)',
    color: active ? 'var(--accent-blue)' : 'var(--text-secondary)',
    fontSize: 11,
    fontWeight: active ? 600 : 400,
    cursor: 'pointer',
    flexShrink: 0,
  };
}

function toolBtnStyle() {
  return {
    height: 28,
    padding: '0 10px',
    borderRadius: 5,
    border: '1px solid var(--border)',
    backgroundColor: 'var(--bg-tertiary)',
    color: 'var(--text-secondary)',
    fontSize: 12,
    cursor: 'pointer',
    flexShrink: 0,
  };
}

function chipBtnStyle() {
  return {
    height: 24,
    minWidth: 28,
    padding: '0 6px',
    borderRadius: 4,
    border: '1px solid var(--border)',
    fontSize: 10,
    fontFamily: 'var(--font-mono)',
    cursor: 'pointer',
  };
}
