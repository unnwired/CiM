from pathlib import Path

p = Path(r"d:\Programs\NSE Pulse\Claude Ai\frontend\src\pages\MoversPage.js")
text = p.read_text(encoding="utf-8")

old = """        {selectedSymbol && (
          <a href={`https://www.screener.in/company/${selectedSymbol}/#quarters`} target="_blank" rel="noopener noreferrer"
            style={{ display: 'flex', alignItems: 'center', gap: 4, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12, flexShrink: 0, textDecoration: 'none' }}>
            Financials ↗
          </a>
        )}

        <div ref={indRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button type="button" onClick={() => { setIndOpen(o => !o); setViewOpen(false); }}
            style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: indOpen ? 'var(--bg-active)' : 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12 }}>
            Indicators <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" style={{ opacity: 0.6 }}><path d="M0 0l4 5 4-5z" /></svg>
          </button>
          {indOpen && indicatorMenuRect && (
            <motionPanelDivider style={{ position: 'fixed', top: indicatorMenuRect.top, left: indicatorMenuRect.left, width: indicatorMenuRect.width, zIndex: CHART_TOOLBAR_OVERLAY_Z, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.6)', minWidth: 160, overflow: 'hidden' }}>
              {[{ key: 'stochrsi', label: 'StochRSI' }, { key: 'macd', label: 'MACD' }].map(ind => {
                const active = visiblePanels[ind.key];
                return (
                  <div key={ind.key} onClick={() => { handleTogglePanel(ind.key); setIndOpen(false); }}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 14px', cursor: 'pointer', fontSize: 13, color: active ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                    {ind.label}
                    <div style={{ width: 14, height: 14, borderRadius: 3, border: '1px solid var(--border)', backgroundColor: active ? 'var(--accent-blue)' : 'transparent' }} />
                  </div>
                );
              })}
            </motionPanelDivider>
          )}
        </div>

        <div ref={viewRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button type="button" onClick={() => { setViewOpen(o => !o); setIndOpen(false); }}"""

new = """        {selectedSymbol && onOpenChart && (
          <button type="button" onClick={() => onOpenChart(selectedSymbol)}
            style={{ display: 'flex', alignItems: 'center', gap: 4, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12, flexShrink: 0, cursor: 'pointer' }}>
            Open chart tab ↗
          </button>
        )}

        <div ref={viewRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button type="button" onClick={() => setViewOpen(o => !o)}"""

# fix typo in old - use exact from file
idx = text.find("Financials")
if idx < 0:
    print("Financials not found")
else:
    start = text.rfind("\n        {selectedSymbol", 0, idx)
    end = text.find("<div ref={viewRef}", idx)
    end = text.find("onClick={() => { setViewOpen(o => !o); setIndOpen(false); }}", end)
    end = text.find("\n", end) + 1
    chunk = text[start:end]
    print("chunk len", len(chunk))
    print(repr(chunk[:80]))
    new_chunk = """        {selectedSymbol && onOpenChart && (
          <button type="button" onClick={() => onOpenChart(selectedSymbol)}
            style={{ display: 'flex', alignItems: 'center', gap: 4, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 5, padding: '0 10px', height: 28, color: 'var(--text-secondary)', fontSize: 12, flexShrink: 0, cursor: 'pointer' }}>
            Open chart tab ↗
          </button>
        )}

        <div ref={viewRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button type="button" onClick={() => setViewOpen(o => !o)}
"""
    text = text[:start] + new_chunk + text[end:]
    p.write_text(text, encoding="utf-8")
    print("patched toolbar")
