from pathlib import Path

p = Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "MoversPage.js"
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

for i, ln in enumerate(lines):
    if ln.startswith("import React,"):
        lines[i] = "import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';\n"
        break

# drop fmtSmall and parseMaybeFloat
out = []
skip = False
for ln in lines:
    if ln.startswith("function fmtSmall") or ln.startswith("function parseMaybeFloat"):
        skip = True
        continue
    if skip:
        if ln.startswith("function formatVolume") or ln.startswith("function TabBtn"):
            skip = False
        else:
            continue
    out.append(ln)
lines = out

hooks = """  useEffect(() => {
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

s = next(i for i, l in enumerate(lines) if "PLACEHOLDER_FILTERED" in l)
e = next(i for i, l in enumerate(lines) if "function onDividerMouseDown" in l)
lines = lines[:s] + [hooks] + lines[e:]

left = r'''          <motionPanelLeft />
'''
left = """          <motionPanelLeftPlaceholder />\n"""

left = r"""          <motionPanelLeft />
"""

# proper left pane without bogus tags
left = r"""          <div style={{ borderBottom: '1px solid var(--border)', padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <TabBtn active={mainTab === 'day'} onClick={() => setMainTab('day')}>Day change</TabBtn>
              <TabBtn active={mainTab === 'volume'} onClick={() => setMainTab('volume')}>Volume</TabBtn>
            </div>
            {mainTab === 'day' && (
              <motionPanelDaySub />
            )}
            {mainTab === 'volume' && (
              <motionPanelVolSub />
            )}
            <motionPanelFilters />
            {(mcapError || fetchError) ? (
              <div style={{ fontSize: 10, color: 'var(--accent-red)' }}>{mcapError || fetchError}</motionPanelErr>
            ) : null}
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
              {loading ? 'Loading…' : `${rows.length} stocks`}{meta?.as_of_date ? ` · EOD ${meta.as_of_date}` : ''}
            </div>
          </div>
          <motionPanelTable />
          <motionPanelPager />
"""

# Write left pane correctly in one go
left = """          <motionPanelLeftContent />
"""

text = "".join(lines)
# fix left - find wlPickWrapRef block
a = text.find("          <div ref={wlPickWrapRef}")
b = text.find("\n        <motionPanelDivider />", a)
if a < 0:
    a = text.find("          <div ref={wlPickWrapRef}")
b = text.find("\n        <motionPanelDivider />", a)
if b < 0:
    b = text.find("\n        <div onMouseDown={onDividerMouseDown}", a)

LEFT = '''
          <div style={{ borderBottom: '1px solid var(--border)', padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <motionPanelTabsRow1 />
            <motionPanelTabsRow2 />
            <motionPanelFiltersRow />
            <motionPanelMetaRow />
          </div>
          <motionPanelList />
          <motionPanelPagerRow />
'''

# Build LEFT properly - single write
LEFT = r"""
          <div style={{ borderBottom: '1px solid var(--border)', padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <TabBtn active={mainTab === 'day'} onClick={() => setMainTab('day')}>Day change</TabBtn>
              <TabBtn active={mainTab === 'volume'} onClick={() => setMainTab('volume')}>Volume</TabBtn>
            </div>
            {mainTab === 'day' && (
              <motionPanelDay />
            )}
"""

print("Use manual StrReplace - script incomplete")
