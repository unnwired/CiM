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
  applyPatchToEarningsRow,
  overlayRows,
} from './patchOverlay';

/**
 * Overlay session quotes onto server rows.
 * Snapshots apply whenever intraday is enabled and a quote exists (same source as chart),
 * not only after "Refresh prices" sets page live.
 */
export function usePatchOverlay(pageId) {
  const intraday = useIntradayPatchOptional();
  const { liveActive } = usePageLive(pageId);
  const liveContextActive = !!intraday?.isLiveContextActive?.(pageId);
  const intradayOn = !!intraday?.enabled;
  const pageLiveOn = liveActive || liveContextActive;
  const refreshTick = intraday?.refreshTick ?? 0;

  const getSnapshot = useCallback((symbol) => {
    if (!intradayOn || !intraday?.getSymbolSnapshot) return null;
    return intraday.getSymbolSnapshot(symbol);
  }, [intradayOn, intraday, refreshTick]);

  const overlayStockRow = useCallback((row, symbol) => {
    if (!intradayOn || !row) return row;
    const sym = String(symbol || row.Symbol || row.symbol || '').trim().toUpperCase();
    const snap = getSnapshot(sym);
    return snap ? applyPatchToStockRow(row, snap) : row;
  }, [intradayOn, getSnapshot]);

  const overlayIndexRow = useCallback((row) => {
    if (!intradayOn || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToIndexRow(row, snap) : row;
  }, [intradayOn, getSnapshot]);

  const overlayMoversRow = useCallback((row) => {
    if (!intradayOn || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToMoversRow(row, snap) : row;
  }, [intradayOn, getSnapshot]);

  const overlayMapStock = useCallback((row) => {
    if (!intradayOn || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToMapStock(row, snap) : row;
  }, [intradayOn, getSnapshot]);

  const overlayMapIndexSummary = useCallback((row) => {
    if (!intradayOn || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToMapIndexSummary(row, snap) : row;
  }, [intradayOn, getSnapshot]);

  const overlayGenericRow = useCallback((row) => {
    if (!intradayOn || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToGenericQuoteRow(row, snap) : row;
  }, [intradayOn, getSnapshot]);

  const overlayPnlRow = useCallback((row) => {
    if (!intradayOn || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToPnlRow(row, snap) : row;
  }, [intradayOn, getSnapshot]);

  const overlayEarningsRow = useCallback((row) => {
    if (!intradayOn || !row) return row;
    const snap = getSnapshot(row.symbol);
    return snap ? applyPatchToEarningsRow(row, snap) : row;
  }, [intradayOn, getSnapshot]);

  const overlayStockRows = useCallback((rows) => (
    overlayRows(rows, (r) => r.Symbol || r.symbol, applyPatchToStockRow, getSnapshot)
  ), [getSnapshot]);

  const overlayIndexRows = useCallback((rows) => (
    overlayRows(rows, (r) => r.symbol, applyPatchToIndexRow, getSnapshot)
  ), [getSnapshot]);

  const overlayMoversRows = useCallback((rows) => (
    overlayRows(rows, (r) => r.symbol, applyPatchToMoversRow, getSnapshot)
  ), [getSnapshot]);

  const overlayMapStocks = useCallback((rows) => (
    overlayRows(rows, (r) => r.symbol, applyPatchToMapStock, getSnapshot)
  ), [getSnapshot]);

  const overlayPnlRows = useCallback((rows) => (
    overlayRows(rows, (r) => r.symbol, applyPatchToPnlRow, getSnapshot)
  ), [getSnapshot]);

  const overlayEarningsRows = useCallback((rows) => (
    overlayRows(rows, (r) => r.symbol, applyPatchToEarningsRow, getSnapshot)
  ), [getSnapshot]);

  const patchCount = useMemo(
    () => (intradayOn ? Object.keys(intraday?.patchBlob || {}).length : 0),
    [intradayOn, intraday?.patchBlob, refreshTick],
  );

  return {
    enabled: intradayOn,
    liveActive: pageLiveOn,
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
    overlayEarningsRow,
    overlayStockRows,
    overlayIndexRows,
    overlayMoversRows,
    overlayMapStocks,
    overlayPnlRows,
    overlayEarningsRows,
  };
}
