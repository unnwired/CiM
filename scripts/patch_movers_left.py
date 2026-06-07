from pathlib import Path

p = Path(r"d:\Programs\NSE Pulse\Claude Ai\frontend\src\pages\MoversPage.js")
text = p.read_text(encoding="utf-8")

start = text.find("          <div ref={wlPickWrapRef}")
end = text.find("\n        <motionPanelDivider />", start)
if end < 0:
    end = text.find("\n        <motionPanelDivider />", start)
if end < 0:
    end = text.find("\n        <motionPanelDivider", start)
if end < 0:
    end = text.find("\n        <div onMouseDown={onDividerMouseDown}", start)
if start < 0 or end < 0:
    print("markers not found", start, end)
    raise SystemExit(1)

LEFT = r"""          <div style={{ borderBottom: '1px solid var(--border)', padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <TabBtn active={mainTab === 'day'} onClick={() => setMainTab('day')}>Day change</TabBtn>
              <TabBtn active={mainTab === 'volume'} onClick={() => setMainTab('volume')}>Volume</TabBtn>
            </div>
            {mainTab === 'day' && (
              <div style={{ display: 'flex', gap: 6 }}>
                <TabBtn active={daySide === 'gainers'} onClick={() => setDaySide('gainers')}>Gainers</TabBtn>
                <TabBtn active={daySide === 'losers'} onClick={() => setDaySide('losers')}>Losers</TabBtn>
              </div>
            )}
            {mainTab === 'volume' && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <TabBtn active={volumeMode === 'absolute'} onClick={() => setVolumeMode('absolute')}>Absolute</TabBtn>
                <TabBtn active={volumeMode === 'surge'} onClick={() => setVolumeMode('surge')}>Surge %</TabBtn>
                <TabBtn active={volumeMode === 'rvol'} onClick={() => setVolumeMode('rvol')}>RVOL 20d</TabBtn>
              </div>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', fontSize: 11 }}>
              <label style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>Min mcap
                <input value={minMcap} onChange={e => setMinMcap(e.target.value)} placeholder="500M" style={{ width: 72, height: 24, padding: '0 6px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 11 }} />
              </label>
              <label style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>Top
                <select value={limit} onChange={e => setLimit(Number(e.target.value))} style={{ height: 24, borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 11 }}>
                  {LIMIT_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <label style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>Per page
                <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ height: 24, borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 11 }}>
                  {PAGE_SIZE_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <button type="button" onClick={fetchMovers} disabled={loading || !mcapValid} style={{ height: 24, padding: '0 10px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 11, cursor: 'pointer' }}>Apply</button>
            </div>
            {(mcapError || fetchError) && (
              <motionPanelErr />
            )}
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
              {loading ? 'Loading…' : `${rows.length} stocks`}{meta?.as_of_date ? ` · EOD ${meta.as_of_date}` : ''}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-secondary)', zIndex: 1 }}>
                <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                  <th style={{ padding: '6px 8px' }}>#</th>
                  <th style={{ padding: '6px 4px' }}>Symbol</th>
                  <th style={{ padding: '6px 4px', textAlign: 'right' }}>Price</th>
                  <th style={{ padding: '6px 4px', textAlign: 'right' }}>Chg%</th>
                  {mainTab === 'volume' && <th style={{ padding: '6px 4px', textAlign: 'right' }}>{volumeColLabel}</th>}
                  <th style={{ padding: '6px 8px', textAlign: 'right' }}>Mcap</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map(row => {
                  const sym = String(row.symbol || '').toUpperCase();
                  const active = sym === selectedSymbol;
                  const volCell = volumeMode === 'surge'
                    ? formatPct(row.volume_change_pct)
                    : volumeMode === 'rvol'
                      ? (row.rvol_20d != null ? Number(row.rvol_20d).toFixed(2) : '-')
                      : formatVolume(row.volume);
                  const chg = Number(row.change_pct);
                  const chgColor = Number.isFinite(chg) ? (chg >= 0 ? 'var(--accent-green)' : 'var(--accent-red)') : 'var(--text-muted)';
                  return (
                    <tr key={sym} onClick={() => { setSelectedSymbol(sym); setLastCandleChange(null); setCrosshairTime(null); }}
                      style={{ cursor: 'pointer', background: active ? 'rgba(56,139,253,0.12)' : 'transparent', borderBottom: '1px solid var(--border-light)' }}>
                      <td style={{ padding: '5px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{row.rank}</td>
                      <td style={{ padding: '5px 4px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: active ? 'var(--accent-blue)' : 'var(--text-primary)' }}>{sym}</td>
                      <td style={{ padding: '5px 4px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{formatPrice(row.price)}</td>
                      <td style={{ padding: '5px 4px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: chgColor }}>{formatPct(row.change_pct)}</td>
                      {mainTab === 'volume' && <td style={{ padding: '5px 4px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{volCell}</td>}
                      <td style={{ padding: '5px 8px', textAlign: 'right' }}>{formatMarketCap(row.market_cap)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!loading && pageRows.length === 0 && (
              <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>No results. Adjust min market cap or refresh OHLC.</div>
            )}
          </div>
          <div style={{ padding: '8px 10px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
            <button type="button" disabled={safePage <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} style={{ padding: '2px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', cursor: safePage <= 1 ? 'default' : 'pointer', opacity: safePage <= 1 ? 0.4 : 1 }}>Prev</button>
            <span>Page {safePage} / {totalPages}</span>
            <button type="button" disabled={safePage >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))} style={{ padding: '2px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', cursor: safePage >= totalPages ? 'default' : 'pointer', opacity: safePage >= totalPages ? 0.4 : 1 }}>Next</button>
          </div>
"""

LEFT = LEFT.replace(
    """            {(mcapError || fetchError) && (
              <motionPanelErr />
            )}""",
    """            {(mcapError || fetchError) && (
              <motionPanelErr />
            )}""",
)
LEFT = LEFT.replace(
    """            {(mcapError || fetchError) && (
              <motionPanelErr />
            )}""",
    """            {(mcapError || fetchError) && (
              <div style={{ fontSize: 10, color: 'var(--accent-red)' }}>{mcapError || fetchError}</motionPanelErr>
            )}""",
)
LEFT = LEFT.replace("</motionPanelErr>", "</motionPanelErr>").replace(
    "<motionPanelErr />",
    "<motionPanelErr />",
)
LEFT = LEFT.replace(
    "<div style={{ fontSize: 10, color: 'var(--accent-red)' }}>{mcapError || fetchError}</motionPanelErr>",
    "<motionPanelErr />",
)
LEFT = LEFT.replace(
    "<motionPanelErr />",
    "<div style={{ fontSize: 10, color: 'var(--accent-red)' }}>{mcapError || fetchError}</div>",
)

text = text[:start] + LEFT + text[end:]
text = text.replace("Scanning potential swings...", "Loading movers...")
text = text.replace("potential-swings:", "movers:")
text = text.replace("potentialSwings", "movers")
text = text.replace("  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());\n  const [panelOrder, setPanelOrder] = useState(['stochrsi', 'macd']);\n\n", "\n")
text = text.replace("  getPersistedVisiblePanels,\n", "")
text = text.replace("  persistVisiblePanels,\n", "")
text = text.replace("  PANELS_PREFS_KEY,\n  PANELS_PREFS_UPDATED_EVENT,\n", "")

p.write_text(text, encoding="utf-8")
print("left pane patched")
