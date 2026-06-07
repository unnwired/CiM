import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { dispatchChartDataUpdated } from '../chartEvents';
import useAdminJobStatus from '../hooks/useAdminJobStatus';

const API = '';

const inp = {
  width: '100%',
  padding: '6px 8px',
  fontSize: 12,
  borderRadius: 4,
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-tertiary)',
  color: 'var(--text-primary)',
};

export default function AdminPanel({ onClose, defaultTab = 'data', hideJobsTab = false }) {
  const [tab, setTab] = useState(defaultTab);
  const [message, setMessage] = useState('');
  const { status, startPolling, refreshStatus } = useAdminJobStatus({
    autoStart: false,
    onFinished: (next) => {
      setMessage(next.error ? `Error: ${next.error}` : next.message || 'Done.');
      if (!next.error) {
        dispatchChartDataUpdated({ job: next.job });
      }
    },
  });

  const [mapping, setMapping] = useState({
    rules: [], symbol_overrides: {}, canonical_sectors: [], use_exchange_labels: true,
  });
  const [mapMsg, setMapMsg]   = useState('');
  const [newRule, setNewRule] = useState({ field: 'industry', type: 'contains', pattern: '', sector: '' });
  const [ovSym, setOvSym]     = useState('');
  const [ovSec, setOvSec]     = useState('');
  const [scSym, setScSym]     = useState('');
  const [scSe, setScSe]       = useState('');
  const [scInd, setScInd]     = useState('');

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    if (tab !== 'sectors') return;
    (async () => {
      try {
        const r = await axios.get(`${API}/api/sector-mapping`);
        setMapping({
          rules: r.data.rules || [],
          symbol_overrides: r.data.symbol_overrides || {},
          canonical_sectors: r.data.canonical_sectors || [],
          use_exchange_labels: r.data.use_exchange_labels !== false,
        });
        setMapMsg('');
      } catch (e) {
        setMapMsg('Failed to load mapping: ' + (e.response?.data?.detail || e.message));
      }
    })();
  }, [tab]);

  async function handleFetchAll() {
    try {
      setMessage('');
      await axios.post(`${API}/api/admin/fetch-ohlcv`);
      startPolling();
    } catch (e) {
      setMessage(e.response?.data?.detail || 'Failed to start job.');
    }
  }

  async function saveSectorMapping(next) {
    try {
      await axios.post(`${API}/api/sector-mapping`, {
        rules: next.rules,
        symbol_overrides: next.symbol_overrides,
        canonical_sectors: next.canonical_sectors || [],
        use_exchange_labels: next.use_exchange_labels !== false,
      });
      setMapMsg('Mapping saved. Dashboard will refresh classifications.');
    } catch (e) {
      setMapMsg('Save failed: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function fetchScreenerSectors() {
    setMapMsg('');
    try {
      await axios.post(`${API}/api/admin/fetch-screener-sectors`);
      setMapMsg('Screener.in job started. Open the Jobs tab for progress (~1–2s per symbol; respect Screener.in rate limits).');
      startPolling();
    } catch (e) {
      setMapMsg(e.response?.data?.detail || e.message);
    }
  }

  async function syncFromExchanges() {
    setMapMsg('Syncing from NSE/BSE sources…');
    try {
      const r = await axios.post(`${API}/api/sync-exchange-classification`, {});
      setMapMsg(
        `Synced: ${r.data.rows_updated} classification rows (symbol: ${r.data.rows_updated_by_symbol ?? '—'}, `
        + `ISIN: ${r.data.rows_updated_by_isin ?? '—'}), ${r.data.distinct_industries} industry labels, `
        + `${r.data.symbols_in_feed} symbols in NSE index feeds, ISIN column writes: ${r.data.isin_column_rows_updated ?? 0}. `
        + (r.data.nse_errors?.length ? `NSE warnings: ${r.data.nse_errors.join('; ')}` : ''),
      );
      const m = await axios.get(`${API}/api/sector-mapping`);
      setMapping({
        rules: m.data.rules || [],
        symbol_overrides: m.data.symbol_overrides || {},
        canonical_sectors: m.data.canonical_sectors || [],
        use_exchange_labels: m.data.use_exchange_labels !== false,
      });
    } catch (e) {
      setMapMsg('Sync failed: ' + (e.response?.data?.detail || e.message));
    }
  }

  function setUseExchangeLabels(checked) {
    const next = { ...mapping, use_exchange_labels: checked };
    setMapping(next);
    saveSectorMapping(next);
  }

  async function saveScreenerLabels() {
    const sym = scSym.trim().toUpperCase();
    if (!sym) { setMapMsg('Enter a symbol'); return; }
    try {
      const r = await axios.post(`${API}/api/screener-classification`, {
        symbol: sym,
        nse_sector: scSe.trim() || null,
        nse_industry: scInd.trim() || null,
      });
      setMapMsg(`Screener labels saved (${r.data.rows_updated || 0} row).`);
      setScSym(''); setScSe(''); setScInd('');
    } catch (e) {
      setMapMsg('Save failed: ' + (e.response?.data?.detail || e.message));
    }
  }

  function addRule() {
    if (!newRule.pattern.trim() || !newRule.sector.trim()) {
      setMapMsg('Rule needs pattern and target sector');
      return;
    }
    const rules = [...mapping.rules, { ...newRule, pattern: newRule.pattern.trim(), sector: newRule.sector.trim() }];
    const next = { ...mapping, rules };
    setMapping(next);
    setNewRule({ field: 'industry', type: 'contains', pattern: '', sector: '' });
    saveSectorMapping(next);
  }

  function removeRule(i) {
    const rules = mapping.rules.filter((_, j) => j !== i);
    const next = { ...mapping, rules };
    setMapping(next);
    saveSectorMapping(next);
  }

  function addOverride() {
    const s = ovSym.trim().toUpperCase();
    if (!s || !ovSec.trim()) { setMapMsg('Override needs symbol + sector'); return; }
    const symbol_overrides = { ...mapping.symbol_overrides, [s]: ovSec.trim() };
    const next = { ...mapping, symbol_overrides };
    setMapping(next);
    setOvSym(''); setOvSec('');
    saveSectorMapping(next);
  }

  function removeOverride(sym) {
    const symbol_overrides = { ...mapping.symbol_overrides };
    delete symbol_overrides[sym];
    const next = { ...mapping, symbol_overrides };
    setMapping(next);
    saveSectorMapping(next);
  }

  const isRunning = status?.running;
  const pct       = status?.percent || 0;
  const panelW    = tab === 'sectors' ? 920 : 480;

  const btnBase = {
    border: 'none', borderRadius: 5,
    padding: '8px 14px', fontSize: 13, fontWeight: 600,
    cursor: isRunning ? 'not-allowed' : 'pointer',
    opacity: isRunning ? 0.6 : 1, transition: 'opacity 0.15s',
    color: isRunning ? 'var(--text-muted)' : '#fff',
    backgroundColor: isRunning ? 'var(--bg-active)' : undefined,
  };

  const sectionStyle = {
    backgroundColor: 'var(--bg-tertiary)', borderRadius: 6,
    padding: '14px 16px', border: '1px solid var(--border)',
    display: 'flex', flexDirection: 'column', gap: 8,
  };

  const labelStyle = {
    fontSize: 11, color: 'var(--text-muted)', marginBottom: 4,
    fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em',
  };

  const descStyle = { fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 };

  const canon = mapping.canonical_sectors || [];

  return (
    <div
      style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 9000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8,
        width: panelW, maxWidth: '96vw', maxHeight: '92vh', overflow: 'hidden', boxShadow: '0 16px 48px rgba(0,0,0,0.6)', display: 'flex', flexDirection: 'column',
      }}>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 18px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-tertiary)', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Data Management</span>
            <div style={{ display: 'flex', borderRadius: 5, overflow: 'hidden', border: '1px solid var(--border)' }}>
              {!hideJobsTab && (
                <button type="button" onClick={() => setTab('data')} style={{
                  padding: '5px 12px', fontSize: 11, border: 'none', cursor: 'pointer',
                  backgroundColor: tab === 'data' ? 'var(--accent-blue)' : 'var(--bg-secondary)', color: tab === 'data' ? '#fff' : 'var(--text-secondary)',
                }}>Jobs</button>
              )}
              <button type="button" onClick={() => setTab('sectors')} style={{
                padding: '5px 12px', fontSize: 11, border: 'none', cursor: 'pointer',
                backgroundColor: tab === 'sectors' ? 'var(--accent-blue)' : 'var(--bg-secondary)', color: tab === 'sectors' ? '#fff' : 'var(--text-secondary)',
              }}>Market sectors</button>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1 }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
          >×</button>
        </div>

        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto', flex: 1 }}>

          {!hideJobsTab && tab === 'data' && (
            <>
              {isRunning && (
                <div style={{ backgroundColor: 'var(--bg-tertiary)', borderRadius: 6, padding: '12px 14px', border: '1px solid var(--border)' }}>
                  <div style={{ marginBottom: 10, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.55, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {status?.message}
                  </div>
                  <div style={{ height: 6, backgroundColor: 'var(--bg-active)', borderRadius: 3, overflow: 'hidden', marginBottom: 6 }}>
                    <div style={{ height: '100%', width: `${pct}%`, backgroundColor: 'var(--accent-blue)', borderRadius: 3, transition: 'width 0.3s ease' }} />
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right' }}>
                    {status?.progress} / {status?.total} ({pct}%)
                  </div>
                </div>
              )}

              <div style={sectionStyle}>
                <div style={labelStyle}>Chart &amp; Price Data</div>
                <div style={descStyle}>
                  Appends missing daily candles for all stocks and indices, then updates live prices,
                  <strong>market cap</strong> from <strong>Screener.in</strong> company pages when the HTML parse succeeds (optional <code style={{ fontSize: 11 }}>data/screener_session.json</code> cookies), otherwise from the NSE quote,
                  PE and recalculates all change % values. Run daily after market close (3:30 PM IST).
                </div>
                <button onClick={handleFetchAll} disabled={isRunning} style={{ ...btnBase, backgroundColor: isRunning ? 'var(--bg-active)' : '#6e40c9' }}>
                  {isRunning && status?.job === 'ohlcv' ? 'Updating...' : 'Fetch Latest Chart + Price Data'}
                </button>
              </div>

              {message && (
                <div style={{
                  fontSize: 12,
                  color: message.startsWith('Error') ? 'var(--accent-red)' : 'var(--accent-green)',
                  backgroundColor: message.startsWith('Error') ? 'rgba(248,81,73,0.1)' : 'rgba(63,185,80,0.1)',
                  border: `1px solid ${message.startsWith('Error') ? 'var(--accent-red)' : 'var(--accent-green)'}`,
                  borderRadius: 5, padding: '8px 12px',
                }}>
                  {message}
                </div>
              )}

              <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6 }}>
                Run daily after market close. Chart + Price Data takes 5–10 minutes.
              </div>
            </>
          )}

          {tab === 'sectors' && (
            <>
              <div style={sectionStyle}>
                <div style={labelStyle}>Exchange master sync (NSE + optional BSE file)</div>
                <div style={descStyle}>
                  Downloads official NSE index CSVs (Industry + ISIN), merges <strong>EQUITY_L.csv</strong> into an <strong>isin</strong> column on screener, then fills industry by <strong>symbol</strong> first and by <strong>ISIN</strong> for rows still blank (covers symbol mismatches and BSE-only listings if your BSE file has ISIN + Industry).
                  Put a BSE export in <code style={{ fontSize: 11 }}>data/</code> and set <code style={{ fontSize: 11 }}>bse_local_path</code> in <code style={{ fontSize: 11 }}>data/exchange_classification_config.json</code> for maximum coverage.
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
                  <button type="button" onClick={syncFromExchanges} style={{ ...btnBase, backgroundColor: '#238636', height: 34 }}>
                    Sync from NSE/BSE masters
                  </button>
                  <button type="button" onClick={fetchScreenerSectors} disabled={isRunning} style={{ ...btnBase, backgroundColor: '#6f42c1', height: 34 }}>
                    Fill empty from Screener.in
                  </button>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={mapping.use_exchange_labels !== false}
                      onChange={e => setUseExchangeLabels(e.target.checked)}
                    />
                    Use exchange industry as <strong>Market Sector</strong> when rules do not match (recommended after sync)
                  </label>
                </div>
              </div>

              <div style={sectionStyle}>
                <div style={labelStyle}>Raw screener labels (feeds rule matching)</div>
                <div style={descStyle}>
                  Set optional <strong>NSE sector</strong> and <strong>NSE industry</strong> text per symbol, or use sync above.
                  Rules below match against these fields; overrides win over rules.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 8, alignItems: 'end' }}>
                  <div>
                    <div style={{ ...labelStyle, marginBottom: 2 }}>Symbol</div>
                    <input value={scSym} onChange={e => setScSym(e.target.value)} placeholder="RELIANCE" style={inp} />
                  </div>
                  <div>
                    <div style={{ ...labelStyle, marginBottom: 2 }}>NSE sector (raw)</div>
                    <input value={scSe} onChange={e => setScSe(e.target.value)} placeholder="e.g. Energy" style={inp} />
                  </div>
                  <div>
                    <div style={{ ...labelStyle, marginBottom: 2 }}>NSE industry (raw)</div>
                    <input value={scInd} onChange={e => setScInd(e.target.value)} placeholder="e.g. Refineries" style={inp} />
                  </div>
                  <button type="button" onClick={saveScreenerLabels} style={{ ...btnBase, backgroundColor: '#238636', height: 32 }}>Save</button>
                </div>
              </div>

              <div style={sectionStyle}>
                <div style={labelStyle}>Symbol → market sector override</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, alignItems: 'end' }}>
                  <input value={ovSym} onChange={e => setOvSym(e.target.value)} placeholder="Symbol" style={inp} />
                  <select value={ovSec} onChange={e => setOvSec(e.target.value)} style={inp}>
                    <option value="">Choose sector…</option>
                    {canon.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <button type="button" onClick={addOverride} style={{ ...btnBase, backgroundColor: '#388bfd', height: 32 }}>Add</button>
                </div>
                <div style={{ maxHeight: 140, overflowY: 'auto', marginTop: 6 }}>
                  {Object.entries(mapping.symbol_overrides || {}).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, padding: '4px 0', borderBottom: '1px solid var(--border-light)' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{k}</span>
                      <span style={{ color: 'var(--text-secondary)', flex: 1, marginLeft: 8 }}>{v}</span>
                      <button type="button" onClick={() => removeOverride(k)} style={{ background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer', fontSize: 14 }}>×</button>
                    </div>
                  ))}
                </div>
              </div>

              <div style={sectionStyle}>
                <div style={labelStyle}>Rules (first match wins after overrides)</div>
                <div style={{ display: 'grid', gridTemplateColumns: '100px 110px 1fr 1fr auto', gap: 6, alignItems: 'end' }}>
                  <select value={newRule.field} onChange={e => setNewRule(r => ({ ...r, field: e.target.value }))} style={inp}>
                    <option value="industry">Industry</option>
                    <option value="sector">Sector</option>
                  </select>
                  <select value={newRule.type} onChange={e => setNewRule(r => ({ ...r, type: e.target.value }))} style={inp}>
                    <option value="contains">contains</option>
                    <option value="equals">equals</option>
                    <option value="regex">regex</option>
                  </select>
                  <input value={newRule.pattern} onChange={e => setNewRule(r => ({ ...r, pattern: e.target.value }))} placeholder="Pattern" style={inp} />
                  <select value={newRule.sector} onChange={e => setNewRule(r => ({ ...r, sector: e.target.value }))} style={inp}>
                    <option value="">Target sector…</option>
                    {canon.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <button type="button" onClick={addRule} style={{ ...btnBase, backgroundColor: '#388bfd', height: 32 }}>Add rule</button>
                </div>
                <div style={{ maxHeight: 200, overflowY: 'auto', marginTop: 8 }}>
                  {(mapping.rules || []).map((r, i) => (
                    <div key={i} style={{ display: 'flex', gap: 8, fontSize: 11, padding: '5px 0', borderBottom: '1px solid var(--border-light)', alignItems: 'center' }}>
                      <span style={{ color: 'var(--text-muted)', width: 72 }}>{r.field}</span>
                      <span style={{ color: 'var(--text-muted)', width: 72 }}>{r.type}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', flex: 1, color: 'var(--text-primary)' }}>{r.pattern}</span>
                      <span style={{ color: 'var(--accent-blue)', flex: 1 }}>{r.sector}</span>
                      <button type="button" onClick={() => removeRule(i)} style={{ background: 'none', border: 'none', color: 'var(--accent-red)', cursor: 'pointer' }}>×</button>
                    </div>
                  ))}
                </div>
              </div>

              {mapMsg && (
                <div style={{ fontSize: 12, color: mapMsg.startsWith('Failed') ? 'var(--accent-red)' : 'var(--accent-green)', padding: '6px 0' }}>{mapMsg}</div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
