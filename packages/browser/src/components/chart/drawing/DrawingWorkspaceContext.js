import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { DEFAULT_LINE_COLOR, DEFAULT_LINE_WIDTH } from './drawingTypes';

const PREFS_KEY = 'nsePulse.drawings.workspacePrefs.v1';

function loadPrefs(workspaceId) {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    const j = raw ? JSON.parse(raw) : {};
    const w = j[workspaceId] || {};
    return {
      favorites: Array.isArray(w.favorites) ? w.favorites : [],
      toolbarCollapsed: w.toolbarCollapsed !== false,
      linesExpanded: !!w.linesExpanded,
      floatOpen: !!w.floatOpen,
    };
  } catch {
    return { favorites: [], toolbarCollapsed: true, linesExpanded: false, floatOpen: false };
  }
}

function savePrefs(workspaceId, next) {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    const all = raw ? JSON.parse(raw) : {};
    all[workspaceId] = next;
    localStorage.setItem(PREFS_KEY, JSON.stringify(all));
  } catch {}
}

const Ctx = createContext(null);

/**
 * Single drawing toolbar + which chart receives new drawings (focus).
 * @param {{ children: React.ReactNode, workspaceId?: string }} props
 */
export function DrawingWorkspaceProvider({ children, workspaceId = 'default' }) {
  const chartApisRef = useRef({});
  const [focusedScopeId, setFocusedScopeId] = useState(null);
  const [toolbarTick, setToolbarTick] = useState(0);

  const [activeTool, setActiveToolState] = useState(null);
  const [lineColor, setLineColorState] = useState(DEFAULT_LINE_COLOR);
  const [lineWidth, setLineWidthState] = useState(DEFAULT_LINE_WIDTH);

  const [prefs, setPrefs] = useState(() => loadPrefs(workspaceId));

  const persistPartial = useCallback(
    (partial) => {
      setPrefs((prev) => {
        const next = { ...prev, ...partial };
        savePrefs(workspaceId, next);
        return next;
      });
    },
    [workspaceId],
  );

  const setToolbarCollapsed = useCallback((v) => persistPartial({ toolbarCollapsed: !!v }), [persistPartial]);
  const setLinesExpanded = useCallback((v) => persistPartial({ linesExpanded: !!v }), [persistPartial]);
  const setFloatOpen = useCallback((v) => persistPartial({ floatOpen: !!v }), [persistPartial]);
  const setFavorites = useCallback(
    (updater) => {
      setPrefs((prev) => {
        const nextF = typeof updater === 'function' ? updater(prev.favorites) : updater;
        const next = { ...prev, favorites: nextF };
        savePrefs(workspaceId, next);
        return next;
      });
    },
    [workspaceId],
  );

  const setActiveTool = useCallback((t) => setActiveToolState(t), []);
  const setLineColor = useCallback((c) => setLineColorState(c), []);
  const setLineWidth = useCallback((w) => setLineWidthState(w), []);

  useEffect(() => {
    const onExternalToolPick = (e) => {
      const tool = e?.detail?.tool;
      if (typeof tool === 'string' || tool === null) {
        setActiveToolState(tool || null);
      }
    };
    window.addEventListener('cim-drawing-set-tool', onExternalToolPick);
    return () => window.removeEventListener('cim-drawing-set-tool', onExternalToolPick);
  }, []);

  const mountChart = useCallback((scopeId, api) => {
    if (!scopeId) return () => {};
    chartApisRef.current[scopeId] = api;
    return () => {
      delete chartApisRef.current[scopeId];
      setFocusedScopeId((cur) => (cur === scopeId ? null : cur));
    };
  }, []);

  const notifyToolbar = useCallback(() => setToolbarTick((x) => x + 1), []);

  const clearFocusedDrawings = useCallback(() => {
    const api = chartApisRef.current[focusedScopeId];
    if (api?.clearAll) api.clearAll();
    notifyToolbar();
  }, [focusedScopeId, notifyToolbar]);

  const deleteFocusedSelected = useCallback(() => {
    const api = chartApisRef.current[focusedScopeId];
    if (api?.deleteSelected) api.deleteSelected();
    notifyToolbar();
  }, [focusedScopeId, notifyToolbar]);

  const focusedHasSelection = useMemo(() => {
    void toolbarTick;
    const api = focusedScopeId ? chartApisRef.current[focusedScopeId] : null;
    return !!(api?.hasSelection?.());
  }, [focusedScopeId, toolbarTick]);

  const value = useMemo(
    () => ({
      workspaceId,
      focusedScopeId,
      setFocusedScopeId,
      mountChart,
      notifyToolbar,
      activeTool,
      setActiveTool,
      lineColor,
      setLineColor,
      lineWidth,
      setLineWidth,
      favorites: prefs.favorites,
      setFavorites,
      toolbarCollapsed: prefs.toolbarCollapsed,
      setToolbarCollapsed,
      linesExpanded: prefs.linesExpanded,
      setLinesExpanded,
      floatOpen: prefs.floatOpen,
      setFloatOpen,
      clearFocusedDrawings,
      deleteFocusedSelected,
      focusedHasSelection,
    }),
    [
      workspaceId,
      focusedScopeId,
      mountChart,
      notifyToolbar,
      activeTool,
      lineColor,
      lineWidth,
      prefs.favorites,
      prefs.toolbarCollapsed,
      prefs.linesExpanded,
      prefs.floatOpen,
      setFavorites,
      setToolbarCollapsed,
      setLinesExpanded,
      setFloatOpen,
      clearFocusedDrawings,
      deleteFocusedSelected,
      focusedHasSelection,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDrawingWorkspace() {
  return useContext(Ctx);
}
