import axios from 'axios';
import React, { useState, useEffect, useCallback, useRef, useLayoutEffect, useMemo } from 'react';
import DashboardPage  from './pages/DashboardPage';
import ChartPage      from './pages/ChartPage';
import SplitChartPage from './pages/SplitChartPage';
import IndicesPage    from './pages/IndicesPage';
import MarketPulsePage from './pages/MarketPulsePage';
import MoversPage from './pages/MoversPage';
import MarketMapPage from './pages/MarketMapPage';
import IndexChartPage from './pages/IndexChartPage';
import ConstituentsPage from './pages/ConstituentsPage';
import WatchlistPage from './pages/WatchlistPage';
import PotentialSwingsPage from './pages/PotentialSwingsPage';
import EarningsBeatsPage from './pages/EarningsBeatsPage';
import AdminPanel     from './components/AdminPanel';
import { isDistributionProfile } from './config/exportProfile';
import { dispatchChartDataUpdated, CHART_DATA_UPDATED_EVENT, MARKET_PULSE_REFRESH_EVENT, MOVERS_REFRESH_EVENT } from './chartEvents';
import useAdminJobStatus from './hooks/useAdminJobStatus';
import { searchUniverse } from './api/client';
import SupportQrModalBody from './components/SupportQrModalBody';
import AboutCiMModalBody from './components/AboutCiMModalBody';
import CiMKnowledgeBase from './components/CiMKnowledgeBase';
import KnowledgeBaseEditor from './components/KnowledgeBaseEditor';
import { resolveKnowledgeBaseGuideId } from './content/knowledgeBasePages';

const MAX_CHART_TABS = 5;
const API = '';
const ISSUE_FORM_BASE = 'https://docs.google.com/forms/d/e/1FAIpQLScLR6u8TeQCvaWA82FhEZhm6-T7WT-LoU5RPJtvzZRIy99X0g/viewform';
const FEATURE_FORM_BASE = 'https://docs.google.com/forms/d/e/1FAIpQLScgADzeVq17F_gNe1O5tiJhkhuxlrntWuaq56A0r3UvkIbnxw/viewform';
const ISSUE_ENTRY_ID = '1471558971';
const FEATURE_ENTRY_ID = '779443803';
const CONTEXT_MENU_MARGIN = 8;

function watchlistContainsSymbol(w, symbol, itemType) {
  const sym = String(symbol || '').toUpperCase();
  const typ = String(itemType || 'stock').toLowerCase();
  return (w.items || []).some(
    it => String(it.symbol || '').toUpperCase() === sym
      && String(it.type || 'stock').toLowerCase() === typ,
  );
}

export default function AppWrapper() {
  return <App />;
}

function App() {
  const [view, setView]                 = useState('dashboard');
  const [chartTabs, setChartTabs]       = useState([]);
  const [activeTabIdx, setActiveTabIdx] = useState(null);
  const [indexTabs, setIndexTabs]       = useState([]);
  const [activeIndexTab, setActiveIndexTab] = useState(null);
  const [constituentsTabs, setConstituentsTabs] = useState([]);
  const [watchlists, setWatchlists]       = useState([]);
  const [activeWatchlistName, setActiveWatchlistName] = useState(() => localStorage.getItem('watchlist.activeName') || '');
  const [watchlistSelectedItem, setWatchlistSelectedItem] = useState(() => {
    try {
      const item = JSON.parse(localStorage.getItem('watchlist.selectedItem') || 'null');
      if (!item || !item.symbol) return null;
      return { symbol: String(item.symbol).toUpperCase(), type: String(item.type || 'stock').toLowerCase() };
    } catch {
      return null;
    }
  });
  const [contextMenuState, setContextMenuState] = useState({
    visible: false, x: 0, y: 0, symbol: '', type: 'stock',
    createMode: false, newWatchlistName: '', sourcePage: 'pulse',
    watchlistName: null,
  });
  const [contextMenuPos, setContextMenuPos] = useState({ left: 0, top: 0, flipX: false, flipY: false });
  const [adminOpen, setAdminOpen]       = useState(false);
  const [toastMessage, setToastMessage]  = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [aggressiveCacheRam, setAggressiveCacheRam] = useState(false);
  const [cacheBusy, setCacheBusy] = useState(false);
  const [rebuildSnapshotsBusy, setRebuildSnapshotsBusy] = useState(false);
  const [rebuildSnapshotsPercent, setRebuildSnapshotsPercent] = useState(0);
  const [rebuildSnapshotsMessage, setRebuildSnapshotsMessage] = useState('Preparing rebuild...');
  const [desktopCanRestartBackend, setDesktopCanRestartBackend] = useState(false);
  const [restartBackendBusy, setRestartBackendBusy] = useState(false);
  const [desktopCanReloadFrontend, setDesktopCanReloadFrontend] = useState(false);
  const [reloadFrontendBusy, setReloadFrontendBusy] = useState(false);
  const [updatePanelOpen, setUpdatePanelOpen] = useState(false);
  const [earningsPlusRefreshPending, setEarningsPlusRefreshPending] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [supportOpen, setSupportOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [feedbackType, setFeedbackType] = useState('issue');
  const [feedbackMessage, setFeedbackMessage] = useState('');
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false);
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');
  const [globalSearchResults, setGlobalSearchResults] = useState([]);
  const [globalSearchActiveIndex, setGlobalSearchActiveIndex] = useState(0);
  const [knowledgeBaseOpen, setKnowledgeBaseOpen] = useState(false);
  const [knowledgeBaseEditorOpen, setKnowledgeBaseEditorOpen] = useState(false);
  const [knowledgeBaseContentRevision, setKnowledgeBaseContentRevision] = useState(0);
  const [knowledgeBasePreview, setKnowledgeBasePreview] = useState(null);
  const mainColumnRef = useRef(null);
  const updateRequestedRef = useRef(false);
  const globalSearchInputRef = useRef(null);
  const globalSearchTimerRef = useRef(null);
  const contextMenuRef = useRef(null);
  const settingsRef = useRef(null);

  useEffect(() => {
    if (!knowledgeBaseOpen) return;
    setSettingsOpen(false);
    setGlobalSearchOpen(false);
    setGlobalSearchQuery('');
    setGlobalSearchResults([]);
    setGlobalSearchActiveIndex(0);
  }, [knowledgeBaseOpen]);
  const tabCreationOrder                = useRef([]);
  const viewRef                         = useRef(view);

  useEffect(() => {
    viewRef.current = view;
  }, [view]);
  const {
    status: jobStatus,
    isRunning: updateRunning,
    isPendingStart: updatePendingStart,
    percent: updatePercent,
    startAdminJob,
    startOhlcvUpdate,
    startIndicatorSnapshotsUpdate,
    startSplitAdjustmentsApplyPending,
    startSplitCatchupScan,
    fetchSplitWatchStatus,
    startRefreshShareCounts,
  } = useAdminJobStatus({
    autoStart: true,
    onFinished: (finalStatus) => {
      const didRequest = updateRequestedRef.current;
      updateRequestedRef.current = false;
      if (finalStatus?.job === 'earnings_plus_cache') {
        setEarningsPlusRefreshPending(false);
        if (finalStatus?.meta?.quiet) {
          dispatchChartDataUpdated({
            job: finalStatus?.job,
            ...(finalStatus?.meta || {}),
          });
          return;
        }
      }
      if (!didRequest) return;
      if (finalStatus?.error) {
        setToastMessage(`Update failed: ${finalStatus.error}`);
        return;
      }
      dispatchChartDataUpdated({
        job: finalStatus?.job,
        ...(finalStatus?.meta || {}),
      });
      window.dispatchEvent(new CustomEvent('dashboard-refresh'));
      window.dispatchEvent(new CustomEvent(MOVERS_REFRESH_EVENT));
      setToastMessage(finalStatus?.message || 'Update completed.');
    },
  });
  const panelTotal = Number(jobStatus?.total || 0);
  const panelProgress = Number(jobStatus?.progress || 0);
  const panelPercent = Number(updatePercent || 0);
  const panelHasProgress = panelTotal > 0;
  const statusMeta = jobStatus?.meta || {};
  const splitScanLine = typeof statusMeta?.split_scan_line === 'string' ? statusMeta.split_scan_line : null;
  const splitDetectedCount = Number(statusMeta?.split_detected_count || 0);
  const splitDetectedSymbols = Array.isArray(statusMeta?.split_detected_symbols)
    ? statusMeta.split_detected_symbols
    : [];
  const [splitWatchStatus, setSplitWatchStatus] = useState(null);
  const splitPendingCount = Number(splitWatchStatus?.pending_count || 0) + Number(splitWatchStatus?.failed_count || 0);
  const splitPendingList = Array.isArray(splitWatchStatus?.pending) ? splitWatchStatus.pending : [];

  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      const data = await fetchSplitWatchStatus();
      if (mounted && data) setSplitWatchStatus(data);
    };
    poll();
    const id = setInterval(poll, 60000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [fetchSplitWatchStatus]);

  useEffect(() => {
    if (!updateRunning && !updatePendingStart) {
      fetchSplitWatchStatus().then((data) => {
        if (data) setSplitWatchStatus(data);
      });
    }
  }, [updateRunning, updatePendingStart, fetchSplitWatchStatus, jobStatus?.message]);

  useEffect(() => {
    let mounted = true;
    async function checkDesktopRestartCapability() {
      try {
        const fn = window?.cimDesktop?.canRestartBackend;
        if (typeof fn !== 'function') {
          if (mounted) setDesktopCanRestartBackend(false);
          return;
        }
        const can = await fn();
        if (mounted) setDesktopCanRestartBackend(!!can);
      } catch {
        if (mounted) setDesktopCanRestartBackend(false);
      }
    }
    checkDesktopRestartCapability();
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    let mounted = true;
    async function checkDesktopReloadCapability() {
      try {
        const fn = window?.cimDesktop?.canReloadFrontend;
        if (typeof fn !== 'function') {
          if (mounted) setDesktopCanReloadFrontend(false);
          return;
        }
        const can = await fn();
        if (mounted) setDesktopCanReloadFrontend(!!can);
      } catch {
        if (mounted) setDesktopCanReloadFrontend(false);
      }
    }
    checkDesktopReloadCapability();
    return () => { mounted = false; };
  }, []);

  const onRebuildIndicatorSnapshots = useCallback(async () => {
    if (!window.confirm(
      'Clear cached indicator snapshots and rebuild from historical data for the full universe?\n\n'
      + 'This can take several minutes. Technical filters will use the new data after it completes.'
    )) return;

    try {
      setRebuildSnapshotsBusy(true);
      setRebuildSnapshotsPercent(0);
      setRebuildSnapshotsMessage('Starting Rebuild Indicator Snapshots...');
      setSettingsOpen(false);
      await axios.post(`${API}/api/admin/rebuild-indicator-snapshots`, null, {
        params: { confirm_full: 'REBUILD_FULL_UNIVERSE' },
      });
    } catch (e) {
      setRebuildSnapshotsBusy(false);
      const d = e.response?.data?.detail;
      setToastMessage(typeof d === 'string' ? d : (e.message || 'Failed to start rebuild'));
      return;
    }

    const poll = async () => {
      try {
        const s = await axios.get(`${API}/api/admin/status`);
        const st = s.data || {};
        const isSnapshotJob = st.job === 'indicator_snapshots';
        if (st.running && (isSnapshotJob || rebuildSnapshotsBusy)) {
          const pct = Number.isFinite(Number(st.percent))
            ? Number(st.percent)
            : (
              Number(st.total) > 0
                ? (Number(st.progress || 0) / Number(st.total)) * 100
                : 0
            );
          setRebuildSnapshotsPercent(Math.max(0, Math.min(100, pct)));
          if (st.message) setRebuildSnapshotsMessage(String(st.message));
          setTimeout(poll, 1200);
          return;
        }
        setRebuildSnapshotsPercent(100);
        setRebuildSnapshotsBusy(false);
        setRebuildSnapshotsMessage(st.message || 'Rebuild completed.');
        if (st.error) setToastMessage(`Rebuild failed: ${st.error}`);
        else setToastMessage(st.message || 'Rebuild Indicator Snapshots completed.');
      } catch {
        setRebuildSnapshotsBusy(false);
        setToastMessage('Rebuild status check failed.');
      }
    };
    setTimeout(poll, 1000);
  }, []);

  const navigateAfterLastChartClosed = useCallback((returnView) => {
    if (returnView && returnView !== 'chart') {
      if (returnView.startsWith('index_')) {
        setActiveIndexTab(returnView.slice('index_'.length));
      }
      setView(returnView);
      return;
    }
    // Go to most recently active indices-related tab, not dashboard
    setConstituentsTabs(ct => {
      if (ct.length > 0) {
        setView('constituents_' + ct[ct.length - 1].symbol);
        return ct;
      }
      setIndexTabs(it => {
        if (it.length > 0) {
          setActiveIndexTab(it[it.length - 1].symbol);
          setView('index_' + it[it.length - 1].symbol);
        } else {
          setView('dashboard');
        }
        return it;
      });
      return ct;
    });
  }, []);

  // ── Open stock chart ───────────────────────────────────────────────────────
  const openChart = useCallback((symbol) => {
    const originView = viewRef.current === 'chart' ? null : viewRef.current;
    setChartTabs(prev => {
      const existingIdx = prev.findIndex(t => t.symbol === symbol);
      if (existingIdx !== -1) {
        setActiveTabIdx(existingIdx);
        setView('chart');
        if (!originView) return prev;
        return prev.map((t, i) => (
          i === existingIdx ? { ...t, returnView: originView } : t
        ));
      }
      let next;
      const tab = { symbol, id: `${symbol}-${Date.now()}`, returnView: originView };
      if (prev.length < MAX_CHART_TABS) {
        next = [...prev, tab];
        setActiveTabIdx(next.length - 1);
      } else {
        const oldestId  = tabCreationOrder.current[0];
        const oldestIdx = prev.findIndex(t => t.id === oldestId);
        const replaceAt = oldestIdx !== -1 ? oldestIdx : 0;
        next            = [...prev];
        next[replaceAt] = tab;
        setActiveTabIdx(replaceAt);
      }
      tabCreationOrder.current = next.map(t => t.id);
      setView('chart');
      return next;
    });
  }, []);

  const closeChart = useCallback((idx) => {
    setChartTabs(prev => {
      const closedTab = prev[idx];
      const next = prev.filter((_, i) => i !== idx);
      tabCreationOrder.current = next.map(t => t.id);
      if (next.length === 0) {
        setActiveTabIdx(null);
        navigateAfterLastChartClosed(closedTab?.returnView);
      } else {
        const newIdx = Math.min(idx, next.length - 1);
        setActiveTabIdx(newIdx);
        setView('chart');
      }
      return next;
    });
  }, [navigateAfterLastChartClosed]);

  const switchChart = useCallback((idx) => {
    setActiveTabIdx(idx);
    setView('chart');
  }, []);

  const reorderChartTabs = useCallback((fromIdx, toIdx) => {
    setChartTabs(prev => {
      const next = [...prev];
      const [moved] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, moved);
      setActiveTabIdx(ai => {
        if (ai === fromIdx) return toIdx;
        if (fromIdx < ai && toIdx >= ai) return ai - 1;
        if (fromIdx > ai && toIdx <= ai) return ai + 1;
        return ai;
      });
      return next;
    });
  }, []);

  // ── Open index chart ───────────────────────────────────────────────────────
  const openIndex = useCallback((index) => {
    setIndexTabs(prev => {
      const exists = prev.find(t => t.symbol === index.symbol);
      if (exists) {
        setActiveIndexTab(index.symbol);
        setView('index_' + index.symbol);
        return prev;
      }
      setActiveIndexTab(index.symbol);
      setView('index_' + index.symbol);
      return [...prev, index];
    });
  }, []);

  const closeIndexTab = useCallback((symbol) => {
    setIndexTabs(prev => {
      const closedIdx = prev.findIndex(t => t.symbol === symbol);
      const next      = prev.filter(t => t.symbol !== symbol);
      if (next.length === 0) {
        setActiveIndexTab(null);
        // Check if a constituents tab for this index is open
        setConstituentsTabs(ct => {
          const related = ct.find(t => t.symbol === symbol);
          if (related) {
            setView('constituents_' + related.symbol);
          } else if (ct.length > 0) {
            setView('constituents_' + ct[ct.length - 1].symbol);
          } else {
            setView('indices');
          }
          return ct;
        });
      } else {
        const newIdx = Math.max(0, closedIdx - 1);
        const target = next[newIdx];
        setActiveIndexTab(target.symbol);
        setView('index_' + target.symbol);
      }
      return next;
    });
  }, []);

  // ── Open constituents ──────────────────────────────────────────────────────
  const openConstituents = useCallback((index) => {
    setConstituentsTabs(prev => {
      const exists = prev.find(t => t.symbol === index.symbol);
      if (exists) {
        setView('constituents_' + index.symbol);
        return prev;
      }
      setView('constituents_' + index.symbol);
      return [...prev, index];
    });
  }, []);

  const closeConstituentsTab = useCallback((symbol) => {
    setConstituentsTabs(prev => {
      const closedIdx = prev.findIndex(t => t.symbol === symbol);
      const next      = prev.filter(t => t.symbol !== symbol);
      if (next.length === 0) {
        // Go to related index chart if open, else adjacent index tab, else indices
        setIndexTabs(idxTabs => {
          const related = idxTabs.find(t => t.symbol === symbol);
          if (related) {
            setActiveIndexTab(related.symbol);
            setView('index_' + related.symbol);
          } else if (idxTabs.length > 0) {
            const last = idxTabs[idxTabs.length - 1];
            setActiveIndexTab(last.symbol);
            setView('index_' + last.symbol);
          } else {
            setView('indices');
          }
          return idxTabs;
        });
      } else {
        const newIdx = Math.max(0, closedIdx - 1);
        setView('constituents_' + next[newIdx].symbol);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    function handleOutsideClick(e) {
      if (!settingsOpen) return;
      if (settingsRef.current?.contains(e.target)) return;
      setSettingsOpen(false);
    }
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [settingsOpen]);

  const loadWatchlists = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/watchlists`);
      const list = r.data?.watchlists || [];
      setWatchlists(list);
      setActiveWatchlistName(prev => {
        if (list.length === 0) return '';
        if (!prev || !list.some(w => w.name === prev)) return list[0].name;
        return prev;
      });
    } catch {}
  }, []);

  useLayoutEffect(() => {
    if (!contextMenuState.visible) return;
    const el = contextMenuRef.current;
    if (!el) return;
    const frame = requestAnimationFrame(() => {
      const r = el.getBoundingClientRect();
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const preferFlipX = contextMenuState.x + r.width + CONTEXT_MENU_MARGIN > vw;
      const preferFlipY = contextMenuState.y + r.height + CONTEXT_MENU_MARGIN > vh;
      const rawLeft = preferFlipX ? contextMenuState.x - r.width : contextMenuState.x;
      const rawTop = preferFlipY ? contextMenuState.y - r.height : contextMenuState.y;
      const left = Math.max(CONTEXT_MENU_MARGIN, Math.min(rawLeft, vw - r.width - CONTEXT_MENU_MARGIN));
      const top = Math.max(CONTEXT_MENU_MARGIN, Math.min(rawTop, vh - r.height - CONTEXT_MENU_MARGIN));
      setContextMenuPos(prev => {
        if (
          prev.left === left
          && prev.top === top
          && prev.flipX === preferFlipX
          && prev.flipY === preferFlipY
        ) {
          return prev;
        }
        return { left, top, flipX: preferFlipX, flipY: preferFlipY };
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [
    contextMenuState.visible,
    contextMenuState.x,
    contextMenuState.y,
    contextMenuState.createMode,
    watchlists.length,
  ]);

  useEffect(() => {
    loadWatchlists();
  }, [loadWatchlists]);

  useEffect(() => {
    let active = true;
    axios.get(`${API}/api/admin/cache-settings`)
      .then((r) => {
        if (!active) return;
        setAggressiveCacheRam(!!r.data?.aggressiveCacheRam);
      })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (activeWatchlistName) localStorage.setItem('watchlist.activeName', activeWatchlistName);
    else localStorage.removeItem('watchlist.activeName');
  }, [activeWatchlistName]);

  useEffect(() => {
    if (!toastMessage) return undefined;
    const t = setTimeout(() => setToastMessage(null), 4000);
    return () => clearTimeout(t);
  }, [toastMessage]);

  useEffect(() => {
    function onToast(e) {
      const msg = typeof e?.detail === 'string' ? e.detail : String(e?.detail?.message || '');
      if (!msg) return;
      setToastMessage(msg);
    }
    window.addEventListener('cim-toast', onToast);
    return () => window.removeEventListener('cim-toast', onToast);
  }, []);

  useEffect(() => {
    if (watchlistSelectedItem) localStorage.setItem('watchlist.selectedItem', JSON.stringify(watchlistSelectedItem));
  }, [watchlistSelectedItem]);

  useEffect(() => {
    function onClick() {
      setContextMenuState(s => ({
        ...s,
        visible: false,
        createMode: false,
        newWatchlistName: '',
        watchlistName: null,
      }));
    }
    function onEsc(e) {
      if (e.key === 'Escape') setContextMenuState(s => ({ ...s, visible: false, watchlistName: null }));
    }
    window.addEventListener('click', onClick);
    window.addEventListener('keydown', onEsc);
    return () => {
      window.removeEventListener('click', onClick);
      window.removeEventListener('keydown', onEsc);
    };
  }, []);

  const goToMarketPulse = useCallback(() => {
    setView('market-pulse');
  }, []);

  const goToMarketMovers = useCallback(() => {
    setView('market-movers');
  }, []);

  const goToMarketMap = useCallback(() => {
    setView('market-map');
  }, []);

  const goToDashboard = useCallback(() => {
    setView('dashboard');
  }, []);

  const goToIndices = useCallback(() => {
    setView('indices');
  }, []);

  const goToWatchlist = useCallback(() => {
    setView('watchlist');
  }, []);

  const goToPortfolio = useCallback(() => {
    setView('portfolio');
  }, []);

  const goToPotentialSwings = useCallback(() => {
    if (isDistributionProfile) return;
    setView('potential-swings');
  }, []);

  const goToEarningsBeats = useCallback(() => {
    setView('earnings-beats');
  }, []);
  const startUpdateJob = useCallback(async (starter, startErrMessage) => {
    setSettingsOpen(false);
    if (updateRunning || updatePendingStart) {
      setUpdatePanelOpen(true);
      return;
    }
    updateRequestedRef.current = true;
    setUpdatePanelOpen(true);
    try {
      await starter();
    } catch (e) {
      updateRequestedRef.current = false;
      setToastMessage(e.response?.data?.detail || startErrMessage);
    }
  }, [updatePendingStart, updateRunning]);

  const handleUpdatePriceVolume = useCallback(async () => {
    await startUpdateJob(startOhlcvUpdate, 'Failed to start price/volume update.');
  }, [startOhlcvUpdate, startUpdateJob]);

  const handleUpdateIndicatorSnapshots = useCallback(async () => {
    await startUpdateJob(() => startIndicatorSnapshotsUpdate(1), 'Failed to start indicator snapshots update.');
  }, [startIndicatorSnapshotsUpdate, startUpdateJob]);

  const handleStockSplitAdjustments = useCallback(async () => {
    await startUpdateJob(
      () => startSplitAdjustmentsApplyPending(),
      'Failed to start pending split adjustments.'
    );
  }, [startSplitAdjustmentsApplyPending, startUpdateJob]);

  const handleSplitCatchupScan = useCallback(async () => {
    await startUpdateJob(
      () => startSplitCatchupScan(90),
      'Failed to start catch-up split scan (90 days).'
    );
  }, [startSplitCatchupScan, startUpdateJob]);

  const handleRefreshShareCounts = useCallback(async () => {
    await startUpdateJob(
      startRefreshShareCounts,
      'Failed to start share count refresh (market cap basis).'
    );
  }, [startRefreshShareCounts, startUpdateJob]);

  const handleRefreshEarningsPlusCache = useCallback(async (options = {}) => {
    const now = new Date();
    const params = {
      year: Number.isFinite(Number(options.year)) ? Number(options.year) : now.getFullYear(),
      month: Number.isFinite(Number(options.month)) ? Number(options.month) : (now.getMonth() + 1),
      force: !!options.force,
      only_incomplete: !!options.onlyIncomplete,
    };
    if (options.force) {
      const ok = window.confirm(
        'Force refresh recomputes every reported symbol for this month and may re-scrape Screener data. This can take a long time. Continue?'
      );
      if (!ok) return;
    }
    setSettingsOpen(false);
    if (updateRunning || updatePendingStart) {
      setUpdatePanelOpen(true);
      return;
    }
    updateRequestedRef.current = true;
    setUpdatePanelOpen(true);
    setEarningsPlusRefreshPending(true);
    try {
      await startAdminJob('/api/admin/refresh-earnings-plus-cache', { params });
    } catch (e) {
      updateRequestedRef.current = false;
      setEarningsPlusRefreshPending(false);
      setToastMessage(e.response?.data?.detail || 'Failed to start Earnings+ cache refresh.');
    }
  }, [startAdminJob, updatePendingStart, updateRunning]);

  const openSupport = useCallback(() => {
    setSettingsOpen(false);
    setSupportOpen(true);
  }, []);

  const openAbout = useCallback(() => {
    setSettingsOpen(false);
    setAboutOpen(true);
  }, []);

  const openFeedback = useCallback((type) => {
    const now = new Date();
    const template = [
      `Product: Charts In Motion`,
      `Type: ${type === 'issue' ? 'Issue report' : 'Feature request'}`,
      `View: ${view}`,
      `Time: ${now.toLocaleString('en-IN')}`,
      ``,
      type === 'issue'
        ? 'Describe the issue and steps to reproduce:'
        : 'Describe the feature you want and why:',
    ].join('\n');
    setSettingsOpen(false);
    setFeedbackType(type);
    setFeedbackMessage(template);
    setFeedbackOpen(true);
  }, [view]);

  const submitFeedback = useCallback(async () => {
    const message = feedbackMessage.trim();
    if (!message) {
      setToastMessage('Please add your details before sending.');
      return;
    }
    setFeedbackSending(true);
    try {
      const isIssue = feedbackType === 'issue';
      const baseUrl = isIssue ? ISSUE_FORM_BASE : FEATURE_FORM_BASE;
      const entryId = isIssue ? ISSUE_ENTRY_ID : FEATURE_ENTRY_ID;
      const target = `${baseUrl}?usp=pp_url&entry.${entryId}=${encodeURIComponent(message)}`;
      window.open(target, '_blank', 'noopener,noreferrer');
      setFeedbackOpen(false);
      setToastMessage('Form opened with your details pre-filled.');
    } catch (e) {
      setToastMessage(e.response?.data?.detail || 'Failed to open form.');
    }
    setFeedbackSending(false);
  }, [feedbackMessage, feedbackType]);

  const handleToggleAggressiveCache = useCallback(async () => {
    const next = !aggressiveCacheRam;
    setCacheBusy(true);
    try {
      const r = await axios.post(`${API}/api/admin/cache-settings`, { aggressiveCacheRam: next });
      setAggressiveCacheRam(!!r.data?.aggressiveCacheRam);
      setToastMessage(next ? 'Aggressive Cache (RAM) enabled.' : 'Aggressive Cache (RAM) disabled.');
    } catch (e) {
      setToastMessage(e.response?.data?.detail || 'Failed to update cache mode.');
    }
    setCacheBusy(false);
  }, [aggressiveCacheRam]);

  const handleClearCacheNow = useCallback(async () => {
    setCacheBusy(true);
    try {
      await axios.post(`${API}/api/admin/cache-clear`);
      setToastMessage('Cache cleared.');
    } catch (e) {
      setToastMessage(e.response?.data?.detail || 'Failed to clear cache.');
    }
    setCacheBusy(false);
  }, []);

  const [cimUpdateBusy, setCimUpdateBusy] = useState(false);
  const [appVersion, setAppVersion] = useState('');
  const [productName, setProductName] = useState('CiM');
  const DISMISSED_UPDATE_KEY = 'cim.dismissedUpdateVersion';

  const runCiMUpdateApply = useCallback(async ({ skipConfirm = false, promptData = null } = {}) => {
    if (cimUpdateBusy || updateRunning) return false;
    setCimUpdateBusy(true);
    try {
      let preview = promptData;
      if (!preview) {
        const { data } = await axios.get(`${API}/api/update/check`);
        preview = data;
      }
      if (!preview?.available) {
        if (!skipConfirm) {
          setToastMessage('No Charts In Motion update available. Add a package under CiM\\UPDATE or publish a release on GitHub.');
        }
        return false;
      }
      const u = preview.update || {};
      const sourceLabel = u.source === 'local'
        ? 'local UPDATE folder'
        : u.source === 'github'
          ? `GitHub (${preview.githubRepo || 'unnwired/cim-updates'})`
          : 'update source';
      const count = u.fileCount ?? '?';
      if (!skipConfirm) {
        const ok = window.confirm(
          `Apply Charts In Motion update ${u.version} from ${sourceLabel}${count !== '?' ? ` (${count} files)` : ''}?\n\nCharts In Motion will close to apply the update.`,
        );
        if (!ok) return false;
      }
      const { data: fullCheck } = await axios.get(`${API}/api/update/check`);
      if (!fullCheck?.available) {
        setToastMessage('Update is no longer available.');
        return false;
      }
      const picked = fullCheck.update || {};
      if (picked.source === 'github') {
        setToastMessage('Downloading update from GitHub…');
        await axios.post(`${API}/api/update/download`);
      }
      await axios.post(`${API}/api/update/apply`);
      try {
        await axios.post(`${API}/api/admin/stop-all`);
      } catch {
        // apply script still runs after exit
      }
      setToastMessage('Applying update — Charts In Motion is closing…');
      setSettingsOpen(false);
      if (typeof window?.cimDesktop?.quitForUpdate === 'function') {
        setTimeout(() => { window.cimDesktop.quitForUpdate(); }, 700);
      }
      return true;
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : (detail?.error || e.message || 'Update failed.');
      setToastMessage(msg);
      return false;
    } finally {
      setCimUpdateBusy(false);
    }
  }, [cimUpdateBusy, updateRunning]);

  const handleApplyCiMUpdate = useCallback(async () => {
    await runCiMUpdateApply({ skipConfirm: false });
  }, [runCiMUpdateApply]);

  useEffect(() => {
    let mounted = true;
    let intervalId = null;

    const isDismissed = (version) => {
      try {
        return sessionStorage.getItem(DISMISSED_UPDATE_KEY) === String(version);
      } catch {
        return false;
      }
    };

    const rememberDismiss = (version) => {
      try {
        sessionStorage.setItem(DISMISSED_UPDATE_KEY, String(version));
      } catch {
        // ignore
      }
    };

    const runBackgroundCheck = async () => {
      if (cimUpdateBusy || updateRunning || updatePendingStart) return;
      try {
        const { data } = await axios.get(`${API}/api/update/check`, { params: { background: true } });
        if (!mounted || !data?.available) return;
        if (data.backgroundCheckEnabled === false) return;
        const u = data.update || {};
        const ver = u.version;
        if (!ver || isDismissed(ver)) return;
        const sourceName = u.source === 'github'
          ? `GitHub (${data.githubRepo || 'unnwired/cim-updates'})`
          : 'your UPDATE folder';
        const ok = window.confirm(
          `Charts In Motion update ${ver} is available from ${sourceName}.\n\nWould you like to update now? Charts In Motion will close to apply the update.`,
        );
        if (!ok) {
          rememberDismiss(ver);
          return;
        }
        await runCiMUpdateApply({ skipConfirm: true, promptData: data });
      } catch {
        // background check failures are silent
      }
    };

    const startInterval = (intervalMs) => {
      intervalId = setInterval(runBackgroundCheck, intervalMs);
    };

    (async () => {
      try {
        const { data } = await axios.get(`${API}/api/update/settings`);
        if (!mounted) return;
        const name = String(data?.productName || 'CiM').trim() || 'CiM';
        setProductName(name);
        const ver = String(data?.currentVersion || '').trim();
        if (ver) {
          setAppVersion(ver);
          document.title = `${name} ${ver}`;
        } else {
          document.title = name;
        }
        runBackgroundCheck();
        if (data?.backgroundCheckEnabled === false) return;
        const mins = Number(data?.checkIntervalMinutes) || 90;
        startInterval(Math.max(5, mins) * 60 * 1000);
      } catch {
        if (!mounted) return;
        runBackgroundCheck();
        startInterval(90 * 60 * 1000);
      }
    })();

    return () => {
      mounted = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [cimUpdateBusy, updateRunning, updatePendingStart, runCiMUpdateApply]);

  const handleRestartBackendAndFrontendDev = useCallback(async () => {
    if (restartBackendBusy || reloadFrontendBusy) return;
    const canRestartBackend = typeof window?.cimDesktop?.restartBackend === 'function';
    const canReloadFrontend = typeof window?.cimDesktop?.reloadFrontend === 'function';
    if (!canRestartBackend || !canReloadFrontend) {
      setToastMessage('Restart backend + frontend is not available in this build.');
      return;
    }
    if (!window.confirm('Restart backend and frontend now?\n\nThis is a development-only action and may take a few seconds.')) {
      return;
    }
    setSettingsOpen(false);
    setRestartBackendBusy(true);
    setReloadFrontendBusy(true);
    try {
      setToastMessage('Restarting backend and frontend...');
      await window.cimDesktop.restartBackend();
      dispatchChartDataUpdated({ job: 'backend_restart' });
      await window.cimDesktop.reloadFrontend();
      setToastMessage('Backend and frontend restarted.');
    } catch (e) {
      const msg = e?.message || e?.toString?.() || 'Failed to restart backend and frontend.';
      setToastMessage(msg);
    } finally {
      setRestartBackendBusy(false);
      setReloadFrontendBusy(false);
    }
  }, [restartBackendBusy, reloadFrontendBusy]);

  const handleGlobalRefresh = useCallback(() => {
    if (view === 'market-pulse') {
      window.dispatchEvent(new CustomEvent(MARKET_PULSE_REFRESH_EVENT));
    } else if (view === 'market-movers') {
      window.dispatchEvent(new CustomEvent(MOVERS_REFRESH_EVENT));
    } else if (view === 'market-map') {
      window.dispatchEvent(new CustomEvent(CHART_DATA_UPDATED_EVENT));
    } else {
      window.dispatchEvent(new CustomEvent('dashboard-refresh'));
    }
  }, [view]);

  const handleKnowledgeBaseSaved = useCallback(() => {
    setKnowledgeBasePreview(null);
    setKnowledgeBaseContentRevision((n) => n + 1);
  }, []);

  const handleKnowledgeBasePreview = useCallback((_guideId, content) => {
    setKnowledgeBasePreview(content);
    setKnowledgeBaseOpen(true);
  }, []);

  const addToPortfolio = useCallback(async (symbol, type) => {
    const sym = String(symbol || '').trim().toUpperCase();
    const typ = String(type || 'stock').toLowerCase();
    if (!sym) return;
    try {
      await axios.post(`${API}/api/portfolio/items`, { symbol: sym, type: typ === 'index' ? 'index' : 'stock' });
      window.dispatchEvent(new CustomEvent('portfolio-updated'));
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  }, []);

  const removeFromPortfolio = useCallback(async (symbol, type) => {
    try {
      await axios.delete(`${API}/api/portfolio/items/${encodeURIComponent(symbol)}`, { params: { type: type || 'stock' } });
      window.dispatchEvent(new CustomEvent('portfolio-updated'));
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  }, []);

  const removeFromWatchlist = useCallback(async (watchlistName, symbol, type) => {
    const sym = String(symbol || '').trim();
    const typ = String(type || 'stock').toLowerCase();
    if (!watchlistName || !sym) return;
    try {
      await axios.delete(
        `${API}/api/watchlists/${encodeURIComponent(watchlistName)}/items/${encodeURIComponent(sym)}`,
        { params: { type: typ === 'index' ? 'index' : 'stock' } },
      );
      await loadWatchlists();
      window.dispatchEvent(new CustomEvent('watchlists-updated'));
      setToastMessage(`Removed ${sym} from "${watchlistName}".`);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  }, [loadWatchlists]);

  const addItemsToNamedWatchlist = useCallback(async (items, watchlistName) => {
    if (!items || items.length === 0 || !watchlistName) {
      return { ok: false, error: 'Nothing to add or no watchlist selected.' };
    }
    try {
      for (const item of items) {
        await axios.post(`${API}/api/watchlists/${encodeURIComponent(watchlistName)}/items`, item);
      }
      await loadWatchlists();
      setActiveWatchlistName(watchlistName);
      if (items[0]) setWatchlistSelectedItem(items[0]);
      window.dispatchEvent(new CustomEvent('watchlists-updated'));
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e.response?.data?.detail || e.message || 'Request failed' };
    }
  }, [loadWatchlists]);

  const handleDashboardAddToWatchlist = useCallback(async (symbols, watchlistName) => {
    const items = symbols.map(sym => ({ symbol: String(sym).trim().toUpperCase(), type: 'stock' }));
    const r = await addItemsToNamedWatchlist(items, watchlistName);
    if (r.ok) {
      setToastMessage(`Added ${symbols.length} symbol(s) to "${watchlistName}".`);
      return;
    }
    alert(r.error || 'Failed to update watchlist.');
    throw new Error(r.error || 'Failed to update watchlist');
  }, [addItemsToNamedWatchlist]);

  const handleContextMenuRequest = useCallback((payload) => {
    if (!payload?.symbol || !payload?.type) return;
    setContextMenuState({
      visible: true,
      x: payload.x || 0,
      y: payload.y || 0,
      symbol: payload.symbol,
      type: payload.type,
      createMode: false,
      newWatchlistName: '',
      sourcePage: payload.sourcePage || 'pulse',
      watchlistName: payload.watchlistName ?? null,
    });
  }, []);

  const canOpenGlobalSearch = view === 'dashboard'
    || view === 'portfolio'
    || view === 'indices'
    || view === 'watchlist';

  useEffect(() => {
    if (!globalSearchOpen) return;
    const t = setTimeout(() => globalSearchInputRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [globalSearchOpen]);

  useEffect(() => {
    if (globalSearchTimerRef.current) clearTimeout(globalSearchTimerRef.current);
    const q = globalSearchQuery.trim();
    if (!globalSearchOpen || !q) {
      setGlobalSearchResults([]);
      setGlobalSearchActiveIndex(0);
      return;
    }
    globalSearchTimerRef.current = setTimeout(async () => {
      try {
        const d = await searchUniverse(q);
        const stocks = (d.stocks || []).map(sym => ({ symbol: String(sym || '').toUpperCase(), type: 'stock', label: String(sym || '').toUpperCase() }));
        const indices = (d.indices || []).map(it => ({
          symbol: String(it.symbol || '').toUpperCase(),
          type: 'index',
          label: String(it.name || it.symbol || '').trim() || String(it.symbol || '').toUpperCase(),
        }));
        const rows = [...stocks, ...indices].slice(0, 24);
        setGlobalSearchResults(rows);
        setGlobalSearchActiveIndex(0);
      } catch {
        setGlobalSearchResults([]);
      }
    }, 140);
    return () => {
      if (globalSearchTimerRef.current) clearTimeout(globalSearchTimerRef.current);
    };
  }, [globalSearchOpen, globalSearchQuery]);

  useEffect(() => {
    setGlobalSearchActiveIndex(prev => Math.max(0, Math.min(prev, Math.max(0, globalSearchResults.length - 1))));
  }, [globalSearchResults.length]);

  const applyGlobalSearchPick = useCallback((row) => {
    if (!row?.symbol) return;
    const targetView = view === 'portfolio' ? 'portfolio'
      : view === 'watchlist' ? 'watchlist'
      : view === 'indices' ? 'indices'
      : 'dashboard';
    window.dispatchEvent(new CustomEvent('cim-global-search-select', {
      detail: {
        symbol: String(row.symbol || '').toUpperCase(),
        type: String(row.type || 'stock').toLowerCase() === 'index' ? 'index' : 'stock',
        targetView,
      },
    }));
    if (targetView === 'watchlist') {
      setWatchlistSelectedItem({
        symbol: String(row.symbol || '').toUpperCase(),
        type: String(row.type || 'stock').toLowerCase() === 'index' ? 'index' : 'stock',
      });
    }
    setGlobalSearchOpen(false);
    setGlobalSearchQuery('');
    setGlobalSearchResults([]);
    setGlobalSearchActiveIndex(0);
  }, [view]);

  const activeWatchlistForSearch = useMemo(
    () => watchlists.find(w => w.name === activeWatchlistName) || null,
    [watchlists, activeWatchlistName],
  );

  const addGlobalSearchResultToActiveWatchlist = useCallback(async (row) => {
    if (!row?.symbol || row.type !== 'stock') return;
    const sym = String(row.symbol || '').trim().toUpperCase();
    const nm = activeWatchlistName?.trim();
    if (!nm) {
      alert('Select a watchlist first.');
      return;
    }
    if (activeWatchlistForSearch && watchlistContainsSymbol(activeWatchlistForSearch, sym, 'stock')) {
      setToastMessage(`${sym} is already in "${nm}".`);
      return;
    }
    const r = await addItemsToNamedWatchlist([{ symbol: sym, type: 'stock' }], nm);
    if (r.ok) {
      setToastMessage(`Added ${sym} to "${nm}".`);
    } else {
      alert(r.error || 'Failed to add symbol to watchlist.');
    }
  }, [activeWatchlistName, activeWatchlistForSearch, addItemsToNamedWatchlist]);

  useEffect(() => {
    function isTypingTarget(el) {
      if (!el) return false;
      const tag = (el.tagName || '').toLowerCase();
      return tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable;
    }
    function onKeydown(e) {
      const consume = () => {
        e.preventDefault();
        e.stopPropagation();
        if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
      };
      if (e.defaultPrevented) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const key = e.key || '';

      if (knowledgeBaseOpen) return;

      if (globalSearchOpen) {
        if (key === 'Escape') {
          consume();
          setGlobalSearchOpen(false);
          setGlobalSearchQuery('');
          setGlobalSearchResults([]);
          setGlobalSearchActiveIndex(0);
          return;
        }
        if (key === 'Backspace') {
          consume();
          setGlobalSearchQuery(prev => prev.slice(0, -1));
          return;
        }
        if (key === 'ArrowDown' && globalSearchResults.length) {
          consume();
          setGlobalSearchActiveIndex(prev => Math.min(prev + 1, globalSearchResults.length - 1));
          return;
        }
        if (key === 'ArrowUp' && globalSearchResults.length) {
          consume();
          setGlobalSearchActiveIndex(prev => Math.max(prev - 1, 0));
          return;
        }
        if (key === 'Enter') {
          if (!globalSearchResults.length) return;
          consume();
          const row = globalSearchResults[Math.max(0, Math.min(globalSearchActiveIndex, globalSearchResults.length - 1))];
          applyGlobalSearchPick(row);
          return;
        }
        if (key.length === 1 && !/\s/.test(key)) {
          consume();
          setGlobalSearchQuery(prev => `${prev}${key}`.toUpperCase());
          globalSearchInputRef.current?.focus();
        }
        return;
      }

      if (!canOpenGlobalSearch) return;
      if (isTypingTarget(e.target)) return;
      if (key === 'Escape') return;
      if (key.length === 1 && !/\s/.test(key)) {
        consume();
        setGlobalSearchOpen(true);
        setGlobalSearchQuery(key.toUpperCase());
      }
    }
    window.addEventListener('keydown', onKeydown, true);
    return () => window.removeEventListener('keydown', onKeydown, true);
  }, [applyGlobalSearchPick, canOpenGlobalSearch, globalSearchActiveIndex, globalSearchOpen, globalSearchResults, knowledgeBaseOpen]);

  return (
    <div style={{
      display:         'flex',
      flexDirection:   'column',
      height:          '100vh',
      width:           '100vw',
      backgroundColor: 'var(--bg-primary)',
      overflow:        'hidden',
    }}>
      <div className="cim-app-body" style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
          <TabBar
            view={view}
            chartTabs={chartTabs}
            activeTabIdx={activeTabIdx}
            indexTabs={indexTabs}
            activeIndexTab={activeIndexTab}
            constituentsTabs={constituentsTabs}
            onDashboard={goToDashboard}
            onIndices={goToIndices}
            onWatchlist={goToWatchlist}
            onPortfolio={goToPortfolio}
            onPotentialSwings={goToPotentialSwings}
            onMarketPulse={goToMarketPulse}
            onMarketMovers={goToMarketMovers}
            onMarketMap={goToMarketMap}
            onEarningsBeats={goToEarningsBeats}
            onSwitchChart={switchChart}
            onCloseChart={closeChart}
            onSwitchIndex={sym => { setActiveIndexTab(sym); setView('index_' + sym); }}
            onCloseIndex={closeIndexTab}
            onSwitchConstituents={sym => setView('constituents_' + sym)}
            onCloseConstituents={closeConstituentsTab}
            onReorderChartTabs={reorderChartTabs}
            onOpenSectors={() => { setAdminOpen(true); setSettingsOpen(false); }}
            onOpenSettings={() => setSettingsOpen(v => !v)}
            onOpenKnowledgeBaseEditor={!isDistributionProfile ? () => {
              setSettingsOpen(false);
              setKnowledgeBaseEditorOpen(true);
            } : undefined}
            onOpenIssue={() => openFeedback('issue')}
            onOpenFeature={() => openFeedback('feature')}
            onOpenSupport={openSupport}
            onOpenAbout={openAbout}
            aggressiveCacheRam={aggressiveCacheRam}
            cacheBusy={cacheBusy}
            onToggleAggressiveCache={handleToggleAggressiveCache}
            onClearCacheNow={handleClearCacheNow}
            onUpdatePriceVolume={handleUpdatePriceVolume}
            onUpdateIndicatorSnapshots={handleUpdateIndicatorSnapshots}
            onUpdateSplitAdjustments={handleStockSplitAdjustments}
            onSplitCatchupScan={handleSplitCatchupScan}
            splitPendingCount={splitPendingCount}
            onRefreshShareCounts={handleRefreshShareCounts}
            onRefreshEarningsPlusCache={() => handleRefreshEarningsPlusCache()}
            onToggleUpdateProgress={() => setUpdatePanelOpen(true)}
            updateRunning={updateRunning}
            updatePercent={updatePercent}
            settingsOpen={settingsOpen}
            settingsRef={settingsRef}
            rebuildSnapshotsBusy={rebuildSnapshotsBusy}
            onRebuildIndicatorSnapshots={onRebuildIndicatorSnapshots}
            earningsPlusRefreshRunning={earningsPlusRefreshPending || (updateRunning && jobStatus?.job === 'earnings_plus_cache')}
            desktopCanRestartBackend={desktopCanRestartBackend}
            restartBackendBusy={restartBackendBusy}
            desktopCanReloadFrontend={desktopCanReloadFrontend}
            reloadFrontendBusy={reloadFrontendBusy}
            onRestartBackendAndFrontendDev={handleRestartBackendAndFrontendDev}
            onApplyCiMUpdate={handleApplyCiMUpdate}
            cimUpdateBusy={cimUpdateBusy}
            appVersion={appVersion}
            productName={productName}
            onRefresh={handleGlobalRefresh}
            knowledgeBaseOpen={knowledgeBaseOpen}
          />

          <div
            ref={mainColumnRef}
            style={{ flex: 1, position: 'relative', overflow: 'hidden', minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}
          >

        {/* Market Pulse */}
        <div style={{ display: view === 'market-pulse' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <MarketPulsePage />
        </div>

        {/* Market Movers */}
        <div style={{ display: view === 'market-movers' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <MoversPage
            onOpenChart={openChart}
            isActive={view === 'market-movers'}
            onContextMenuRequest={handleContextMenuRequest}
          />
        </div>

        {/* Market Map — index breadth + constituent heatmap */}
        <div style={{ display: view === 'market-map' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <MarketMapPage
            onOpenChart={openChart}
            isActive={view === 'market-map'}
          />
        </div>

        {/* Earnings beats (TradingView screener) */}
        <div style={{ display: view === 'earnings-beats' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <EarningsBeatsPage
            onOpenChart={openChart}
            isActive={view === 'earnings-beats'}
            onContextMenuRequest={handleContextMenuRequest}
            onRefreshEarningsPlusCache={handleRefreshEarningsPlusCache}
            earningsPlusRefreshRunning={earningsPlusRefreshPending || (updateRunning && jobStatus?.job === 'earnings_plus_cache')}
          />
        </div>

        {/* Dashboard */}
        <div style={{ display: view === 'dashboard' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <DashboardPage
            pageMode="pulse"
            onOpenChart={openChart}
            watchlists={watchlists}
            onGoToWatchlist={goToWatchlist}
            onAddStocksToWatchlist={handleDashboardAddToWatchlist}
            onContextMenuRequest={handleContextMenuRequest}
          />
        </div>
        <div style={{ display: view === 'portfolio' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <DashboardPage
            pageMode="portfolio"
            onOpenChart={openChart}
            watchlists={watchlists}
            onGoToWatchlist={goToWatchlist}
            onAddStocksToWatchlist={handleDashboardAddToWatchlist}
            onContextMenuRequest={handleContextMenuRequest}
          />
        </div>
        <div style={{ display: view === 'potential-swings' && !isDistributionProfile ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          {!isDistributionProfile && (
          <PotentialSwingsPage
            onOpenChart={openChart}
            watchlists={watchlists}
            onGoToWatchlist={goToWatchlist}
            onAddStocksToWatchlist={handleDashboardAddToWatchlist}
          />
          )}
        </div>
        <div style={{ display: view === 'watchlist' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <WatchlistPage
            onOpenChart={openChart}
            onOpenConstituents={openConstituents}
            watchlists={watchlists}
            onWatchlistsChange={loadWatchlists}
            appActiveWatchlistName={activeWatchlistName}
            onAppActiveWatchlistNameChange={setActiveWatchlistName}
            appSelectedItem={watchlistSelectedItem}
            onAppSelectedItemChange={setWatchlistSelectedItem}
            onContextMenuRequest={handleContextMenuRequest}
          />
        </div>


        {/* Market Indices list */}
        <div style={{ display: view === 'indices' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <IndicesPage
            onOpenConstituents={openConstituents}
            onContextMenuRequest={handleContextMenuRequest}
          />
        </div>

        {/* Index chart tabs */}
        {indexTabs.map(idx => (
          <div key={idx.symbol} style={{ display: view === 'index_' + idx.symbol ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
            <IndexChartPage
              index={idx}
              onOpenChart={openChart}
              onOpenConstituents={openConstituents}
              onBack={goToIndices}
            />
          </div>
        ))}

        {/* Constituents tabs */}
        {constituentsTabs.map(idx => (
          <div key={idx.symbol} style={{ display: view === 'constituents_' + idx.symbol ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
            <ConstituentsPage
              index={idx}
              onOpenChart={openChart}
              onContextMenuRequest={handleContextMenuRequest}
              onBack={() => {
                const indexTab = indexTabs.find(t => t.symbol === idx.symbol);
                if (indexTab) setView('index_' + idx.symbol);
                else setView('indices');
              }}
            />
          </div>
        ))}

        {/* Chart tabs */}
        {chartTabs.map((tab, idx) => (
          <div key={tab.id} style={{ display: (view === 'chart' && idx === activeTabIdx) ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
            <SplitChartPage
              symbol={tab.symbol}
              onOpenChart={openChart}
              onActiveSymbolChange={(sym) => {
                setChartTabs(prev => prev.map((t, i) => i === activeTabIdx ? { ...t, symbol: sym } : t));
              }}
            />
          </div>
        ))}
          </div>
        </div>

        <CiMKnowledgeBase
          mainColumnRef={mainColumnRef}
          open={knowledgeBaseOpen}
          onOpenChange={setKnowledgeBaseOpen}
          view={view}
          contentRevision={knowledgeBaseContentRevision}
          previewContent={knowledgeBasePreview}
        />
      </div>

      {(updateRunning || updatePendingStart || updatePanelOpen) && (
        <div style={{
          position: 'fixed',
          top: 'calc(var(--tabbar-height) + 8px)',
          right: 'calc(var(--cim-kb-chrome-width, 16px) + 12px)',
          zIndex: 12000,
          width: 360,
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          boxShadow: '0 10px 28px rgba(0,0,0,0.55)',
          padding: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
              {(updateRunning || updatePendingStart) ? 'Update in progress' : 'Last update status'}
            </div>
            {!(updateRunning || updatePendingStart) && (
              <button onClick={() => setUpdatePanelOpen(false)} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 16, lineHeight: 1 }}>×</button>
            )}
          </div>
          <div style={{ fontSize: 11, color: jobStatus?.error ? 'var(--accent-red)' : 'var(--text-secondary)', marginBottom: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.35, minHeight: '2.7em' }}>
            {jobStatus?.error
              ? jobStatus.error
              : (jobStatus?.message || ((updateRunning || updatePendingStart) ? 'Starting update job…' : 'No active update job.'))}
          </div>
          {(splitPendingCount > 0 || (jobStatus?.job === 'split_adjustments' && (updateRunning || updatePendingStart))) && (
            <div style={{ marginBottom: 8, border: '1px solid var(--border-light)', borderRadius: 6, backgroundColor: 'var(--bg-tertiary)', padding: '8px 10px' }}>
              {jobStatus?.job === 'split_adjustments' && (updateRunning || updatePendingStart) && (
                <>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
                    {splitScanLine || `Split apply ${panelProgress}/${panelTotal || '…'}`}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
                    {`Pending / applying: ${splitDetectedCount}`}
                  </div>
                </>
              )}
              {!(updateRunning || updatePendingStart) && splitPendingCount > 0 && (
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
                  {`Splits pending adjustment: ${splitPendingCount}`}
                </div>
              )}
              <div
                style={{
                  maxHeight: (splitDetectedSymbols.length > 6 || splitPendingList.length > 6) ? 114 : undefined,
                  overflowY: (splitDetectedSymbols.length > 6 || splitPendingList.length > 6) ? 'auto' : 'visible',
                  borderTop: '1px solid var(--border-light)',
                  paddingTop: 6,
                }}
              >
                {(updateRunning || updatePendingStart) && splitDetectedSymbols.length > 0
                  ? splitDetectedSymbols.slice(0, 200).map((sym, idx) => (
                    <div key={`run-${sym}-${idx}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)', lineHeight: 1.35 }}>
                      {sym}
                    </div>
                  ))
                  : splitPendingList.slice(0, 50).map((row, idx) => (
                    <div key={`pend-${row.symbol}-${idx}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)', lineHeight: 1.35 }}>
                      {`${row.symbol} ${row.split_date} (${Number(row.ratio).toFixed(2)}:1)`}
                    </div>
                  ))}
                {splitPendingCount === 0 && splitDetectedSymbols.length === 0 && (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>No split symbols pending.</div>
                )}
              </div>
            </div>
          )}
          <div style={{ height: 6, backgroundColor: 'var(--bg-active)', borderRadius: 3, overflow: 'hidden', marginBottom: 6 }}>
            <div style={{ height: '100%', width: `${panelHasProgress ? panelPercent : ((updateRunning || updatePendingStart) ? 6 : 0)}%`, backgroundColor: 'var(--accent-blue)', borderRadius: 3, transition: 'width 0.25s ease' }} />
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right' }}>
            {panelHasProgress
              ? `${panelProgress} / ${panelTotal} (${panelPercent}%)`
              : ((updateRunning || updatePendingStart) ? 'Starting job…' : 'No active job')}
          </div>
        </div>
      )}

      {adminOpen && <AdminPanel onClose={() => setAdminOpen(false)} defaultTab="sectors" hideJobsTab={true} />}
      {knowledgeBaseEditorOpen && !isDistributionProfile && (
        <KnowledgeBaseEditor
          onClose={() => {
            setKnowledgeBaseEditorOpen(false);
            setKnowledgeBasePreview(null);
          }}
          initialGuideId={resolveKnowledgeBaseGuideId(view)}
          onSaved={handleKnowledgeBaseSaved}
          onPreview={handleKnowledgeBasePreview}
        />
      )}
      {contextMenuState.visible && (
        <div
          ref={contextMenuRef}
          onClick={e => e.stopPropagation()}
          style={{
            position: 'fixed',
            left: contextMenuPos.left,
            top: contextMenuPos.top,
            zIndex: 12000,
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            minWidth: 220,
            maxWidth: 'min(94vw, 360px)',
            maxHeight: 'min(72vh, 520px)',
            overflowX: 'hidden',
            overflowY: 'auto',
            transformOrigin: `${contextMenuPos.flipX ? 'right' : 'left'} ${contextMenuPos.flipY ? 'bottom' : 'top'}`,
          }}
        >
          <div style={{ padding: '8px 10px', fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            {contextMenuState.symbol}
          </div>
          <div
            onClick={() => {
              addToPortfolio(contextMenuState.symbol, contextMenuState.type);
              setContextMenuState(s => ({ ...s, visible: false }));
            }}
            style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--accent-green)', borderBottom: '1px solid var(--border)' }}
            onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
            onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
          >
            Add to portfolio
          </div>
          {(contextMenuState.sourcePage === 'portfolio'
            || contextMenuState.sourcePage === 'constituents') && (
              <div
                onClick={() => {
                  removeFromPortfolio(contextMenuState.symbol, contextMenuState.type);
                  setContextMenuState(s => ({ ...s, visible: false }));
                }}
                style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--accent-red)', borderBottom: '1px solid var(--border)' }}
                onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                Delete from portfolio
              </div>
            )}
          {contextMenuState.sourcePage === 'watchlist' && contextMenuState.watchlistName && (
            <div
              onClick={() => {
                removeFromWatchlist(
                  contextMenuState.watchlistName,
                  contextMenuState.symbol,
                  contextMenuState.type,
                );
                setContextMenuState(s => ({ ...s, visible: false }));
              }}
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--accent-red)', borderBottom: '1px solid var(--border)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Delete from watchlist
            </div>
          )}
          {contextMenuState.sourcePage === 'constituents'
            && watchlists.filter(w => watchlistContainsSymbol(w, contextMenuState.symbol, contextMenuState.type)).map(w => (
              <div
                key={`rm-${w.name}`}
                onClick={() => {
                  removeFromWatchlist(w.name, contextMenuState.symbol, contextMenuState.type);
                  setContextMenuState(s => ({ ...s, visible: false }));
                }}
                style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--accent-red)', borderBottom: '1px solid var(--border)' }}
                onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                {`Delete from "${w.name}"`}
              </div>
            ))}
          <div style={{ height: 1, backgroundColor: 'var(--border)' }} />
          <div style={{ padding: '6px 10px 2px', fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Add to watchlist
          </div>
          {watchlists.map(w => (
            <div
              key={w.name}
              onClick={async () => {
                const r = await addItemsToNamedWatchlist([{ symbol: contextMenuState.symbol, type: contextMenuState.type }], w.name);
                if (r.ok) {
                  setToastMessage(`Added ${contextMenuState.symbol} to "${w.name}".`);
                  setContextMenuState(s => ({ ...s, visible: false }));
                } else {
                  alert(r.error || 'Failed to add to watchlist.');
                }
              }}
              style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              {w.name}
            </div>
          ))}
          <div style={{ height: 1, backgroundColor: 'var(--border)' }} />
          {!contextMenuState.createMode ? (
            <div
              onClick={() => setContextMenuState(s => ({ ...s, createMode: true }))}
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--accent-blue)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Create New Watchlist
            </div>
          ) : (
            <div style={{ padding: 10, display: 'flex', gap: 6, alignItems: 'center' }}>
              <input
                autoFocus
                value={contextMenuState.newWatchlistName}
                placeholder="Watchlist name..."
                onChange={(e) => setContextMenuState(s => ({ ...s, newWatchlistName: e.target.value }))}
                onKeyDown={async (e) => {
                  if (e.key === 'Escape') setContextMenuState(s => ({ ...s, createMode: false, newWatchlistName: '' }));
                  if (e.key !== 'Enter') return;
                  const targetName = contextMenuState.newWatchlistName.trim();
                  if (!targetName) return;
                  try {
                    if (!watchlists.some(w => w.name.toLowerCase() === targetName.toLowerCase())) {
                      await axios.post(`${API}/api/watchlists`, { name: targetName });
                    }
                    const r = await addItemsToNamedWatchlist([{ symbol: contextMenuState.symbol, type: contextMenuState.type }], targetName);
                    if (r.ok) {
                      setToastMessage(`Added ${contextMenuState.symbol} to "${targetName}".`);
                      setContextMenuState(s => ({ ...s, visible: false, createMode: false, newWatchlistName: '' }));
                    } else {
                      alert(r.error || 'Failed to add to watchlist.');
                    }
                  } catch (err) {
                    alert('Failed to create watchlist: ' + (err.response?.data?.detail || err.message));
                  }
                }}
                style={{ flex: 1, height: 28, background: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: 4, padding: '0 8px' }}
              />
              <button
                onClick={async () => {
                  const targetName = contextMenuState.newWatchlistName.trim();
                  if (!targetName) return;
                  try {
                    if (!watchlists.some(w => w.name.toLowerCase() === targetName.toLowerCase())) {
                      await axios.post(`${API}/api/watchlists`, { name: targetName });
                    }
                    const r = await addItemsToNamedWatchlist([{ symbol: contextMenuState.symbol, type: contextMenuState.type }], targetName);
                    if (r.ok) {
                      setToastMessage(`Added ${contextMenuState.symbol} to "${targetName}".`);
                      setContextMenuState(s => ({ ...s, visible: false, createMode: false, newWatchlistName: '' }));
                    } else {
                      alert(r.error || 'Failed to add to watchlist.');
                    }
                  } catch (err) {
                    alert('Failed to create watchlist: ' + (err.response?.data?.detail || err.message));
                  }
                }}
                style={{ height: 28, padding: '0 10px', borderRadius: 4, border: '1px solid var(--accent-blue)', background: 'transparent', color: 'var(--accent-blue)', cursor: 'pointer' }}
              >
                Add
              </button>
            </div>
          )}
        </div>
      )}
      {aboutOpen && (
        <div
          style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.62)', zIndex: 16000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={(e) => { if (e.target === e.currentTarget) setAboutOpen(false); }}
        >
          <div
            style={{
              width: 'min(480px, 94vw)',
              maxHeight: 'min(85vh, 640px)',
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              boxShadow: '0 20px 48px rgba(0,0,0,0.6)',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>About Charts In Motion</div>
              <button type="button" onClick={() => setAboutOpen(false)} aria-label="Close" style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ padding: 16, overflowY: 'auto' }}>
              <AboutCiMModalBody />
            </div>
          </div>
        </div>
      )}
      {supportOpen && (
        <div
          style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.62)', zIndex: 16000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={(e) => { if (e.target === e.currentTarget) setSupportOpen(false); }}
        >
          <div
            style={{
              maxWidth: 'min(420px, 94vw)',
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              boxShadow: '0 20px 48px rgba(0,0,0,0.6)',
              overflow: 'hidden',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Support the Development</div>
              <button type="button" onClick={() => setSupportOpen(false)} aria-label="Close" style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ padding: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
              <SupportQrModalBody open={supportOpen} />
            </div>
          </div>
        </div>
      )}
      {feedbackOpen && (
        <div
          style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.62)', zIndex: 16000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={(e) => { if (e.target === e.currentTarget) setFeedbackOpen(false); }}
        >
          <div style={{ width: 560, maxWidth: '94vw', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8, boxShadow: '0 20px 48px rgba(0,0,0,0.6)' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                {feedbackType === 'issue' ? 'Report Issue' : 'Feature Request'}
              </div>
              <button onClick={() => setFeedbackOpen(false)} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <textarea
                value={feedbackMessage}
                onChange={(e) => setFeedbackMessage(e.target.value)}
                placeholder={feedbackType === 'issue' ? 'Describe the issue and steps to reproduce...' : 'Describe the feature and why it helps...'}
                rows={12}
                style={{ resize: 'vertical', borderRadius: 4, border: '1px solid var(--border)', backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', padding: '8px 10px' }}
              />
            </div>
            <div style={{ padding: '10px 16px 14px', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button onClick={() => setFeedbackOpen(false)} style={{ height: 32, padding: '0 12px', borderRadius: 4, border: '1px solid var(--border)', backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>Cancel</button>
              <button onClick={submitFeedback} disabled={feedbackSending} style={{ height: 32, padding: '0 14px', borderRadius: 4, border: 'none', backgroundColor: '#238636', color: '#fff', opacity: feedbackSending ? 0.7 : 1 }}>
                {feedbackSending ? 'Sending...' : 'Send'}
              </button>
            </div>
          </div>
        </div>
      )}
      {globalSearchOpen && (
        <div
          style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.45)', zIndex: 17000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: 90 }}
          onClick={(e) => {
            if (e.target !== e.currentTarget) return;
            setGlobalSearchOpen(false);
            setGlobalSearchQuery('');
            setGlobalSearchResults([]);
            setGlobalSearchActiveIndex(0);
          }}
        >
          <div style={{ width: 700, maxWidth: '92vw', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8, boxShadow: '0 24px 56px rgba(0,0,0,0.65)', overflow: 'hidden' }}>
            <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10, backgroundColor: 'var(--bg-tertiary)' }}>
              <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>⌕</span>
              <input
                ref={globalSearchInputRef}
                value={globalSearchQuery}
                onChange={e => setGlobalSearchQuery(e.target.value.toUpperCase())}
                placeholder="Type symbol or index name…"
                style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)' }}
              />
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>↑↓ select · Enter confirm · Esc close</span>
            </div>
            <div style={{ maxHeight: 'min(56vh, 430px)', overflowY: 'auto' }}>
              {!globalSearchResults.length ? (
                <div style={{ padding: '14px 16px', fontSize: 12, color: 'var(--text-muted)' }}>
                  {globalSearchQuery.trim() ? 'No matches found.' : 'Start typing to search.'}
                </div>
              ) : globalSearchResults.map((row, idx) => {
                const active = idx === globalSearchActiveIndex;
                const showWlAdd = view === 'watchlist' && row.type === 'stock';
                const alreadyInWl = showWlAdd && activeWatchlistForSearch
                  ? watchlistContainsSymbol(activeWatchlistForSearch, row.symbol, 'stock')
                  : false;
                const canWlAdd = showWlAdd && !!activeWatchlistName?.trim() && !alreadyInWl;
                return (
                  <div
                    key={`${row.type}:${row.symbol}:${idx}`}
                    onMouseEnter={() => setGlobalSearchActiveIndex(idx)}
                    onClick={() => applyGlobalSearchPick(row)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 10,
                      padding: '9px 14px',
                      cursor: 'pointer',
                      backgroundColor: active ? 'rgba(56,139,253,0.14)' : 'transparent',
                      borderBottom: '1px solid var(--border-light)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                      <span style={{ fontSize: 10, color: row.type === 'index' ? 'var(--accent-blue)' : 'var(--text-muted)', border: '1px solid var(--border)', borderRadius: 4, padding: '1px 6px', flexShrink: 0 }}>
                        {row.type === 'index' ? 'INDEX' : 'STOCK'}
                      </span>
                      <span style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 700, flexShrink: 0 }}>{row.symbol}</span>
                      {row.type === 'index' ? <span style={{ fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.label}</span> : null}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                      {showWlAdd ? (
                        <button
                          type="button"
                          disabled={!canWlAdd}
                          title={
                            alreadyInWl
                              ? 'Already in active watchlist'
                              : !activeWatchlistName?.trim()
                                ? 'Select a watchlist first'
                                : `Add ${row.symbol} to ${activeWatchlistName}`
                          }
                          onClick={e => {
                            e.stopPropagation();
                            if (!canWlAdd) return;
                            addGlobalSearchResultToActiveWatchlist(row);
                          }}
                          style={{
                            height: 24,
                            padding: '0 10px',
                            borderRadius: 4,
                            fontSize: 11,
                            fontWeight: 600,
                            border: `1px solid ${canWlAdd ? 'var(--accent-blue)' : 'var(--border)'}`,
                            backgroundColor: canWlAdd ? 'rgba(56,139,253,0.15)' : 'var(--bg-tertiary)',
                            color: canWlAdd ? 'var(--accent-blue)' : 'var(--text-muted)',
                            cursor: canWlAdd ? 'pointer' : 'not-allowed',
                            opacity: canWlAdd ? 1 : 0.85,
                          }}
                        >
                          {alreadyInWl ? 'In watchlist' : 'Add to watchlist'}
                        </button>
                      ) : null}
                      <span style={{ fontSize: 10, color: 'var(--text-muted)', width: 36, textAlign: 'right' }}>{active ? 'Enter' : ''}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
      {toastMessage && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: 'fixed',
            bottom: 24,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 200020,
            maxWidth: 'min(90vw, 440px)',
            padding: '10px 18px',
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--accent-green)',
            borderRadius: 8,
            boxShadow: '0 8px 32px rgba(0,0,0,0.45)',
            color: 'var(--text-primary)',
            fontSize: 13,
            textAlign: 'center',
          }}
        >
          {toastMessage}
        </div>
      )}
      {rebuildSnapshotsBusy && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 250000,
            backgroundColor: 'rgba(0,0,0,0.72)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'wait',
          }}
        >
          <div
            style={{
              width: 520,
              maxWidth: '92vw',
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 10,
              boxShadow: '0 20px 48px rgba(0,0,0,0.6)',
              padding: 20,
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
              Rebuild Indicator Snapshots
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Please wait while the full snapshot universe is rebuilt. The app is locked until this completes.
            </div>
            <div style={{ height: 10, borderRadius: 999, backgroundColor: 'var(--bg-tertiary)', overflow: 'hidden', border: '1px solid var(--border)' }}>
              <div
                style={{
                  height: '100%',
                  width: `${Math.max(0, Math.min(100, rebuildSnapshotsPercent))}%`,
                  background: 'linear-gradient(90deg, #1f6feb, #3fb950)',
                  transition: 'width 0.25s ease',
                }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12 }}>
              <span style={{ color: 'var(--text-secondary)' }}>{rebuildSnapshotsMessage || 'Processing...'}</span>
              <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                {Math.round(rebuildSnapshotsPercent)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TabBar({
  view, chartTabs, activeTabIdx, indexTabs, activeIndexTab,
  constituentsTabs, onDashboard, onIndices, onWatchlist, onPortfolio, onPotentialSwings, onMarketPulse, onMarketMovers, onMarketMap, onEarningsBeats, onSwitchChart, onCloseChart,
  onSwitchIndex, onCloseIndex, onSwitchConstituents, onCloseConstituents,
  onReorderChartTabs, onOpenSectors, onOpenSettings, onOpenKnowledgeBaseEditor, onOpenIssue, onOpenFeature, onOpenAbout, onOpenSupport,
  aggressiveCacheRam, cacheBusy, onToggleAggressiveCache, onClearCacheNow,
  onUpdatePriceVolume, onUpdateIndicatorSnapshots, onUpdateSplitAdjustments, onSplitCatchupScan, splitPendingCount, onRefreshShareCounts, onRefreshEarningsPlusCache, onToggleUpdateProgress, updateRunning, updatePercent, settingsOpen, settingsRef,
  rebuildSnapshotsBusy, onRebuildIndicatorSnapshots,
  earningsPlusRefreshRunning,
  desktopCanRestartBackend, restartBackendBusy,
  desktopCanReloadFrontend, reloadFrontendBusy, onRestartBackendAndFrontendDev,
  onApplyCiMUpdate, cimUpdateBusy, appVersion, productName,
  onRefresh,
  knowledgeBaseOpen,
}) {
  const dragIdx     = useRef(null);
  const dragType    = useRef(null);
  const updateBtnRef = useRef(null);
  const updateMenuRef = useRef(null);
  const [updateMenuRect, setUpdateMenuRect] = useState(null);

  useEffect(() => {
    if (knowledgeBaseOpen) setUpdateMenuRect(null);
  }, [knowledgeBaseOpen]);

  function onDragStart(e, type, idx) {
    dragIdx.current  = idx;
    dragType.current = type;
    e.dataTransfer.effectAllowed = 'move';
  }

  function onDrop(e, type, idx) {
    e.preventDefault();
    if (dragType.current === 'chart' && type === 'chart' && dragIdx.current !== idx) {
      onReorderChartTabs(dragIdx.current, idx);
    }
    dragIdx.current  = null;
    dragType.current = null;
  }

  function Tab({ label, isActive, onClose, onClick, draggable, onDragStart, onDrop, mono }) {
    return (
      <div
        draggable={draggable}
        onDragStart={onDragStart}
        onDragOver={e => e.preventDefault()}
        onDrop={onDrop}
        onClick={onClick}
        style={{
          display:         'flex',
          alignItems:      'center',
          justifyContent:  'space-between',
          minWidth:        120,
          maxWidth:        160,
          padding:         '0 10px 0 12px',
          cursor:          draggable ? 'grab' : 'pointer',
          borderRight:     '1px solid var(--border)',
          backgroundColor: isActive ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom:    isActive ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color:           isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          flexShrink:      0,
          userSelect:      'none',
          height:          '100%',
        }}
      >
        <span style={{
          fontFamily:   mono ? 'var(--font-mono)' : 'inherit',
          fontSize:     11,
          fontWeight:   isActive ? 600 : 400,
          overflow:     'hidden',
          textOverflow: 'ellipsis',
          whiteSpace:   'nowrap',
          flex:         1,
        }}>
          {label}
        </span>
        {onClose && (
          <button
            onClick={e => { e.stopPropagation(); onClose(); }}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16, flexShrink: 0, background: 'none', color: 'var(--text-muted)', fontSize: 14, marginLeft: 4 }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
          >×</button>
        )}
      </div>
    );
  }

  useLayoutEffect(() => {
    if (!updateMenuRect) return;
    const btn = updateBtnRef.current;
    if (!btn) return;
    const update = () => {
      const r = btn.getBoundingClientRect();
      const width = 280;
      const pad = 8;
      const maxLeft = Math.max(pad, window.innerWidth - width - pad);
      const left = Math.min(Math.max(pad, r.right - width), maxLeft);
      const top = r.bottom + 4;
      setUpdateMenuRect(prev => {
        if (!prev) return { top, left, width };
        if (prev.top === top && prev.left === left && prev.width === width) return prev;
        return { top, left, width };
      });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [!!updateMenuRect]);

  useEffect(() => {
    if (!updateMenuRect) return;
    function onDocMouseDown(e) {
      const btn = updateBtnRef.current;
      const insideBtn = !!btn && btn.contains(e.target);
      const menu = updateMenuRef.current;
      const insideMenu = !!menu && menu.contains(e.target);
      if (insideBtn || insideMenu) return;
      setUpdateMenuRect(null);
    }
    function onEsc(e) {
      if (e.key === 'Escape') setUpdateMenuRect(null);
    }
    document.addEventListener('mousedown', onDocMouseDown);
    window.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      window.removeEventListener('keydown', onEsc);
    };
  }, [updateMenuRect]);

  return (
    <div className="chart-app-toolbar" style={{
      height:          'var(--tabbar-height)',
      minHeight:       'var(--tabbar-height)',
      backgroundColor: 'var(--bg-secondary)',
      borderBottom:    '1px solid var(--border)',
      display:         'flex',
      alignItems:      'stretch',
      flexShrink:      0,
      overflowY:       'visible',
      position:        'relative',
    }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '0 14px',
          borderRight: '1px solid var(--border)',
          flexShrink: 0,
          userSelect: 'none',
          gap: 6,
        }}
        title={appVersion ? `${productName} ${appVersion}` : productName}
      >
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.02em' }}>
          {productName}
        </span>
        {appVersion ? (
          <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {appVersion}
          </span>
        ) : null}
      </div>
      <div style={{ flex: 1, overflowX: 'auto', overflowY: 'hidden', display: 'flex', alignItems: 'stretch' }}>
        {/* Fixed nav tabs — order: NSE | Indices | Market Map | Market Pulse | Market Movers | Earnings | Watchlist | Portfolio | Potential Swings */}
        <div onClick={onDashboard} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 7, padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'dashboard' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'dashboard' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'dashboard' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'dashboard' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 18, height: 18, backgroundColor: 'var(--accent-blue)',
            borderRadius: 4, fontSize: 10, fontWeight: 800, color: '#fff', flexShrink: 0,
          }}>N</span>
          NSE
        </div>
        <div onClick={onIndices} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'indices' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'indices' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'indices' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'indices' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          Indices
        </div>
        <div onClick={onMarketMap} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'market-map' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'market-map' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'market-map' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'market-map' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          Market Map
        </div>
        <div onClick={onMarketPulse} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'market-pulse' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'market-pulse' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'market-pulse' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'market-pulse' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          Market Pulse
        </div>
        <div onClick={onMarketMovers} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'market-movers' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'market-movers' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'market-movers' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'market-movers' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          Market Movers
        </div>
        <div onClick={onEarningsBeats} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'earnings-beats' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'earnings-beats' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'earnings-beats' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'earnings-beats' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          Earnings
        </div>
        <div onClick={onWatchlist} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'watchlist' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'watchlist' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'watchlist' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'watchlist' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          Watchlist
        </div>
        <div onClick={onPortfolio} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'portfolio' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'portfolio' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'portfolio' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'portfolio' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          Portfolio
        </div>
        {!isDistributionProfile && (
        <div onClick={onPotentialSwings} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'potential-swings' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'potential-swings' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'potential-swings' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'potential-swings' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          Potential Swings
        </div>
        )}
        {indexTabs.map((idx, i) => (
          <Tab key={idx.symbol} label={idx.name} isActive={view === 'index_' + idx.symbol}
            onClick={() => onSwitchIndex(idx.symbol)} onClose={() => onCloseIndex(idx.symbol)}
            draggable={true} onDragStart={e => onDragStart(e, 'index', i)} onDrop={e => onDrop(e, 'index', i)} />
        ))}
        {constituentsTabs.map((idx, i) => (
          <Tab key={'c_' + idx.symbol} label={idx.name + ' — Const.'} isActive={view === 'constituents_' + idx.symbol}
            onClick={() => onSwitchConstituents(idx.symbol)} onClose={() => onCloseConstituents(idx.symbol)}
            draggable={true} onDragStart={e => onDragStart(e, 'constituents', i)} onDrop={e => onDrop(e, 'constituents', i)} />
        ))}
        {chartTabs.map((tab, idx) => (
          <Tab key={tab.id} label={tab.symbol} isActive={view === 'chart' && idx === activeTabIdx}
            onClick={() => onSwitchChart(idx)} onClose={() => onCloseChart(idx)}
            draggable={true} mono={true} onDragStart={e => onDragStart(e, 'chart', idx)} onDrop={e => onDrop(e, 'chart', idx)} />
        ))}
      </div>

      <div style={{ display: 'flex', flexShrink: 0, alignItems: 'stretch', borderLeft: '1px solid var(--border)' }}>
        {onRefresh && (
          <div
            onClick={onRefresh}
            title={
              view === 'market-pulse' ? 'Refresh market indices'
                : view === 'market-movers' ? 'Refresh market movers'
                : view === 'market-map' ? 'Refresh market map'
                : 'Refresh NSE / Portfolio table'
            }
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 12px', height: '100%', cursor: 'pointer', borderRight: '1px solid var(--border)', color: 'var(--text-muted)', fontSize: 12 }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.backgroundColor = 'transparent'; }}
          >↻ Refresh</div>
        )}
        <button
          ref={updateBtnRef}
          onClick={() => {
            if (updateRunning) {
              onToggleUpdateProgress && onToggleUpdateProgress();
              return;
            }
            const btn = updateBtnRef.current;
            if (!btn) return;
            const r = btn.getBoundingClientRect();
            setUpdateMenuRect({ top: r.bottom + 4, left: Math.max(8, r.right - 280), width: 280 });
          }}
          title={
            updateRunning
              ? 'A job is running. Open progress panel.'
              : splitPendingCount > 0
                ? `${splitPendingCount} split(s) pending — choose update action`
                : 'Choose update action'
          }
          style={{
            position: 'relative',
            overflow: 'hidden',
            borderRight: '1px solid var(--border)',
            padding: '0 12px',
            color: 'var(--text-primary)',
            fontSize: 12,
            fontWeight: 600,
            background: 'transparent',
            flexShrink: 0,
          }}
        >
          {!updateRunning && splitPendingCount > 0 && (
            <span style={{
              position: 'absolute',
              top: 4,
              right: 4,
              minWidth: 16,
              height: 16,
              borderRadius: 8,
              backgroundColor: 'var(--accent-orange, #d29922)',
              color: '#fff',
              fontSize: 10,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '0 4px',
              zIndex: 2,
            }}>
              {splitPendingCount > 99 ? '99+' : splitPendingCount}
            </span>
          )}
          {updateRunning && (
            <span style={{
              position: 'absolute',
              left: 0,
              top: 0,
              bottom: 0,
              width: `${updatePercent || 0}%`,
              backgroundColor: 'rgba(56,139,253,0.25)',
              transition: 'width 0.3s ease',
            }} />
          )}
          <span style={{ position: 'relative', zIndex: 1 }}>
            {updateRunning ? `Updating ${Math.round(updatePercent || 0)}%` : 'Update'}
          </span>
        </button>
        {!updateRunning && updateMenuRect && (
          <div
            ref={updateMenuRef}
            style={{
              position: 'fixed',
              top: updateMenuRect.top,
              left: updateMenuRect.left,
              width: updateMenuRect.width,
              zIndex: 200000,
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
              overflow: 'hidden',
            }}
          >
            <div style={{ padding: '8px 12px 4px', fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Update options
            </div>
            <div
              onClick={() => { setUpdateMenuRect(null); onUpdatePriceVolume && onUpdatePriceVolume(); }}
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)', borderTop: '1px solid var(--border-light)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Update price and volume data
            </div>
            <div
              onClick={() => { setUpdateMenuRect(null); onUpdateIndicatorSnapshots && onUpdateIndicatorSnapshots(); }}
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)', borderTop: '1px solid var(--border-light)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Update indicator snapshots (incremental)
            </div>
            <div
              onClick={() => { setUpdateMenuRect(null); onUpdateSplitAdjustments && onUpdateSplitAdjustments(); }}
              title="Apply only symbols in the pending split ledger (skips already applied)."
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)', borderTop: '1px solid var(--border-light)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Apply pending split adjustments
              {splitPendingCount > 0 ? ` (${splitPendingCount})` : ''}
            </div>
            <div
              onClick={() => { setUpdateMenuRect(null); onSplitCatchupScan && onSplitCatchupScan(); }}
              title="Scan last 90 days; marks splits with existing history as applied without re-download."
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)', borderTop: '1px solid var(--border-light)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Catch-up split scan (90 days)
            </div>
            <div
              onClick={() => { setUpdateMenuRect(null); onRefreshShareCounts && onRefreshShareCounts(); }}
              title="NSE issued share count — used for market cap (shares × price). Run weekly or after splits."
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)', borderTop: '1px solid var(--border-light)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Refresh share counts (market cap basis)
            </div>
          </div>
        )}
        <div ref={settingsRef} style={{ position: 'relative', flexShrink: 0 }}>
        <div onClick={onOpenSettings} title="Settings"
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 36, height: '100%', cursor: 'pointer',
            color: aggressiveCacheRam ? '#f85149' : (settingsOpen ? 'var(--text-primary)' : 'var(--text-muted)'), fontSize: 16, flexShrink: 0,
            backgroundColor: settingsOpen ? 'var(--bg-hover)' : 'transparent',
          }}
          onMouseEnter={e => { e.currentTarget.style.color = aggressiveCacheRam ? '#f85149' : 'var(--text-primary)'; e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
          onMouseLeave={e => { if (!settingsOpen) { e.currentTarget.style.color = aggressiveCacheRam ? '#f85149' : 'var(--text-muted)'; e.currentTarget.style.backgroundColor = 'transparent'; } }}
        >⚙</div>
        {settingsOpen && (
          <div style={{
            position: 'absolute',
            right: 0,
            top: 'calc(100% + 4px)',
            minWidth: 230,
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            zIndex: 200000,
            overflow: 'hidden',
          }}>
            <button
              type="button"
              onClick={onToggleAggressiveCache}
              disabled={cacheBusy}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '9px 12px',
                border: 'none',
                borderBottom: '1px solid var(--border-light)',
                backgroundColor: 'transparent',
                color: cacheBusy ? 'var(--text-muted)' : 'var(--text-primary)',
                cursor: cacheBusy ? 'not-allowed' : 'pointer',
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 16, textAlign: 'center' }}>⚡</span>
                Aggressive Cache (RAM)
              </span>
              <span
                style={{
                  width: 30,
                  height: 16,
                  borderRadius: 999,
                  border: '1px solid var(--border)',
                  backgroundColor: aggressiveCacheRam ? '#f85149' : '#707b8a',
                  position: 'relative',
                  flexShrink: 0,
                }}
              >
                <span
                  style={{
                    position: 'absolute',
                    top: 1,
                    left: aggressiveCacheRam ? 15 : 1,
                    width: 12,
                    height: 12,
                    borderRadius: 999,
                    backgroundColor: '#ffffff',
                    transition: 'left 0.15s ease',
                  }}
                />
              </span>
            </button>
            <MenuItem icon="🧹" label="Clear Cache Now" onClick={onClearCacheNow} disabled={cacheBusy} />
            <MenuItem
              icon="✨"
              label={earningsPlusRefreshRunning ? 'Refreshing Earnings+ Cache…' : 'Refresh Earnings+ Cache (This Month)'}
              onClick={onRefreshEarningsPlusCache}
              disabled={cacheBusy || earningsPlusRefreshRunning}
            />
            <MenuItem
              icon="🧱"
              label={rebuildSnapshotsBusy ? "Rebuilding Indicator Snapshots…" : "Rebuild Indicator Snapshots (may take time)"}
              onClick={onRebuildIndicatorSnapshots}
              disabled={cacheBusy || rebuildSnapshotsBusy || updateRunning}
            />
            {desktopCanRestartBackend && desktopCanReloadFrontend && (
              <MenuItem
                icon="🔁"
                label={(restartBackendBusy || reloadFrontendBusy) ? 'Restarting Backend + Frontend (Dev)…' : 'Restart Backend + Frontend (Dev)'}
                onClick={onRestartBackendAndFrontendDev}
                disabled={restartBackendBusy || reloadFrontendBusy || updateRunning}
              />
            )}
            <MenuItem icon="🗂" label="Data Management" onClick={onOpenSectors} />
            {onOpenKnowledgeBaseEditor && (
              <MenuItem icon="📖" label="Edit Knowledge Base" onClick={onOpenKnowledgeBaseEditor} />
            )}
            <MenuItem icon="🐞" label="Report Issue" onClick={onOpenIssue} />
            <MenuItem icon="💡" label="Feature Request" onClick={onOpenFeature} />
            <MenuItem
              icon="⬆"
              label={cimUpdateBusy ? 'Updating App…' : 'Update App'}
              onClick={onApplyCiMUpdate}
              disabled={cacheBusy || cimUpdateBusy || updateRunning}
            />
            <MenuItem icon="❤" label="Support the Development" onClick={onOpenSupport} />
            <MenuItem icon="ℹ" label="About Charts In Motion" onClick={onOpenAbout} />
          </div>
        )}
      </div>
      </div>
    </div>
  );
}

function MenuItem({ icon, label, onClick, disabled = false }) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={{
        width: '100%',
        textAlign: 'left',
        padding: '9px 12px',
        border: 'none',
        borderBottom: '1px solid var(--border-light)',
        backgroundColor: 'transparent',
        color: disabled ? 'var(--text-muted)' : 'var(--text-primary)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        fontSize: 12,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <span style={{ width: 16, textAlign: 'center' }}>{icon}</span>
      {label}
    </button>
  );
}
