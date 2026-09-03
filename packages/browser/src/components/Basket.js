import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import api from '../api/http';
import EarningsPlusInlineMark from './EarningsPlusInlineMark';
import PortfolioEarningsModal from './PortfolioEarningsModal';
import {
  BASKET_MIME,
  normalizeBasketKind,
  normalizeBasketSymbol,
  readBasketSymbolDrag,
  startBasketSymbolDrag,
} from '../utils/basketDnD';
import { reorderByGap, insertionGapFromRowHover } from '../utils/listOrder';
import { DropInsetLine, setListDragImage } from '../utils/listDnD';
import {
  getEarningsMarkerColor,
  getEarningsModalVariant,
  getEarningsStatusLabel,
} from '../utils/earningsChartMarkers';
import { formatMarketCap } from '../utils/formatMarketCap';
import { daysSinceYmd, formatEarningsBadgeDate } from '../utils/portfolioEarnings';
import { useIntradayPatchOptional } from '../intraday/useIntradayPatch';
import {
  applyPatchToEarningsRow,
  attachEarningsMonthRefClose,
} from '../intraday/patchOverlay';

const Z_PANEL = 10070;
const BasketContext = createContext(null);
const BASKET_REORDER_MIME = 'application/x-cim-basket-reorder';

function basketEntryKey(entry) {
  return `${normalizeBasketKind(entry?.kind)}:${normalizeBasketSymbol(entry?.symbol)}`;
}

function mapEarningsLatest(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const date = String(raw.earnings_release_date || '').trim().slice(0, 10);
  if (!date) return null;
  const outcome = String(raw.outcome_kind || '').trim().toLowerCase() === 'beat' ? 'beat' : 'miss';
  return {
    earnings_release_date: date,
    outcome_kind: outcome,
    comparison_status: raw.comparison_status || null,
    comparison_note: raw.comparison_note || '',
  };
}

function mapBasketRows(rows) {
  return (Array.isArray(rows) ? rows : [])
    .map((r) => attachEarningsMonthRefClose({
      symbol: normalizeBasketSymbol(r.symbol),
      kind: normalizeBasketKind(r.kind),
      addedAt: r.addedAt || r.added_at || new Date().toISOString(),
      market_cap: r.market_cap ?? null,
      price: r.price ?? null,
      change_1d_pct: r.change_1d_pct ?? null,
      change_1m_pct: r.change_1m_pct ?? null,
      earnings_latest: mapEarningsLatest(r.earnings_latest),
      earnings_plus: Boolean(r.earnings_plus),
      month_ref_close: r.month_ref_close ?? null,
    }))
    .filter((r) => r.symbol);
}

function readLiveFeedEnabled() {
  try {
    const st = (window.CiMLive?.getState?.() || window.CiMLiveState || {});
    return !!st.enabled;
  } catch {
    return false;
  }
}

function BasketEarningsBadge({ event, onOpen }) {
  if (!event?.earnings_release_date) return null;
  const color = getEarningsMarkerColor(event.outcome_kind);
  const dateLabel = formatEarningsBadgeDate(event.earnings_release_date);
  const statusLabel = getEarningsStatusLabel(event.comparison_status);
  const titleParts = [
    event.outcome_kind === 'beat' ? 'Beat' : 'Miss',
    dateLabel || event.earnings_release_date,
    statusLabel || null,
    'Click for earnings',
  ].filter(Boolean);
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onOpen?.(event);
      }}
      onMouseDown={(e) => e.stopPropagation()}
      title={titleParts.join(' · ')}
      aria-label={`Open earnings · ${dateLabel || event.earnings_release_date}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        padding: 0,
        border: 'none',
        background: 'transparent',
        color,
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        fontWeight: 700,
        lineHeight: 1,
        cursor: 'pointer',
        flexShrink: 0,
      }}
    >
      <span>E</span>
      <span>{dateLabel || event.earnings_release_date}</span>
    </button>
  );
}

function fmtPrice(val) {
  const n = Number(val);
  if (!Number.isFinite(n)) return '—';
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(val) {
  const n = Number(val);
  if (!Number.isFinite(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

function pctColor(val) {
  const n = Number(val);
  if (!Number.isFinite(n) || n === 0) return 'var(--text-muted)';
  return n > 0 ? 'var(--accent-green)' : 'var(--accent-red)';
}

function MetricCell({ label, value, color }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 1,
      minWidth: 0,
    }}
    >
      <span style={{
        fontSize: 9,
        fontWeight: 600,
        color: 'var(--text-muted)',
        letterSpacing: 0.02,
        textTransform: 'uppercase',
        lineHeight: 1.1,
      }}
      >
        {label}
      </span>
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        fontWeight: 600,
        color: color || 'var(--text-secondary)',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        lineHeight: 1.2,
      }}
      >
        {value}
      </span>
    </div>
  );
}

const buttonBaseStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  height: 28,
  border: '1px solid var(--border)',
  borderRadius: 5,
  backgroundColor: 'var(--bg-tertiary)',
  overflow: 'hidden',
  cursor: 'pointer',
  flexShrink: 0,
  padding: '0 10px',
  gap: 6,
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  fontWeight: 500,
  color: 'var(--text-secondary)',
  whiteSpace: 'nowrap',
};

function CartGlyph({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 5h2l2.2 9.2a2 2 0 0 0 2 1.5h7.6a2 2 0 0 0 2-1.5L21 8H7"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="10" cy="19" r="1.4" fill="currentColor" />
      <circle cx="17" cy="19" r="1.4" fill="currentColor" />
    </svg>
  );
}

export function useBasket() {
  return useContext(BasketContext);
}

export function BasketProvider({ children, onOpenStock, onOpenIndex }) {
  const [symbols, setSymbols] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dropHover, setDropHover] = useState(false);
  const [earningsModal, setEarningsModal] = useState(null);
  const [liveOn, setLiveOn] = useState(() => readLiveFeedEnabled());
  const [geom, setGeom] = useState(() => ({
    left: Math.max(24, window.innerWidth - 380),
    top: 88,
    w: 360,
    h: 420,
  }));
  const dragRef = useRef(null);
  const saveTimer = useRef(null);
  const symbolsRef = useRef(symbols);
  symbolsRef.current = symbols;
  const reorderDragIdxRef = useRef(null);
  const reorderDropGapRef = useRef(null);
  const [reorderDraggingIdx, setReorderDraggingIdx] = useState(null);
  const [reorderDropGap, setReorderDropGap] = useState(null);
  const intraday = useIntradayPatchOptional();
  const patchRefreshTick = intraday?.refreshTick ?? 0;
  const basketSymbolKey = useMemo(
    () => symbols.map((e) => e.symbol).filter(Boolean).join('|'),
    [symbols],
  );

  const persist = useCallback(async (next) => {
    setSaving(true);
    try {
      await api.put('/api/user-basket', {
        symbols: next.map(({ symbol, kind, addedAt }) => ({ symbol, kind, addedAt })),
      });
      // Re-fetch enriched quotes after save.
      const res = await api.get('/api/user-basket');
      setSymbols(mapBasketRows(res.data?.symbols));
    } catch (err) {
      console.warn('[basket] save failed', err);
    } finally {
      setSaving(false);
    }
  }, []);

  const schedulePersist = useCallback((next) => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      persist(next);
    }, 250);
  }, [persist]);

  const reloadBasket = useCallback(async () => {
    try {
      const res = await api.get('/api/user-basket');
      setSymbols(mapBasketRows(res.data?.symbols));
    } catch (err) {
      console.warn('[basket] reload failed', err);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get('/api/user-basket');
        if (cancelled) return;
        setSymbols(mapBasketRows(res.data?.symbols));
      } catch (err) {
        console.warn('[basket] load failed', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    };
  }, []);

  // Refresh EOD quotes while the panel is open (live overlay patches on top when LIVE is on).
  useEffect(() => {
    if (!open) return undefined;
    reloadBasket();
    const id = window.setInterval(reloadBasket, 60_000);
    return () => window.clearInterval(id);
  }, [open, reloadBasket]);

  useEffect(() => {
    const syncLive = (e) => {
      if (e?.type === 'cim:live-feed-toggle' && e.detail && typeof e.detail.enabled === 'boolean') {
        setLiveOn(!!e.detail.enabled);
        return;
      }
      setLiveOn(readLiveFeedEnabled());
    };
    syncLive();
    window.addEventListener('cim:live-feed-toggle', syncLive);
    window.addEventListener('cim:live-active', syncLive);
    return () => {
      window.removeEventListener('cim:live-feed-toggle', syncLive);
      window.removeEventListener('cim:live-active', syncLive);
    };
  }, []);

  // Keep basket symbols on the live LTPC socket while LIVE is on (independent of current page).
  useEffect(() => {
    const live = window.CiMLive;
    if (!live?.subscribe || !live?.unsubscribe) return undefined;
    const syms = basketSymbolKey
      ? basketSymbolKey.split('|').filter(Boolean)
      : [];
    let cancelled = false;
    (async () => {
      try {
        if (!liveOn || !syms.length) {
          await live.unsubscribe('basket');
          return;
        }
        // Replaces prior basket context set (no need to unsubscribe first).
        await live.subscribe('basket', syms, 'ltpc');
      } catch (err) {
        if (!cancelled) console.warn('[basket] live subscribe failed', err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [liveOn, basketSymbolKey]);

  useEffect(() => () => {
    try { window.CiMLive?.unsubscribe?.('basket'); } catch { /* ignore */ }
  }, []);

  const displaySymbols = useMemo(() => {
    if (!liveOn || !intraday?.enabled || !intraday?.getSymbolSnapshot) return symbols;
    return symbols.map((entry) => {
      const snap = intraday.getSymbolSnapshot(entry.symbol);
      return snap ? applyPatchToEarningsRow(entry, snap) : entry;
    });
  }, [symbols, liveOn, intraday, patchRefreshTick]);

  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener('cim:basket-open', onOpen);
    return () => window.removeEventListener('cim:basket-open', onOpen);
  }, []);

  const openPanel = useCallback(() => setOpen(true), []);
  const closePanel = useCallback(() => setOpen(false), []);
  const togglePanel = useCallback(() => setOpen((v) => !v), []);

  const addEntry = useCallback((symbol, kind = 'stock') => {
    const sym = normalizeBasketSymbol(symbol);
    if (!sym) return;
    const k = normalizeBasketKind(kind);
    setSymbols((prev) => {
      if (prev.some((e) => e.symbol === sym && e.kind === k)) return prev;
      const next = [...prev, { symbol: sym, kind: k, addedAt: new Date().toISOString() }];
      schedulePersist(next);
      return next;
    });
  }, [schedulePersist]);

  const removeEntry = useCallback((symbol, kind = null) => {
    const sym = normalizeBasketSymbol(symbol);
    if (!sym) return;
    const k = kind ? normalizeBasketKind(kind) : null;
    setSymbols((prev) => {
      const next = prev.filter((e) => !(e.symbol === sym && (k == null || e.kind === k)));
      schedulePersist(next);
      return next;
    });
  }, [schedulePersist]);

  const clearReorderDnD = useCallback(() => {
    reorderDragIdxRef.current = null;
    reorderDropGapRef.current = null;
    setReorderDraggingIdx(null);
    setReorderDropGap(null);
  }, []);

  const onReorderDragStart = useCallback((e, idx) => {
    e.stopPropagation();
    const entry = symbolsRef.current[idx];
    if (!entry) return;
    reorderDragIdxRef.current = idx;
    reorderDropGapRef.current = idx;
    setReorderDraggingIdx(idx);
    setReorderDropGap(idx);
    try {
      e.dataTransfer.setData(BASKET_REORDER_MIME, String(idx));
      e.dataTransfer.setData('text/plain', entry.symbol);
      e.dataTransfer.effectAllowed = 'move';
    } catch { /* ignore */ }
    setListDragImage(e.dataTransfer, entry.symbol, entry.kind === 'index' ? 'Index' : 'Stock');
  }, []);

  const onReorderDragOver = useCallback((e, idx) => {
    if (reorderDragIdxRef.current === null) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    const gap = insertionGapFromRowHover(
      e.clientY,
      e.currentTarget,
      idx,
      symbolsRef.current.length,
    );
    reorderDropGapRef.current = gap;
    setReorderDropGap(gap);
  }, []);

  const onReorderDrop = useCallback((e) => {
    if (reorderDragIdxRef.current === null) return;
    e.preventDefault();
    e.stopPropagation();
    const from = reorderDragIdxRef.current;
    const gap = reorderDropGapRef.current;
    clearReorderDnD();
    if (from == null || gap == null) return;
    setSymbols((prev) => {
      const next = reorderByGap(prev, from, gap);
      const same = next.length === prev.length
        && next.every((row, i) => basketEntryKey(row) === basketEntryKey(prev[i]));
      if (same) return prev;
      schedulePersist(next);
      return next;
    });
  }, [clearReorderDnD, schedulePersist]);

  const onReorderDragEnd = useCallback((e) => {
    e?.stopPropagation?.();
    clearReorderDnD();
  }, [clearReorderDnD]);

  const openEntry = useCallback((entry) => {
    if (!entry?.symbol) return;
    if (entry.kind === 'index') {
      if (typeof onOpenIndex === 'function') {
        onOpenIndex({ symbol: entry.symbol, name: entry.symbol });
        return;
      }
    }
    if (typeof onOpenStock === 'function') {
      onOpenStock(entry.symbol);
      return;
    }
    try {
      window.dispatchEvent(new CustomEvent('cim:live-open-chart', {
        detail: { symbol: entry.symbol },
      }));
    } catch { /* ignore */ }
  }, [onOpenIndex, onOpenStock]);

  const openEarningsForEntry = useCallback((entry, event) => {
    const ev = event || entry?.earnings_latest;
    if (!entry?.symbol || !ev?.earnings_release_date) return;
    setEarningsModal({
      symbol: entry.symbol,
      outcome_kind: ev.outcome_kind,
      earnings_release_date: ev.earnings_release_date,
      comparison_status: ev.comparison_status,
      comparison_note: ev.comparison_note || '',
    });
  }, []);

  const onPanelDragOver = useCallback((e) => {
    const types = [...(e.dataTransfer?.types || [])];
    if (types.includes(BASKET_REORDER_MIME) || reorderDragIdxRef.current !== null) return;
    const hasMime = types.some(
      (t) => t === BASKET_MIME || t === 'text/plain',
    );
    if (!hasMime) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    setDropHover(true);
  }, []);

  const onPanelDragLeave = useCallback((e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setDropHover(false);
  }, []);

  const onPanelDrop = useCallback((e) => {
    const types = [...(e.dataTransfer?.types || [])];
    if (types.includes(BASKET_REORDER_MIME) || reorderDragIdxRef.current !== null) return;
    e.preventDefault();
    setDropHover(false);
    const payload = readBasketSymbolDrag(e);
    if (payload) addEntry(payload.symbol, payload.kind);
  }, [addEntry]);

  useEffect(() => {
    const onMove = (e) => {
      const d = dragRef.current;
      if (!d?.active) return;
      const dx = e.clientX - d.sx;
      const dy = e.clientY - d.sy;
      setGeom((g) => ({
        ...g,
        left: Math.max(8, Math.min(window.innerWidth - g.w - 8, d.sl + dx)),
        top: Math.max(8, Math.min(window.innerHeight - 80, d.st + dy)),
      }));
    };
    const onUp = () => {
      if (dragRef.current) dragRef.current.active = false;
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const startDrag = useCallback((e) => {
    if (e.button !== 0) return;
    dragRef.current = {
      active: true,
      sx: e.clientX,
      sy: e.clientY,
      sl: geom.left,
      st: geom.top,
    };
    e.preventDefault();
  }, [geom.left, geom.top]);

  const value = useMemo(() => ({
    symbols,
    count: symbols.length,
    open,
    loading,
    saving,
    openPanel,
    closePanel,
    togglePanel,
    addEntry,
    removeEntry,
    openEntry,
    startBasketSymbolDrag,
  }), [
    symbols, open, loading, saving,
    openPanel, closePanel, togglePanel,
    addEntry, removeEntry, openEntry,
  ]);

  const panel = open
    ? createPortal(
      <div
        role="dialog"
        aria-label="Basket"
        onDragOver={onPanelDragOver}
        onDragLeave={onPanelDragLeave}
        onDrop={onPanelDrop}
        style={{
          position: 'fixed',
          left: geom.left,
          top: geom.top,
          width: geom.w,
          height: geom.h,
          zIndex: Z_PANEL,
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: 'var(--bg-secondary)',
          border: dropHover
            ? '1px solid var(--accent-blue, #388bfd)'
            : '1px solid var(--border)',
          borderRadius: 6,
          boxShadow: '0 8px 28px rgba(0,0,0,0.5)',
          overflow: 'hidden',
        }}
      >
        <div
          onMouseDown={startDrag}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            padding: '6px 10px',
            cursor: 'move',
            userSelect: 'none',
            borderBottom: '1px solid var(--border)',
            backgroundColor: 'var(--bg-primary)',
            flexShrink: 0,
          }}
        >
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 12, fontWeight: 600, color: 'var(--text-primary)',
          }}
          >
            <CartGlyph />
            Basket
            <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>({symbols.length})</span>
          </span>
          <button
            type="button"
            onClick={closePanel}
            onMouseDown={(e) => e.stopPropagation()}
            title="Close"
            style={{
              border: 'none', background: 'transparent', color: 'var(--text-muted)',
              cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 2,
            }}
          >
            ×
          </button>
        </div>

        <div style={{
          padding: '6px 10px',
          fontSize: 11,
          color: dropHover ? 'var(--accent-blue)' : 'var(--text-muted)',
          borderBottom: '1px solid var(--border-light, var(--border))',
          flexShrink: 0,
        }}
        >
          {dropHover
            ? 'Drop to add'
            : 'Drag symbols here · drag ⋮⋮ to reorder'}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 4 }}>
          {loading && (
            <div style={{ padding: 12, fontSize: 12, color: 'var(--text-muted)' }}>Loading…</div>
          )}
          {!loading && displaySymbols.length === 0 && (
            <div style={{ padding: 12, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>
              Basket is empty. Drag a symbol from a list onto this panel.
            </div>
          )}
          {!loading && reorderDraggingIdx !== null && reorderDropGap === 0 ? <DropInsetLine /> : null}
          {!loading && displaySymbols.map((entry, wi) => (
            <React.Fragment key={basketEntryKey(entry)}>
            <div
              onDragOver={(e) => onReorderDragOver(e, wi)}
              onDrop={onReorderDrop}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
                padding: '8px 8px 9px',
                borderRadius: 4,
                cursor: 'pointer',
                borderBottom: '1px solid var(--border-light, var(--border))',
                opacity: reorderDraggingIdx === wi ? 0.45 : 1,
              }}
              onClick={() => openEntry(entry)}
              onMouseEnter={(e) => {
                if (reorderDraggingIdx === wi) return;
                e.currentTarget.style.backgroundColor = 'var(--bg-hover)';
              }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
              title={`Open chart · ${entry.symbol}`}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                <span
                  draggable={displaySymbols.length > 1}
                  title="Drag to reorder"
                  onDragStart={(e) => onReorderDragStart(e, wi)}
                  onDragEnd={onReorderDragEnd}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                  style={{
                    flexShrink: 0,
                    width: 14,
                    cursor: displaySymbols.length > 1 ? 'grab' : 'default',
                    color: 'var(--text-muted)',
                    fontSize: 10,
                    letterSpacing: '-0.12em',
                    userSelect: 'none',
                    lineHeight: 1,
                  }}
                >
                  ⋮⋮
                </span>
                <span style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  fontWeight: 700,
                  color: 'var(--text-primary)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  flexShrink: 1,
                  minWidth: 0,
                }}
                >
                  {entry.symbol}
                </span>
                {entry.kind === 'index' && (
                  <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>IDX</span>
                )}
                {entry.kind !== 'index' && entry.earnings_latest && (
                  <BasketEarningsBadge
                    event={entry.earnings_latest}
                    onOpen={(ev) => openEarningsForEntry(entry, ev)}
                  />
                )}
                {entry.kind !== 'index' && entry.earnings_plus && (
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      if (entry.earnings_latest) openEarningsForEntry(entry);
                    }}
                    onMouseDown={(e) => e.stopPropagation()}
                    style={{
                      display: 'inline-flex',
                      flexShrink: 0,
                      cursor: entry.earnings_latest ? 'pointer' : 'default',
                    }}
                    title={entry.earnings_latest ? 'Earnings+ · click for earnings' : 'Earnings+ quality'}
                  >
                    <EarningsPlusInlineMark />
                  </span>
                )}
                <span style={{ flex: 1, minWidth: 4 }} />
                <button
                  type="button"
                  title={`Remove ${entry.symbol}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    removeEntry(entry.symbol, entry.kind);
                  }}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    fontSize: 14,
                    lineHeight: 1,
                    width: 18,
                    height: 18,
                    padding: 0,
                    flexShrink: 0,
                  }}
                >
                  ×
                </button>
              </div>
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr 1fr',
                gap: 8,
                alignItems: 'start',
              }}
              >
                <MetricCell label="MCap" value={formatMarketCap(entry.market_cap)} />
                <MetricCell label="Price" value={fmtPrice(entry.price)} />
                <MetricCell
                  label="1D"
                  value={fmtPct(entry.change_1d_pct)}
                  color={pctColor(entry.change_1d_pct)}
                />
                <MetricCell
                  label="1M"
                  value={fmtPct(entry.change_1m_pct)}
                  color={pctColor(entry.change_1m_pct)}
                />
              </div>
            </div>
            {reorderDraggingIdx !== null && reorderDropGap === wi + 1 ? <DropInsetLine /> : null}
            </React.Fragment>
          ))}
        </div>

        {saving && (
          <div style={{
            padding: '4px 10px',
            fontSize: 10,
            color: 'var(--text-muted)',
            borderTop: '1px solid var(--border)',
            flexShrink: 0,
          }}
          >
            Saving…
          </div>
        )}
      </div>,
      document.body,
    )
    : null;

  return (
    <BasketContext.Provider value={value}>
      {children}
      {panel}
      {earningsModal && (
        <PortfolioEarningsModal
          symbol={earningsModal.symbol}
          variant={getEarningsModalVariant(earningsModal.outcome_kind)}
          earningsDate={earningsModal.earnings_release_date}
          daysSinceReport={daysSinceYmd(earningsModal.earnings_release_date)}
          comparisonStatus={earningsModal.comparison_status}
          comparisonNote={earningsModal.comparison_note || ''}
          onClose={() => setEarningsModal(null)}
          onOpenChart={(sym) => {
            setEarningsModal(null);
            if (typeof onOpenStock === 'function') onOpenStock(sym);
          }}
        />
      )}
    </BasketContext.Provider>
  );
}

/** Toolbar control that replaces Drawing Tools. */
export default function BasketToolbarButton() {
  const basket = useBasket();
  const count = basket?.count || 0;
  const open = Boolean(basket?.open);

  return (
    <button
      type="button"
      onClick={() => basket?.togglePanel?.()}
      title="Basket — drag symbols here to keep tabs on them"
      aria-label="Basket"
      aria-expanded={open}
      style={{
        ...buttonBaseStyle,
        backgroundColor: open ? 'rgba(56,139,253,0.12)' : 'var(--bg-tertiary)',
        color: open ? 'var(--accent-blue)' : 'var(--text-secondary)',
        borderColor: open ? 'rgba(56,139,253,0.45)' : 'var(--border)',
      }}
    >
      <CartGlyph />
      Basket
      {count > 0 && (
        <span style={{
          minWidth: 16,
          height: 16,
          padding: '0 4px',
          borderRadius: 8,
          backgroundColor: 'var(--accent-blue)',
          color: '#fff',
          fontSize: 10,
          fontWeight: 700,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        >
          {count > 99 ? '99+' : count}
        </span>
      )}
    </button>
  );
}

export { startBasketSymbolDrag };
