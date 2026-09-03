import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

const API = '';

export default function useAdminJobStatus({
  pollIntervalMs = 1500,
  autoStart = true,
  onFinished = null,
} = {}) {
  const [status, setStatus] = useState(null);
  const [isPendingStart, setIsPendingStart] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const pollRef = useRef(null);
  const prevRunningRef = useRef(false);
  const pendingStartRef = useRef(false);
  const pendingStartUntilRef = useRef(0);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollOnce = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/admin/status`);
      const next = r.data;
      const isRunning = !!next?.running;
      const withinPendingWindow = pendingStartRef.current && Date.now() < pendingStartUntilRef.current;
      setStatus(next);
      if (prevRunningRef.current && !isRunning) {
        setIsCancelling(false);
        onFinishedRef.current?.(next);
      }
      prevRunningRef.current = isRunning;
      if (isRunning && pendingStartRef.current) {
        pendingStartRef.current = false;
        pendingStartUntilRef.current = 0;
        setIsPendingStart(false);
      }
      if (!isRunning && !withinPendingWindow) {
        if (pendingStartRef.current) {
          pendingStartRef.current = false;
          pendingStartUntilRef.current = 0;
          setIsPendingStart(false);
        }
        // Keep polling in autoStart mode so externally started backend jobs
        // (or delayed job state transitions) are still reflected in UI.
        if (!autoStart) stopPolling();
      }
      return next;
    } catch {
      return null;
    }
  }, [autoStart, stopPolling]);

  const startPolling = useCallback(() => {
    stopPolling();
    pollOnce();
    pollRef.current = setInterval(pollOnce, pollIntervalMs);
  }, [pollIntervalMs, pollOnce, stopPolling]);

  const refreshStatus = useCallback(() => pollOnce(), [pollOnce]);

  const startAdminJob = useCallback(async (path, config = undefined) => {
    pendingStartRef.current = true;
    pendingStartUntilRef.current = Date.now() + 60000;
    setIsPendingStart(true);
    const r = await axios.post(`${API}${path}`, null, config);
    startPolling();
    return r?.data || null;
  }, [startPolling]);

  const startOhlcvUpdate = useCallback(async () => {
    await startAdminJob('/api/admin/fetch-ohlcv');
  }, [startAdminJob]);

  const startRepairIndexChartGaps = useCallback(async () => {
    await startAdminJob('/api/admin/repair-index-chart-gaps');
  }, [startAdminJob]);

  const startBuildBars4h = useCallback(async () => {
    await startAdminJob('/api/admin/build-bars-4h');
  }, [startAdminJob]);

  const startBuildBars30m = useCallback(async () => {
    await startAdminJob('/api/admin/build-bars-30m');
  }, [startAdminJob]);

  const startIndicatorSnapshotsUpdate = useCallback(async (daysBack = 1, options = {}) => {
    const params = { days_back: daysBack };
    if (typeof options.force === 'boolean') params.force = options.force;
    if (typeof options.deferHeavy === 'boolean') params.defer_heavy = options.deferHeavy;
    if (typeof options.scope === 'string' && options.scope.trim()) params.scope = options.scope.trim();
    if (Array.isArray(options.timeframes) && options.timeframes.length > 0) {
      params.timeframes = options.timeframes.join(',');
    }
    await startAdminJob('/api/admin/rebuild-indicator-snapshots-incremental', {
      params,
    });
  }, [startAdminJob]);

  const startSplitAdjustmentsApplyPending = useCallback(async () => {
    await startAdminJob('/api/admin/apply-split-adjustments', {
      params: { apply_only: true },
    });
  }, [startAdminJob]);

  const startSplitAdjustmentsScanFirst = useCallback(async (daysBack = 20) => {
    await startAdminJob('/api/admin/apply-split-adjustments', {
      params: { days_back: daysBack, scan_first: true, apply_only: false },
    });
  }, [startAdminJob]);

  const startSplitCatchupScan = useCallback(async (daysBack = 90) => {
    await startAdminJob('/api/admin/scan-stock-splits', {
      params: { days_back: daysBack, auto_apply: true },
    });
  }, [startAdminJob]);

  const fetchSplitWatchStatus = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/admin/split-watch-status`);
      return r.data;
    } catch {
      return null;
    }
  }, []);

  const startRefreshShareCounts = useCallback(async () => {
    await startAdminJob('/api/admin/fetch-issued-shares');
  }, [startAdminJob]);

  const cancelAdminJob = useCallback(async () => {
    if (!status?.running && !isPendingStart) return null;
    setIsCancelling(true);
    try {
      const r = await axios.post(`${API}/api/admin/cancel-job`);
      const next = await pollOnce();
      return r.data || next;
    } catch (err) {
      setIsCancelling(false);
      throw err;
    }
  }, [isPendingStart, pollOnce, status?.running]);

  const cancelQueuedJob = useCallback(async (id) => {
    await axios.post(`${API}/api/admin/job-queue/cancel`, { id });
    return pollOnce();
  }, [pollOnce]);

  const clearJobQueue = useCallback(async () => {
    await axios.post(`${API}/api/admin/job-queue/cancel`, { clear: true });
    return pollOnce();
  }, [pollOnce]);

  useEffect(() => {
    if (autoStart) startPolling();
    return () => stopPolling();
  }, [autoStart, startPolling, stopPolling]);

  return {
    status,
    isRunning: !!status?.running,
    isPendingStart,
    isCancelling: isCancelling || !!status?.cancel_requested,
    percent: status?.percent || 0,
    queued: Array.isArray(status?.queued) ? status.queued : [],
    startPolling,
    stopPolling,
    refreshStatus,
    startAdminJob,
    startOhlcvUpdate,
    startRepairIndexChartGaps,
    startBuildBars4h,
    startBuildBars30m,
    startIndicatorSnapshotsUpdate,
    startSplitAdjustmentsApplyPending,
    startSplitAdjustmentsScanFirst,
    startSplitCatchupScan,
    fetchSplitWatchStatus,
    startRefreshShareCounts,
    cancelAdminJob,
    cancelQueuedJob,
    clearJobQueue,
  };
}
