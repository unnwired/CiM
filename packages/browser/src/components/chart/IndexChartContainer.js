/* eslint-disable react-hooks/exhaustive-deps */
import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import ChartContainer from './ChartContainer';
import { CHART_DATA_UPDATED_EVENT, dispatchChromeIntroReadyOnce } from '../../chartEvents';

const API = '';

export default function IndexChartContainer({
  symbol, timeframe, emas, volumeVisible, visiblePanels, panelOrder,
  onTogglePanel, onMovePanel, onLastChange, onHeightsChange,
  panelHeights,
  columnIndex = 0,
  independentHeights = false,
  columnCount = 1,
  neighborHeightsLeft = null,
  neighborHeightsRight = null,
  heightsRevision = 0,
  onCrosshairMove, crosshairTime,
  liveToday = false,
  liveRefreshKey = null,
  drawingScopeId = null,
  drawingAutoFocus = true,
}) {
  const [chartData, setChartData] = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  const emaKey = emas.map(e => e.period).join(',');

  const reloadIndexChart = useCallback(() => {
    if (!symbol) return;
    setLoading(true);
    setError(null);
    setChartData(null);

    const emaPeriods = emas.map(e => e.period);
    const params = { timeframe };
    if (emaPeriods[0]) params.ema1 = emaPeriods[0];
    if (emaPeriods[1]) params.ema2 = emaPeriods[1];
    if (emaPeriods[2]) params.ema3 = emaPeriods[2];
    if (emaPeriods[3]) params.ema4 = emaPeriods[3];

    axios.get(`${API}/api/index-chart/${encodeURIComponent(symbol)}`, { params })
      .then(r => {
        setChartData(r.data);
        setLoading(false);
        if (r.data?.bars?.length) dispatchChromeIntroReadyOnce();
      })
      .catch(err => {
        const detail = err?.response?.data?.detail;
        const msg = typeof detail === 'string' && detail.trim()
          ? detail
          : (timeframe === '4H'
            ? '4H chart unavailable. Run Update after 15:30 IST. Upstox primary; Yahoo/NSE fallback.'
            : timeframe === '30m'
              ? '30m chart unavailable. Run Update after 15:30 IST (same 5m build as 4H).'
              : err.message);
        setError(msg);
        setLoading(false);
      });
  }, [symbol, timeframe, emaKey]);

  useEffect(() => {
    reloadIndexChart();
  }, [reloadIndexChart]);

  useEffect(() => {
    const onChartDataUpdated = () => reloadIndexChart();
    window.addEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
    return () => window.removeEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
  }, [reloadIndexChart]);

  return (
    <ChartContainer
      preloadedData={chartData}
      preloadedLoading={loading}
      preloadedError={error}
      isIndexChart={true}
      symbol={symbol}
      timeframe={timeframe}
      emas={emas}
      volumeVisible={volumeVisible}
      visiblePanels={visiblePanels}
      panelOrder={panelOrder}
      onTogglePanel={onTogglePanel}
      onMovePanel={onMovePanel}
      onLastChange={onLastChange}
      onHeightsChange={onHeightsChange}
      panelHeights={panelHeights}
      columnIndex={columnIndex}
      independentHeights={independentHeights}
      columnCount={columnCount}
      neighborHeightsLeft={neighborHeightsLeft}
      neighborHeightsRight={neighborHeightsRight}
      heightsRevision={heightsRevision}
      onCrosshairMove={onCrosshairMove}
      crosshairTime={crosshairTime}
      liveToday={liveToday}
      liveRefreshKey={liveRefreshKey}
      pricePanelTitle="Index"
      drawingScopeId={drawingScopeId}
      drawingAutoFocus={drawingAutoFocus}
    />
  );
}