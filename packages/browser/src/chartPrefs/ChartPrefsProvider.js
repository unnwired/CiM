import React, {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import {
  applyChartPrefsToLegacyKeys,
  formatChartPrefsSummary,
  loadChartPrefs,
  hasStoredChartPrefs,
  migrateLegacyToEmailPrefs,
  resetChartPrefsToDefaults,
  saveChartPrefs,
  snapshotGlobalChartPrefsFromLegacy,
  EMA_PREFS_UPDATED_EVENT,
  PANELS_PREFS_UPDATED_EVENT,
  VOLUME_PREFS_UPDATED_EVENT,
} from './chartPrefsStore';
import { saveWebPageLayoutNow } from './chartPageLayout';

const ChartPrefsContext = createContext(null);

export function useChartPrefsContext() {
  return useContext(ChartPrefsContext);
}

export function ChartPrefsProvider({ enabled, email, children }) {
  const [prefsVersion, setPrefsVersion] = useState(0);
  const layoutTimersRef = useRef({});
  const globalTimerRef = useRef(null);
  const prevEmailRef = useRef(null);

  useEffect(() => {
    if (!enabled || !email) return;

    const prevEmail = prevEmailRef.current;
    const switchedUser = prevEmail != null && prevEmail !== email;
    prevEmailRef.current = email;

    const hadPrefs = hasStoredChartPrefs(email);
    migrateLegacyToEmailPrefs(email);
    const justMigrated = !hadPrefs && hasStoredChartPrefs(email);

    if (switchedUser || justMigrated) {
      applyChartPrefsToLegacyKeys(loadChartPrefs(email));
    } else {
      saveChartPrefs(email, snapshotGlobalChartPrefsFromLegacy());
    }
    setPrefsVersion((v) => v + 1);
  }, [enabled, email]);

  const flushGlobalSave = useCallback(() => {
    if (!enabled || !email) return;
    saveChartPrefs(email, snapshotGlobalChartPrefsFromLegacy());
    setPrefsVersion((v) => v + 1);
  }, [enabled, email]);

  useEffect(() => {
    if (!enabled || !email) return;
    const scheduleGlobal = () => {
      if (globalTimerRef.current) clearTimeout(globalTimerRef.current);
      globalTimerRef.current = setTimeout(flushGlobalSave, 0);
    };
    window.addEventListener(EMA_PREFS_UPDATED_EVENT, scheduleGlobal);
    window.addEventListener(VOLUME_PREFS_UPDATED_EVENT, scheduleGlobal);
    window.addEventListener(PANELS_PREFS_UPDATED_EVENT, scheduleGlobal);
    return () => {
      window.removeEventListener(EMA_PREFS_UPDATED_EVENT, scheduleGlobal);
      window.removeEventListener(VOLUME_PREFS_UPDATED_EVENT, scheduleGlobal);
      window.removeEventListener(PANELS_PREFS_UPDATED_EVENT, scheduleGlobal);
      if (globalTimerRef.current) clearTimeout(globalTimerRef.current);
    };
  }, [enabled, email, flushGlobalSave]);

  useEffect(() => {
    if (!enabled || !email) return undefined;
    const onPageHide = () => flushGlobalSave();
    window.addEventListener('pagehide', onPageHide);
    return () => window.removeEventListener('pagehide', onPageHide);
  }, [enabled, email, flushGlobalSave]);

  const scheduleLayoutSave = useCallback((pageId, snapshot) => {
    if (!enabled || !email || !pageId) return;
    if (layoutTimersRef.current[pageId]) clearTimeout(layoutTimersRef.current[pageId]);
    layoutTimersRef.current[pageId] = setTimeout(() => {
      saveWebPageLayoutNow(email, pageId, snapshot);
      setPrefsVersion((v) => v + 1);
    }, 500);
  }, [enabled, email]);

  const savePageLayoutNow = useCallback((pageId, snapshot) => {
    if (!enabled || !email || !pageId) return;
    if (layoutTimersRef.current[pageId]) clearTimeout(layoutTimersRef.current[pageId]);
    saveWebPageLayoutNow(email, pageId, snapshot);
    setPrefsVersion((v) => v + 1);
  }, [enabled, email]);

  const saveNow = useCallback(() => {
    flushGlobalSave();
    Object.keys(layoutTimersRef.current).forEach((pageId) => {
      if (layoutTimersRef.current[pageId]) clearTimeout(layoutTimersRef.current[pageId]);
    });
    setPrefsVersion((v) => v + 1);
  }, [flushGlobalSave]);

  const resetToDefaults = useCallback(() => {
    if (!enabled || !email) return;
    resetChartPrefsToDefaults(email);
    setPrefsVersion((v) => v + 1);
  }, [enabled, email]);

  const summary = useMemo(() => {
    if (!enabled || !email) return null;
    return formatChartPrefsSummary(loadChartPrefs(email));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, email, prefsVersion]);

  const value = useMemo(() => ({
    enabled: !!enabled,
    email: email || null,
    scheduleLayoutSave,
    savePageLayoutNow,
    saveNow,
    resetToDefaults,
    summary,
  }), [enabled, email, scheduleLayoutSave, savePageLayoutNow, saveNow, resetToDefaults, summary]);

  return (
    <ChartPrefsContext.Provider value={value}>
      {children}
    </ChartPrefsContext.Provider>
  );
}
