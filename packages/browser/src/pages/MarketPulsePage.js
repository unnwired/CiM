import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import { MARKET_PULSE_REFRESH_EVENT } from '../chartEvents';
import { usePatchOverlay } from '../intraday/usePatchOverlay';
import { useRegisterFocusedSymbol } from '../intraday/useRegisterFocusedSymbol';
import { useRegisterIntradaySymbols } from '../intraday/useRegisterIntradaySymbols';
import { symbolsForMarketPulse } from '../intraday/intradayRefreshScopes';
import { applySavedOrder, reorderByGap, insertionGapFromChipHover } from '../utils/listOrder';
import { setListDragImage } from '../utils/listDnD';
import { useChartPrefsContext } from '../chartPrefs/useChartPrefs';
import { loadChartPrefs } from '../chartPrefs/chartPrefsStore';
import {
  hydrateListOrderFields,
  LIST_ORDER_KEYS,
  persistLayoutOrderFields,
  syncListOrdersToServerIfNeeded,
} from '../layout/listOrderPersistence';

const API = '';

function formatPrice(val) {
  if (val === null || val === undefined) return '—';
  return Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ChangeBadge({ value }) {
  if (value === null || value === undefined) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
  const n     = parseFloat(value);
  const color = n > 0 ? 'var(--accent-green)' : n < 0 ? 'var(--accent-red)' : 'var(--text-secondary)';
  return (
    <span style={{ color, fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500 }}>
      {n > 0 ? '+' : ''}{n.toFixed(2)}%
    </span>
  );
}

export default function MarketPulsePage() {
  const [indices, setIndices]       = useState([]);
  const [loading, setLoading]       = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [equityOrder, setEquityOrder] = useState(null);
  const [nseOrder, setNseOrder] = useState(null);
  const chartPrefs = useChartPrefsContext();
  const { overlayIndexRows, refreshTick: patchRefreshTick } = usePatchOverlay('market-pulse');
  const displayIndices = useMemo(
    () => overlayIndexRows(indices),
    [indices, overlayIndexRows, patchRefreshTick],
  );
  useRegisterFocusedSymbol('market-pulse', useMemo(
    () => symbolsForMarketPulse(indices),
    [indices],
  ));
  useRegisterIntradaySymbols('market-pulse', useMemo(
    () => symbolsForMarketPulse(indices),
    [indices],
  ));

  const fetchIndices = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/indices`);
      setIndices(r.data.data || []);
      setLastUpdate(new Date());
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIndices();
  }, [fetchIndices]);

  useEffect(() => {
    const handler = () => { fetchIndices(); };
    window.addEventListener(MARKET_PULSE_REFRESH_EVENT, handler);
    return () => window.removeEventListener(MARKET_PULSE_REFRESH_EVENT, handler);
  }, [fetchIndices]);

  useEffect(() => {
    axios.get(`${API}/api/layout`).then((r) => {
      const prefsOrders = chartPrefs?.email
        ? (loadChartPrefs(chartPrefs.email).listOrders || {})
        : {};
      const { orders, usedLocal, needsStarTagsServerSync } = hydrateListOrderFields(
        r.data || {},
        chartPrefs?.email,
        prefsOrders,
      );
      const savedEquity = orders[LIST_ORDER_KEYS.equityIndexSymbolOrder];
      if (Array.isArray(savedEquity)) setEquityOrder(savedEquity);
      const savedNse = orders[LIST_ORDER_KEYS.equityNseIndexSymbolOrder];
      if (Array.isArray(savedNse)) setNseOrder(savedNse);
      if (usedLocal || needsStarTagsServerSync) {
        syncListOrdersToServerIfNeeded(chartPrefs?.email, orders, {
          usedLocal,
          needsStarTagsServerSync,
        });
      }
    }).catch(() => {
      const { orders } = hydrateListOrderFields({}, chartPrefs?.email);
      const savedEquity = orders[LIST_ORDER_KEYS.equityIndexSymbolOrder];
      if (Array.isArray(savedEquity)) setEquityOrder(savedEquity);
      const savedNse = orders[LIST_ORDER_KEYS.equityNseIndexSymbolOrder];
      if (Array.isArray(savedNse)) setNseOrder(savedNse);
    });
  }, [chartPrefs?.email]);

  const equity = useMemo(
    () => applySavedOrder(
      displayIndices.filter((i) => i.category === 'equity'),
      equityOrder,
      (i) => i.symbol,
    ),
    [displayIndices, equityOrder],
  );
  const nseAll = useMemo(
    () => applySavedOrder(
      displayIndices.filter((i) => i.category === 'equity_nse'),
      nseOrder,
      (i) => i.symbol,
    ),
    [displayIndices, nseOrder],
  );

  const persistEquityOrder = useCallback((symbols) => {
    setEquityOrder(symbols);
    persistLayoutOrderFields(chartPrefs?.email, {
      [LIST_ORDER_KEYS.equityIndexSymbolOrder]: symbols,
    });
  }, [chartPrefs?.email]);

  const persistNseOrder = useCallback((symbols) => {
    setNseOrder(symbols);
    persistLayoutOrderFields(chartPrefs?.email, {
      [LIST_ORDER_KEYS.equityNseIndexSymbolOrder]: symbols,
    });
  }, [chartPrefs?.email]);

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100%', width: '100%',
      backgroundColor: 'var(--bg-primary)', overflow: 'hidden',
    }}>
      {/* Top bar */}
      <div style={{
        height: 52, backgroundColor: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center',
        padding: '0 20px', gap: 16, flexShrink: 0,
      }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          Market Indices
        </span>
        {lastUpdate && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            Updated {lastUpdate.toLocaleTimeString('en-IN')}
          </span>
        )}
        <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto' }}>
          Drag cards by the grip to rearrange
        </span>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
        {loading ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: 20 }}>Loading indices...</div>
        ) : (
          <>
            <Section
              title="Equity Indices"
              indices={equity}
              onReorder={persistEquityOrder}
            />
            <Section
              title="Equity Indices (Non-Chartable)"
              indices={nseAll}
              isNonChartable
              onReorder={persistNseOrder}
            />
          </>
        )}
      </div>
    </div>
  );
}

function Section({ title, indices, isNonChartable, onReorder }) {
  const dragIdxRef = useRef(null);
  const dropGapRef = useRef(null);
  const [draggingIdx, setDraggingIdx] = useState(null);
  const [dropGap, setDropGap] = useState(null);

  if (!indices.length) return null;

  function clearDnD() {
    dragIdxRef.current = null;
    dropGapRef.current = null;
    setDropGap(null);
    setDraggingIdx(null);
  }

  function onDragStart(e, idx) {
    dragIdxRef.current = idx;
    setDraggingIdx(idx);
    const row = indices[idx];
    if (row) setListDragImage(e.dataTransfer, row.symbol, row.name);
  }

  function onDragOver(e, i) {
    if (dragIdxRef.current === null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const gap = insertionGapFromChipHover(e.clientX, e.currentTarget, i, indices.length);
    dropGapRef.current = gap;
    setDropGap(gap);
  }

  function onDrop(e) {
    e.preventDefault();
    const from = dragIdxRef.current;
    const gap = dropGapRef.current;
    clearDnD();
    if (from === null || gap == null || !onReorder) return;
    const syms = indices.map((r) => r.symbol);
    const next = reorderByGap(syms, from, gap);
    if (JSON.stringify(next) === JSON.stringify(syms)) return;
    onReorder(next);
  }

  return (
    <div style={{ marginBottom: 32 }}>
      <div style={{
        fontSize: 11, fontWeight: 700, color: 'var(--text-muted)',
        letterSpacing: '0.08em', textTransform: 'uppercase',
        marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10,
      }}>
        {title}
        <div style={{ flex: 1, height: 1, backgroundColor: 'var(--border)' }} />
        <span style={{ fontSize: 10, fontWeight: 400 }}>{indices.length}</span>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isNonChartable
            ? 'repeat(auto-fill, minmax(220px, 1fr))'
            : 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: isNonChartable ? 8 : 12,
        }}
        onDragEnd={clearDnD}
      >
        {indices.map((idx, i) => (
          isNonChartable
            ? (
              <NonChartableCard
                key={idx.symbol}
                index={idx}
                dragIdx={i}
                draggingIdx={draggingIdx}
                dropGap={dropGap}
                onDragStart={onDragStart}
                onDragOver={onDragOver}
                onDrop={onDrop}
              />
            )
            : (
              <IndexCard
                key={idx.symbol}
                index={idx}
                dragIdx={i}
                draggingIdx={draggingIdx}
                dropGap={dropGap}
                onDragStart={onDragStart}
                onDragOver={onDragOver}
                onDrop={onDrop}
              />
            )
        ))}
      </div>
    </div>
  );
}

function DragGrip({ dense }) {
  return (
    <span
      title="Drag to rearrange"
      aria-hidden
      style={{
        cursor: 'grab',
        color: 'var(--text-muted)',
        fontSize: dense ? 11 : 13,
        letterSpacing: dense ? '-1px' : '-2px',
        userSelect: 'none',
        lineHeight: 1,
        padding: dense ? '2px 4px' : '2px 6px',
        marginLeft: -4,
        borderRadius: 4,
        flexShrink: 0,
      }}
    >
      ⋮⋮
    </span>
  );
}

function cardDropOutline(draggingIdx, dropGap, dragIdx) {
  if (draggingIdx === null || dropGap == null || draggingIdx === dragIdx) return undefined;
  if (dropGap === dragIdx || dropGap === dragIdx + 1) {
    return '1px solid var(--accent-blue)';
  }
  return undefined;
}

function cardDropBoxShadow(draggingIdx, dropGap, dragIdx) {
  if (draggingIdx === null || dropGap == null || draggingIdx === dragIdx) return undefined;
  if (dropGap === dragIdx) {
    return 'inset 3px 0 0 var(--accent-blue)';
  }
  if (dropGap === dragIdx + 1) {
    return 'inset -3px 0 0 var(--accent-blue)';
  }
  return undefined;
}

function IndexCard({
  index, dragIdx, draggingIdx, dropGap, onDragStart, onDragOver, onDrop,
}) {
  const isUp   = index.change_pct > 0;
  const isDown = index.change_pct < 0;
  const isDragging = draggingIdx === dragIdx;

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, dragIdx)}
      onDragOver={(e) => onDragOver(e, dragIdx)}
      onDrop={onDrop}
      style={{
        backgroundColor: 'var(--bg-secondary)',
        border:          `1px solid ${isUp ? '#3fb95033' : isDown ? '#f8514933' : 'var(--border)'}`,
        outline:         cardDropOutline(draggingIdx, dropGap, dragIdx),
        boxShadow:       cardDropBoxShadow(draggingIdx, dropGap, dragIdx),
        borderRadius:    8, padding: '14px 16px',
        transition: 'opacity 0.15s, box-shadow 0.1s',
        opacity: isDragging ? 0.45 : 1,
        cursor: 'grab',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, minWidth: 0 }}>
          <DragGrip />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
              {index.name}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {index.symbol}
            </div>
          </div>
        </div>
        <div style={{
          backgroundColor: isUp ? 'rgba(63,185,80,0.12)' : isDown ? 'rgba(248,81,73,0.12)' : 'var(--bg-tertiary)',
          border:          `1px solid ${isUp ? '#3fb95044' : isDown ? '#f8514944' : 'var(--border)'}`,
          borderRadius:    5, padding: '3px 8px', minWidth: 60, textAlign: 'center', flexShrink: 0,
        }}>
          <ChangeBadge value={index.change_pct} />
        </div>
      </div>

      <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', marginBottom: 10 }}>
        {formatPrice(index.last_price)}
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>1M</div>
          <ChangeBadge value={index.change_30d} />
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>1Y</div>
          <ChangeBadge value={index.change_1y} />
        </div>
      </div>
    </div>
  );
}

function NonChartableCard({
  index, dragIdx, draggingIdx, dropGap, onDragStart, onDragOver, onDrop,
}) {
  const isUp   = index.change_pct > 0;
  const isDown = index.change_pct < 0;
  const isDragging = draggingIdx === dragIdx;

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, dragIdx)}
      onDragOver={(e) => onDragOver(e, dragIdx)}
      onDrop={onDrop}
      style={{
        backgroundColor: 'var(--bg-secondary)',
        border:          `1px solid ${isUp ? '#3fb95022' : isDown ? '#f8514922' : 'var(--border-light)'}`,
        outline:         cardDropOutline(draggingIdx, dropGap, dragIdx),
        boxShadow:       cardDropBoxShadow(draggingIdx, dropGap, dragIdx),
        borderRadius:    6, padding: '10px 12px',
        opacity: isDragging ? 0.45 : 1,
        cursor: 'grab',
        transition: 'opacity 0.15s, box-shadow 0.1s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flex: 1, marginRight: 8, minWidth: 0 }}>
          <DragGrip dense />
          <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)', lineHeight: 1.3 }}>
            {index.name}
          </span>
        </div>
        <ChangeBadge value={index.change_pct} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          {Number(index.last_price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 1 }}>1M</div>
            <ChangeBadge value={index.change_30d} />
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 1 }}>1Y</div>
            <ChangeBadge value={index.change_1y} />
          </div>
        </div>
      </div>
    </div>
  );
}
