import './api/http';
import axios from 'axios';
import React, { useState, useEffect, useCallback, useRef, useLayoutEffect, useMemo, Suspense, lazy } from 'react';
import { createPortal } from 'react-dom';
import DashboardPage  from './pages/DashboardPage';
import ChartPage      from './pages/ChartPage';
import SplitChartPage from './pages/SplitChartPage';
import IndicesPage    from './pages/IndicesPage';
import FundsPage      from './pages/FundsPage';
import MarketPulsePage from './pages/MarketPulsePage';
import MoversPage from './pages/MoversPage';
import IndexChartPage from './pages/IndexChartPage';
import ConstituentsPage from './pages/ConstituentsPage';
import WatchlistPage from './pages/WatchlistPage';
import AdminPanel     from './components/AdminPanel';
import ShowcaseSchedulerModal from './components/ShowcaseSchedulerModal';
import { isDistributionProfile, isDevAccountPreview, DEV_ACCOUNT_PREVIEW } from './config/exportProfile';
import { dispatchAppDataRefresh, CHART_DATA_UPDATED_EVENT, MARKET_PULSE_REFRESH_EVENT, MOVERS_REFRESH_EVENT, MOVERS_LIVE_PREFETCH_EVENT, PNL_REFRESH_EVENT } from './chartEvents';
import useAdminJobStatus from './hooks/useAdminJobStatus';
import { searchUniverse } from './api/client';
import SupportQrModalBody from './components/SupportQrModalBody';
import { prefetchSupportQr } from './utils/supportQrPrefetch';
import AboutCiMModalBody from './components/AboutCiMModalBody';
import CiMKnowledgeBase from './components/CiMKnowledgeBase';
import KnowledgeBaseEditor from './components/KnowledgeBaseEditor';
import { resolveKnowledgeBaseGuideId } from './content/knowledgeBasePages';
import AccountSettingsModal from './components/AccountSettingsModal';
import ServerStatusBar from './components/ServerStatusBar';
import UniversalNotes from './components/UniversalNotes';
import UniversalAlerts from './components/UniversalAlerts';
import { BasketProvider } from './components/Basket';
import LiveFeedPopover from './components/LiveFeedPopover';
import { useServerStatus } from './hooks/useServerStatus';
import { useWheelHorizontalScroll } from './hooks/useWheelHorizontalScroll';
import {
  trimChartTabsToMax,
} from './utils/chartTabFifo';
import {
  activateChartInStack,
  activeChart,
  closeActiveChartInStack,
  closeChartInStack,
  findChartInStacks,
  openChartInStacks,
  setActiveChartSymbol,
} from './utils/chartTabStack';
import ConfirmDialog, { askConfirm } from './components/ConfirmDialog';
import { ToastProvider } from './context/ToastContext';
import { fetchLicenseStatus, licenseHeartbeat } from './api/auth';
import { IntradayPatchProvider } from './intraday/useIntradayPatch';
import { PageLiveProvider } from './intraday/pageLiveContext';
import { refreshEmptyMessage } from './intraday/intradayRefreshScopes';
import {
  resolvePageId,
  getRefreshSymbols,
  pageDisplayName,
  livePageContextFromView,
} from './intraday/intradaySymbolRegistry';
import { ChartPrefsProvider } from './chartPrefs/useChartPrefs';
import {
  captureOperatorFromUrl,
  isLoopbackHost,
  isOperatorSessionActive,
} from './config/operatorMode';
import { shouldBlockGlobalSearchTypeahead } from './utils/isTypingTarget';

const MarketMapPage = lazy(() => import('./pages/MarketMapPage'));
const PotentialSwingsPage = lazy(() => import('./pages/PotentialSwingsPage'));
const PnLPage = lazy(() => import('./pages/PnLPage'));
const EarningsBeatsPage = lazy(() => import('./pages/EarningsBeatsPage'));
const API = '';
const ISSUE_FORM_BASE = 'https://docs.google.com/forms/d/e/1FAIpQLScLR6u8TeQCvaWA82FhEZhm6-T7WT-LoU5RPJtvzZRIy99X0g/viewform';
const FEATURE_FORM_BASE = 'https://docs.google.com/forms/d/e/1FAIpQLScgADzeVq17F_gNe1O5tiJhkhuxlrntWuaq56A0r3UvkIbnxw/viewform';
const ISSUE_ENTRY_ID = '1471558971';
const FEATURE_ENTRY_ID = '779443803';
const CONTEXT_MENU_MARGIN = 8;

/** Admin jobs that rewrite OHLCV / chart payloads — refresh open charts even when scheduler started the job. */
const CHART_DATA_REFRESH_JOBS = new Set(['ohlcv', 'bars_4h_build', 'bars_30m_build', 'indicator_snapshots', 'filter_rebuild', 'ohlc_repair', 'indices', 'indexChartGapRepair']);

function watchlistContainsSymbol(w, symbol, itemType) {
  const sym = String(symbol || '').toUpperCase();
  const typ = String(itemType || 'stock').toLowerCase();
  return (w.items || []).some(
    it => String(it.symbol || '').toUpperCase() === sym
      && String(it.type || 'stock').toLowerCase() === typ,
  );
}

export default function AppWrapper() {
  return (
    <ToastProvider>
      <App />
    </ToastProvider>
  );
}

function App() {
  const [view, setView]                 = useState('dashboard');
  const [maxChartTabs, setMaxChartTabs] = useState(5);
  const [confirmState, setConfirmState] = useState(null);
  const [chartTabs, setChartTabs]       = useState([]);
  const [activeTabIdx, setActiveTabIdx] = useState(null);
  const [indexTabs, setIndexTabs]       = useState([]);
  const [activeIndexTab, setActiveIndexTab] = useState(null);
  const [constituentsStacks, setConstituentsStacks] = useState([]);
  const [activeConstituentsStackIdx, setActiveConstituentsStackIdx] = useState(null);
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
    items: null,
    allVisibleItems: null,
  });
  const [contextMenuPos, setContextMenuPos] = useState({ left: 0, top: 0, flipX: false, flipY: false });
  const [adminOpen, setAdminOpen]       = useState(false);
  const [schedulerOpen, setSchedulerOpen] = useState(false);
  const [toastMessage, setToastMessage]  = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [aggressiveCacheRam, setAggressiveCacheRam] = useState(false);
  const [cacheBusy, setCacheBusy] = useState(false);
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
  const [accountOpen, setAccountOpen] = useState(false);
  const [licenseStatus, setLicenseStatus] = useState(null);
  const [operatorSession, setOperatorSession] = useState(() => {
    captureOperatorFromUrl();
    return isOperatorSessionActive();
  });
  useEffect(() => {
    if (captureOperatorFromUrl()) setOperatorSession(true);
  }, []);
  const appBrandName = licenseStatus?.showcase_role === 'testbed' ? 'CIM Testbed' : 'CiM';
  const isWebBrowserUser = isDistributionProfile && licenseStatus?.host_mode === 'web';
  const isWebBrowserHost = isWebBrowserUser
    && !!licenseStatus?.is_showcase_host
    && operatorSession;
  const showScheduleOperatorHint = isWebBrowserUser
    && !!licenseStatus?.is_showcase_host
    && !operatorSession
    && isLoopbackHost();
  const showcaseWebClient = isWebBrowserUser && !isWebBrowserHost;
  const showDesktopAdminUi = !isWebBrowserUser || isWebBrowserHost;
  const showSchedulerMenu = showDesktopAdminUi && !showcaseWebClient;
  const schedulerCanEdit = isWebBrowserHost || (!isWebBrowserUser && showDesktopAdminUi);
  const { healthState, usersOnline } = useServerStatus(isWebBrowserUser);
  const intradayApiRef = useRef(null);
  const pageLiveApiRef = useRef(null);
  const [intradayRefreshBusy, setIntradayRefreshBusy] = useState(false);
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
  const constituentsCreationOrder       = useRef([]);
  const viewRef                         = useRef(view);
  const activeTabIdxRef                 = useRef(activeTabIdx);
  const activeConstituentsStackIdxRef   = useRef(activeConstituentsStackIdx);
  activeTabIdxRef.current = activeTabIdx;
  activeConstituentsStackIdxRef.current = activeConstituentsStackIdx;

  const prevViewRef = useRef(null);
  useEffect(() => {
    const prev = prevViewRef.current;
    viewRef.current = view;
    if (prev != null && prev !== view) {
      pageLiveApiRef.current?.clearPageLive?.();
    }
    prevViewRef.current = view;
  }, [view]);

  useEffect(() => {
    if (!isDistributionProfile) return undefined;
    let cancelled = false;
    const refresh = async () => {
      try {
        const status = await fetchLicenseStatus();
        if (!cancelled) setLicenseStatus(status);
        if (status?.valid && status?.mode === 'online') {
          try { await licenseHeartbeat(); } catch { /* offline grace */ }
        }
      } catch {
        if (!cancelled) setLicenseStatus({ valid: false });
      }
    };
    refresh();
    const id = setInterval(refresh, 24 * 60 * 60 * 1000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    if (!accountOpen || !isDistributionProfile) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const status = await fetchLicenseStatus();
        if (!cancelled) setLicenseStatus(status);
      } catch {
        /* keep prior status */
      }
    })();
    return () => { cancelled = true; };
  }, [accountOpen]);
  const {
    status: jobStatus,
    isRunning: updateRunning,
    isPendingStart: updatePendingStart,
    isCancelling: updateCancelling,
    percent: updatePercent,
    queued: jobQueue,
    startAdminJob,
    startOhlcvUpdate,
    startRepairIndexChartGaps,
    startSplitAdjustmentsApplyPending,
    startSplitCatchupScan,
    fetchSplitWatchStatus,
    startRefreshShareCounts,
    cancelAdminJob,
    cancelQueuedJob,
    clearJobQueue,
  } = useAdminJobStatus({
    autoStart: !showcaseWebClient,
    onFinished: (finalStatus) => {
      const didRequest = updateRequestedRef.current;
      updateRequestedRef.current = false;
      const meta = finalStatus?.meta || {};
      const cancelled = !!meta.cancelled;
      const partial = !!meta.partial;

      if (cancelled && !partial) {
        if (didRequest) setToastMessage(finalStatus?.message || 'Update cancelled.');
        return;
      }

      if (finalStatus?.job === 'earnings_plus_cache') {
        setEarningsPlusRefreshPending(false);
        if (finalStatus?.meta?.quiet) {
          dispatchAppDataRefresh({
            job: finalStatus?.job,
            ...meta,
          });
          return;
        }
      }

      const refreshData = didRequest || CHART_DATA_REFRESH_JOBS.has(finalStatus?.job) || partial;
      if (!refreshData) return;

      if (finalStatus?.error) {
        if (didRequest) setToastMessage(`Update failed: ${finalStatus.error}`);
        return;
      }

      dispatchAppDataRefresh({
        job: finalStatus?.job,
        ...meta,
      });

      if (didRequest) {
        setToastMessage(finalStatus?.message || 'Update completed.');
      }
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

  const onOpenFilterSchedule = useCallback(() => {
    setSchedulerOpen(true);
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
    setConstituentsStacks(stacks => {
      if (stacks.length > 0) {
        const face = activeChart(stacks[stacks.length - 1]);
        if (face?.symbol) {
          setActiveConstituentsStackIdx(stacks.length - 1);
          setView('constituents_' + face.symbol);
          return stacks;
        }
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
      return stacks;
    });
  }, []);

  // ── Open stock chart ───────────────────────────────────────────────────────
  // Tab slots fill left→right until max; when full, replace oldest open → next oldest
  // (FIFO by open time), not a fixed index. Opening an already-open symbol just focuses it.
  const openChart = useCallback((symbol) => {
    const originView = viewRef.current === 'chart' ? null : viewRef.current;
    const viewIsChart = viewRef.current === 'chart';
    setChartTabs((prev) => {
      const result = openChartInStacks({
        stacks: prev,
        creationOrder: tabCreationOrder.current,
        activeStackIdx: activeTabIdxRef.current,
        viewIsChart,
        symbol,
        originView,
        maxStacks: maxChartTabs,
      });
      tabCreationOrder.current = result.creationOrder;
      setActiveTabIdx(result.activeStackIdx);
      setView('chart');
      return result.stacks;
    });
  }, [maxChartTabs]);

  useEffect(() => {
    function onLiveOpenChart(e) {
      const sym = String(e?.detail?.symbol || '').trim().toUpperCase();
      if (!sym) return;
      openChart(sym);
    }
    window.addEventListener('cim:live-open-chart', onLiveOpenChart);
    return () => window.removeEventListener('cim:live-open-chart', onLiveOpenChart);
  }, [openChart]);

  const closeChart = useCallback((stackIdx, chartIdx = null) => {
    setChartTabs((prev) => {
      const result = chartIdx == null
        ? closeActiveChartInStack(prev, tabCreationOrder.current, stackIdx)
        : closeChartInStack(prev, tabCreationOrder.current, stackIdx, chartIdx);
      tabCreationOrder.current = result.creationOrder;
      if (result.stacks.length === 0) {
        setActiveTabIdx(null);
        navigateAfterLastChartClosed(result.closedReturnView);
      } else if (result.removedStack) {
        const newIdx = result.nextActiveStackIdxHint;
        setActiveTabIdx(newIdx);
        setView('chart');
      } else {
        setActiveTabIdx(stackIdx);
        setView('chart');
      }
      return result.stacks;
    });
  }, [navigateAfterLastChartClosed]);

  const switchChart = useCallback((stackIdx, chartIdx = null) => {
    if (chartIdx != null) {
      setChartTabs((prev) => activateChartInStack(prev, stackIdx, chartIdx));
    }
    setActiveTabIdx(stackIdx);
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
        // Check if a constituents stack still has pages open
        setConstituentsStacks(stacks => {
          const related = findChartInStacks(stacks, symbol);
          if (related) {
            const nextStacks = activateChartInStack(stacks, related.stackIdx, related.chartIdx);
            setActiveConstituentsStackIdx(related.stackIdx);
            setView('constituents_' + symbol);
            return nextStacks;
          }
          if (stacks.length > 0) {
            const face = activeChart(stacks[stacks.length - 1]);
            if (face?.symbol) {
              setActiveConstituentsStackIdx(stacks.length - 1);
              setView('constituents_' + face.symbol);
              return stacks;
            }
          }
          setView('indices');
          return stacks;
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

  // ── Open constituents (stacked like symbol charts) ─────────────────────────
  const openConstituents = useCallback((index) => {
    const sym = String(index?.symbol || '').trim().toUpperCase();
    if (!sym) return;
    const originView = String(viewRef.current || '').startsWith('constituents_')
      ? null
      : viewRef.current;
    setConstituentsStacks((prev) => {
      const result = openChartInStacks({
        stacks: prev,
        creationOrder: constituentsCreationOrder.current,
        activeStackIdx: activeConstituentsStackIdxRef.current,
        viewIsChart: false,
        symbol: sym,
        originView,
        maxStacks: maxChartTabs,
        entryMeta: {
          // Preserve index payload fields ConstituentsPage may read.
          ...index,
          symbol: sym,
          name: index.name || sym,
        },
      });
      constituentsCreationOrder.current = result.creationOrder;
      setActiveConstituentsStackIdx(result.activeStackIdx);
      const face = activeChart(result.stacks[result.activeStackIdx]);
      if (face?.symbol) setView('constituents_' + face.symbol);
      return result.stacks;
    });
  }, [maxChartTabs]);

  const closeConstituentsTab = useCallback((stackIdx, chartIdx = null) => {
    setConstituentsStacks((prev) => {
      const stack = prev[stackIdx];
      const closedEntry = chartIdx == null
        ? stack?.charts?.[stack.activeIdx]
        : stack?.charts?.[chartIdx];
      const closedSym = closedEntry?.symbol;
      const result = chartIdx == null
        ? closeActiveChartInStack(prev, constituentsCreationOrder.current, stackIdx)
        : closeChartInStack(prev, constituentsCreationOrder.current, stackIdx, chartIdx);
      constituentsCreationOrder.current = result.creationOrder;
      if (result.stacks.length === 0) {
        setActiveConstituentsStackIdx(null);
        // Go to related index chart if open, else adjacent index tab, else indices
        setIndexTabs(idxTabs => {
          const related = closedSym
            ? idxTabs.find(t => t.symbol === closedSym)
            : null;
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
        const newIdx = result.nextActiveStackIdxHint;
        setActiveConstituentsStackIdx(newIdx);
        const face = activeChart(result.stacks[newIdx]);
        if (face?.symbol) setView('constituents_' + face.symbol);
      }
      return result.stacks;
    });
  }, []);

  const switchConstituents = useCallback((stackIdx, chartIdx = null) => {
    if (chartIdx == null) {
      setActiveConstituentsStackIdx(stackIdx);
      setConstituentsStacks((prev) => {
        const face = activeChart(prev[stackIdx]);
        if (face?.symbol) setView('constituents_' + face.symbol);
        return prev;
      });
      return;
    }
    setConstituentsStacks((prev) => {
      const next = activateChartInStack(prev, stackIdx, chartIdx);
      setActiveConstituentsStackIdx(stackIdx);
      const face = activeChart(next[stackIdx]);
      if (face?.symbol) setView('constituents_' + face.symbol);
      return next;
    });
  }, []);

  const reorderConstituentsStacks = useCallback((fromIdx, toIdx) => {
    setConstituentsStacks((prev) => {
      const next = [...prev];
      const [moved] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, moved);
      setActiveConstituentsStackIdx((ai) => {
        if (ai === fromIdx) return toIdx;
        if (fromIdx < ai && toIdx >= ai) return ai - 1;
        if (fromIdx > ai && toIdx <= ai) return ai + 1;
        return ai;
      });
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

  // Warm support QR (dev PNG fetch or secure decrypt) so the modal is not blank on first open.
  useEffect(() => {
    prefetchSupportQr().catch(() => {});
  }, []);

  useEffect(() => {
    if (settingsOpen) prefetchSupportQr().catch(() => {});
  }, [settingsOpen]);

  useEffect(() => {
    let active = true;
    axios.get(`${API}/api/admin/cache-settings`)
      .then((r) => {
        if (!active) return;
        setAggressiveCacheRam(!!r.data?.aggressiveCacheRam);
      })
      .catch(() => {});
    axios.get(`${API}/api/layout`)
      .then((r) => {
        if (!active) return;
        const n = Number(r.data?.maxChartTabs);
        if (Number.isFinite(n) && n >= 1 && n <= 20) setMaxChartTabs(n);
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

  const goToFunds = useCallback(() => {
    setView('funds');
  }, []);

  const goToWatchlist = useCallback(() => {
    setView('watchlist');
  }, []);

  const goToPortfolio = useCallback(() => {
    setView('portfolio');
  }, []);

  const goToPnL = useCallback(() => {
    setView('pnl');
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
    setUpdatePanelOpen(true);
    updateRequestedRef.current = true;
    try {
      const result = await starter();
      if (result?.status === 'queued') {
        setToastMessage(
          result.coalesced
            ? `Already queued: ${result.label || result.job || 'job'} (position ${result.position}).`
            : `Queued behind current job: ${result.label || result.job || 'job'} (position ${result.position}).`,
        );
      }
    } catch (e) {
      updateRequestedRef.current = false;
      setToastMessage(e.response?.data?.detail || startErrMessage);
    }
  }, []);

  const handleCancelUpdate = useCallback(async () => {
    if (!updateRunning && !updatePendingStart) return;
    setUpdatePanelOpen(true);
    try {
      await cancelAdminJob();
    } catch {
      setToastMessage('Failed to request cancellation.');
    }
  }, [cancelAdminJob, updatePendingStart, updateRunning]);

  const handleUpdatePriceVolume = useCallback(async () => {
    await startUpdateJob(startOhlcvUpdate, 'Failed to start price/volume update.');
  }, [startOhlcvUpdate, startUpdateJob]);

  const handleRepairIndexChartGaps = useCallback(async () => {
    await startUpdateJob(
      startRepairIndexChartGaps,
      'Failed to start index chart gap repair.',
    );
  }, [startRepairIndexChartGaps, startUpdateJob]);

  const handleUpdateIndicatorSnapshots = useCallback(async () => {
    setSchedulerOpen(true);
  }, []);

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
      const ok = await askConfirm(setConfirmState, {
        title: 'Force Earnings+ Refresh',
        message:
          'Force refresh recomputes every reported symbol for this month and may re-scrape Screener data. This can take a long time. Continue?',
        confirmLabel: 'Continue',
        danger: true,
      });
      if (!ok) return;
    }
    setSettingsOpen(false);
    updateRequestedRef.current = true;
    setUpdatePanelOpen(true);
    setEarningsPlusRefreshPending(true);
    try {
      const result = await startAdminJob('/api/admin/refresh-earnings-plus-cache', { params });
      if (result?.status === 'queued') {
        setToastMessage(
          `Queued Earnings+ refresh behind current job (position ${result.position}).`,
        );
      }
    } catch (e) {
      updateRequestedRef.current = false;
      setEarningsPlusRefreshPending(false);
      setToastMessage(e.response?.data?.detail || 'Failed to start Earnings+ cache refresh.');
    }
  }, [startAdminJob]);

  const openSupport = useCallback(() => {
    setSettingsOpen(false);
    prefetchSupportQr().catch(() => {});
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

  const handleUpdateMaxChartTabs = useCallback(async (value) => {
    const n = Number(value);
    if (!Number.isFinite(n) || n < 1 || n > 20) return;
    setMaxChartTabs(n);
    setChartTabs(prev => {
      if (prev.length <= n) return prev;
      const trimmed = trimChartTabsToMax(prev, tabCreationOrder.current, activeTabIdx, n);
      tabCreationOrder.current = trimmed.creationOrder;
      setActiveTabIdx(trimmed.activeIdx);
      return trimmed.tabs;
    });
    try {
      await axios.post(`${API}/api/layout`, { maxChartTabs: n });
    } catch {
      setToastMessage('Failed to save max chart tabs setting.');
    }
  }, [activeTabIdx]);

  const [cimUpdateBusy, setCimUpdateBusy] = useState(false);
  const [appVersion, setAppVersion] = useState('');
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
        const ok = await askConfirm(setConfirmState, {
          title: 'Apply Update',
          message: `Apply Charts In Motion update ${u.version} from ${sourceLabel}${count !== '?' ? ` (${count} files)` : ''}?\n\nCharts In Motion will close to apply the update.`,
          confirmLabel: 'Update',
        });
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
    if (isWebBrowserUser) return undefined;
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
        const ok = await askConfirm(setConfirmState, {
          title: 'Update Available',
          message: `Charts In Motion update ${ver} is available from ${sourceName}.\n\nWould you like to update now? Charts In Motion will close to apply the update.`,
          confirmLabel: 'Update now',
        });
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
  }, [cimUpdateBusy, updateRunning, updatePendingStart, runCiMUpdateApply, isWebBrowserUser]);

  const handleRestartBackendAndFrontendDev = useCallback(async () => {
    if (restartBackendBusy || reloadFrontendBusy) return;
    const canRestartBackend = typeof window?.cimDesktop?.restartBackend === 'function';
    const canReloadFrontend = typeof window?.cimDesktop?.reloadFrontend === 'function';
    if (!canRestartBackend || !canReloadFrontend) {
      setToastMessage('Restart backend + frontend is not available in this build.');
      return;
    }
    if (!(await askConfirm(setConfirmState, {
      title: 'Restart Dev Servers',
      message: 'Restart backend and frontend now?\n\nThis is a development-only action and may take a few seconds.',
      confirmLabel: 'Restart',
    }))) {
      return;
    }
    setSettingsOpen(false);
    setRestartBackendBusy(true);
    setReloadFrontendBusy(true);
    try {
      setToastMessage('Restarting backend and frontend...');
      await window.cimDesktop.restartBackend();
      dispatchAppDataRefresh({ job: 'backend_restart' });
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
    } else if (view === 'pnl') {
      window.dispatchEvent(new CustomEvent(PNL_REFRESH_EVENT));
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
    const items = Array.isArray(payload.items) && payload.items.length
      ? payload.items.map((it) => ({
          symbol: String(it.symbol || '').trim().toUpperCase(),
          type: String(it.type || 'stock').toLowerCase() === 'index' ? 'index' : 'stock',
        })).filter((it) => it.symbol)
      : [{ symbol: String(payload.symbol).trim().toUpperCase(), type: payload.type }];
    const allVisibleItems = Array.isArray(payload.allVisibleItems)
      ? payload.allVisibleItems.map((it) => ({
          symbol: String(it.symbol || '').trim().toUpperCase(),
          type: String(it.type || 'stock').toLowerCase() === 'index' ? 'index' : 'stock',
        })).filter((it) => it.symbol)
      : null;
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
      items,
      allVisibleItems,
    });
  }, []);

  const canOpenGlobalSearch = view === 'dashboard'
    || view === 'portfolio'
    || view === 'pnl'
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
      : view === 'pnl' ? 'pnl'
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
    let lastPointerDownTarget = null;
    function onPointerDown(e) {
      lastPointerDownTarget = e.target;
    }
    function onKeydown(e) {
      const consume = () => {
        e.preventDefault();
        e.stopPropagation();
        if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
      };
      if (e.defaultPrevented) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const blockTypeahead = shouldBlockGlobalSearchTypeahead(e, lastPointerDownTarget);
      const key = e.key || '';

      // Inputs / Alerts / Portfolio % UI — never steal Backspace or digits.
      if (blockTypeahead) {
        return;
      }

      // Stop browser "Back" navigation when focus is not in a field / no-typeahead UI.
      if ((key === 'Backspace' || key === 'Delete') && !globalSearchOpen) {
        e.preventDefault();
        return;
      }

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
        const searchOwnsFocus = !!globalSearchInputRef.current
          && document.activeElement === globalSearchInputRef.current;
        if (key === 'Backspace') {
          if (!searchOwnsFocus) {
            e.preventDefault();
            return;
          }
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
          if (!searchOwnsFocus && document.activeElement
            && document.activeElement !== document.body
            && document.activeElement !== document.documentElement) {
            return;
          }
          consume();
          setGlobalSearchQuery(prev => `${prev}${key}`.toUpperCase());
          globalSearchInputRef.current?.focus();
        }
        return;
      }

      if (!canOpenGlobalSearch) return;
      if (key === '/' && !globalSearchOpen) {
        consume();
        setGlobalSearchOpen(true);
        setGlobalSearchQuery('');
        return;
      }
      if (key === 'Escape') return;
      if (key.length === 1 && !/\s/.test(key)) {
        consume();
        setGlobalSearchOpen(true);
        setGlobalSearchQuery(key.toUpperCase());
      }
    }
    window.addEventListener('mousedown', onPointerDown, true);
    window.addEventListener('keydown', onKeydown, true);
    return () => {
      window.removeEventListener('mousedown', onPointerDown, true);
      window.removeEventListener('keydown', onKeydown, true);
    };
  }, [applyGlobalSearchPick, canOpenGlobalSearch, globalSearchActiveIndex, globalSearchOpen, globalSearchResults, knowledgeBaseOpen]);

  // Live Feed scope follows the active page (no Mode dropdown).
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const chartTabSymbol = view === 'chart' && activeTabIdx != null
      ? activeChart(chartTabs[activeTabIdx])?.symbol
      : null;
    const scope = livePageContextFromView(view, { chartSymbol: chartTabSymbol });
    window.dispatchEvent(new CustomEvent('cim:live-page-context', {
      detail: {
        context: scope.context,
        pageId: scope.pageId,
        label: scope.label,
        symbol: chartTabSymbol || undefined,
      },
    }));
    try {
      const snap = window.CiMLiveFeedControl?.getSnapshot?.();
      if (snap?.enabled && scope.pageId) {
        pageLiveApiRef.current?.setPageLive?.(scope.pageId);
      }
    } catch { /* ignore */ }
    return undefined;
  }, [view, activeTabIdx, chartTabs]);

  // Keep pageLiveId in sync with Live Feed ON/OFF so charts get liveToday.
  // Only trust cim:live-feed-toggle from the feed controller — cim:live-active can
  // briefly report enabled:false while resubscribing (stopMoversUniverse mid-sync).
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onToggle = (e) => {
      const enabled = !!(e?.detail?.enabled);
      if (!enabled) {
        try {
          const snap = window.CiMLiveFeedControl?.getSnapshot?.();
          if (snap?.enabled) return;
        } catch { /* ignore */ }
        pageLiveApiRef.current?.clearPageLive?.();
        return;
      }
      const pageId = e?.detail?.pageId || resolvePageId(view);
      if (pageId) pageLiveApiRef.current?.setPageLive?.(pageId);
    };
    window.addEventListener('cim:live-feed-toggle', onToggle);
    return () => {
      window.removeEventListener('cim:live-feed-toggle', onToggle);
    };
  }, [view]);

  const handleRefreshLivePrices = useCallback(async () => {
    const pageId = resolvePageId(view);
    const chartTabSymbol = view === 'chart' && activeTabIdx != null
      ? activeChart(chartTabs[activeTabIdx])?.symbol
      : null;
    let symbols = getRefreshSymbols(pageId, chartTabSymbol);

    if (pageId === 'movers') {
      setToastMessage('Fetching today\'s movers…');
      setIntradayRefreshBusy(true);
      try {
        const prefetched = await new Promise((resolve) => {
          let settled = false;
          const finish = (list) => {
            if (settled) return;
            settled = true;
            resolve(Array.isArray(list) ? list : []);
          };
          window.dispatchEvent(new CustomEvent(MOVERS_LIVE_PREFETCH_EVENT, {
            detail: { resolve: finish },
          }));
          setTimeout(() => finish(symbols), 90000);
        });
        if (prefetched.length) symbols = prefetched;
      } catch {
        /* fall back to registry symbols */
      }
    }

    if (!symbols.length) {
      setToastMessage(refreshEmptyMessage(pageId));
      setIntradayRefreshBusy(false);
      return;
    }
    const pageLabel = pageDisplayName(pageId);
    if (pageId !== 'movers') {
      setToastMessage(`Fetching live prices for ${symbols.length} symbol${symbols.length === 1 ? '' : 's'}…`);
    } else {
      setToastMessage(`Updating live prices for ${symbols.length} mover${symbols.length === 1 ? '' : 's'}…`);
    }
    if (pageId !== 'movers') {
      setIntradayRefreshBusy(true);
    }
    const api = intradayApiRef.current;
    if (!api?.refreshPatch) {
      setToastMessage('Live prices not ready — wait a moment and try again.');
      setIntradayRefreshBusy(false);
      return;
    }
    try {
      const result = await api.refreshPatch(symbols);
      const returned = result?.count ?? 0;
      if (returned > 0) {
        pageLiveApiRef.current?.setPageLive?.(pageId);
      }
      if (returned <= 0) {
        const nseHint = result?.nseError ? ` ${result.nseError}` : '';
        setToastMessage(`No live prices returned for ${pageLabel}.${nseHint}`.trim());
      } else {
        const trunc = result?.truncated ? ' (some symbols skipped — page cap reached)' : '';
        setToastMessage(`Updated ${returned} live price${returned === 1 ? '' : 's'} on ${pageLabel}.${trunc}`);
      }
    } catch (e) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail;
      if (status === 502) {
        setToastMessage('Live price fetch timed out. Try again.');
      } else {
        setToastMessage(typeof detail === 'string' ? detail : (e.message || 'Failed to refresh prices.'));
      }
    } finally {
      setIntradayRefreshBusy(false);
    }
  }, [view, activeTabIdx, chartTabs]);

  const contextMenuItems = (
    Array.isArray(contextMenuState.items) && contextMenuState.items.length
      ? contextMenuState.items
      : (contextMenuState.symbol
        ? [{ symbol: contextMenuState.symbol, type: contextMenuState.type || 'stock' }]
        : [])
  );
  const contextMenuAllVisible = Array.isArray(contextMenuState.allVisibleItems)
    ? contextMenuState.allVisibleItems
    : [];
  const contextMenuLabel = contextMenuItems.length > 1
    ? `${contextMenuItems.length} symbols`
    : (contextMenuState.symbol || '');

  return (
    <IntradayPatchProvider
      enabled={!!isWebBrowserUser}
      userEmail={licenseStatus?.email}
      onApiReady={(api) => { intradayApiRef.current = api; }}
    >
    <PageLiveProvider onApiReady={(api) => { pageLiveApiRef.current = api; }}>
    <ChartPrefsProvider enabled={isWebBrowserUser} email={licenseStatus?.email}>
    <BasketProvider onOpenStock={openChart} onOpenIndex={openIndex}>
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
          {isDistributionProfile && licenseStatus?.offline_cached && (
            <div style={{
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: '#3d2e00',
              color: '#f0c040',
              fontSize: 11,
              textAlign: 'center',
              padding: '6px 12px',
              borderBottom: '1px solid #5c4500',
              lineHeight: 1.45,
            }}>
              <span>
                Offline —{' '}
                <button
                  type="button"
                  onClick={() => setAccountOpen(true)}
                  style={{
                    display: 'inline',
                    margin: 0,
                    padding: '0 2px',
                    background: 'rgba(240, 192, 64, 0.18)',
                    border: 'none',
                    borderRadius: 3,
                    color: '#fff3b0',
                    fontSize: 'inherit',
                    fontWeight: 700,
                    textDecoration: 'underline',
                    cursor: 'pointer',
                    verticalAlign: 'baseline',
                  }}
                >
                  Sign out
                </button>
                {', then sign in again to start a new session. '}
                {licenseStatus.offline_grace_until
                  ? `This cached session expires on ${String(licenseStatus.offline_grace_until).slice(0, 10)}.`
                  : 'This cached session will expire soon.'}
              </span>
            </div>
          )}
          <TabBar
            view={view}
            chartTabs={chartTabs}
            activeTabIdx={activeTabIdx}
            indexTabs={indexTabs}
            activeIndexTab={activeIndexTab}
            constituentsStacks={constituentsStacks}
            activeConstituentsStackIdx={activeConstituentsStackIdx}
            onDashboard={goToDashboard}
            onIndices={goToIndices}
            onFunds={goToFunds}
            onWatchlist={goToWatchlist}
            onPortfolio={goToPortfolio}
            onPnL={goToPnL}
            onPotentialSwings={goToPotentialSwings}
            onMarketPulse={goToMarketPulse}
            onMarketMovers={goToMarketMovers}
            onMarketMap={goToMarketMap}
            onEarningsBeats={goToEarningsBeats}
            onSwitchChart={switchChart}
            onCloseChart={closeChart}
            onSwitchIndex={sym => { setActiveIndexTab(sym); setView('index_' + sym); }}
            onCloseIndex={closeIndexTab}
            onSwitchConstituents={switchConstituents}
            onCloseConstituents={closeConstituentsTab}
            onReorderChartTabs={reorderChartTabs}
            onReorderConstituentsStacks={reorderConstituentsStacks}
            onOpenSectors={() => { setAdminOpen(true); setSettingsOpen(false); }}
            onOpenScheduler={() => { setSchedulerOpen(true); setSettingsOpen(false); }}
            onOpenSettings={() => setSettingsOpen(v => !v)}
            onOpenAccount={(isDistributionProfile || isDevAccountPreview) ? () => { setSettingsOpen(false); setAccountOpen(true); } : undefined}
            onOpenKnowledgeBaseEditor={!isDistributionProfile ? () => {
              setSettingsOpen(false);
              setKnowledgeBaseEditorOpen(true);
            } : undefined}
            onOpenIssue={() => openFeedback('issue')}
            onOpenFeature={() => openFeedback('feature')}
            onOpenSupport={openSupport}
            onOpenAbout={openAbout}
            aggressiveCacheRam={aggressiveCacheRam}
            maxChartTabs={maxChartTabs}
            onUpdateMaxChartTabs={handleUpdateMaxChartTabs}
            cacheBusy={cacheBusy}
            onToggleAggressiveCache={handleToggleAggressiveCache}
            onClearCacheNow={handleClearCacheNow}
            onUpdatePriceVolume={handleUpdatePriceVolume}
            onRepairIndexChartGaps={handleRepairIndexChartGaps}
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
            onRebuildIndicatorSnapshots={onOpenFilterSchedule}
            earningsPlusRefreshRunning={earningsPlusRefreshPending || (updateRunning && jobStatus?.job === 'earnings_plus_cache')}
            desktopCanRestartBackend={desktopCanRestartBackend}
            restartBackendBusy={restartBackendBusy}
            desktopCanReloadFrontend={desktopCanReloadFrontend}
            reloadFrontendBusy={reloadFrontendBusy}
            onRestartBackendAndFrontendDev={handleRestartBackendAndFrontendDev}
            onApplyCiMUpdate={handleApplyCiMUpdate}
            cimUpdateBusy={cimUpdateBusy}
            appVersion={appVersion}
            appBrandName={appBrandName}
            onRefresh={handleGlobalRefresh}
            knowledgeBaseOpen={knowledgeBaseOpen}
            previewAccountMenu={isDevAccountPreview}
            showcaseWebClient={showcaseWebClient}
            isWebBrowserUser={isWebBrowserUser}
            isWebBrowserHost={isWebBrowserHost}
            showDesktopAdminUi={showDesktopAdminUi}
            showSchedulerMenu={showSchedulerMenu}
            onRefreshLivePrices={handleRefreshLivePrices}
            intradayRefreshBusy={intradayRefreshBusy}
            healthState={healthState}
            usersOnline={usersOnline}
            onOpenChart={openChart}
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
            showcaseWebClient={showcaseWebClient}
            onContextMenuRequest={handleContextMenuRequest}
          />
        </div>

        {/* Market Map — index breadth + constituent heatmap */}
        <div style={{ display: view === 'market-map' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <Suspense fallback={<div style={{ padding: 16, color: 'var(--text-muted)' }}>Loading Market Map…</div>}>
            <MarketMapPage
              onOpenChart={openChart}
              isActive={view === 'market-map'}
            />
          </Suspense>
        </div>

        {/* Earnings beats (TradingView screener) */}
        <div style={{ display: view === 'earnings-beats' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <Suspense fallback={<div style={{ padding: 16, color: 'var(--text-muted)' }}>Loading Earnings…</div>}>
            <EarningsBeatsPage
              onOpenChart={openChart}
              isActive={view === 'earnings-beats'}
              onContextMenuRequest={handleContextMenuRequest}
              onAddStocksToWatchlist={handleDashboardAddToWatchlist}
              watchlists={watchlists}
              onGoToWatchlist={goToWatchlist}
              onRefreshEarningsPlusCache={showDesktopAdminUi ? handleRefreshEarningsPlusCache : undefined}
              earningsPlusRefreshRunning={earningsPlusRefreshPending || (updateRunning && jobStatus?.job === 'earnings_plus_cache')}
            />
          </Suspense>
        </div>

        {/* Dashboard */}
        <div style={{ display: view === 'dashboard' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <DashboardPage
            pageMode="pulse"
            isLayoutActive={view === 'dashboard'}
            onOpenChart={openChart}
            watchlists={watchlists}
            onGoToWatchlist={goToWatchlist}
            onAddStocksToWatchlist={handleDashboardAddToWatchlist}
            onContextMenuRequest={handleContextMenuRequest}
            showcaseWebClient={showcaseWebClient}
          />
        </div>
        <div style={{ display: view === 'portfolio' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <DashboardPage
            pageMode="portfolio"
            isLayoutActive={view === 'portfolio'}
            onOpenChart={openChart}
            watchlists={watchlists}
            onGoToWatchlist={goToWatchlist}
            onAddStocksToWatchlist={handleDashboardAddToWatchlist}
            onContextMenuRequest={handleContextMenuRequest}
            showcaseWebClient={showcaseWebClient}
          />
        </div>
        <div style={{ display: view === 'pnl' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <Suspense fallback={<div style={{ padding: 16, color: 'var(--text-muted)' }}>Loading P&amp;L…</div>}>
            <PnLPage onOpenChart={openChart} />
          </Suspense>
        </div>
        <div style={{ display: view === 'potential-swings' && !isDistributionProfile ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          {!isDistributionProfile && (
          <Suspense fallback={<div style={{ padding: 16, color: 'var(--text-muted)' }}>Loading Potential Swings…</div>}>
            <PotentialSwingsPage
              onOpenChart={openChart}
              watchlists={watchlists}
              onGoToWatchlist={goToWatchlist}
              onAddStocksToWatchlist={handleDashboardAddToWatchlist}
            />
          </Suspense>
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
            showcaseWebClient={showcaseWebClient}
          />
        </div>
        {/* Market Indices list */}
        <div style={{ display: view === 'indices' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <IndicesPage
            onOpenConstituents={openConstituents}
            onContextMenuRequest={handleContextMenuRequest}
          />
        </div>

        {/* Mutual Funds (AMFI daily NAV) */}
        <div style={{ display: view === 'funds' ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
          <FundsPage />
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

        {/* Constituents stacks — one ConstituentsPage per active entry */}
        {constituentsStacks.map((stack, idx) => {
          const page = activeChart(stack);
          if (!page) return null;
          return (
            <div
              key={`${stack.id}-${page.id}`}
              style={{
                display: (view === 'constituents_' + page.symbol && idx === activeConstituentsStackIdx)
                  ? 'flex'
                  : 'none',
                flex: 1,
                flexDirection: 'column',
                overflow: 'hidden',
                height: '100%',
              }}
            >
              <ConstituentsPage
                index={page}
                onOpenChart={openChart}
                onContextMenuRequest={handleContextMenuRequest}
                onBack={() => {
                  const indexTab = indexTabs.find(t => t.symbol === page.symbol);
                  if (indexTab) setView('index_' + page.symbol);
                  else setView('indices');
                }}
              />
            </div>
          );
        })}
        {/* Chart stacks — one SplitChartPage per stack slot */}
        {chartTabs.map((stack, idx) => {
          const chart = activeChart(stack);
          if (!chart) return null;
          return (
            <div
              key={`${stack.id}-${chart.id}`}
              style={{
                display: (view === 'chart' && idx === activeTabIdx) ? 'flex' : 'none',
                flex: 1,
                flexDirection: 'column',
                overflow: 'hidden',
                height: '100%',
              }}
            >
              <SplitChartPage
                symbol={chart.symbol}
                onOpenChart={openChart}
                onActiveSymbolChange={(sym) => {
                  setChartTabs((prev) => setActiveChartSymbol(prev, idx, sym));
                  try {
                    window.dispatchEvent(new CustomEvent('cim:chart-focus-symbol', {
                      detail: { symbol: String(sym || '').trim().toUpperCase() },
                    }));
                  } catch (_) { /* ignore */ }
                }}
              />
            </div>
          );
        })}
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

      {(updateRunning || updatePendingStart || updatePanelOpen || (jobQueue && jobQueue.length > 0)) && (
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
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
              {(updateRunning || updatePendingStart)
                ? (updateCancelling ? 'Cancelling update…' : 'Update in progress')
                : (jobQueue?.length ? 'Job queue' : 'Last update status')}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {(updateRunning || updatePendingStart) && (
                <button
                  type="button"
                  onClick={handleCancelUpdate}
                  disabled={updateCancelling}
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    color: 'var(--accent-red)',
                    background: 'rgba(248,81,73,0.1)',
                    border: '1px solid var(--accent-red)',
                    borderRadius: 4,
                    padding: '4px 8px',
                    cursor: updateCancelling ? 'default' : 'pointer',
                    opacity: updateCancelling ? 0.6 : 1,
                  }}
                >
                  {updateCancelling ? 'Cancelling…' : 'Cancel'}
                </button>
              )}
              {!(updateRunning || updatePendingStart) && (
                <button onClick={() => setUpdatePanelOpen(false)} style={{ background: 'none', color: 'var(--text-muted)', fontSize: 16, lineHeight: 1 }}>×</button>
              )}
            </div>
          </div>
          <div style={{ fontSize: 11, color: jobStatus?.error ? 'var(--accent-red)' : 'var(--text-secondary)', marginBottom: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.35, minHeight: '2.7em' }}>
            {jobStatus?.error
              ? jobStatus.error
              : (jobStatus?.message || ((updateRunning || updatePendingStart) ? 'Starting update job…' : 'No active update job.'))}
          </div>
          {(() => {
            const src = statusMeta?.sources || {};
            const daily = src.daily || {};
            const bars = src.bars_4h || {};
            const hasDaily = daily.upstox != null || daily.failed != null || daily.skipped_current != null;
            const has4h = bars.upstox != null || bars.failed != null || bars.none != null || bars.skipped_current != null;
            if (!hasDaily && !has4h) return null;
            const parts = [];
            if (hasDaily) {
              parts.push(
                `Daily Upstox ${Number(daily.upstox || 0)}` +
                (daily.failed != null ? ` · failed ${Number(daily.failed || 0)}` : '') +
                (daily.skipped_current != null ? ` · skip ${Number(daily.skipped_current || 0)}` : '')
              );
            }
            if (has4h) {
              parts.push(
                `4H Upstox ${Number(bars.upstox || 0)}` +
                (bars.none != null ? ` · miss ${Number(bars.none || 0)}` : '') +
                (bars.failed != null ? ` · failed ${Number(bars.failed || 0)}` : '') +
                (bars.skipped_current != null ? ` · skip ${Number(bars.skipped_current || 0)}` : '')
              );
            }
            return (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, lineHeight: 1.35 }}>
                Source: {parts.join(' · ')}
              </div>
            );
          })()}
          {Array.isArray(jobQueue) && jobQueue.length > 0 && (
            <div style={{ marginBottom: 8, border: '1px solid var(--border-light)', borderRadius: 6, backgroundColor: 'var(--bg-tertiary)', padding: '8px 10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6, gap: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)' }}>
                  Queued ({jobQueue.length})
                </div>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await clearJobQueue();
                    } catch {
                      setToastMessage('Failed to clear job queue.');
                    }
                  }}
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: 'var(--text-secondary)',
                    background: 'transparent',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    padding: '2px 6px',
                    cursor: 'pointer',
                  }}
                >
                  Clear queue
                </button>
              </div>
              {jobQueue.map((item) => (
                <div
                  key={item.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    padding: '4px 0',
                    borderTop: '1px solid var(--border-light)',
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.position}. {item.label || item.key}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                      {item.source === 'scheduled' ? 'scheduled' : 'manual'}
                    </div>
                  </div>
                  <button
                    type="button"
                    title="Remove from queue"
                    onClick={async () => {
                      try {
                        await cancelQueuedJob(item.id);
                      } catch {
                        setToastMessage('Failed to remove queued job.');
                      }
                    }}
                    style={{
                      fontSize: 10,
                      fontWeight: 600,
                      color: 'var(--accent-red)',
                      background: 'transparent',
                      border: '1px solid var(--accent-red)',
                      borderRadius: 4,
                      padding: '2px 6px',
                      cursor: 'pointer',
                      flexShrink: 0,
                    }}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
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

      {adminOpen && (
        <AdminPanel
          onClose={() => setAdminOpen(false)}
          defaultTab={isWebBrowserUser ? 'chartPrefs' : 'sectors'}
          hideJobsTab
          showSectorsTab={!!isWebBrowserHost || !isWebBrowserUser}
          showChartPrefsTab={!!isWebBrowserUser}
        />
      )}
      {schedulerOpen && (
        <ShowcaseSchedulerModal
          open={schedulerOpen}
          onClose={() => setSchedulerOpen(false)}
          canEdit={schedulerCanEdit}
          showOperatorHint={showScheduleOperatorHint}
        />
      )}
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
      {accountOpen && (isDistributionProfile || isDevAccountPreview) && (
        <AccountSettingsModal
          open={accountOpen}
          onClose={() => setAccountOpen(false)}
          licenseStatus={isDistributionProfile ? licenseStatus : DEV_ACCOUNT_PREVIEW}
          previewMode={isDevAccountPreview}
          showHostOperatorPanels={isWebBrowserHost}
          isWebBrowserHost={isWebBrowserHost}
          onSignedOut={() => { setAccountOpen(false); setOperatorSession(false); }}
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
            {contextMenuLabel}
          </div>
          <div
            onClick={async () => {
              for (const it of contextMenuItems) {
                await addToPortfolio(it.symbol, it.type);
              }
              setToastMessage(
                contextMenuItems.length > 1
                  ? `Added ${contextMenuItems.length} symbols to portfolio.`
                  : `Added ${contextMenuItems[0]?.symbol || ''} to portfolio.`,
              );
              setContextMenuState(s => ({ ...s, visible: false }));
            }}
            style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--accent-green)', borderBottom: '1px solid var(--border)' }}
            onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
            onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
          >
            {contextMenuItems.length > 1 ? `Add ${contextMenuItems.length} to portfolio` : 'Add to portfolio'}
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
            {contextMenuItems.length > 1 ? `Add ${contextMenuItems.length} to watchlist` : 'Add to watchlist'}
          </div>
          {watchlists.map(w => (
            <div
              key={w.name}
              onClick={async () => {
                const r = await addItemsToNamedWatchlist(contextMenuItems, w.name);
                if (r.ok) {
                  setToastMessage(
                    contextMenuItems.length > 1
                      ? `Added ${contextMenuItems.length} symbols to "${w.name}".`
                      : `Added ${contextMenuItems[0]?.symbol || ''} to "${w.name}".`,
                  );
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
          {contextMenuState.sourcePage === 'earnings-beats' && contextMenuAllVisible.length > 0 && (
            <>
              <div style={{ height: 1, backgroundColor: 'var(--border)' }} />
              <div style={{ padding: '6px 10px 2px', fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {`Add all visible (${contextMenuAllVisible.length})`}
              </div>
              {watchlists.map(w => (
                <div
                  key={`all-vis-${w.name}`}
                  onClick={async () => {
                    const r = await addItemsToNamedWatchlist(contextMenuAllVisible, w.name);
                    if (r.ok) {
                      setToastMessage(`Added ${contextMenuAllVisible.length} visible symbols to "${w.name}".`);
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
            </>
          )}
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
                    const r = await addItemsToNamedWatchlist(contextMenuItems, targetName);
                    if (r.ok) {
                      setToastMessage(contextMenuItems.length > 1 ? `Added ${contextMenuItems.length} symbols to "${targetName}".` : `Added ${contextMenuItems[0]?.symbol || ''} to "${targetName}".`);
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
                    const r = await addItemsToNamedWatchlist(contextMenuItems, targetName);
                    if (r.ok) {
                      setToastMessage(contextMenuItems.length > 1 ? `Added ${contextMenuItems.length} symbols to "${targetName}".` : `Added ${contextMenuItems[0]?.symbol || ''} to "${targetName}".`);
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
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexShrink: 0, gap: 12 }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>About Charts In Motion</div>
                <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-muted)', marginTop: 4 }}>Created by Sandeep Balachandran</div>
              </div>
              <button type="button" onClick={() => setAboutOpen(false)} aria-label="Close" style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1, flexShrink: 0 }}>×</button>
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
      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title}
        message={confirmState?.message}
        confirmLabel={confirmState?.confirmLabel}
        danger={confirmState?.danger}
        onConfirm={confirmState?.onConfirm}
        onCancel={confirmState?.onCancel}
      />
    </div>
    </BasketProvider>
    </ChartPrefsProvider>
    </PageLiveProvider>
    </IntradayPatchProvider>
  );
}

function TabBarTab({
  label,
  isActive,
  onClose,
  onClick,
  draggable,
  onDragStart,
  onDrop,
  mono,
  badge,
  rootRef,
  title,
}) {
  return (
    <div
      ref={rootRef}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={e => e.preventDefault()}
      onDrop={onDrop}
      onClick={onClick}
      title={title}
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
      }}
      >
        {label}
      </span>
      {badge != null && badge > 1 && (
        <span
          aria-hidden
          style={{
            flexShrink: 0,
            marginLeft: 4,
            fontSize: 9,
            fontWeight: 700,
            color: isActive ? 'var(--accent-blue)' : 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {badge}
        </span>
      )}
      {onClose && (
        <button
          onClick={e => { e.stopPropagation(); onClose(); }}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16, flexShrink: 0, background: 'none', color: 'var(--text-muted)', fontSize: 14, marginLeft: 4 }}
          onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)'; }}
          onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; }}
        >
          ×
        </button>
      )}
    </div>
  );
}

const CHART_STACK_MENU_Z = 10060;

function ChartStackTab({
  stack,
  stackIdx,
  isActive,
  onSwitchStack,
  onCloseActive,
  onSwitchChart,
  onCloseChart,
  draggable,
  onDragStart,
  onDrop,
  getFaceLabel,
  getItemLabel,
  stackNoun = 'charts',
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuRect, setMenuRect] = useState(null);
  const anchorRef = useRef(null);
  const menuRef = useRef(null);
  const leaveTimerRef = useRef(null);
  const dragOriginRef = useRef(null);
  const [dragEnabled, setDragEnabled] = useState(false);

  const face = activeChart(stack);
  const count = stack?.charts?.length || 0;
  const stacked = count > 1;
  const labelFor = useCallback((entry) => {
    if (typeof getItemLabel === 'function') return getItemLabel(entry);
    if (typeof getFaceLabel === 'function') return getFaceLabel(entry);
    return entry?.symbol || '—';
  }, [getFaceLabel, getItemLabel]);
  const faceLabel = (typeof getFaceLabel === 'function' ? getFaceLabel(face) : null)
    || face?.symbol
    || '—';

  const clearLeaveTimer = useCallback(() => {
    if (leaveTimerRef.current != null) {
      window.clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
  }, []);

  const openMenu = useCallback(() => {
    if (!stacked) return;
    clearLeaveTimer();
    setMenuOpen(true);
  }, [stacked, clearLeaveTimer]);

  const scheduleCloseMenu = useCallback(() => {
    clearLeaveTimer();
    leaveTimerRef.current = window.setTimeout(() => {
      setMenuOpen(false);
      leaveTimerRef.current = null;
    }, 140);
  }, [clearLeaveTimer]);

  const closeMenu = useCallback(() => {
    clearLeaveTimer();
    setMenuOpen(false);
  }, [clearLeaveTimer]);

  useLayoutEffect(() => {
    if (!menuOpen || !stacked) {
      setMenuRect(null);
      return undefined;
    }
    const update = () => {
      const el = anchorRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const width = Math.max(160, Math.min(280, Math.max(r.width, 180)));
      const pad = 8;
      const left = Math.min(
        Math.max(pad, r.left),
        Math.max(pad, window.innerWidth - width - pad),
      );
      setMenuRect({ top: r.bottom + 2, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [menuOpen, stacked, count, faceLabel]);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDoc = (e) => {
      const t = e.target;
      if (anchorRef.current?.contains(t)) return;
      if (menuRef.current?.contains(t)) return;
      closeMenu();
    };
    const onKey = (e) => {
      if (e.key === 'Escape') closeMenu();
    };
    // Use click (not mousedown) so menu item selection can complete first.
    document.addEventListener('click', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('click', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen, closeMenu]);

  useEffect(() => () => clearLeaveTimer(), [clearLeaveTimer]);

  // Stacked tabs: only enable HTML5 drag after a short drag gesture so click/hover open the menu.
  useEffect(() => {
    if (!stacked) {
      setDragEnabled(Boolean(draggable));
      return undefined;
    }
    setDragEnabled(false);
    const onUp = () => {
      dragOriginRef.current = null;
      setDragEnabled(false);
    };
    window.addEventListener('mouseup', onUp);
    window.addEventListener('blur', onUp);
    return () => {
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('blur', onUp);
    };
  }, [stacked, draggable]);

  const onFaceMouseDown = (e) => {
    if (!stacked || !draggable || e.button !== 0) return;
    dragOriginRef.current = { x: e.clientX, y: e.clientY };
    const onMove = (ev) => {
      const origin = dragOriginRef.current;
      if (!origin) return;
      const dx = Math.abs(ev.clientX - origin.x);
      const dy = Math.abs(ev.clientY - origin.y);
      if (dx > 6 || dy > 6) {
        setDragEnabled(true);
        window.removeEventListener('mousemove', onMove);
      }
    };
    window.addEventListener('mousemove', onMove);
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mouseup', onUp);
  };

  const onFaceClick = (e) => {
    onSwitchStack();
    if (!stacked) return;
    e.stopPropagation();
    clearLeaveTimer();
    // Always open on click (do not toggle closed — hover may already have opened it).
    setMenuOpen(true);
  };

  const canDrag = Boolean(draggable) && !menuOpen && (!stacked || dragEnabled);

  const menu = stacked && menuOpen && menuRect
    ? createPortal(
      <div
        ref={menuRef}
        role="menu"
        data-cim="chart-stack-menu"
        aria-label={`Stacked ${stackNoun} (${count})`}
        onMouseEnter={openMenu}
        onMouseLeave={scheduleCloseMenu}
        style={{
          position: 'fixed',
          top: menuRect.top,
          left: menuRect.left,
          width: menuRect.width,
          zIndex: CHART_STACK_MENU_Z,
          maxHeight: 280,
          overflowY: 'auto',
          backgroundColor: 'var(--bg-secondary, #161b22)',
          border: '1px solid var(--border, #30363d)',
          borderRadius: 6,
          boxShadow: '0 10px 28px rgba(0,0,0,0.55)',
          padding: 4,
        }}
      >
        {stack.charts.map((chart, chartIdx) => {
          const selected = chartIdx === stack.activeIdx;
          const itemLabel = labelFor(chart);
          return (
            <div
              key={chart.id}
              role="menuitem"
              onMouseDown={(e) => {
                // Select on mousedown so outside-click handlers cannot steal the gesture.
                e.preventDefault();
                e.stopPropagation();
                onSwitchChart(stackIdx, chartIdx);
                closeMenu();
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '7px 10px',
                borderRadius: 4,
                cursor: 'pointer',
                backgroundColor: selected ? 'var(--bg-active, #2d333b)' : 'transparent',
                color: selected ? 'var(--text-primary, #e6edf3)' : 'var(--text-secondary, #8b949e)',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: selected ? 600 : 400,
                whiteSpace: 'nowrap',
              }}
              onMouseEnter={(e) => {
                if (!selected) e.currentTarget.style.backgroundColor = 'var(--bg-hover, #21262d)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = selected ? 'var(--bg-active, #2d333b)' : 'transparent';
              }}
            >
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>{itemLabel}</span>
              <button
                type="button"
                title={`Close ${itemLabel}`}
                onMouseDown={(e) => {
                  // Must handle on mousedown: parent menuitem also uses mousedown to switch,
                  // and that fires before click — so × never closed without this.
                  e.preventDefault();
                  e.stopPropagation();
                  onCloseChart(stackIdx, chartIdx);
                }}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 16,
                  height: 16,
                  flexShrink: 0,
                  background: 'none',
                  color: 'var(--text-muted)',
                  fontSize: 13,
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)'; }}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>,
      document.body,
    )
    : null;

  return (
    <div
      style={{ position: 'relative', height: '100%', flexShrink: 0 }}
      onMouseEnter={openMenu}
      onMouseLeave={scheduleCloseMenu}
      onMouseDown={onFaceMouseDown}
    >
      <TabBarTab
        rootRef={anchorRef}
        label={faceLabel}
        isActive={isActive}
        onClick={onFaceClick}
        onClose={onCloseActive}
        draggable={canDrag}
        mono
        badge={count}
        title={stacked ? `${count} ${stackNoun} stacked — hover or click to switch` : undefined}
        onDragStart={(e) => {
          if (!canDrag) {
            e.preventDefault();
            return;
          }
          onDragStart?.(e);
        }}
        onDrop={onDrop}
      />
      {menu}
    </div>
  );
}

function TabBar({
  view, chartTabs, activeTabIdx, indexTabs, activeIndexTab,
  constituentsStacks, activeConstituentsStackIdx,
  onDashboard, onIndices, onFunds, onWatchlist, onPortfolio, onPnL, onPotentialSwings, onMarketPulse, onMarketMovers, onMarketMap, onEarningsBeats, onSwitchChart, onCloseChart,
  onSwitchIndex, onCloseIndex, onSwitchConstituents, onCloseConstituents,
  onReorderChartTabs, onReorderConstituentsStacks, onOpenSectors, onOpenScheduler, onOpenSettings, onOpenAccount, onOpenKnowledgeBaseEditor, onOpenIssue, onOpenFeature, onOpenAbout, onOpenSupport,
  aggressiveCacheRam, maxChartTabs, onUpdateMaxChartTabs, cacheBusy, onToggleAggressiveCache, onClearCacheNow,
  onUpdatePriceVolume, onRepairIndexChartGaps, onUpdateIndicatorSnapshots, onUpdateSplitAdjustments, onSplitCatchupScan, splitPendingCount, onRefreshShareCounts, onRefreshEarningsPlusCache, onToggleUpdateProgress, updateRunning, updatePercent, settingsOpen, settingsRef,
  onRebuildIndicatorSnapshots,
  earningsPlusRefreshRunning,
  desktopCanRestartBackend, restartBackendBusy,
  desktopCanReloadFrontend, reloadFrontendBusy, onRestartBackendAndFrontendDev,
  onApplyCiMUpdate, cimUpdateBusy, appVersion, appBrandName = 'CiM',
  onRefresh,
  knowledgeBaseOpen,
  previewAccountMenu = false,
  showcaseWebClient = false,
  isWebBrowserUser = false,
  isWebBrowserHost = false,
  showDesktopAdminUi = false,
  showSchedulerMenu = false,
  onRefreshLivePrices,
  intradayRefreshBusy = false,
  healthState = 'loading',
  usersOnline = null,
  onOpenChart,
}) {
  const dragIdx     = useRef(null);
  const dragType    = useRef(null);
  const tabsScrollRef = useRef(null);
  useWheelHorizontalScroll(tabsScrollRef);
  const updateBtnRef = useRef(null);
  const updateMenuRef = useRef(null);
  const updateMenuWrapRef = useRef(null);
  const [updateMenuRect, setUpdateMenuRect] = useState(null);

  const toggleUpdateMenu = useCallback(() => {
    setUpdateMenuRect(prev => {
      if (prev) return null;
      const btn = updateBtnRef.current;
      if (!btn) return null;
      const r = btn.getBoundingClientRect();
      return { top: r.bottom + 4, left: Math.max(8, r.right - 280), width: 280 };
    });
  }, []);

  // Close Live Feed popover when Update menu opens (LiveFeedPopover listens via custom event).
  useEffect(() => {
    if (!updateMenuRect) return undefined;
    try {
      window.dispatchEvent(new CustomEvent('cim:live-feed-popover-close'));
    } catch { /* ignore */ }
    return undefined;
  }, [updateMenuRect]);

  useEffect(() => {
    if (knowledgeBaseOpen) setUpdateMenuRect(null);
  }, [knowledgeBaseOpen]);

  useEffect(() => {
    if (settingsOpen) setUpdateMenuRect(null);
  }, [settingsOpen]);

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
    if (
      dragType.current === 'constituents'
      && type === 'constituents'
      && dragIdx.current !== idx
      && typeof onReorderConstituentsStacks === 'function'
    ) {
      onReorderConstituentsStacks(dragIdx.current, idx);
    }
    dragIdx.current  = null;
    dragType.current = null;
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
      if (updateMenuWrapRef.current?.contains(e.target)) return;
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
        title={appVersion ? `${appBrandName} ${appVersion}` : appBrandName}
      >
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.02em' }}>
          {appBrandName}
        </span>
        {appVersion ? (
          <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {appVersion}
          </span>
        ) : null}
      </div>
      <div
        ref={tabsScrollRef}
        style={{ flex: 1, overflowX: 'auto', overflowY: 'hidden', display: 'flex', alignItems: 'stretch' }}
      >
        {/* Fixed nav tabs — order: NSE | Indices | Funds | Market Map | Market Pulse | Market Movers | Earnings | Watchlist | Portfolio | Potential Swings */}
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
        <div onClick={onFunds} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'funds' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'funds' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'funds' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'funds' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          Funds
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
        <div onClick={onPnL} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px', cursor: 'pointer',
          borderRight: '1px solid var(--border)',
          backgroundColor: view === 'pnl' ? 'var(--bg-tertiary)' : 'transparent',
          borderBottom: view === 'pnl' ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: view === 'pnl' ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: 12, fontWeight: view === 'pnl' ? 600 : 400,
          whiteSpace: 'nowrap', flexShrink: 0, userSelect: 'none',
        }}>
          P&amp;L
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
          <TabBarTab key={idx.symbol} label={idx.name} isActive={view === 'index_' + idx.symbol}
            onClick={() => onSwitchIndex(idx.symbol)} onClose={() => onCloseIndex(idx.symbol)}
            draggable={true} onDragStart={e => onDragStart(e, 'index', i)} onDrop={e => onDrop(e, 'index', i)} />
        ))}
        {(constituentsStacks || []).map((stack, idx) => {
          const face = activeChart(stack);
          return (
            <ChartStackTab
              key={stack.id}
              stack={stack}
              stackIdx={idx}
              isActive={Boolean(
                face?.symbol
                && view === 'constituents_' + face.symbol
                && idx === activeConstituentsStackIdx,
              )}
              onSwitchStack={() => onSwitchConstituents(idx)}
              onCloseActive={() => onCloseConstituents(idx)}
              onSwitchChart={onSwitchConstituents}
              onCloseChart={onCloseConstituents}
              getFaceLabel={(entry) => `${entry?.name || entry?.symbol || '—'} — Const.`}
              getItemLabel={(entry) => `${entry?.name || entry?.symbol || '—'} — Const.`}
              stackNoun="constituents"
              draggable
              onDragStart={e => onDragStart(e, 'constituents', idx)}
              onDrop={e => onDrop(e, 'constituents', idx)}
            />
          );
        })}
        {chartTabs.map((stack, idx) => (
          <ChartStackTab
            key={stack.id}
            stack={stack}
            stackIdx={idx}
            isActive={view === 'chart' && idx === activeTabIdx}
            onSwitchStack={() => onSwitchChart(idx)}
            onCloseActive={() => onCloseChart(idx)}
            onSwitchChart={onSwitchChart}
            onCloseChart={onCloseChart}
            draggable
            onDragStart={e => onDragStart(e, 'chart', idx)}
            onDrop={e => onDrop(e, 'chart', idx)}
          />
        ))}
      </div>

      <div style={{ display: 'flex', flexShrink: 0, alignItems: 'stretch' }}>
        {isWebBrowserUser && (
          <ServerStatusBar
            healthState={healthState}
            usersOnline={usersOnline}
            inline
          />
        )}
        <div style={{ display: 'flex', flexShrink: 0, alignItems: 'stretch', borderLeft: isWebBrowserUser ? undefined : '1px solid var(--border)' }}>
        {onRefresh && (
          <div
            onClick={onRefresh}
            title={
              view === 'market-pulse' ? 'Refresh market indices'
                : view === 'market-movers' ? 'Refresh market movers'
                : view === 'market-map' ? 'Refresh market map'
                : view === 'pnl' ? 'Refresh P&L prices (saved in this browser until Update)'
                : 'Refresh NSE / Portfolio table'
            }
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 12px', height: '100%', cursor: 'pointer', borderRight: '1px solid var(--border)', color: 'var(--text-muted)', fontSize: 12 }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.backgroundColor = 'transparent'; }}
          >↻ Refresh</div>
        )}
        <LiveFeedPopover
          knowledgeBaseOpen={knowledgeBaseOpen}
          settingsOpen={settingsOpen}
          onOpenChange={(isOpen) => { if (isOpen) setUpdateMenuRect(null); }}
        />
        <UniversalAlerts onOpenChart={onOpenChart} />
        <UniversalNotes />
        <div ref={updateMenuWrapRef} style={{ position: 'relative', flexShrink: 0, display: 'flex', alignItems: 'stretch' }}>
        <button
          ref={updateBtnRef}
          onClick={() => {
            if (showcaseWebClient) {
              if (!intradayRefreshBusy) onRefreshLivePrices && onRefreshLivePrices();
              return;
            }
            if (updateRunning) {
              onToggleUpdateProgress && onToggleUpdateProgress();
              return;
            }
            toggleUpdateMenu();
          }}
          title={
            showcaseWebClient
              ? 'Refresh prices in this browser only (not shared with other sessions)'
              : updateRunning
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
            background: updateMenuRect ? 'var(--bg-hover)' : 'transparent',
            flexShrink: 0,
            opacity: showcaseWebClient && intradayRefreshBusy ? 0.7 : 1,
          }}
          disabled={showcaseWebClient && intradayRefreshBusy}
        >
          {!showcaseWebClient && !updateRunning && splitPendingCount > 0 && (
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
          <span style={{ position: 'relative', zIndex: 1, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {showcaseWebClient
              ? (intradayRefreshBusy ? 'Refreshing…' : 'Refresh prices')
              : (updateRunning ? `Updating ${Math.round(updatePercent || 0)}%` : 'Update')}
            {isWebBrowserHost && !updateRunning && (
              <span style={{
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                padding: '2px 5px',
                borderRadius: 3,
                backgroundColor: 'rgba(56,139,253,0.2)',
                color: 'var(--accent-blue, #388bfd)',
                border: '1px solid rgba(56,139,253,0.35)',
              }}>
                Admin
              </span>
            )}
          </span>
        </button>
        {!showcaseWebClient && !updateRunning && updateMenuRect && (
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
              onClick={() => { setUpdateMenuRect(null); onRepairIndexChartGaps && onRepairIndexChartGaps(); }}
              title="Scan all index charts for missing daily bars and backfill gaps from NSE (Yahoo fallback). Run when index charts show long flat gaps."
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)', borderTop: '1px solid var(--border-light)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Repair Index Chart Gaps
            </div>
            {showDesktopAdminUi && (
              <>
            {showSchedulerMenu && onOpenScheduler && (
            <div
              onClick={() => { setUpdateMenuRect(null); onOpenScheduler(); }}
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)', borderTop: '1px solid var(--border-light)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Admin Scheduler…
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>Chart data fetch, filter rebuild, EOD, splits, earnings+</div>
            </div>
            )}
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
              title="Refresh issued share counts (Yahoo → Screener) — market cap = shares × price. Run weekly or after splits."
              style={{ padding: '9px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-primary)', borderTop: '1px solid var(--border-light)' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              Refresh share counts (market cap basis)
            </div>
              </>
            )}
          </div>
        )}
        </div>
        <div ref={settingsRef} style={{ position: 'relative', flexShrink: 0 }}>
        <div onClick={onOpenSettings} title="Settings"
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 36, height: '100%', cursor: 'pointer',
            color: (showDesktopAdminUi && aggressiveCacheRam) ? '#f85149' : (settingsOpen ? 'var(--text-primary)' : 'var(--text-muted)'), fontSize: 16, flexShrink: 0,
            backgroundColor: settingsOpen ? 'var(--bg-hover)' : 'transparent',
          }}
          onMouseEnter={e => { e.currentTarget.style.color = (showDesktopAdminUi && aggressiveCacheRam) ? '#f85149' : 'var(--text-primary)'; e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
          onMouseLeave={e => { if (!settingsOpen) { e.currentTarget.style.color = (showDesktopAdminUi && aggressiveCacheRam) ? '#f85149' : 'var(--text-muted)'; e.currentTarget.style.backgroundColor = 'transparent'; } }}
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
            {onOpenAccount && (
              <MenuItem
                icon="👤"
                label={previewAccountMenu ? 'Account (preview)' : 'Account'}
                onClick={onOpenAccount}
              />
            )}
            {showSchedulerMenu && onOpenScheduler && (
              <MenuItem
                icon="🕐"
                label="Admin Scheduler"
                onClick={onOpenScheduler}
              />
            )}
            <div
              style={{
                padding: '8px 12px',
                borderBottom: '1px solid var(--border-light)',
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 16, textAlign: 'center' }}>📈</span>
                Max Chart Stacks
              </span>
              <select
                value={maxChartTabs}
                onChange={e => onUpdateMaxChartTabs(Number(e.target.value))}
                disabled={cacheBusy}
                style={{ fontSize: 12 }}
              >
                {[1, 3, 5, 8, 10, 15].map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
            {showDesktopAdminUi && (
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
            )}
            <MenuItem icon="🧹" label="Clear Cache Now" onClick={onClearCacheNow} disabled={cacheBusy} />
            {showDesktopAdminUi && (
              <>
                <MenuItem
                  icon="✨"
                  label={earningsPlusRefreshRunning ? 'Refreshing Earnings + Cache…' : 'Refresh Earnings + Cache (this month)'}
                  onClick={onRefreshEarningsPlusCache}
                  disabled={cacheBusy || earningsPlusRefreshRunning}
                />
              </>
            )}
            {desktopCanRestartBackend && desktopCanReloadFrontend && (
              <MenuItem
                icon="🔁"
                label={(restartBackendBusy || reloadFrontendBusy) ? 'Restarting Backend & Frontend (Dev)…' : 'Restart Backend & Frontend (Dev)'}
                onClick={onRestartBackendAndFrontendDev}
                disabled={restartBackendBusy || reloadFrontendBusy || updateRunning}
              />
            )}
            {onOpenSectors && (
              <MenuItem icon="🗂" label="Data Management" onClick={onOpenSectors} />
            )}
            {!isWebBrowserUser && (
              <MenuItem
                icon="⬆"
                label={cimUpdateBusy ? 'Updating App…' : 'Update App'}
                onClick={onApplyCiMUpdate}
                disabled={cacheBusy || cimUpdateBusy || updateRunning}
              />
            )}
            <MenuItem icon="🐞" label="Report Issue" onClick={onOpenIssue} />
            <MenuItem icon="💡" label="Feature Request" onClick={onOpenFeature} />
            <MenuItem icon="❤" label="Support the Development" onClick={onOpenSupport} />
            <MenuItem icon="ℹ" label="About Charts in Motion" onClick={onOpenAbout} />
            {onOpenKnowledgeBaseEditor && (
              <MenuItem icon="📖" label="Edit Knowledge Base" onClick={onOpenKnowledgeBaseEditor} />
            )}
          </div>
        )}
      </div>
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
