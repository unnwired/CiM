import React, { useEffect, useMemo, useState } from 'react';
import IndexTopBar         from '../components/chart/IndexTopBar';
import ChartHeaderBar        from '../components/chart/ChartHeaderBar';
import IndexChartContainer from '../components/chart/IndexChartContainer';
import { DrawingWorkspaceProvider } from '../components/chart/drawing/DrawingWorkspaceContext';
import { DrawingToolbarConnected, DrawingFloatPaletteConnected } from '../components/chart/drawing/DrawingToolbar';
import {
  EMA_PREFS_UPDATED_EVENT,
  PANELS_PREFS_KEY,
  PANELS_PREFS_UPDATED_EVENT,
  VOLUME_PREFS_UPDATED_EVENT,
  getPersistedEmaSet,
  getPersistedVisiblePanels,
  getPersistedVolumeVisible,
  persistEmaSet,
  persistVisiblePanels,
  persistVolumeVisible,
} from '../config/chartDefaults';
import { isIntradayLiveTimeframe } from '../intraday/patchOverlay';
import { useRegisterFocusedSymbol } from '../intraday/useRegisterFocusedSymbol';
import { usePageLive } from '../intraday/pageLiveContext';
import { useSyncedPanelHeights } from '../hooks/useSyncedPanelHeights';
import { useIndicatorPanelAutoSave, useIndicatorPanelsBootstrap } from '../chartPrefs/useIndicatorPanelAutoSave';
import { persistIndicatorPanelsGlobal } from '../chartPrefs/chartPageLayout';
import { useChartPrefsContext } from '../chartPrefs/useChartPrefs';

export default function IndexChartPage({ index, onOpenChart, onOpenConstituents, onBack }) {
  const intradayPageId = `index-${index?.symbol || 'index'}`;
  const { liveActive, liveTick } = usePageLive(intradayPageId);
  useRegisterFocusedSymbol(intradayPageId, useMemo(
    () => (index?.symbol ? [index.symbol] : []),
    [index?.symbol, intradayPageId],
  ));
  const [timeframe, setTimeframe]         = useState('1D');
  const [emas, setEmas]                   = useState(() => getPersistedEmaSet());
  const [volumeVisible, setVolumeVisible] = useState(() => getPersistedVolumeVisible(true));
  const [visiblePanels, setVisiblePanels] = useState(() => getPersistedVisiblePanels());
  const [panelOrder, setPanelOrder]       = useState(['stochrsi', 'macd']);
  const [lastCandleChange, setLastCandleChange] = useState(null);
  const chartPrefs = useChartPrefsContext();
  const { getPanelHeights, heightsRef, handleHeightsChange, applyLayoutHeights, heightsRevision } = useSyncedPanelHeights({
    columnCount: 1,
  });
  const indicatorsHydrated = useIndicatorPanelsBootstrap({ applyLayoutHeights, setPanelOrder });
  const onHeightsChangePersist = useIndicatorPanelAutoSave({
    handleHeightsChange,
    heightsRef,
    panelOrder,
    ready: indicatorsHydrated,
  });

  useEffect(() => {
    persistEmaSet(emas);
  }, [emas]);

  useEffect(() => {
    persistVolumeVisible(volumeVisible);
  }, [volumeVisible]);

  useEffect(() => {
    persistVisiblePanels(visiblePanels);
  }, [visiblePanels]);

  useEffect(() => {
    function onEmaPrefs(e) {
      if (!e?.detail) return;
      setEmas(prev => (JSON.stringify(prev) === JSON.stringify(e.detail) ? prev : e.detail));
    }
    function onVolumePrefs(e) {
      if (typeof e?.detail !== 'boolean') return;
      setVolumeVisible(prev => (prev === e.detail ? prev : e.detail));
    }
    function onPanelsPrefs(e) {
      if (!e?.detail) return;
      setVisiblePanels(prev => (JSON.stringify(prev) === JSON.stringify(e.detail) ? prev : e.detail));
    }
    function onStorage(e) {
      if (e.key === 'cim.chart.ema') setEmas(getPersistedEmaSet());
      if (e.key === 'cim.chart.volumeVisible') setVolumeVisible(getPersistedVolumeVisible(true));
      if (e.key === PANELS_PREFS_KEY) setVisiblePanels(getPersistedVisiblePanels());
    }
    window.addEventListener(EMA_PREFS_UPDATED_EVENT, onEmaPrefs);
    window.addEventListener(VOLUME_PREFS_UPDATED_EVENT, onVolumePrefs);
    window.addEventListener(PANELS_PREFS_UPDATED_EVENT, onPanelsPrefs);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(EMA_PREFS_UPDATED_EVENT, onEmaPrefs);
      window.removeEventListener(VOLUME_PREFS_UPDATED_EVENT, onVolumePrefs);
      window.removeEventListener(PANELS_PREFS_UPDATED_EVENT, onPanelsPrefs);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  function handleTogglePanel(key) {
    setVisiblePanels(prev => ({ ...prev, [key]: !prev[key] }));
  }

  function handleMovePanel(key, direction) {
    setPanelOrder(prev => {
      const idx     = prev.indexOf(key);
      if (idx === -1) return prev;
      const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
      if (swapIdx < 0 || swapIdx >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[swapIdx]] = [next[swapIdx], next[idx]];
      return next;
    });
  }

  function handleSaveLayout() {
    persistIndicatorPanelsGlobal({
      email: chartPrefs?.email,
      chartPrefsEnabled: !!(chartPrefs?.enabled && chartPrefs?.email),
      heights: heightsRef.current,
      panelOrder,
    });
    window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Layout saved successfully.' }));
  }

  const tfLive = liveActive && isIntradayLiveTimeframe(timeframe);

  return (
    <div style={{
      display:         'flex',
      flexDirection:   'column',
      width:           '100%',
      height:          '100%',
      backgroundColor: 'var(--bg-primary)',
      overflow:        'hidden',
      position:        'relative',
    }}>
      <IndexTopBar
        index={index}
        timeframe={timeframe}
        onTimeframeChange={setTimeframe}
        emas={emas}
        onEmasChange={setEmas}
        volumeVisible={volumeVisible}
        onToggleVolume={() => setVolumeVisible(v => !v)}
        visiblePanels={visiblePanels}
        onTogglePanel={handleTogglePanel}
        lastCandleChange={lastCandleChange}
        onShowConstituents={() => onOpenConstituents && onOpenConstituents(index)}
        onSaveLayout={handleSaveLayout}
        onBack={onBack}
      />

      <ChartHeaderBar
        symbol={index?.symbol}
        timeframe={timeframe}
        onTimeframeChange={setTimeframe}
      />

      <DrawingWorkspaceProvider workspaceId={`index-page-${index.symbol}`}>
        <div style={{ flex: 1, minHeight: 0, position: 'relative', display: 'flex', flexDirection: 'column' }}>
          <DrawingToolbarConnected />
          <DrawingFloatPaletteConnected />
          <IndexChartContainer
            symbol={index.symbol}
            timeframe={timeframe}
            liveToday={tfLive}
            liveRefreshKey={tfLive ? liveTick : null}
            emas={emas}
            volumeVisible={volumeVisible}
            visiblePanels={visiblePanels}
            panelOrder={panelOrder}
            onTogglePanel={handleTogglePanel}
            onMovePanel={handleMovePanel}
            onLastChange={pct => setLastCandleChange(pct)}
            onHeightsChange={onHeightsChangePersist}
            panelHeights={getPanelHeights(0)}
            heightsRevision={heightsRevision}
            drawingScopeId={`index:${index.symbol}:${timeframe}`}
          />
        </div>
      </DrawingWorkspaceProvider>

      <div style={{
        position: 'absolute', bottom: 8, left: 8,
        fontSize: 10, color: 'var(--text-muted)',
        zIndex: 5, pointerEvents: 'none',
      }}>
        Powered by TradingView Lightweight Charts
      </div>
    </div>
  );
}
