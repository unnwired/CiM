# One-off patch: Option E form card for MoversPage.js
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "MoversPage.js"
text = path.read_text(encoding="utf-8")
start_marker = "        <div style={{ width: paneWidth, minWidth: 240"
end_marker = "          <div style={{ flex: 1, overflowY: 'auto' }}>"
start = text.find(start_marker)
end = text.find(end_marker)
if start < 0 or end < 0:
    raise SystemExit(f"markers not found start={start} end={end}")

new_block = """        <motionPanelDivider style={{ width: paneWidth, minWidth: 280, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRight: '1px solid var(--border)', position: 'relative' }}>
          <motionPanelDivider style={{ borderBottom: '1px solid var(--border)', padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <motionPanelDivider style={moversFormCardStyle}>
              <section>
                <div style={moversSectionLabelStyle}>Ranking</div>
                <SegmentedBar
                  options={[
                    { value: 'day', label: 'Day change' },
                    { value: 'volume', label: 'Volume' },
                  ]}
                  value={mainTab}
                  onChange={setMainTab}
                />
                <div style={{ height: 8 }} />
                {mainTab === 'day' ? (
                  <SegmentedBar
                    options={[
                      { value: 'gainers', label: 'Gainers' },
                      { value: 'losers', label: 'Losers' },
                    ]}
                    value={daySide}
                    onChange={setDaySide}
                  />
                ) : (
                  <SegmentedBar
                    options={[
                      { value: 'absolute', label: 'Absolute' },
                      { value: 'surge', label: 'Surge %' },
                      { value: 'rvol', label: 'RVOL 20d' },
                    ]}
                    value={volumeMode}
                    onChange={setVolumeMode}
                  />
                )}
              </section>

              <div style={{ height: 1, backgroundColor: 'var(--border)' }} />

              <section>
                <div style={moversSectionLabelStyle}>Filters</div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 8,
                    alignItems: 'end',
                  }}
                >
                  <FormField label="Min market cap">
                    <input
                      value={minMcap}
                      onChange={e => { setMinMcap(e.target.value); setMcapError(''); }}
                      onKeyDown={e => { if (e.key === 'Enter') applyMcapAndFetch(); }}
                      placeholder="50B"
                      style={moversInputStyle}
                    />
                  </FormField>
                  <FormField label="Top">
                    <select value={limit} onChange={e => setLimit(Number(e.target.value))} style={moversSelectStyle}>
                      {LIMIT_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </FormField>
                  <FormField label="Per page">
                    <select
                      value={pageSize}
                      onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
                      style={moversSelectStyle}
                    >
                      {PAGE_SIZE_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </FormField>
                  <FormField label="Live refresh">
                    <select
                      value={pollIntervalSec}
                      onChange={e => setPollIntervalSec(Number(e.target.value))}
                      style={moversSelectStyle}
                    >
                      {POLL_INTERVAL_OPTIONS.map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </FormField>
                  <button
                    type="button"
                    onClick={applyMcapAndFetch}
                    disabled={loading || (minMcap.trim() && !mcapValid)}
                    style={{
                      gridColumn: '1 / -1',
                      width: '100%',
                      height: MOVERS_CTRL_H,
                      marginTop: 2,
                      borderRadius: 4,
                      border: '1px solid var(--accent-blue)',
                      background: 'rgba(56,139,253,0.15)',
                      color: 'var(--accent-blue)',
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: loading || (minMcap.trim() && !mcapValid) ? 'not-allowed' : 'pointer',
                      opacity: loading || (minMcap.trim() && !mcapValid) ? 0.5 : 1,
                    }}
                  >
                    Apply filters
                  </button>
                </div>
              </section>
            </div>

            {parsedMinMcap != null && Number.isFinite(parsedMinMcap) && mcapValid && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', paddingLeft: 2 }}>
                Min cap: ≥ {formatMarketCap(parsedMinMcap)}
                {appliedMinMcapInr != null && appliedMinMcapInr === parsedMinMcap ? ' · applied' : ' · press Apply'}
              </div>
            )}
            {(mcapError || fetchError) && (
              <div style={{ fontSize: 10, color: 'var(--accent-red)', paddingLeft: 2 }}>{mcapError || fetchError}</div>
            )}
          </div>

          <div
            style={{
              flexShrink: 0,
              padding: '6px 10px',
              fontSize: 10,
              color: 'var(--text-muted)',
              borderBottom: '1px solid var(--border)',
              backgroundColor: 'var(--bg-secondary)',
              lineHeight: 1.4,
            }}
          >
            {loading ? 'Loading…' : `${rows.length} stocks`}
            {useLive ? (
              <>
                {' · Live'}
                {meta?.live_status?.last_nse_refresh_at ? ` · NSE ${meta.live_status.last_nse_refresh_at}` : ''}
                {meta?.live_status?.market_open === false ? ' · market closed' : ''}
                {lastFetchedAt ? ` · UI ${lastFetchedAt.toLocaleTimeString('en-IN')}` : ''}
              </>
            ) : meta?.as_of_date ? (
              ` · EOD ${meta.as_of_date}`
            ) : ''}
          </div>

"""

new_block = new_block.replace("motionPanelDivider", "div")
path.write_text(text[:start] + new_block + text[end:], encoding="utf-8")
print("patched", path)
