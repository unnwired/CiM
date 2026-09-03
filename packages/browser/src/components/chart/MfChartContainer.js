/* eslint-disable react-hooks/exhaustive-deps */
import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import ChartContainer from './ChartContainer';
import { CHART_DATA_UPDATED_EVENT, dispatchChromeIntroReadyOnce } from '../../chartEvents';

const API = '';

export default function MfChartContainer({
  schemeCode,
  schemeName,
  timeframe,
  emas,
  volumeVisible,
  visiblePanels,
  panelOrder,
  onTogglePanel,
  onMovePanel,
  onLastChange,
  onHeightsChange,
  panelHeights,
  columnIndex = 0,
  independentHeights = false,
  columnCount = 1,
  neighborHeightsLeft = null,
  neighborHeightsRight = null,
  heightsRevision = 0,
  onCrosshairMove,
  crosshairTime,
}) {
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const emaKey = emas.map(e => e.period).join(',');

  const reload = useCallback(() => {
    if (!schemeCode) return;
    setLoading(true);
    setError(null);
    setChartData(null);

    const emaPeriods = emas.map(e => e.period);
    const params = { timeframe };
    if (emaPeriods[0]) params.ema1 = emaPeriods[0];
    if (emaPeriods[1]) params.ema2 = emaPeriods[1];
    if (emaPeriods[2]) params.ema3 = emaPeriods[2];
    if (emaPeriods[3]) params.ema4 = emaPeriods[3];

    axios.get(`${API}/api/mf/nav/${encodeURIComponent(schemeCode)}`, { params })
      .then(r => {
        setChartData(r.data);
        setLoading(false);
        if (r.data?.bars?.length) dispatchChromeIntroReadyOnce();
      })
      .catch(err => {
        const detail = err?.response?.data?.detail;
        const msg = typeof detail === 'string' && detail.trim()
          ? detail
          : (err.message || 'Failed to load NAV chart');
        setError(msg);
        setLoading(false);
      });
  }, [schemeCode, timeframe, emaKey]);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    const onUpdated = () => reload();
    window.addEventListener(CHART_DATA_UPDATED_EVENT, onUpdated);
    return () => window.removeEventListener(CHART_DATA_UPDATED_EVENT, onUpdated);
  }, [reload]);

  return (
    <ChartContainer
      preloadedData={chartData}
      preloadedLoading={loading}
      preloadedError={error}
      isIndexChart={true}
      symbol={schemeName || schemeCode}
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
      liveToday={false}
      liveRefreshKey={null}
      pricePanelTitle="NAV"
      drawingScopeId={schemeCode ? `mf:${schemeCode}` : null}
      drawingAutoFocus={false}
    />
  );
}
