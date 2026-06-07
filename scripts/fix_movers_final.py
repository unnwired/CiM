from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = root / "frontend" / "src" / "pages" / "MoversPage.js"
hooks = (root / "scripts" / "movers_hooks.txt").read_text(encoding="utf-8")

LEFT = r"""          <motionPanelLEFT />
          <div style={{ borderBottom: '1px solid var(--border)', padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <motionPanelLEFT />
"""

LEFT = """          <motionPanelLEFT />
"""

# Real left pane JSX
LEFT = """
          <div style={{ borderBottom: '1px solid var(--border)', padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <TabBtn active={mainTab === 'day'} onClick={() => setMainTab('day')}>Day change</TabBtn>
              <TabBtn active={mainTab === 'volume'} onClick={() => setMainTab('volume')}>Volume</TabBtn>
            </motionPanelLEFT>
"""

print("fix script needs LEFT content - aborting")
