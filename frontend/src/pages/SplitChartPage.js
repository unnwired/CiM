import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import ChartContainer from '../components/chart/ChartContainer';
import { DrawingWorkspaceProvider } from '../components/chart/drawing/DrawingWorkspaceContext';
import { DrawingToolbarConnected, DrawingFloatPaletteConnected } from '../components/chart/drawing/DrawingToolbar';
import DrawingToolsDesignControl from '../components/chart/drawing/DrawingToolsDesignControl';
import ExternalFinancialsLinks from '../components/ExternalFinancialsLinks';
import EMAControls    from '../components/chart/EMAControls';
import axios          from 'axios';
import {
  EMA_PREFS_UPDATED_EVENT,
  PANELS_PREFS_KEY,
  PANELS_PREFS_UPDATED_EVENT,
  VOLUME_PREFS_UPDATED_EVENT,
  getPersistedEmaSet,
  getPersistedVisiblePanels,
  getPersistedVolumeVisible,
  persistEmaSet,
  persistVisiblePanels,
  persistVolumeVisible,
} from '../config/chartDefaults';
import {
  DEFAULT_CHART_TIMEFRAME_1,
  DEFAULT_CHART_TIMEFRAMES,
  DEFAULT_SPLIT_LAYOUT,
  timeframeForPanelIndex,
  normalizeSavedTimeframe3,
} from '../config/chartViewDefaults';

const API = '';

/** Match dashboard: above chart / drawing layers; toolbar overflow-x:auto clips absolute descendants. */
const CHART_TOOLBAR_OVERLAY_Z = 200000;

const DEFAULT_PANEL_ORDER = ['stochrsi', 'macd'];

const LAYOUTS = [
  { key: 'single',    label: 'Single',           count: 1 },
  { key: '2h',        label: '2 — Side by Side', count: 2 },
  { key: '3s',        label: '3 — Side by Side', count: 3 },
];

function makePanel(symbol, timeframe) {
  return {
    symbol,
    timeframe:     timeframe || DEFAULT_CHART_TIMEFRAME_1,
    emas:          getPersistedEmaSet(),
    volumeVisible: getPersistedVolumeVisible(true),
    visiblePanels: getPersistedVisiblePanels(),
    panelOrder:    DEFAULT_PANEL_ORDER,
    lastChange:    null,
    lastPrice:     null,
  };
}

export default function SplitChartPage({ symbol: initialSymbol, onOpenChart, onOpenFinancials, onActiveSymbolChange }) {
  const [layout, setLayout]         = useState(DEFAULT_SPLIT_LAYOUT);
  const [panels, setPanels]         = useState(() =>
    DEFAULT_CHART_TIMEFRAMES.map((tf) => makePanel(initialSymbol, tf))
  );
  const [activeIdx, setActiveIdx]   = useState(0);

  // Notify parent when active panel symbol changes
  useEffect(() => {
    const sym = panels[activeIdx]?.symbol;
    if (sym && onActiveSymbolChange) onActiveSymbolChange(sym);
  }, [activeIdx, panels]);
  const [syncSymbol, setSyncSymbol] = useState(false);
  const [syncInterval, setSyncInterval] = useState(false);
  const [viewOpen, setViewOpen]     = useState(false);
  const [indOpen, setIndOpen]       = useState(false);
  const [indicatorMenuRect, setIndicatorMenuRect] = useState(null);
  const [viewMenuRect, setViewMenuRect] = useState(null);
  const viewRef                     = useRef(null);
  const indRef                      = useRef(null);
  const heightsRef                  = useRef({});
  const [crosshairTime, setCrosshairTime] = useState(null); // {time, price} or null

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e) {
      if (viewRef.current && !viewRef.current.contains(e.target)) setViewOpen(false);
      if (indRef.current && !indRef.current.contains(e.target))  setIndOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  useLayoutEffect(() => {
    if (!indOpen) {
      setIndicatorMenuRect(null);
      return;
    }
    const el = indRef.current;
    if (!el) {
      setIndicatorMenuRect(null);
      return;
    }
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = Math.max(160, r.width);
      let left = r.left;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      left = Math.min(Math.max(pad, left), maxLeft);
      setIndicatorMenuRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [indOpen]);

  useLayoutEffect(() => {
    if (!viewOpen) {
      setViewMenuRect(null);
      return;
    }
    const el = viewRef.current;
    if (!el) {
      setViewMenuRect(null);
      return;
    }
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = Math.min(400, Math.max(260, r.width));
      let left = r.right - width;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      left = Math.min(Math.max(pad, left), maxLeft);
      setViewMenuRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [viewOpen]);

  // Load saved layout — always use initialSymbol for ALL panels on first load
  useEffect(() => {
    axios.get(`${API}/api/layout`).then(r => {
      const d = r.data;
      if (d.splitLayout) {
        const savedLayout = d.splitLayout.layout || DEFAULT_SPLIT_LAYOUT;
        setLayout(savedLayout);
        if (d.splitLayout.syncSymbol   != null) setSyncSymbol(d.splitLayout.syncSymbol);
        if (d.splitLayout.syncInterval != null) setSyncInterval(d.splitLayout.syncInterval);
        if (d.splitLayout.panels?.length) {
          // Always use initialSymbol for all panels — saved symbols are stale
          setPanels(d.splitLayout.panels.map((p, i) =>
            makePanel(initialSymbol, normalizeSavedTimeframe3(p.timeframe) || timeframeForPanelIndex(i))
          ));
        }
      }
    }).catch(() => {});
  }, [initialSymbol]);

  function switchLayout(key) {
    const def  = LAYOUTS.find(l => l.key === key);
    const count = def?.count || 1;
    const base  = panels[0]?.symbol || initialSymbol;
    setPanels(prev => {
      const next = [...prev];
      while (next.length < count) {
        next.push(makePanel(base, timeframeForPanelIndex(next.length)));
      }
      return next.slice(0, count);
    });
    setLayout(key);
    setActiveIdx(0);
    setViewOpen(false);
  }

  function updatePanel(idx, key, val) {
    setPanels((prev) => {
      if (key === 'timeframe' && syncInterval) {
        return prev.map((p) => ({ ...p, timeframe: val }));
      }
      return prev.map((p, i) => (i === idx ? { ...p, [key]: val } : p));
    });
    // If active panel timeframe changed, notify parent for tab sync
    if (key === 'timeframe' && idx === activeIdx && onActiveSymbolChange) {
      onActiveSymbolChange(panels[idx]?.symbol);
    }
  }

  function setSymbol(val) {
    if (syncSymbol) {
      setPanels(prev => prev.map(p => ({ ...p, symbol: val })));
    } else {
      updatePanel(activeIdx, 'symbol', val);
    }
  }

  function handleSaveLayout() {
    const payload = {
      ...heightsRef.current,
      splitLayout: {
        layout,
        syncSymbol,
        syncInterval,
        panels: panels.map(p => ({ symbol: p.symbol, timeframe: p.timeframe })),
      },
    };
    axios.post(`${API}/api/layout`, payload)
      .then(() => window.dispatchEvent(new CustomEvent('flowx-toast', { detail: 'Layout saved.' })))
      .catch(() => window.dispatchEvent(new CustomEvent('flowx-toast', { detail: 'Failed to save layout.' })));
  }

  const active = panels[activeIdx] || panels[0];

  useEffect(() => {
    const activeEmaSet = panels[activeIdx]?.emas || panels[0]?.emas;
    if (activeEmaSet) persistEmaSet(activeEmaSet);
  }, [activeIdx, panels]);

  useEffect(() => {
    const activeVolume = panels[activeIdx]?.volumeVisible;
    if (typeof activeVolume === 'boolean') persistVolumeVisible(activeVolume);
  }, [activeIdx, panels]);

  useEffect(() => {
    const activePanels = panels[activeIdx]?.visiblePanels;
    if (activePanels) persistVisiblePanels(activePanels);
  }, [activeIdx, panels]);

  useEffect(() => {
    function onEmaPrefs(e) {
      if (!Array.isArray(e?.detail)) return;
      setPanels(prev => {
        const unchanged = prev.every(p => JSON.stringify(p.emas) === JSON.stringify(e.detail));
        return unchanged ? prev : prev.map(p => ({ ...p, emas: e.detail }));
      });
    }
    function onVolumePrefs(e) {
      if (typeof e?.detail !== 'boolean') return;
      setPanels(prev => {
        const unchanged = prev.every(p => p.volumeVisible === e.detail);
        return unchanged ? prev : prev.map(p => ({ ...p, volumeVisible: e.detail }));
      });
    }
    function onStorage(e) {
      if (e.key === 'flowx.chart.ema') {
        const next = getPersistedEmaSet();
        setPanels(prev => prev.map(p => ({ ...p, emas: next })));
      }
      if (e.key === 'flowx.chart.volumeVisible') {
        const next = getPersistedVolumeVisible(true);
        setPanels(prev => prev.map(p => ({ ...p, volumeVisible: next })));
      }
      if (e.key === PANELS_PREFS_KEY) {
        const next = getPersistedVisiblePanels();
        setPanels(prev => prev.map(p => ({ ...p, visiblePanels: next })));
      }
    }
    function onPanelsPrefs(e) {
      if (!e?.detail) return;
      setPanels(prev => {
        const unchanged = prev.every(p => JSON.stringify(p.visiblePanels) === JSON.stringify(e.detail));
        return unchanged ? prev : prev.map(p => ({ ...p, visiblePanels: e.detail }));
      });
    }
    window.addEventListener(EMA_PREFS_UPDATED_EVENT, onEmaPrefs);
    window.addEventListener(VOLUME_PREFS_UPDATED_EVENT, onVolumePrefs);
    window.addEventListener(PANELS_PREFS_UPDATED_EVENT, onPanelsPrefs);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(EMA_PREFS_UPDATED_EVENT, onEmaPrefs);
      window.removeEventListener(VOLUME_PREFS_UPDATED_EVENT, onVolumePrefs);
      window.removeEventListener(PANELS_PREFS_UPDATED_EVENT, onPanelsPrefs);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', minHeight: 0, backgroundColor: 'var(--bg-primary)', overflow: 'hidden' }}>

      {/* Top bar — overflow-x:auto clips absolute children; Indicators/View use fixed + rects */}
      <div className="chart-app-toolbar" style={{
        height: 44, flexShrink: 0, backgroundColor: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', padding: '0 10px', gap: 8, overflowX: 'auto',
      }}>
        {/* Symbol search */}
        <SymbolSearch
          symbol={active.symbol}
          onChange={setSymbol}
          lastChange={active.lastChange}
          lastPrice={active.lastPrice}
        />

        <div style={{ width: 1, height: 20, backgroundColor: 'var(--border)', flexShrink: 0 }} />

        {/* Volume toggle */}
        <div onClick={() => updatePanel(activeIdx, 'volumeVisible', !active.volumeVisible)}
          style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: 'var(--bg-tertiary)', border: `1px solid ${active.volumeVisible ? '#388bfd55' : 'var(--border)'}`, borderRadius: 4, padding: '0 8px', height: 26, opacity: active.volumeVisible ? 1 : 0.5, cursor: 'pointer', flexShrink: 0 }}>
          <div style={{ width: 8, height: 8, backgroundColor: '#388bfd', borderRadius: 2 }} />
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 500 }}>Vol</span>
        </div>

        {/* EMA controls */}
        <EMAControls emas={active.emas} onChange={val => updatePanel(activeIdx, 'emas', val)} />

        <ExternalFinancialsLinks symbol={active.symbol} />

        <div style={{ flex: 1, minWidth: 8 }} />

        {/* View dropdown */}
        <div ref={viewRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button onClick={() => { setViewOpen(o => !o); setIndOpen(false); }}
            style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: layout !== 'single' ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)', border: `1px solid ${layout !== 'single' ? 'var(--accent-blue)' : 'var(--border)'}`, borderRadius: 5, padding: '0 10px', height: 28, color: layout !== 'single' ? 'var(--accent-blue)' : 'var(--text-secondary)', fontSize: 12, cursor: 'pointer' }}>
            View
            <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6 }}><path d="M0 0l4 5 4-5z"/></svg>
          </button>
          {viewOpen && viewMenuRect && (
            <div style={{
              position: 'fixed', top: viewMenuRect.top, left: viewMenuRect.left, width: viewMenuRect.width,
              zIndex: CHART_TOOLBAR_OVERLAY_Z, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6,
              boxShadow: '0 8px 24px rgba(0,0,0,0.6)', minWidth: 220, overflow: 'hidden',
            }}>
              {/* Sync toggles */}
              <div style={{ padding: '10px 14px 8px', borderBottom: '1px solid var(--border)' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Sync</div>
                {[
                  { label: 'Sync Symbol',   val: syncSymbol,   set: setSyncSymbol },
                  { label: 'Sync Interval', val: syncInterval, set: setSyncInterval },
                ].map(s => (
                  <div key={s.label} onClick={() => s.set(v => !v)}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '5px 0', cursor: 'pointer' }}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{s.label}</span>
                    <div style={{ width: 32, height: 18, borderRadius: 9, backgroundColor: s.val ? 'var(--accent-blue)' : 'var(--bg-active)', border: '1px solid var(--border)', position: 'relative', transition: 'background 0.2s' }}>
                      <div style={{ position: 'absolute', top: 2, left: s.val ? 14 : 2, width: 12, height: 12, borderRadius: '50%', backgroundColor: '#fff', transition: 'left 0.2s' }} />
                    </div>
                  </div>
                ))}
              </div>
              {/* Layout options */}
              <div style={{ padding: '8px 0' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0 14px 6px' }}>Layout</div>
                {LAYOUTS.map(l => (
                  <div key={l.key} onClick={() => switchLayout(l.key)}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 14px', cursor: 'pointer', backgroundColor: layout === l.key ? 'rgba(56,139,253,0.10)' : 'transparent', color: layout === l.key ? 'var(--accent-blue)' : 'var(--text-secondary)', fontSize: 13 }}
                    onMouseEnter={e => { if (layout !== l.key) e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                    onMouseLeave={e => { if (layout !== l.key) e.currentTarget.style.backgroundColor = 'transparent'; }}
                  >
                    {l.label}
                    {layout === l.key && <span style={{ fontSize: 11, color: 'var(--accent-blue)' }}>✓</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <DrawingToolsDesignControl />

        {/* Indicators */}
        <div ref={indRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button onClick={() => { setIndOpen(o => !o); setViewOpen(false); }}
            style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer' }}>
            Indicators
            <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6 }}><path d="M0 0l4 5 4-5z"/></svg>
          </button>
          {indOpen && indicatorMenuRect && (
            <div style={{
              position: 'fixed', top: indicatorMenuRect.top, left: indicatorMenuRect.left, width: indicatorMenuRect.width,
              zIndex: CHART_TOOLBAR_OVERLAY_Z, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6,
              boxShadow: '0 8px 24px rgba(0,0,0,0.6)', minWidth: 160, overflow: 'hidden',
            }}>
              {[{ key: 'stochrsi', label: 'StochRSI' }, { key: 'macd', label: 'MACD' }].map(ind => {
                const active2 = active.visiblePanels[ind.key];
                return (
                  <div key={ind.key}
                    onClick={() => { updatePanel(activeIdx, 'visiblePanels', { ...active.visiblePanels, [ind.key]: !active2 }); setIndOpen(false); }}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 14px', cursor: 'pointer', fontSize: 13, color: active2 ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--bg-hover)'}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                  >
                    {ind.label}
                    <div style={{ width: 14, height: 14, borderRadius: 3, border: '1px solid var(--border)', backgroundColor: active2 ? 'var(--accent-blue)' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {active2 && <svg width="9" height="7" viewBox="0 0 9 7" fill="none"><path d="M1 3.5L3.5 6L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Save Layout */}
        <button onClick={handleSaveLayout}
          style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer', flexShrink: 0 }}
          onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
        >Save Layout</button>
      </div>

      {/* Chart area */}
      <DrawingWorkspaceProvider workspaceId={`split-${initialSymbol}`}>
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', position: 'relative' }}>
          <DrawingToolbarConnected />
          <DrawingFloatPaletteConnected />
          <LayoutGrid
            layout={layout}
            panels={panels}
            activeIdx={activeIdx}
            onActivate={setActiveIdx}
            onUpdatePanel={updatePanel}
            onHeightsChange={h => { heightsRef.current = h; }}
            crosshairTime={crosshairTime}
            onCrosshairMove={setCrosshairTime}
          />
        </div>
      </DrawingWorkspaceProvider>
    </div>
  );
}

// ── Symbol search component ───────────────────────────────────────────────────
function SymbolSearch({ symbol, onChange, lastChange, lastPrice }) {
  const [query, setQuery]       = useState(symbol || '');
  const [results, setResults]   = useState([]);
  const [open, setOpen]         = useState(false);
  const ref                     = useRef(null);

  useEffect(() => { setQuery(symbol || ''); setOpen(false); setResults([]); }, [symbol]);

  useEffect(() => {
    function handle(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  async function handleInput(val) {
    setQuery(val);
    if (val.length < 1) { setResults([]); setOpen(false); return; }
    try {
      const r = await axios.get(`${API}/api/stocks/search?q=${val}`);
      setResults(r.data.results || []);
      setOpen(true);
    } catch {}
  }

  function select(sym) {
    setQuery(sym);
    setOpen(false);
    onChange(sym);
  }

  return (
    <div ref={ref} style={{ position: 'relative', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, width: 130 }}>
          <input
            value={query}
            onChange={e => handleInput(e.target.value)}
            onFocus={() => query && setOpen(true)}
            placeholder="Symbol..."
            style={{ background: 'transparent', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)', fontWeight: 600, width: '100%' }}
          />
        </div>
        {symbol && (
          <>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)', flexShrink: 0 }}>
              {lastPrice != null ? `₹${lastPrice.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : ''}
            </span>
            {lastChange != null && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, flexShrink: 0, color: lastChange >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', backgroundColor: lastChange >= 0 ? 'rgba(63,185,80,0.12)' : 'rgba(248,81,73,0.12)', border: `1px solid ${lastChange >= 0 ? '#3fb95044' : '#f8514944'}`, borderRadius: 4, padding: '1px 6px' }}>
                {lastChange >= 0 ? '+' : ''}{lastChange.toFixed(2)}%
              </span>
            )}
          </>
        )}
      </div>
      {open && results.length > 0 && (
        <div style={{ position: 'fixed', top: 'auto', left: 'auto', zIndex: 99999, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.6)', minWidth: 200, maxHeight: 300, overflowY: 'auto' }}>
          {results.map(sym => (
            <div key={sym} onClick={() => select(sym)}
              style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 12 }}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--bg-hover)'}
              onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)' }}>{sym}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Panel header with timeframe switcher ────────────────────────────────────────
// ── Panel header with timeframe switcher ──────────────────────────────────────────────
const PANEL_TF_GROUPS = {
  D: ['1D','2D','3D','4D','5D','6D','7D'],
  W: ['1W','2W','3W','4W'],
  M: ['1M','2M','3M','4M','5M','6M','7M','8M','9M','10M','11M','12M'],
};

function getPanelTFGroupKey(tf) {
  if (!tf) return 'D';
  if (/^\d+m$/.test(tf) || /^\d+h$/.test(tf)) return 'D';
  if (tf.endsWith('D')) return 'D';
  if (tf.endsWith('W')) return 'W';
  return 'M';
}

function PanelHeader({ panel, idx, isActive, showHeader, onTimeframeChange }) {
  const [activeGroup, setActiveGroup] = React.useState(() => getPanelTFGroupKey(panel.timeframe));
  if (!showHeader) return null;
  const currentKey   = getPanelTFGroupKey(panel.timeframe);
  const displayGroup = currentKey !== activeGroup ? currentKey : activeGroup;
  const group        = PANEL_TF_GROUPS[displayGroup] || PANEL_TF_GROUPS.D;
  function handleGroupClick(g) {
    setActiveGroup(g);
    onTimeframeChange(PANEL_TF_GROUPS[g][0]);
  }
  return (
    <div style={{ position:'absolute', top:0, left:0, right:0, height:28, zIndex:10,
      display:'flex', alignItems:'center', minWidth:0, backgroundColor:'rgba(13,17,23,0.85)',
      borderBottom:'1px solid var(--border)', padding:'0 8px', gap:4, pointerEvents:'none' }}
    >
      <span style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:11,
        color: isActive ? 'var(--accent-blue)' : 'var(--text-primary)', flexShrink:0 }}>
        {panel.symbol || '—'}
      </span>
      <span style={{ color:'var(--border)', fontSize:11, flexShrink:0 }}>|</span>
      {/* D/W/M group switcher */}
      <div
        role="group"
        aria-label="Timeframe group"
        style={{ display:'flex', gap:2, flexShrink:0, pointerEvents:'auto' }}
      >
        {Object.keys(PANEL_TF_GROUPS).map(g => {
          const isGA = g === displayGroup;
          return (
            <button key={g} onClick={e => { e.stopPropagation(); handleGroupClick(g); }}
              aria-pressed={isGA}
              style={{ backgroundColor: isGA ? 'rgba(255,255,255,0.12)' : 'transparent',
                border:'1px solid transparent', borderRadius:3, padding:'1px 5px', fontSize:10,
                fontFamily:'var(--font-mono)', fontWeight: isGA ? 700 : 400,
                color: isGA ? 'var(--text-primary)' : 'var(--text-muted)', cursor:'pointer' }}
              onMouseEnter={e => { if (!isGA) e.currentTarget.style.color='var(--text-primary)'; }}
              onMouseLeave={e => { if (!isGA) e.currentTarget.style.color='var(--text-muted)'; }}
            >{g}</button>
          );
        })}
      </div>
      <span style={{ color:'var(--border)', fontSize:11, flexShrink:0 }}>|</span>
      {/* TF buttons for active group */}
      <div
        role="group"
        aria-label="Timeframe options"
        style={{
        flex:1, minWidth:0, display:'flex', alignItems:'center', gap:2, overflowX:'auto', overflowY:'hidden',
        WebkitOverflowScrolling:'touch', pointerEvents:'auto',
      }}>
        {group.map(tf => {
          const isSel = tf === panel.timeframe;
          return (
            <button key={tf} onClick={e => { e.stopPropagation(); onTimeframeChange(tf); }}
              aria-pressed={isSel}
              style={{ flexShrink:0, backgroundColor: isSel ? 'var(--accent-blue)' : 'transparent',
                border: isSel ? 'none' : '1px solid transparent', borderRadius:3,
                padding:'1px 5px', fontSize:10, fontFamily:'var(--font-mono)',
                fontWeight: isSel ? 700 : 400,
                color: isSel ? '#fff' : 'var(--text-muted)', cursor:'pointer' }}
              onMouseEnter={e => { if (!isSel) e.currentTarget.style.color='var(--text-primary)'; }}
              onMouseLeave={e => { if (!isSel) e.currentTarget.style.color='var(--text-muted)'; }}
            >{tf}</button>
          );
        })}
      </div>
    </div>
  );
}

// ── Layout grid ───────────────────────────────────────────────────────────────
function LayoutGrid({ layout, panels, activeIdx, onActivate, onUpdatePanel, onHeightsChange, crosshairTime, onCrosshairMove }) {
  function renderPanel(idx) {
    const p = panels[idx];
    if (!p) return null;
    const isActive = idx === activeIdx;
    const showHeader = panels.length > 1 || !!p.symbol;
    return (
      <div
        key={idx}
        onClick={() => onActivate(idx)}
        style={{
          flex: 1, minWidth: 0, minHeight: 0,
          height: '100%', width: '100%',
          position: 'relative', overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
          outline: isActive ? '2px solid var(--accent-blue)' : '1px solid var(--border)',
          outlineOffset: '-1px',
        }}
      >
        {p.symbol ? (
          <div style={{ position: 'absolute', top: showHeader ? 28 : 0, left: 0, right: 0, bottom: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <ChartContainer
            key={`${p.symbol}-${idx}`}
            symbol={p.symbol}
            timeframe={p.timeframe}
            emas={p.emas}
            volumeVisible={p.volumeVisible}
            visiblePanels={p.visiblePanels}
            panelOrder={p.panelOrder}
            onTogglePanel={(key) => onUpdatePanel(idx, 'visiblePanels', { ...p.visiblePanels, [key]: !p.visiblePanels[key] })}
            onMovePanel={() => {}}
            onLastChange={(pct, price) => {
              onUpdatePanel(idx, 'lastChange', pct);
              onUpdatePanel(idx, 'lastPrice', price ?? null);
            }}
            onHeightsChange={onHeightsChange}
            onCrosshairMove={onCrosshairMove}
            crosshairTime={crosshairTime}
            drawingScopeId={`split:${idx}:${p.symbol}:${p.timeframe}`}
            drawingAutoFocus={false}
          />
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 13 }}>
            Click to select, then search symbol
          </div>
        )}
        {/* Panel header — symbol + timeframe switcher */}
        <PanelHeader
          panel={p}
          idx={idx}
          isActive={isActive}
          showHeader={showHeader}
          onTimeframeChange={tf => onUpdatePanel(idx, 'timeframe', tf)}
        />
      </div>
    );
  }

  const s = { display: 'flex', width: '100%', height: '100%', overflow: 'hidden' };

  if (layout === 'single') return <div style={s}>{renderPanel(0)}</div>;
  if (layout === '2h')     return <div style={s}>{renderPanel(0)}{renderPanel(1)}</div>;
  if (layout === '3s')     return <div style={s}>{renderPanel(0)}{renderPanel(1)}{renderPanel(2)}</div>;
  return <div style={s}>{renderPanel(0)}</div>;
}
