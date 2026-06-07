# One-off script to build MoversPage.js from PotentialSwingsPage template
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "MoversPage.js"
text = src.read_text(encoding="utf-8")

# Strip screener groups block
start = text.index("const SCREENER_GROUPS = [")
end = text.index("function formatPrice", start)
header = text[:start]
footer_from_format = text[end:]

new_header = header.replace(
    "} from '../config/chartViewDefaults';\n",
    "} from '../config/chartViewDefaults';\n"
    "import { MOVERS_REFRESH_EVENT } from '../chartEvents';\n"
    "import { formatMarketCap, parseMarketCapInput } from '../utils/formatMarketCap';\n\n"
    "const LIMIT_OPTIONS = [20, 50, 100, 200, 400];\n"
    "const PAGE_SIZE_OPTIONS = [10, 20, 25, 50];\n\n"
)

new_header = new_header.replace(
    "  getPersistedVisiblePanels,\n  getPersistedVolumeVisible,\n  persistEmaSet,\n  persistVisiblePanels,\n  persistVolumeVisible,\n} from '../config/chartDefaults';",
    "  getPersistedVolumeVisible,\n  persistEmaSet,\n  persistVolumeVisible,\n} from '../config/chartDefaults';",
).replace(
    "  EMA_PREFS_UPDATED_EVENT,\n  PANELS_PREFS_KEY,\n  PANELS_PREFS_UPDATED_EVENT,\n  VOLUME_PREFS_UPDATED_EVENT,\n",
    "  EMA_PREFS_UPDATED_EVENT,\n  VOLUME_PREFS_UPDATED_EVENT,\n",
)

footer = footer_from_format
footer = footer.replace("function parseMarketCapInput(raw) {\n  const s0 = String(raw || '').trim();\n  if (!s0) return null;\n  const s = s0.toUpperCase().replace(/,/g, '');\n  const m = s.match(/^([0-9]*\\.?[0-9]+)\\s*([MBT])?$/);\n  if (!m) return NaN;\n  const base = Number(m[1]);\n  if (!Number.isFinite(base)) return NaN;\n  const unit = m[2] || 'M';\n  const factor = unit === 'T' ? 1e12 : unit === 'B' ? 1e9 : 1e6;\n  return base * factor;\n}\n\n", "")

footer = footer.replace(
    "export default function PotentialSwingsPage({\n  onOpenChart,\n  onAddStocksToWatchlist,\n  watchlists = [],\n  onGoToWatchlist,\n}) {",
    "function formatVolume(v) {\n  if (v == null || Number.isNaN(Number(v))) return '-';\n  const n = Number(v);\n  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;\n  if (n >= 1e5) return `${(n / 1e5).toFixed(2)} L`;\n  return n.toLocaleString('en-IN');\n}\n\nfunction TabBtn({ active, onClick, children }) {\n  return (\n    <button type=\"button\" onClick={onClick} style={{ padding: '4px 10px', fontSize: 11, fontWeight: active ? 600 : 400, color: active ? 'var(--accent-blue)' : 'var(--text-secondary)', background: active ? 'rgba(56,139,253,0.12)' : 'transparent', border: `1px solid ${active ? 'var(--accent-blue)' : 'var(--border)'}`, borderRadius: 4, cursor: 'pointer', whiteSpace: 'nowrap' }}>{children}</button>\n  );\n}\n\nexport default function MoversPage({ onOpenChart }) {",
)

# State block replacement - from first useState through filterInputsValid closing
old_state_start = footer.index("  const [rows, setRows]")
old_state_end = footer.index("  const filteredRows = rows.filter")
new_state = """  const [mainTab, setMainTab] = useState('day');
  const [daySide, setDaySide] = useState('gainers');
  const [volumeMode, setVolumeMode] = useState('absolute');
  const [limit, setLimit] = useState(50);
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);
  const [minMcap, setMinMcap] = useState('');
  const [mcapError, setMcapError] = useState('');

  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState(null);

  const [timeframe, setTimeframe] = useState(DEFAULT_CHART_TIMEFRAME_1);
  const [timeframe2, setTimeframe2] = useState(DEFAULT_CHART_TIMEFRAME_2);
  const [timeframe3, setTimeframe3] = useState(DEFAULT_CHART_TIMEFRAME_3);
  const [chartLayout, setChartLayout] = useState(DEFAULT_CHART_LAYOUT);
  const [lastCandleChange, setLastCandleChange] = useState(null);
  const [crosshairTime, setCrosshairTime] = useState(null);

  const [emas, setEmas] = useState(() => getPersistedEmaSet());
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(true));

  const [paneWidth, setPaneWidth] = useState(360);
  const draggingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  const wrapperRef = useRef(null);
  const heightsRef = useRef({});

  const [viewOpen, setViewOpen] = useState(false);
  const [viewMenuRect, setViewMenuRect] = useState(null);
  const viewRef = useRef(null);

  const parsedMinMcap = parseMarketCapInput(minMcap);
  const mcapValid = parsedMinMcap === null || Number.isFinite(parsedMinMcap);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageRows = rows.slice((safePage - 1) * pageSize, safePage * pageSize);
  const volumeColLabel = volumeMode === 'surge' ? 'Vol chg%' : volumeMode === 'rvol' ? 'RVOL 20d' : 'Volume';

  const fetchMovers = useCallback(async () => {
    if (!mcapValid) {
      setMcapError('Invalid min market cap (e.g. 500M, 2B)');
      return;
    }
    setMcapError('');
    setLoading(true);
    setFetchError('');
    const params = { limit };
    if (parsedMinMcap != null && Number.isFinite(parsedMinMcap)) params.min_market_cap = parsedMinMcap;
    const url = mainTab === 'day' ? `${API}/api/movers/day-change` : `${API}/api/movers/volume`;
    if (mainTab === 'day') params.side = daySide;
    else params.volume_mode = volumeMode;
    try {
      const [listRes, metaRes] = await Promise.all([
        axios.get(url, { params }),
        axios.get(`${API}/api/movers/meta`),
      ]);
      const data = listRes.data?.data || [];
      setRows(data);
      setMeta(metaRes.data || null);
      setPage(1);
      if (data.length > 0) {
        const syms = data.map(r => String(r.symbol || '').toUpperCase());
        setSelectedSymbol(prev => (prev && syms.includes(prev) ? prev : syms[0]));
      } else setSelectedSymbol(null);
    } catch (e) {
      setFetchError(e.response?.data?.detail || e.message || 'Failed to load movers');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [mainTab, daySide, volumeMode, limit, parsedMinMcap, mcapValid]);

  const PLACEHOLDER_FILTERED = null;
"""
footer = footer[:old_state_start] + new_state + footer[old_state_end:]

# Remove filteredRows block through activePresetLabel
fr_start = footer.index("  const filteredRows = rows.filter")
fr_end = footer.index("  useEffect(() => {\n    axios.get(`${API}/api/layout`)")
footer = footer[:fr_start] + footer[fr_end:]

footer = footer.replace("potentialSwings", "movers")
footer = footer.replace("Potential Swings", "Market Movers")
footer = footer.replace("potential-swings", "movers")

# Remove runPreset and related - find runPreset function
if "  async function runPreset" in footer:
    rp_start = footer.index("  async function runPreset")
    rp_end = footer.index("  useEffect(() => {\n    runPreset", rp_start)
    footer = footer[:rp_start] + footer[rp_end:]

footer = footer.replace(
    "  useEffect(() => {\n    runPreset(SCREENER_GROUPS[0].items[0]);\n  }, []);",
    "  useEffect(() => { fetchMovers(); }, [fetchMovers]);\n\n  useEffect(() => {\n    const h = () => fetchMovers();\n    window.addEventListener(MOVERS_REFRESH_EVENT, h);\n    return () => window.removeEventListener(MOVERS_REFRESH_EVENT, h);\n  }, [fetchMovers]);\n\n  useEffect(() => { if (page !== safePage) setPage(safePage); }, [page, safePage]);",
)

# Add useCallback import
footer = footer.replace(
    "import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';",
    "import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';",
)

# Simplify chart - empty visible panels
footer = footer.replace("visiblePanels={visiblePanels}", "visiblePanels={{}}")
footer = footer.replace("panelOrder={panelOrder}", "panelOrder={[]}")
footer = footer.replace("onTogglePanel={handleTogglePanel}", "onTogglePanel={() => {}}")
footer = footer.replace("onMovePanel={handleMovePanel}", "onMovePanel={() => {}}")

# Remove indicator menu block in toolbar (between indRef and viewRef) - manual marker
footer = footer.replace("import { MOVERS_REFRESH_EVENT }", "import { MOVERS_REFRESH_EVENT }")

src.write_text(new_header + footer, encoding="utf-8")
print("Wrote partial MoversPage - manual left panel still needed")
