/* eslint-disable react-hooks/exhaustive-deps */
import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import ChartContainer from '../components/chart/ChartContainer';
import { DrawingWorkspaceProvider } from '../components/chart/drawing/DrawingWorkspaceContext';
import { DrawingToolbarConnected, DrawingFloatPaletteConnected } from '../components/chart/drawing/DrawingToolbar';
import DrawingToolsDesignControl from '../components/chart/drawing/DrawingToolsDesignControl';
import EMAControls    from '../components/chart/EMAControls';
import ChartHeaderBar from '../components/chart/ChartHeaderBar';
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
  STOCK_LIST_HEADER_HEIGHT,
  STOCK_LIST_ROW_HEIGHT,
  stockListHeaderStripStyle,
  stockListFooterStripStyle,
} from '../components/stockTableChrome';
import InstrumentNotesIcon from '../components/InstrumentNotesIcon';
import ExternalFinancialsLinks from '../components/ExternalFinancialsLinks';
import { formatMarketCap } from '../utils/formatMarketCap';
import {
  DEFAULT_CHART_LAYOUT,
  DEFAULT_CHART_TIMEFRAME_1,
  DEFAULT_CHART_TIMEFRAME_2,
  DEFAULT_CHART_TIMEFRAME_3,
  normalizeSavedTimeframe3,
} from '../config/chartViewDefaults';

const API = '';

const LAYOUTS = [
  { key: 'single', label: 'Single',              desc: 'One chart panel'              },
  { key: '2h',     label: '2 — Multi Timeframe', desc: 'Same stock, two timeframes'   },
  { key: '3h',     label: '3 — Multi Timeframe', desc: 'Same stock, three timeframes' },
];

/** Grid aligned with Pulse / Portfolio stock table (extra 30D / 1Y / Vol columns). */
const COLS = [
  { key: 'symbol',     label: 'Symbol',   width: 90 },
  { key: 'market_cap', label: 'Mkt Cap',  width: 110 },
  { key: 'note',       label: '',       width: 36 },
  { key: 'last_price', label: 'Price',    width: 85 },
  { key: 'change_pct', label: '1D Chg %', width: 80 },
  { key: 'change_30d', label: '30D %',    width: 80 },
  { key: 'change_1y',  label: '1Y %',     width: 80 },
  { key: 'volume',     label: 'Volume',   width: 100 },
];

function formatVolume(val) {
  if (val == null || isNaN(val)) return '—';
  if (val >= 1e9) return (val / 1e9).toFixed(2) + ' B';
  if (val >= 1e6) return (val / 1e6).toFixed(2) + ' M';
  if (val >= 1e3) return (val / 1e3).toFixed(2) + ' K';
  return String(Math.round(val));
}

function ChangeCell({ value }) {
  if (value === null || value === undefined) return <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>;
  const n     = parseFloat(value);
  const color = n > 0 ? 'var(--accent-green)' : n < 0 ? 'var(--accent-red)' : 'var(--text-secondary)';
  return (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color, fontWeight: 500 }}>
      {n > 0 ? '+' : ''}{n.toFixed(2)}%
    </span>
  );
}

function CellValue({ col, value }) {
  if (value === null || value === undefined) return <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>;
  if (col === 'market_cap') return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{formatMarketCap(value)}</span>;
  if (col === 'last_price') return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)' }}>₹{Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>;
  if (col === 'volume')     return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{formatVolume(value)}</span>;
  if (['change_pct', 'change_30d', 'change_1y'].includes(col)) return <ChangeCell value={value} />;
  return <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{value}</span>;
}

export default function ConstituentsPage({ index, onOpenChart, onBack, onContextMenuRequest }) {
  const [stocks, setStocks]           = useState([]);
  const [loading, setLoading]         = useState(true);
  const [sortBy, setSortBy]           = useState('market_cap');
  const [sortDir, setSortDir]         = useState('desc');
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [search, setSearch]           = useState('');
  const [chartSymbol, setChartSymbol] = useState(null);
  const [tableWidth, setTableWidth]   = useState(640);
  const [emas, setEmas]               = useState(() => getPersistedEmaSet());
  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());
  const [panelOrder, setPanelOrder]   = useState(['stochrsi', 'macd']);
  const [lastCandleChange, setLastCandleChange] = useState(null);
  const [timeframe,  setTimeframe]    = useState(DEFAULT_CHART_TIMEFRAME_1);
  const [timeframe2, setTimeframe2]   = useState(DEFAULT_CHART_TIMEFRAME_2);
  const [timeframe3, setTimeframe3]   = useState(DEFAULT_CHART_TIMEFRAME_3);
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(true));
  const [viewOpen, setViewOpen]       = useState(false);
  const [chartLayout, setChartLayout] = useState(DEFAULT_CHART_LAYOUT);
  const [crosshairTime, setCrosshairTime] = useState(null);
  const viewRef                       = useRef(null);
  const rowRefs                       = useRef({});
  const wrapperRef                    = useRef(null);
  const draggingRef                   = useRef(false);
  const startXRef                     = useRef(0);
  const startWidthRef                 = useRef(0);
  const currentHeightsRef             = useRef({});

  useEffect(() => {
    axios.get(`${API}/api/layout`).then(r => {
      if (r.data.constituentsChartLayout) setChartLayout(r.data.constituentsChartLayout);
      if (r.data.constituentsTimeframe) setTimeframe(r.data.constituentsTimeframe);
      if (r.data.constituentsTimeframe2) setTimeframe2(r.data.constituentsTimeframe2);
      if (r.data.constituentsTimeframe3) setTimeframe3(normalizeSavedTimeframe3(r.data.constituentsTimeframe3));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    function handle(e) {
      if (viewRef.current && !viewRef.current.contains(e.target)) setViewOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  useEffect(() => {
    axios.get(`${API}/api/index-constituents/${encodeURIComponent(index.symbol)}`)
      .then(r => { setStocks(r.data.data || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [index.symbol]);

  useEffect(() => {
    if (stocks.length === 0 || chartSymbol !== null) return;
    const firstSorted = [...stocks].sort((a, b) => {
      const av = a[sortBy], bv = b[sortBy];
      if (av == null) return 1; if (bv == null) return -1;
      return sortDir === 'asc'
        ? (typeof av === 'string' ? av.localeCompare(bv) : av - bv)
        : (typeof av === 'string' ? bv.localeCompare(av) : bv - av);
    });
    if (firstSorted.length > 0) { setChartSymbol(firstSorted[0].symbol); setSelectedIdx(0); }
  }, [stocks]);

  const sorted = [...stocks]
    .filter(s => !search || s.symbol.includes(search.toUpperCase()) || (s.company_name||'').toUpperCase().includes(search.toUpperCase()))
    .sort((a, b) => {
      const av = a[sortBy], bv = b[sortBy];
      if (av == null) return 1; if (bv == null) return -1;
      return sortDir === 'asc'
        ? (typeof av === 'string' ? av.localeCompare(bv) : av - bv)
        : (typeof av === 'string' ? bv.localeCompare(av) : bv - av);
    });

  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIdx(prev => {
          const next = Math.min(prev + 1, sorted.length - 1);
          rowRefs.current[next]?.scrollIntoView({ block: 'nearest' });
          setChartSymbol(sorted[next]?.symbol || null);
          setCrosshairTime(null);
          return next;
        });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIdx(prev => {
          const next = Math.max(prev - 1, 0);
          rowRefs.current[next]?.scrollIntoView({ block: 'nearest' });
          setChartSymbol(sorted[next]?.symbol || null);
          setCrosshairTime(null);
          return next;
        });
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [sorted]);

  useEffect(() => { setSelectedIdx(0); }, [sortBy, sortDir, search]);

  useEffect(() => {
    persistEmaSet(emas);
  }, [emas]);

  useEffect(() => {
    persistVolumeVisible(volumeVisible);
  }, [volumeVisible]);

  useEffect(() => {
    persistVisiblePanels(visiblePanels);
  }, [visiblePanels]);

  useEffect(() => {
    function onEmaPrefs(e) {
      if (!e?.detail) return;
      setEmas(prev => (JSON.stringify(prev) === JSON.stringify(e.detail) ? prev : e.detail));
    }
    function onVolumePrefs(e) {
      if (typeof e?.detail !== 'boolean') return;
      setVolumeVisible(prev => (prev === e.detail ? prev : e.detail));
    }
    function onPanelsPrefs(e) {
      if (!e?.detail) return;
      setVisiblePanels(prev => (JSON.stringify(prev) === JSON.stringify(e.detail) ? prev : e.detail));
    }
    function onStorage(e) {
      if (e.key === 'flowx.chart.ema') setEmas(getPersistedEmaSet());
      if (e.key === 'flowx.chart.volumeVisible') setVolumeVisible(getPersistedVolumeVisible(true));
      if (e.key === PANELS_PREFS_KEY) setVisiblePanels(getPersistedVisiblePanels());
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

  function handleSort(col) {
    if (col === 'note') return;
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortBy(col); setSortDir(col === 'symbol' ? 'asc' : 'desc'); }
  }

  function handleRowClick(stock, idx) {
    setSelectedIdx(idx);
    setChartSymbol(stock.symbol);
    setLastCandleChange(null);
    setCrosshairTime(null);
  }

  function onDividerMouseDown(e) {
    e.preventDefault();
    draggingRef.current = true; startXRef.current = e.clientX; startWidthRef.current = tableWidth;
    function onMouseMove(ev) {
      if (!draggingRef.current) return;
      const total = wrapperRef.current?.clientWidth || 1200;
      setTableWidth(Math.max(300, Math.min(total - 400, startWidthRef.current + ev.clientX - startXRef.current)));
    }
    function onMouseUp() { draggingRef.current = false; window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp); }
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  function handleTogglePanel(key) { setVisiblePanels(p => ({ ...p, [key]: !p[key] })); }
  function handleMovePanel(key, dir) {
    setPanelOrder(prev => {
      const idx = prev.indexOf(key); if (idx === -1) return prev;
      const si = dir === 'up' ? idx - 1 : idx + 1;
      if (si < 0 || si >= prev.length) return prev;
      const next = [...prev]; [next[idx], next[si]] = [next[si], next[idx]]; return next;
    });
  }

  const selectedStock = sorted[selectedIdx] || null;

  // Render a single chart panel — all panels share crosshairTime
  function renderPanel(symbol, tf, setTf, onLastChange, cacheKey, hasBorderRight) {
    if (!symbol) return null;
    return (
      <div key={cacheKey} style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', minWidth:0, borderRight: hasBorderRight ? '2px solid var(--border)' : 'none' }}>
        <ChartHeaderBar
          symbol={symbol}
          timeframe={tf}
          onTimeframeChange={newTf => { setTf(newTf); onLastChange(null); setCrosshairTime(null); }}
        />
        <ChartContainer
          key={cacheKey}
          symbol={symbol}
          timeframe={tf}
          emas={emas}
          volumeVisible={volumeVisible}
          visiblePanels={visiblePanels}
          panelOrder={panelOrder}
          onTogglePanel={handleTogglePanel}
          onMovePanel={handleMovePanel}
          onLastChange={onLastChange}
          onHeightsChange={h => { currentHeightsRef.current = h; }}
          onCrosshairMove={setCrosshairTime}
          crosshairTime={crosshairTime}
          drawingScopeId={`constituents:${cacheKey}`}
          drawingAutoFocus={false}
        />
      </div>
    );
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', width:'100%', backgroundColor:'var(--bg-primary)', overflow:'hidden', fontSize: 12 }}>

      {/* ── Header ── */}
      <div className="chart-app-toolbar" style={{ height:52, backgroundColor:'var(--bg-secondary)', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', padding:'0 16px', gap:10, flexShrink:0, overflowX:'auto', fontSize: 12 }}>

        <button onClick={onBack}
          style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, color:'var(--text-secondary)', fontSize:12, flexShrink:0 }}
          onMouseEnter={e => e.currentTarget.style.borderColor='var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.borderColor='var(--border)'}
        >← {index.name}</button>

        <div style={{ width:1, height:20, backgroundColor:'var(--border)' }} />
        <span style={{ fontSize:14, fontWeight:600, color:'var(--text-primary)', flexShrink:0 }}>Constituents</span>
        <span style={{ fontSize:12, color:'var(--text-muted)', flexShrink:0 }}>{stocks.length} stocks</span>

        {selectedStock && (
          <>
            <div style={{ width:1, height:20, backgroundColor:'var(--border)' }} />
            <span style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:14, color:'var(--accent-blue)', flexShrink:0 }}>{selectedStock.symbol}</span>
            <span style={{ fontFamily:'var(--font-mono)', fontSize:13, color:'var(--text-primary)', flexShrink:0 }}>
              ₹{Number(selectedStock.last_price).toLocaleString('en-IN', { minimumFractionDigits:2 })}
            </span>
            {lastCandleChange !== null && (
              <span style={{ fontFamily:'var(--font-mono)', fontSize:11, fontWeight:600, color: lastCandleChange>=0?'var(--accent-green)':'var(--accent-red)', backgroundColor: lastCandleChange>=0?'rgba(63,185,80,0.12)':'rgba(248,81,73,0.12)', border:`1px solid ${lastCandleChange>=0?'#3fb95044':'#f8514944'}`, borderRadius:4, padding:'1px 6px', flexShrink:0 }}>
                {lastCandleChange>=0?'+':''}{lastCandleChange.toFixed(2)}%
              </span>
            )}
          </>
        )}

        <div style={{ width:1, height:20, backgroundColor:'var(--border)', flexShrink:0 }} />

        {/* Volume */}
        <div onClick={() => setVolumeVisible(v=>!v)}
          style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--bg-tertiary)', border:`1px solid ${volumeVisible?'#388bfd55':'var(--border)'}`, borderRadius:4, padding:'0 8px', height:26, opacity: volumeVisible?1:0.5, cursor:'pointer', flexShrink:0 }}>
          <div style={{ width:8, height:8, backgroundColor:'#388bfd', borderRadius:2 }} />
          <span style={{ fontSize:11, color:'var(--text-secondary)', fontWeight:500 }}>Vol</span>
        </div>

        <EMAControls emas={emas} onChange={setEmas} />
        {chartSymbol && <ExternalFinancialsLinks symbol={chartSymbol} />}

        <div style={{ flex:1 }} />

        <DrawingToolsDesignControl />

        {/* View dropdown */}
        <div ref={viewRef} style={{ position:'relative', flexShrink:0 }}>
          <button onClick={() => setViewOpen(o=>!o)}
            style={{ display:'flex', alignItems:'center', gap:5, backgroundColor: chartLayout!=='single'?'rgba(56,139,253,0.15)':'var(--bg-tertiary)', border:`1px solid ${chartLayout!=='single'?'var(--accent-blue)':'var(--border)'}`, borderRadius:5, padding:'0 10px', height:28, color: chartLayout!=='single'?'var(--accent-blue)':'var(--text-secondary)', fontSize:12, cursor:'pointer' }}>
            View <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity:0.6 }}><path d="M0 0l4 5 4-5z"/></svg>
          </button>
          {viewOpen && (
            <div style={{ position:'fixed', zIndex:9999, right:120, backgroundColor:'var(--bg-secondary)', border:'1px solid var(--border)', borderRadius:6, boxShadow:'0 8px 24px rgba(0,0,0,0.6)', minWidth:230, overflow:'hidden' }}>
              <div style={{ padding:'6px 0' }}>
                <div style={{ fontSize:10, fontWeight:700, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.06em', padding:'4px 14px 6px' }}>Layout</div>
                {LAYOUTS.map(l => (
                  <div key={l.key} onClick={() => { setChartLayout(l.key); setViewOpen(false); }}
                    style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'8px 14px', cursor:'pointer', backgroundColor: chartLayout===l.key?'rgba(56,139,253,0.10)':'transparent', color: chartLayout===l.key?'var(--accent-blue)':'var(--text-secondary)', fontSize:13 }}
                    onMouseEnter={e => { if (chartLayout!==l.key) e.currentTarget.style.backgroundColor='var(--bg-hover)'; }}
                    onMouseLeave={e => { if (chartLayout!==l.key) e.currentTarget.style.backgroundColor='transparent'; }}
                  >
                    <div>
                      <div style={{ fontWeight: chartLayout===l.key?600:400 }}>{l.label}</div>
                      <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:1 }}>{l.desc}</div>
                    </div>
                    {chartLayout===l.key && <span style={{ fontSize:11 }}>✓</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {chartSymbol && (
          <button onClick={() => onOpenChart(chartSymbol)}
            style={{ display:'flex', alignItems:'center', gap:5, backgroundColor:'var(--accent-blue)', border:'none', borderRadius:5, padding:'0 12px', height:28, color:'#fff', fontSize:12, fontWeight:600, cursor:'pointer', flexShrink:0 }}
            onMouseEnter={e => e.currentTarget.style.opacity='0.85'}
            onMouseLeave={e => e.currentTarget.style.opacity='1'}
          >Open Full Chart ↗</button>
        )}

        {/* Search */}
        <div style={{ display:'flex', alignItems:'center', gap:6, backgroundColor:'var(--bg-tertiary)', border:'1px solid var(--border)', borderRadius:5, padding:'0 10px', height:28, width:160, flexShrink:0 }}>
          <svg width="11" height="11" viewBox="0 0 16 16" fill="var(--text-muted)"><path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z"/></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter..." style={{ background:'transparent', color:'var(--text-primary)', flex:1, fontSize:12 }} />
          {search && <button onClick={() => setSearch('')} style={{ background:'none', color:'var(--text-muted)', fontSize:14 }}>×</button>}
        </div>
      </div>

      {/* ── Body ── */}
      <div ref={wrapperRef} style={{ flex:1, display:'flex', overflow:'hidden' }}>

        {/* Table */}
        <div style={{ width:tableWidth, minWidth:300, flexShrink:0, display:'flex', flexDirection:'column', overflow:'hidden' }}>
          <div style={stockListHeaderStripStyle}>
            {COLS.map(col => (
              <div key={col.key} onClick={() => col.key !== 'note' && handleSort(col.key)}
                style={{ width:col.width, minWidth:col.width, padding:'0 8px', height: STOCK_LIST_HEADER_HEIGHT, display:'flex', alignItems:'center', cursor: col.key === 'note' ? 'default' : 'pointer', fontSize:11, fontWeight:600, color: sortBy===col.key?'var(--accent-blue)':'var(--text-secondary)', borderRight:'1px solid var(--border-light)', userSelect:'none', flexShrink:0 }}>
                {col.label}
                {col.key !== 'note' && sortBy===col.key && <span style={{ marginLeft:3, fontSize:9 }}>{sortDir==='asc'?'▲':'▼'}</span>}
              </div>
            ))}
          </div>
          <div style={{ flex:1, overflowY:'auto', overflowX:'auto' }}>
            {loading ? (
              <div style={{ padding:16, color:'var(--text-muted)', fontSize:12 }}>Loading...</div>
            ) : sorted.map((stock, idx) => {
              const isSelected = idx === selectedIdx;
              return (
                <div key={stock.symbol} ref={el => rowRefs.current[idx]=el}
                  onClick={() => handleRowClick(stock, idx)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    if (onContextMenuRequest) onContextMenuRequest({ x: e.clientX, y: e.clientY, symbol: stock.symbol, type: 'stock', sourcePage: 'constituents' });
                  }}
                  style={{ display:'flex', height: STOCK_LIST_ROW_HEIGHT, borderBottom:'1px solid var(--border-light)', cursor:'pointer', backgroundColor: isSelected?'rgba(56,139,253,0.08)':'transparent', borderLeft: isSelected?'2px solid var(--accent-blue)':'2px solid transparent' }}
                  onMouseEnter={e => { if (!isSelected) e.currentTarget.style.backgroundColor='var(--bg-hover)'; }}
                  onMouseLeave={e => { if (!isSelected) e.currentTarget.style.backgroundColor='transparent'; }}
                >
                  {COLS.map(col => (
                    <div key={col.key} style={{ width:col.width, minWidth:col.width, flexShrink:0, padding: col.key === 'note' ? '0 4px' : '0 8px', display:'flex', alignItems:'center', justifyContent: col.key === 'note' ? 'center' : undefined, borderRight:'1px solid var(--border-light)', overflow:'hidden' }} onClick={col.key === 'note' ? e => e.stopPropagation() : undefined}>
                      {col.key === 'note' ? (
                        <InstrumentNotesIcon symbol={stock.symbol} instrumentType="stock" />
                      ) : col.key === 'symbol' ? (
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11, color: stock.change_pct > 0 ? 'var(--accent-green)' : stock.change_pct < 0 ? 'var(--accent-red)' : 'var(--text-primary)' }}>
                          {stock.symbol}
                        </span>
                      ) : (
                        <CellValue col={col.key} value={stock[col.key]} />
                      )}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
          <div style={stockListFooterStripStyle}>
            {sorted.length} stocks · ↑↓ navigate · click row for chart
          </div>
        </div>

        {/* Resize divider */}
        <div onMouseDown={onDividerMouseDown}
          style={{ width:4, backgroundColor:'var(--border)', cursor:'col-resize', flexShrink:0, transition:'background 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.backgroundColor='var(--accent-blue)'}
          onMouseLeave={e => e.currentTarget.style.backgroundColor='var(--border)'}
        />

        {/* Chart panels */}
        <DrawingWorkspaceProvider workspaceId={`constituents-${index?.symbol || 'idx'}`}>
        <div style={{ flex:1, display:'flex', overflow:'hidden', minWidth:400, position:'relative' }}>
          <DrawingToolbarConnected />
          <DrawingFloatPaletteConnected />
          {!chartSymbol ? (
            <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column', gap:8, color:'var(--text-muted)', fontSize:13 }}>
              <div style={{ fontSize:24, opacity:0.3 }}>📈</div>
              <div>Click a stock to view its chart</div>
              <div style={{ fontSize:11 }}>Use ↑↓ arrow keys to navigate</div>
            </div>
          ) : (
            <>
              {renderPanel(chartSymbol, timeframe,  tf => { setTimeframe(tf); setLastCandleChange(null); }, pct => setLastCandleChange(pct), chartSymbol+'-p1-'+timeframe,  chartLayout!=='single')}
              {(chartLayout==='2h'||chartLayout==='3h') && renderPanel(chartSymbol, timeframe2, tf => setTimeframe2(tf), ()=>{}, chartSymbol+'-p2-'+timeframe2, chartLayout==='3h')}
              {chartLayout==='3h' && renderPanel(chartSymbol, timeframe3, tf => setTimeframe3(tf), ()=>{}, chartSymbol+'-p3-'+timeframe3, false)}
            </>
          )}
        </div>
        </DrawingWorkspaceProvider>
      </div>
    </div>
  );
}