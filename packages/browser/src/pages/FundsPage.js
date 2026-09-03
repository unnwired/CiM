import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import axios from 'axios';
import MfChartContainer from '../components/chart/MfChartContainer';
import StockListSplitBody from '../components/StockListSplitBody';
import EMAControls from '../components/chart/EMAControls';
import ChartHeaderBar from '../components/chart/ChartHeaderBar';
import {
  getPersistedEmaSet,
  getPersistedVisiblePanels,
  getPersistedVolumeVisible,
  persistEmaSet,
  persistVisiblePanels,
  persistVolumeVisible,
} from '../config/chartDefaults';
import { DEFAULT_CHART_TIMEFRAME_1 } from '../config/chartViewDefaults';
import { useSyncedPanelHeights } from '../hooks/useSyncedPanelHeights';

const API = '';
const DEFAULT_ORDER = ['stochrsi', 'macd'];

function formatNav(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function initialTimeframe() {
  const tf = DEFAULT_CHART_TIMEFRAME_1;
  return (tf === '4H' || tf === '30m') ? '1D' : tf;
}

export default function FundsPage() {
  const [schemes, setSchemes] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [favorites, setFavorites] = useState([]);
  const [timeframe, setTimeframe] = useState(initialTimeframe);
  const [lastChange, setLastChange] = useState(null);
  const [emas, setEmas] = useState(() => getPersistedEmaSet());
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(false));
  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());
  const [panelOrder] = useState(DEFAULT_ORDER);
  const [crosshairTime, setCrosshairTime] = useState(null);
  const [indOpen, setIndOpen] = useState(false);
  const [paneWidth, setPaneWidth] = useState(360);
  const [emptyHint, setEmptyHint] = useState('');

  const indRef = useRef(null);
  const wrapperRef = useRef(null);
  const draggingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  const { getPanelHeights, handleHeightsChange, heightsRevision } = useSyncedPanelHeights({
    columnCount: 1,
  });

  useEffect(() => {
    function handle(e) {
      if (indRef.current && !indRef.current.contains(e.target)) setIndOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  useEffect(() => {
    persistEmaSet(emas);
  }, [emas]);

  useEffect(() => {
    persistVolumeVisible(volumeVisible);
  }, [volumeVisible]);

  useEffect(() => {
    persistVisiblePanels(visiblePanels);
  }, [visiblePanels]);

  const loadCategories = useCallback(() => {
    return axios.get(`${API}/api/mf/categories`).then(r => {
      setCategories(Array.isArray(r.data?.data) ? r.data.data : []);
    });
  }, []);

  const loadSchemes = useCallback(() => {
    const params = {};
    if (search.trim()) params.q = search.trim();
    if (category) params.category = category;
    if (favoritesOnly) params.favorites_only = 1;
    return axios.get(`${API}/api/mf/schemes`, { params }).then(r => {
      const rows = Array.isArray(r.data?.data) ? r.data.data : [];
      const fav = Array.isArray(r.data?.favorites) ? r.data.favorites : [];
      setSchemes(rows);
      setFavorites(fav);
      setEmptyHint(rows.length ? '' : (favoritesOnly
        ? 'No favorite funds yet — star a scheme to pin it here.'
        : 'No schemes loaded. Run Admin → Scheduler → AMFI mutual fund NAVs (Run now).'));
      setSelected(prev => {
        if (!rows.length) return null;
        if (prev && rows.some(s => s.scheme_code === prev.scheme_code)) {
          return rows.find(s => s.scheme_code === prev.scheme_code) || rows[0];
        }
        return rows[0];
      });
    });
  }, [search, category, favoritesOnly]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([loadCategories(), loadSchemes()])
      .catch(() => {
        if (!cancelled) setEmptyHint('Failed to load mutual funds.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [loadCategories, loadSchemes]);

  const toggleFavorite = useCallback(async (code, e) => {
    e?.stopPropagation?.();
    const c = String(code || '').trim();
    if (!c) return;
    const next = favorites.includes(c)
      ? favorites.filter(x => x !== c)
      : [...favorites, c];
    try {
      const r = await axios.put(`${API}/api/mf/favorites`, { scheme_codes: next });
      const saved = Array.isArray(r.data?.scheme_codes) ? r.data.scheme_codes : next;
      setFavorites(saved);
      setSchemes(prev => prev.map(row => ({
        ...row,
        favorite: saved.includes(row.scheme_code),
      })));
      if (favoritesOnly) {
        loadSchemes().catch(() => {});
      }
    } catch {
      /* ignore */
    }
  }, [favorites, favoritesOnly, loadSchemes]);

  const handleTogglePanel = useCallback((key) => {
    setVisiblePanels(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const onDividerMouseDown = useCallback((e) => {
    e.preventDefault();
    draggingRef.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = paneWidth;
    const onMove = (ev) => {
      if (!draggingRef.current) return;
      const dx = ev.clientX - startXRef.current;
      setPaneWidth(Math.max(240, Math.min(560, startWidthRef.current + dx)));
    };
    const onUp = () => {
      draggingRef.current = false;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [paneWidth]);

  const categoryOptions = useMemo(
    () => categories.map(c => c.category).filter(Boolean),
    [categories],
  );

  const chartTf = (timeframe === '4H' || timeframe === '30m') ? '1D' : timeframe;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: 'var(--bg-primary)' }}>
      <div className="chart-app-toolbar" style={{
        height: 44, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8,
        padding: '0 12px', borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)',
        overflowX: 'auto',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, background: 'var(--bg-tertiary)',
          border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, width: 220, flexShrink: 0,
        }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search fund…"
            style={{ background: 'transparent', color: 'var(--text-primary)', flex: 1, fontSize: 12, border: 'none', outline: 'none' }}
          />
        </div>
        <select
          value={category}
          onChange={e => setCategory(e.target.value)}
          style={{
            height: 28, maxWidth: 200, background: 'var(--bg-tertiary)',
            border: '1px solid var(--border)', borderRadius: 5, color: 'var(--text-primary)',
            fontSize: 11, padding: '0 6px', flexShrink: 0,
          }}
        >
          <option value="">All categories</option>
          {categoryOptions.map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setFavoritesOnly(v => !v)}
          style={{
            height: 28, padding: '0 10px', borderRadius: 5, fontSize: 11, cursor: 'pointer', flexShrink: 0,
            border: `1px solid ${favoritesOnly ? 'var(--accent-blue)' : 'var(--border)'}`,
            background: favoritesOnly ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)',
            color: favoritesOnly ? 'var(--accent-blue)' : 'var(--text-secondary)',
          }}
        >
          Favorites
        </button>

        {selected && (
          <>
            <div style={{ width: 1, height: 20, background: 'var(--border)', flexShrink: 0 }} />
            <span style={{
              fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 12, color: 'var(--text-primary)',
              flexShrink: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 280,
            }}>
              {selected.scheme_name}
            </span>
            {lastChange != null && Number.isFinite(Number(lastChange)) && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, flexShrink: 0,
                color: Number(lastChange) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
              }}>
                {Number(lastChange) >= 0 ? '+' : ''}{Number(lastChange).toFixed(2)}%
              </span>
            )}
            <div
              onClick={() => setVolumeVisible(v => !v)}
              style={{
                display: 'flex', alignItems: 'center', gap: 5, background: 'var(--bg-tertiary)',
                border: `1px solid ${volumeVisible ? '#388bfd55' : 'var(--border)'}`,
                borderRadius: 4, padding: '0 8px', height: 26, opacity: volumeVisible ? 1 : 0.5,
                cursor: 'pointer', flexShrink: 0,
              }}
            >
              <div style={{ width: 8, height: 8, background: '#388bfd', borderRadius: 2 }} />
              <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>Vol</span>
            </div>
            <EMAControls emas={emas} onChange={setEmas} />
          </>
        )}

        <div style={{ flex: 1, minWidth: 8 }} />

        <div ref={indRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button
            type="button"
            onClick={() => setIndOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', gap: 5, background: 'var(--bg-tertiary)',
              border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28,
              color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer',
            }}
          >
            Indicators
          </button>
          {indOpen && (
            <div style={{
              position: 'absolute', top: 32, right: 0, zIndex: 50, minWidth: 160,
              background: 'var(--bg-secondary)', border: '1px solid var(--border)',
              borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.45)', overflow: 'hidden',
            }}>
              {[{ key: 'stochrsi', label: 'StochRSI' }, { key: 'macd', label: 'MACD' }].map(ind => {
                const active = !!visiblePanels[ind.key];
                return (
                  <div
                    key={ind.key}
                    onClick={() => { handleTogglePanel(ind.key); setIndOpen(false); }}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '9px 14px', cursor: 'pointer', fontSize: 13,
                      color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                    }}
                  >
                    {ind.label}
                    <span style={{ color: active ? 'var(--accent-blue)' : 'var(--text-muted)' }}>{active ? '✓' : ''}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <StockListSplitBody
        splitRef={wrapperRef}
        footer={(
          <>
            {loading ? 'Loading…' : `${schemes.length} fund${schemes.length === 1 ? '' : 's'}`}
            {' · Direct–Growth · daily NAV'}
          </>
        )}
      >
        <div style={{
          width: paneWidth, minWidth: 220, flexShrink: 0, display: 'flex', flexDirection: 'column',
          overflowY: 'auto', overflowX: 'hidden', borderRight: '1px solid var(--border)',
        }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '22px 1fr 72px 72px',
            gap: 4,
            padding: '6px 8px',
            fontSize: 10,
            fontWeight: 700,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            borderBottom: '1px solid var(--border)',
            position: 'sticky',
            top: 0,
            background: 'var(--bg-primary)',
            zIndex: 1,
          }}>
            <span />
            <span>Fund</span>
            <span style={{ textAlign: 'right' }}>NAV</span>
            <span style={{ textAlign: 'right' }}>Date</span>
          </div>
          {loading && (
            <div style={{ padding: 16, fontSize: 12, color: 'var(--text-muted)' }}>Loading funds…</div>
          )}
          {!loading && !schemes.length && (
            <div style={{ padding: 16, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.45 }}>
              {emptyHint || 'No funds.'}
            </div>
          )}
          {schemes.map(row => {
            const active = selected?.scheme_code === row.scheme_code;
            const starred = favorites.includes(row.scheme_code) || row.favorite;
            return (
              <div
                key={row.scheme_code}
                onClick={() => { setSelected(row); setLastChange(null); setCrosshairTime(null); }}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '22px 1fr 72px 72px',
                  gap: 4,
                  alignItems: 'center',
                  padding: '7px 8px',
                  cursor: 'pointer',
                  background: active ? 'rgba(56,139,253,0.12)' : 'transparent',
                  borderBottom: '1px solid var(--border)',
                }}
                onMouseEnter={e => {
                  if (!active) e.currentTarget.style.background = 'var(--bg-hover)';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = active ? 'rgba(56,139,253,0.12)' : 'transparent';
                }}
              >
                <button
                  type="button"
                  title={starred ? 'Remove favorite' : 'Add favorite'}
                  onClick={(ev) => toggleFavorite(row.scheme_code, ev)}
                  style={{
                    border: 'none', background: 'transparent', cursor: 'pointer',
                    color: starred ? '#e3b341' : 'var(--text-muted)', fontSize: 14, lineHeight: 1, padding: 0,
                  }}
                >
                  {starred ? '★' : '☆'}
                </button>
                <div style={{ minWidth: 0 }}>
                  <div style={{
                    fontSize: 12, color: 'var(--text-primary)', fontWeight: active ? 600 : 400,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {row.scheme_name}
                  </div>
                  <div style={{
                    fontSize: 10, color: 'var(--text-muted)', marginTop: 2,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {row.category}
                  </div>
                </div>
                <div style={{
                  textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)',
                }}>
                  {formatNav(row.last_nav)}
                </div>
                <div style={{
                  textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)',
                }}>
                  {String(row.nav_date || '').slice(0, 10)}
                </div>
              </div>
            );
          })}
        </div>

        <div
          onMouseDown={onDividerMouseDown}
          style={{ width: 4, backgroundColor: 'var(--border)', cursor: 'col-resize', flexShrink: 0 }}
          onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--accent-blue)'; }}
          onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'var(--border)'; }}
        />

        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {selected ? (
            <>
              <ChartHeaderBar
                symbol={selected.scheme_code}
                timeframe={chartTf}
                onTimeframeChange={(tf) => {
                  setTimeframe((tf === '4H' || tf === '30m') ? '1D' : tf);
                  setLastChange(null);
                  setCrosshairTime(null);
                }}
                hideIntraday
              />
              <MfChartContainer
                schemeCode={selected.scheme_code}
                schemeName={selected.scheme_name}
                timeframe={chartTf}
                emas={emas}
                volumeVisible={volumeVisible}
                visiblePanels={visiblePanels}
                panelOrder={panelOrder}
                onTogglePanel={handleTogglePanel}
                onLastChange={setLastChange}
                onHeightsChange={handleHeightsChange}
                panelHeights={getPanelHeights(0)}
                heightsRevision={heightsRevision}
                onCrosshairMove={setCrosshairTime}
                crosshairTime={crosshairTime}
              />
            </>
          ) : (
            <div style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--text-muted)', fontSize: 13, padding: 24, textAlign: 'center',
            }}>
              {emptyHint || 'Select a mutual fund to view daily NAV.'}
            </div>
          )}
        </div>
      </StockListSplitBody>
    </div>
  );
}
