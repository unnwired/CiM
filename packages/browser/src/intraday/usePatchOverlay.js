import { useCallback, useMemo } from 'react';
import { useIntradayPatchOptional } from './useIntradayPatch';
import { usePageLive } from './pageLiveContext';
import {
  applyPatchToGenericQuoteRow,
  applyPatchToIndexRow,
  applyPatchToMapIndexSummary,
  applyPatchToMapStock,
  applyPatchToMoversRow,
  applyPatchToPnlRow,
  applyPatchToStockRow,
  overlayRows,
} from './patchOverlay';

/** Overlay session quotes onto server rows after explicit Refresh prices on this page. */
export function usePatchOverlay(pageId) {
  const intraday = useIntradayPatchOptional();
  const { liveActive } = usePageLive(pageId);
  const enabled = !!intraday?.enabled && liveActive;
  const refreshTick = intraday?.refreshTick ?? 0;

  const getSnapshot = useCallback((symbol) => {
    if (!enabled || !intraday?.getSymbolSnapshot) return null;
    return intraday.getSymbolSnapshot(symbol);
  }, [enabled, intraday, refreshTick]);

  const overlayStockRow = useCallback((row, symbol) => {
    if (!enabled || !row) return row;
    const sym = String(symbol || row.Symbol || row.symbol || '').trim().toUpperCase();
    const snap = getSnapshot(sym);
    return snap ? applyPatchToStockRow(row, snap) : row;
  }, [enabled, getSnapshot]);

  const overlayIndexRow = useCallback((row) => {
    if (!enabled || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToIndexRow(row, snap) : row;
  }, [enabled, getSnapshot]);

  const overlayMoversRow = useCallback((row) => {
    if (!enabled || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToMoversRow(row, snap) : row;
  }, [enabled, getSnapshot]);

  const overlayMapStock = useCallback((row) => {
    if (!enabled || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToMapStock(row, snap) : row;
  }, [enabled, getSnapshot]);

  const overlayMapIndexSummary = useCallback((row) => {
    if (!enabled || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToMapIndexSummary(row, snap) : row;
  }, [enabled, getSnapshot]);

  const overlayGenericRow = useCallback((row) => {
    if (!enabled || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToGenericQuoteRow(row, snap) : row;
  }, [enabled, getSnapshot]);

  const overlayPnlRow = useCallback((row) => {
    if (!enabled || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToPnlRow(row, snap) : row;
  }, [enabled, getSnapshot]);

  const overlayStockRows = useCallback((rows) => (
    overlayRows(rows, (r) => r.Symbol || r.symbol, applyPatchToStockRow, getSnapshot)
  ), [getSnapshot, enabled]);

  const overlayIndexRows = useCallback((rows) => (
    overlayRows(rows, (r) => r.symbol, applyPatchToIndexRow, getSnapshot)
  ), [getSnapshot, enabled]);

  const overlayMoversRows = useCallback((rows) => (
    overlayRows(rows, (r) => r.symbol, applyPatchToMoversRow, getSnapshot)
  ), [getSnapshot, enabled]);

  const overlayMapStocks = useCallback((rows) => (
    overlayRows(rows, (r) => r.symbol, applyPatchToMapStock, getSnapshot)
  ), [getSnapshot, enabled]);

  const overlayPnlRows = useCallback((rows) => (
    overlayRows(rows, (r) => r.symbol, applyPatchToPnlRow, getSnapshot)
  ), [getSnapshot, enabled]);

  const patchCount = useMemo(
    () => (enabled ? Object.keys(intraday?.patchBlob || {}).length : 0),
    [enabled, intraday?.patchBlob, refreshTick],
  );

  return {
    enabled,
    liveActive,
    refreshTick,
    patchCount,
    getSnapshot,
    overlayStockRow,
    overlayIndexRow,
    overlayMoversRow,
    overlayMapStock,
    overlayMapIndexSummary,
    overlayGenericRow,
    overlayPnlRow,
    overlayStockRows,
    overlayIndexRows,
    overlayMoversRows,
    overlayMapStocks,
    overlayPnlRows,
  };
}
