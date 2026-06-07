from pathlib import Path

p = Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "MoversPage.js"
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

# Fix import
for i, ln in enumerate(lines):
    if ln.startswith("import React,"):
        lines[i] = "import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';\n"
        break

# Find markers
start_bad = next(i for i, l in enumerate(lines) if "PLACEHOLDER_FILTERED" in l)
end_bad = next(i for i, l in enumerate(lines) if l.strip().startswith("function onDividerMouseDown"))
end_bad2 = next(i for i, l in enumerate(lines) if "async function addSelectedToWatchlist" in l)
# find end of addAllToWatchlist function
end_bad3 = next(i for i, l in enumerate(lines) if i > end_bad2 and l.strip() == "}" and "addAllToWatchlist" in "".join(lines[end_bad2:i+1]))
# simpler: end at onDividerMouseDown
replacement_hooks = """  useEffect(() => {
    axios.get(`${API}/api/layout`).then(r => {
      if (r.data.moversPaneWidth) setPaneWidth(Number(r.data.moversPaneWidth) || 360);
      if (r.data.moversChartLayout) setChartLayout(String(r.data.moversChartLayout));
      if (r.data.moversTimeframe) setTimeframe(r.data.moversTimeframe);
      if (r.data.moversTimeframe2) setTimeframe2(r.data.moversTimeframe2);
      if (r.data.moversTimeframe3) setTimeframe3(normalizeSavedTimeframe3(r.data.moversTimeframe3));
    }).catch(() => {});
  }, []);

  useEffect(() => { persistEmaSet(emas); }, [emas]);
  useEffect(() => { persistVolumeVisible(volumeVisible); }, [volumeVisible]);

  useEffect(() => {
    function onEmaPrefs(e) {
      if (!e?.detail) return;
      setEmas(prev => (JSON.stringify(prev) === JSON.stringify(e.detail) ? prev : e.detail));
    }
    function onVolumePrefs(e) {
      if (typeof e?.detail !== 'boolean') return;
      setVolumeVisible(prev => (prev === e.detail ? prev : e.detail));
    }
    function onStorage(e) {
      if (e.key === 'flowx.chart.ema') setEmas(getPersistedEmaSet());
      if (e.key === 'flowx.chart.volumeVisible') setVolumeVisible(getPersistedVolumeVisible(true));
    }
    window.addEventListener(EMA_PREFS_UPDATED_EVENT, onEmaPrefs);
    window.addEventListener(VOLUME_PREFS_UPDATED_EVENT, onVolumePrefs);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(EMA_PREFS_UPDATED_EVENT, onEmaPrefs);
      window.removeEventListener(VOLUME_PREFS_UPDATED_EVENT, onVolumePrefs);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  useLayoutEffect(() => {
    if (!viewOpen) { setViewMenuRect(null); return; }
    const el = viewRef.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      const width = 230;
      setViewMenuRect({ top: r.bottom + 4, left: Math.max(8, r.right - width), width });
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [viewOpen]);

  useEffect(() => {
    function onDocDown(e) {
      if (viewRef.current && !viewRef.current.contains(e.target)) setViewOpen(false);
    }
    document.addEventListener('mousedown', onDocDown);
    return () => document.removeEventListener('mousedown', onDocDown);
  }, []);

  useEffect(() => { fetchMovers(); }, [fetchMovers]);
  useEffect(() => {
    const h = () => fetchMovers();
    window.addEventListener(MOVERS_REFRESH_EVENT, h);
    return () => window.removeEventListener(MOVERS_REFRESH_EVENT, h);
  }, [fetchMovers]);
  useEffect(() => { if (page !== safePage) setPage(safePage); }, [page, safePage]);

"""
lines[start_bad:end_bad] = [replacement_hooks]

text = "".join(lines)

# Remove indicator toolbar block
import re
text = re.sub(
    r"\s*<motionPanelDivider />.*?</div>\s*<div ref=\{indRef\}.*?</motionPanelDivider>\s*",
    "\n        <motionPanelDivider />\n",
    text,
    flags=re.DOTALL,
    count=0,
)
# manual remove indRef block
ind_start = text.find("        <motionPanelDivider />")
if ind_start < 0:
    ind_start = text.find("        <motionPanelDivider")
if ind_start < 0:
    ind_start = text.find("        <div ref={indRef}")
if ind_start >= 0:
    ind_end = text.find("        <div ref={viewRef}", ind_start)
    if ind_end > ind_start:
        text = text[:ind_start] + text[ind_end:]

# Replace left pane: from wlPickWrapRef to closing before divider
lp_start = text.find("          <div ref={wlPickWrapRef}")
lp_end = text.find("        <motionPanelDivider />", lp_start)
if lp_start < 0:
    lp_start = text.find("          <div ref={wlPickWrapRef}")
lp_end = text.find("\n        <div onMouseDown={onDividerMouseDown}", lp_start)

left_pane = r'''          <div style={{ borderBottom: '1px solid var(--border)', padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <motionPanelTabs />
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
            </motionPanelTabs>
            {(mcapError || fetchError) && <motionPanelErr msg={mcapError || fetchError} />}
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{loading ? 'Loading…' : `${rows.length} stocks`}{meta?.as_of_date ? ` · EOD ${meta.as_of_date}` : ''}</motionPanelTabs>
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
                  const volCell = volumeMode === 'surge' ? formatPct(row.volume_change_pct)
                    : volumeMode === 'rvol' ? (row.rvol_20d != null ? Number(row.rvol_20d).toFixed(2) : '-')
                    : formatVolume(row.volume);
                  return (
                    <tr key={sym} onClick={() => { setSelectedSymbol(sym); setLastCandleChange(null); setCrosshairTime(null); }}
                      style={{ cursor: 'pointer', background: active ? 'rgba(56,139,253,0.12)' : 'transparent', borderBottom: '1px solid var(--border-light)' }}>
                      <td style={{ padding: '5px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{row.rank}</td>
                      <td style={{ padding: '5px 4px', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{sym}</td>
                      <td style={{ padding: '5px 4px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{formatPrice(row.price)}</td>
                      <td style={{ padding: '5px 4px', textAlign: 'right' }}>{formatPct(row.change_pct)}</td>
                      {mainTab === 'volume' && <td style={{ padding: '5px 4px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{volCell}</td>}
                      <td style={{ padding: '5px 8px', textAlign: 'right' }}>{formatMarketCap(row.market_cap)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!loading && pageRows.length === 0 && (
              <motionPanelEmpty />
            )}
          </div>
          <div style={{ padding: '8px 10px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
            <button type="button" disabled={safePage <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} style={{ padding: '2px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', cursor: safePage <= 1 ? 'default' : 'pointer', opacity: safePage <= 1 ? 0.4 : 1 }}>Prev</button>
            <span>Page {safePage} / {totalPages}</span>
            <button type="button" disabled={safePage >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))} style={{ padding: '2px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', cursor: safePage >= totalPages ? 'default' : 'pointer', opacity: safePage >= totalPages ? 0.4 : 1 }}>Next</button>
          </div>
'''
# Fix bogus tags in left_pane
left_pane = left_pane.replace("<motionPanelTabs />", "").replace("</motionPanelTabs>", "").replace("<motionPanelErr msg={mcapError || fetchError} />", "{(mcapError || fetchError) && <motionPanelErr />}".replace("<motionPanelErr />", f'<motionPanelErr />'))
left_pane = left_pane.replace("{(mcapError || fetchError) && <motionPanelErr />}", "<div style={{ fontSize: 10, color: 'var(--accent-red)' }}>{mcapError || fetchError}</motionPanelErr>")
left_pane = left_pane.replace("</motionPanelErr>", "</div>")
left_pane = left_pane.replace("<motionPanelEmpty />", '<motionPanelEmpty />')
left_pane = left_pane.replace("<motionPanelEmpty />", "<div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)' }}>No results</motionPanelEmpty>")
left_pane = left_pane.replace("</motionPanelEmpty>", "</motionPanelEmpty>").replace("<motionPanelEmpty>", "<motionPanelEmpty>").replace("<motionPanelEmpty>", "<div").replace("</motionPanelEmpty>", "</motionPanelEmpty>")
# fix empty - do directly
left_pane = left_pane.replace(
    '<motionPanelEmpty />',
    "<motionPanelEmpty />",
)
left_pane = left_pane.replace(
    "<motionPanelEmpty />",
    "<div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)' }}>No results. Adjust min market cap or refresh OHLC.</div>",
)

if lp_start >= 0 and lp_end > lp_start:
    text = text[:lp_start] + left_pane + text[lp_end:]

text = text.replace("Scanning potential swings...", "Loading movers...")
text = text.replace("{selectedSymbol && (\n          <a href={`https://www.screener.in/company/${selectedSymbol}/#quarters`}", "{selectedSymbol && onOpenChart && (\n          <button type=\"button\" onClick={() => onOpenChart(selectedSymbol)}")
text = text.replace("Financials ↗\n          </a>", "Open chart tab ↗\n          </button>")

# Remove unused functions
for fn in ["function fmtSmall", "function parseMaybeFloat"]:
    if fn in text:
        i = text.find(fn)
        j = text.find("\nfunction ", i + 1)
        if j < 0:
            j = text.find("\nexport default", i + 1)
        text = text[:i] + text[j:]

p.write_text(text, encoding="utf-8")
print("fixed", p)
