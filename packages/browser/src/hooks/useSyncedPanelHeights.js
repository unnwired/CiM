import { useCallback, useEffect, useRef, useState } from 'react';
import { pickIndicatorPanelFields } from '../chartPrefs/chartPageLayout';
import { loadPersistedIndicatorPanelHeights } from '../chartPrefs/indicatorPanelHeightsStore';

export const DEFAULT_PANEL_HEIGHTS = { stochrsi: 130, macd: 130 };

/** Pixel tolerance for the divider being dragged (release only). */
export const PANEL_HEIGHT_DIVIDER_SNAP_THRESHOLD = 12;

export function normalizePanelHeights(raw, fallback = DEFAULT_PANEL_HEIGHTS) {
  return {
    stochrsi: Number(raw?.stochrsi ?? fallback?.stochrsi ?? DEFAULT_PANEL_HEIGHTS.stochrsi),
    macd: Number(raw?.macd ?? fallback?.macd ?? DEFAULT_PANEL_HEIGHTS.macd),
  };
}

export function columnCountForChartLayout(layout) {
  if (layout === '2h') return 2;
  if (layout === '3h' || layout === '3s') return 3;
  if (layout === '4h') return 4;
  return 1;
}

/** Y position of one horizontal resize handle from the top of the chart column. */
export function edgeDividerY(
  upperKey,
  heights,
  containerHeight,
  panelKeys,
  handleH = 4,
  defaultH = 130,
) {
  if (!containerHeight || containerHeight <= 0 || !panelKeys?.length) return null;
  const indicatorTotal = panelKeys.reduce(
    (sum, k) => sum + (heights[k] ?? defaultH) + handleH,
    0,
  );
  const priceH = Math.max(0, containerHeight - indicatorTotal);
  if (upperKey === 'price') return priceH;
  if (upperKey === 'stochrsi') {
    return priceH + handleH + (heights.stochrsi ?? defaultH);
  }
  return null;
}

function allowedSnapTargets(columnIndex, columnCount, leftNeighbor, rightNeighbor) {
  const targets = [];
  if (columnIndex === 0 && rightNeighbor) {
    targets.push(normalizePanelHeights(rightNeighbor));
  } else if (columnIndex === columnCount - 1 && leftNeighbor) {
    targets.push(normalizePanelHeights(leftNeighbor));
  } else {
    if (leftNeighbor) targets.push(normalizePanelHeights(leftNeighbor));
    if (rightNeighbor) targets.push(normalizePanelHeights(rightNeighbor));
  }
  return targets;
}

/**
 * On mouse-up only: if the dragged divider is close to the same divider on an
 * allowed neighbor, copy that neighbor's heights. Otherwise leave as-is.
 */
export function snapDraggedColumnOnEdgeRelease(
  dragged,
  columnIndex,
  columnCount,
  leftNeighbor,
  rightNeighbor,
  upperKey,
  options = {},
) {
  const {
    containerHeight = 0,
    panelKeys = ['stochrsi', 'macd'],
    handleH = 4,
    defaultH = 130,
    dividerThreshold = PANEL_HEIGHT_DIVIDER_SNAP_THRESHOLD,
  } = options;

  if (columnCount <= 1 || !upperKey || containerHeight <= 0) {
    return normalizePanelHeights(dragged);
  }

  const d = normalizePanelHeights(dragged);
  const draggedY = edgeDividerY(upperKey, d, containerHeight, panelKeys, handleH, defaultH);
  if (draggedY == null) return d;

  const targets = allowedSnapTargets(columnIndex, columnCount, leftNeighbor, rightNeighbor);
  if (!targets.length) return d;

  let bestTarget = null;
  let bestDist = Infinity;
  for (const target of targets) {
    const targetY = edgeDividerY(upperKey, target, containerHeight, panelKeys, handleH, defaultH);
    if (targetY == null) continue;
    const dist = Math.abs(draggedY - targetY);
    if (dist < bestDist) {
      bestDist = dist;
      bestTarget = target;
    }
  }

  if (!bestTarget || bestDist > dividerThreshold) return d;
  return { ...bestTarget };
}

/** Props bundle for ChartContainer / IndexChartContainer in multi-view layouts. */
export function multiColumnHeightProps({
  chartLayout,
  columnIndex,
  columnCount,
  getPanelHeights,
  heightsRevision = 0,
}) {
  const count = columnCount ?? columnCountForChartLayout(chartLayout);
  const multi = count > 1;
  return {
    independentHeights: multi,
    columnCount: count,
    columnIndex,
    neighborHeightsLeft: multi && columnIndex > 0 ? getPanelHeights(columnIndex - 1) : null,
    neighborHeightsRight: multi && columnIndex < count - 1 ? getPanelHeights(columnIndex + 1) : null,
    panelHeights: getPanelHeights(columnIndex),
    heightsRevision,
  };
}

/** Per-column heights: independent drag, optional snap on release. */
export function useSyncedPanelHeights({ columnCount = 1, localStorageKey } = {}) {
  const [heightsRevision, setHeightsRevision] = useState(0);
  const [panelHeightsByColumn, setPanelHeightsByColumn] = useState(() => {
    let base = normalizePanelHeights(loadPersistedIndicatorPanelHeights() || {});
    if (localStorageKey) {
      try {
        base = normalizePanelHeights(JSON.parse(localStorage.getItem(localStorageKey) || '{}'), base);
      } catch { /* default */ }
    }
    return ensureColumnCount([base], columnCount);
  });

  const heightsRef = useRef(panelHeightsByColumn[0] || { ...DEFAULT_PANEL_HEIGHTS });

  useEffect(() => {
    setPanelHeightsByColumn(prev => ensureColumnCount(prev, columnCount));
  }, [columnCount]);

  useEffect(() => {
    heightsRef.current = panelHeightsByColumn[0] || { ...DEFAULT_PANEL_HEIGHTS };
  }, [panelHeightsByColumn]);

  useEffect(() => {
    if (!localStorageKey) return;
    localStorage.setItem(localStorageKey, JSON.stringify(panelHeightsByColumn[0] || DEFAULT_PANEL_HEIGHTS));
  }, [localStorageKey, panelHeightsByColumn]);

  const getPanelHeights = useCallback((index = 0) => (
    panelHeightsByColumn[index] || panelHeightsByColumn[0] || { ...DEFAULT_PANEL_HEIGHTS }
  ), [panelHeightsByColumn]);

  const handleHeightsChange = useCallback((heights, columnIndex = 0) => {
    setPanelHeightsByColumn(prev => {
      const idx = Math.max(0, Math.min(columnIndex, prev.length - 1));
      return prev.map((col, i) => (
        i === idx ? normalizePanelHeights(heights, col) : { ...col }
      ));
    });
    setHeightsRevision(r => r + 1);
  }, []);

  const applyLayoutHeights = useCallback((data) => {
    if (!data || typeof data !== 'object') return;
    const fields = pickIndicatorPanelFields(data);
    const hasStoch = Number.isFinite(fields.stochrsi);
    const hasMacd = Number.isFinite(fields.macd);
    if (!hasStoch && !hasMacd) return;
    setPanelHeightsByColumn(prev => prev.map(col => ({
      ...col,
      ...(hasStoch ? { stochrsi: fields.stochrsi } : {}),
      ...(hasMacd ? { macd: fields.macd } : {}),
    })));
    setHeightsRevision(r => r + 1);
  }, []);

  return {
    panelHeightsByColumn,
    getPanelHeights,
    heightsRef,
    handleHeightsChange,
    applyLayoutHeights,
    heightsRevision,
  };
}

function ensureColumnCount(columns, count) {
  const n = Math.max(1, count);
  const next = columns.slice(0, n).map(col => ({ ...normalizePanelHeights(col) }));
  const seed = next[0] || { ...DEFAULT_PANEL_HEIGHTS };
  while (next.length < n) next.push({ ...seed });
  return next;
}
