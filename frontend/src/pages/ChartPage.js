import React, { useState, useEffect, useRef } from 'react';
import ChartTopBar from '../components/chart/ChartTopBar';
import ChartContainer from '../components/chart/ChartContainer';
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

export default function ChartPage({ symbol: initialSymbol, onOpenChart }) {
  const [symbol, setSymbol]                     = useState(initialSymbol);
  const [timeframe, setTimeframe]               = useState('1D');
  const [emas, setEmas]                         = useState(() => getPersistedEmaSet());
  const [volumeVisible, setVolumeVisible]       = useState(() => getPersistedVolumeVisible(true));
  const [visiblePanels, setVisiblePanels]       = useState(() => getPersistedVisiblePanels());
  const [panelOrder, setPanelOrder]             = useState(['stochrsi', 'macd']);
  const [lastCandleChange, setLastCandleChange] = useState(null);
  const currentHeightsRef                       = useRef({});

  useEffect(() => {
    setLastCandleChange(null);
  }, [symbol, timeframe]);

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
      if (e.key === 'flowx.chart.ema') setEmas(getPersistedEmaSet());
      if (e.key === 'flowx.chart.volumeVisible') setVolumeVisible(getPersistedVolumeVisible(true));
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

  function handleSymbolChange(newSymbol) {
    if (newSymbol && newSymbol !== symbol) {
      if (onOpenChart) onOpenChart(newSymbol);
      else setSymbol(newSymbol);
    }
  }

  function handleSaveLayout() {
    fetch('/api/layout', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(currentHeightsRef.current),
    })
      .then(r => r.json())
      .then(() => window.dispatchEvent(new CustomEvent('flowx-toast', { detail: 'Layout saved successfully.' })))
      .catch(() => window.dispatchEvent(new CustomEvent('flowx-toast', { detail: 'Failed to save layout.' })));
  }

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
      <ChartTopBar
        symbol={symbol}
        timeframe={timeframe}
        onTimeframeChange={setTimeframe}
        emas={emas}
        onEmasChange={setEmas}
        volumeVisible={volumeVisible}
        onToggleVolume={() => setVolumeVisible(v => !v)}
        visiblePanels={visiblePanels}
        onTogglePanel={handleTogglePanel}
        onSymbolChange={handleSymbolChange}
        lastCandleChange={lastCandleChange}
        onSaveLayout={handleSaveLayout}
      />

      <DrawingWorkspaceProvider workspaceId={`chart-page-${symbol}-${timeframe}`}>
        <div style={{ flex: 1, minHeight: 0, position: 'relative', display: 'flex', flexDirection: 'column' }}>
          <DrawingToolbarConnected />
          <DrawingFloatPaletteConnected />
          <ChartContainer
            symbol={symbol}
            timeframe={timeframe}
            emas={emas}
            volumeVisible={volumeVisible}
            visiblePanels={visiblePanels}
            panelOrder={panelOrder}
            onTogglePanel={handleTogglePanel}
            onMovePanel={handleMovePanel}
            onLastChange={pct => setLastCandleChange(pct)}
            onHeightsChange={heights => { currentHeightsRef.current = heights; }}
            drawingScopeId={`chart:${symbol}:${timeframe}`}
          />
        </div>
      </DrawingWorkspaceProvider>

      <div style={{
        position: 'absolute', bottom: 8, left: 8,
        fontSize: 10, color: 'var(--text-muted)',
        zIndex: 5, pointerEvents: 'none', userSelect: 'none',
      }}>
        Powered by TradingView Lightweight Charts
      </div>
    </div>
  );
}