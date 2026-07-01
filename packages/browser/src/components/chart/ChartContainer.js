/* eslint-disable react-hooks/exhaustive-deps */
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
} from 'lightweight-charts';
import { fetchChartData, fetchEarningsChartEvents } from '../../api/client';
import { useIntradayPatchOptional } from '../../intraday/useIntradayPatch';
import { sanitizeBarsForDisplay } from '../../intraday/mergeLiveBars';
import { CHART_DATA_UPDATED_EVENT, dispatchChromeIntroReadyOnce } from '../../chartEvents';
import PanelResizeHandle from './PanelResizeHandle';
import { snapDraggedColumnOnEdgeRelease } from '../../hooks/useSyncedPanelHeights';
import { emitChartPanelResizeDrag } from './chartResizeEvents';
import DrawingOverlay from './drawing/DrawingOverlay';
import { CHART_DRAWINGS_ENABLED } from './drawing/drawingFeature';
import { useChartDrawings } from './drawing/useChartDrawings';
import { useDrawingWorkspace } from './drawing/DrawingWorkspaceContext';
import { EMA_COLOR_BY_PERIOD } from '../../config/chartDefaults';
import PortfolioEarningsModal from '../PortfolioEarningsModal';
import {
  buildAnchoredEarningsEvents,
  buildBottomEarningsMarkers,
  buildEarningsEventLookup,
  getEarningsMarkerColor,
  getEarningsModalVariant,
  getEarningsStatusLabel,
  EARNINGS_MARKER_STATUS_COLOR,
  shouldShowEarningsMarkers,
} from '../../utils/earningsChartMarkers';
import { daysSinceYmd, formatEarningsBadgeDate } from '../../utils/portfolioEarnings';
import {
  chartTimeDiffMs,
  formatChartAxisLabel,
  normalizeChartTimeKey,
} from '../../utils/chartTime';
import { loadPersistedIndicatorPanelHeights } from '../../chartPrefs/indicatorPanelHeightsStore';

const MIN_PANEL_H  = 80;
const EARNINGS_PLUS_COLOR = '#d29922';

/** Normalize LW chart times (string, BusinessDay, unix) for reliable bar lookup. */
function normalizeChartTime(t) {
  return normalizeChartTimeKey(t);
}

/** Value at `time` for line/hist series data (StochRSI, MACD, etc.) — used for crosshair Y sync on correct scale. */
function seriesValueAtTime(data, time) {
  if (!data?.length || time == null) return null;
  const norm = normalizeChartTime(time);
  const exact = data.find(d => normalizeChartTime(d.time) === norm);
  if (exact) return exact.value ?? exact.close ?? null;
  let closest = null;
  let minDiff = Infinity;
  for (const d of data) {
    const diff = chartTimeDiffMs(d.time, time);
    if (diff < minDiff) {
      minDiff = diff;
      closest = d;
    }
  }
  if (!closest) return null;
  return closest.value ?? closest.close ?? null;
}

function barCloseAtTime(bars, time) {
  if (!bars?.length || time == null) return null;
  const norm = normalizeChartTime(time);
  const exact = bars.find(b => normalizeChartTime(b.time) === norm);
  if (exact?.close != null) return exact.close;
  let closest = null;
  let minDiff = Infinity;
  for (const b of bars) {
    const diff = chartTimeDiffMs(b.time, time);
    if (diff < minDiff) {
      minDiff = diff;
      closest = b;
    }
  }
  return closest?.close ?? null;
}

function barIndexAtTime(bars, time) {
  if (!bars?.length || time == null) return -1;
  const norm = normalizeChartTime(time);
  const exact = bars.findIndex(b => normalizeChartTime(b.time) === norm);
  if (exact >= 0) return exact;
  const lastIdx = bars.length - 1;
  const last = bars[lastIdx];
  const lastNorm = normalizeChartTime(last?.time);
  if (lastNorm && norm >= lastNorm) return lastIdx;
  const atClose = barCloseAtTime(bars, time);
  if (
    last?.close != null
    && atClose != null
    && Math.abs(Number(atClose) - Number(last.close)) < 0.02
  ) {
    return lastIdx;
  }
  return -1;
}

function changePctAtBarIndex(bars, idx, chartData, dayChangePctOverride, timeframe = '1D') {
  if (!bars?.length || idx < 1) return null;
  const n = bars.length;
  const cur = bars[idx];
  const prev = bars[idx - 1];
  if (prev?.close == null || cur?.close == null || Number(prev.close) === 0) return null;
  const barPct = ((Number(cur.close) - Number(prev.close)) / Number(prev.close)) * 100;
  if (idx === n - 1 && (!timeframe || timeframe === '1D' || timeframe === '4H')) {
    const dayPct = pickDayOverDayPctFromChartPayload(
      chartData ? { ...chartData, bars } : null,
      dayChangePctOverride,
    );
    if (dayPct != null && Number.isFinite(dayPct)) return dayPct;
  }
  return Number.isFinite(barPct) ? barPct : null;
}

function resolveHoverFromCrosshair(p, candleSeries, bars) {
  if (!bars?.length || !p?.time) return null;
  const fromSeries = candleSeries ? p.seriesData?.get(candleSeries) : null;
  if (fromSeries) {
    const stored = bars.find(
      b => normalizeChartTime(b.time) === normalizeChartTime(fromSeries.time),
    );
    return {
      ...(stored || {}),
      ...fromSeries,
      volume: stored?.volume ?? fromSeries.volume,
    };
  }
  const idx = barIndexAtTime(bars, p.time);
  if (idx >= 0) return { ...bars[idx] };
  return null;
}

function formatVolume(val) {
  if (val == null || isNaN(val)) return '—';
  if (val >= 1e9) return (val / 1e9).toFixed(2) + ' B';
  if (val >= 1e6) return (val / 1e6).toFixed(2) + ' M';
  if (val >= 1e3) return (val / 1e3).toFixed(2) + ' K';
  return String(Math.round(val));
}

/** Bar-over-bar % on the loaded series (correct for 2D/2W/1M last candle). */
function barOverBarPct(bars) {
  if (!bars?.length || bars.length < 2) return null;
  const last = bars[bars.length - 1];
  const prev = bars[bars.length - 2];
  if (prev?.close == null || last?.close == null || Number(prev.close) === 0) return null;
  const pct = ((Number(last.close) - Number(prev.close)) / Number(prev.close)) * 100;
  return Number.isFinite(pct) ? pct : null;
}

/** 1D list % from API/override; otherwise last bar vs prior bar on this timeframe. */
function pickDayOverDayPctFromChartPayload(data, overridePct = null) {
  if (overridePct != null && Number.isFinite(Number(overridePct))) return Number(overridePct);
  if (!data?.bars?.length) return null;
  const fromBars = barOverBarPct(data.bars);
  const o = data.day_change_pct;
  if (o != null && Number.isFinite(Number(o))) {
    const official = Number(o);
    // Stale/zero official 1D % — prefer visible bar move when bars disagree materially.
    if (fromBars != null && Math.abs(official) < 0.0001 && Math.abs(fromBars) >= 0.0001) {
      return fromBars;
    }
    // Cached bars out of sync with server 1D % (same source as index list API).
    if (fromBars != null && Math.abs(official - fromBars) >= 0.05) {
      return official;
    }
    return official;
  }
  return fromBars;
}
const INITIAL_BARS = 220;

const globalPanelHeights = {
  stochrsi: 130,
  macd:     130,
};

const savedHeights = loadPersistedIndicatorPanelHeights();
if (savedHeights?.stochrsi) globalPanelHeights.stochrsi = savedHeights.stochrsi;
if (savedHeights?.macd) globalPanelHeights.macd = savedHeights.macd;

fetch('/api/layout')
  .then(r => r.json())
  .then(data => {
    if ('stochrsi' in data && data.stochrsi) globalPanelHeights.stochrsi = data.stochrsi;
    if ('macd' in data && data.macd) globalPanelHeights.macd = data.macd;
  })
  .catch(() => {});

function baseChartOpts(width, height, timeframe = '1D') {
  const tf = String(timeframe || '1D').trim().toUpperCase();
  return {
    width,
    height,
    layout: {
      background:      { color: '#0d1117' },
      textColor:       '#8b949e',
      fontSize:        11,
      attributionLogo: false,
    },
    grid: {
      vertLines: { visible: false },
      horzLines: { visible: false },
    },
    crosshair: {
      mode:     0,
      vertLine: { color: '#8b949e66', style: 1, labelBackgroundColor: '#1c2128' },
      horzLine: { color: '#8b949e66', style: 1, labelBackgroundColor: '#1c2128' },
    },
    timeScale: {
      borderColor:    '#30363d',
      timeVisible:    tf === '4H',
      secondsVisible: false,
      rightOffset:    15,
    },
    localization: {
      timeFormatter: (time) => formatChartAxisLabel(time),
    },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
    handleScale:  { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
  };
}

function PanelHeader({ title, onClose, onMoveUp, onMoveDown, titleUppercase = false }) {
  const label = title ?? '—';
  return (
    <div style={{
      height: 24, display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', padding: '0 8px',
      backgroundColor: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border-light)',
      flexShrink: 0, userSelect: 'none', minWidth: 0,
    }}>
      <span
        title={label}
        style={{
          fontSize: 10, color: 'var(--text-muted)',
          fontWeight: 600, letterSpacing: titleUppercase ? '0.06em' : '0.02em',
          textTransform: titleUppercase ? 'uppercase' : 'none',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          flex: 1, minWidth: 0,
        }}
      >{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        {onMoveUp && (
          <button onClick={onMoveUp}
            aria-label="Move panel up"
            style={{ background: 'none', color: 'var(--text-muted)', fontSize: 11, padding: '0 3px' }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
          >▲</button>
        )}
        {onMoveDown && (
          <button onClick={onMoveDown}
            aria-label="Move panel down"
            style={{ background: 'none', color: 'var(--text-muted)', fontSize: 11, padding: '0 3px' }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
          >▼</button>
        )}
        {onClose && (
          <button onClick={onClose}
            aria-label="Close panel"
            style={{ background: 'none', color: 'var(--text-muted)', fontSize: 14, lineHeight: 1, padding: '0 3px' }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
          >×</button>
        )}
      </div>
    </div>
  );
}

function HoverLegend({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div style={{
      position: 'absolute', top: 28, left: 8, zIndex: 20,
      display: 'flex', gap: 10, fontSize: 11,
      fontFamily: 'var(--font-mono)', pointerEvents: 'none',
      backgroundColor: 'rgba(13,17,23,0.9)',
      padding: '3px 8px', borderRadius: 4,
      border: '1px solid var(--border-light)',
    }}>
      {items.map((item, i) => (
        <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          {item.kind === 'badge' ? (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                minWidth: 18,
                height: 18,
                padding: '0 5px',
                borderRadius: 4,
                fontWeight: 700,
                color: '#ffffff',
                backgroundColor: item.color || 'var(--text-primary)',
              }}
              aria-hidden="true"
            >
              {item.value}
            </span>
          ) : (
            <>
              <span style={{ color: 'var(--text-muted)' }}>{item.label} </span>
              <b style={{ color: item.color || 'var(--text-primary)' }}>{item.value}</b>
            </>
          )}
        </span>
      ))}
    </div>
  );
}

// ─── PricePanel ──────────────────────────────────────────────────────────────

function PricePanel({
  width, height, chartData, timeframe = '1D', emas, volumeVisible, syncRef, syncMutedRef, panelResizeDragRef, markerRelayoutEpoch = 0, onHoverTime, onLastChange, onCrosshairMove, crosshairTime,
  dayChangePctOverride,
  pricePanelTitle,
  earningsEvents = [],
  earningsPlusHelper = null,
  onEarningsMarkerSelect,
  drawingEnabled, drawings, setDrawings, activeTool, lineColor, lineWidth, selectedDrawingId, setSelectedDrawingId,
  isDrawingTarget, onPriceSurfaceMouseDownCapture, onRequestToolbarUpdate,
}) {
  const el           = useRef(null);
  const chart        = useRef(null);
  const candle       = useRef(null);
  const vol          = useRef(null);
  const [markerLayoutVersion, setMarkerLayoutVersion] = useState(0);

  // Receive crosshair from sibling split panels
  useEffect(() => {
    if (!crosshairTime || !chart.current || !candle.current) return;
    try {
      const { time, price } = crosshairTime;
      if (!time) return;
      // Convert the source panel's price to this panel's coordinate then back to price
      // This makes the horizontal line free-flow at the same Y coordinate
      const srcCoord = price != null
        ? candle.current.priceToCoordinate(price)
        : null;
      const displayPrice = srcCoord != null
        ? candle.current.coordinateToPrice(srcCoord)
        : (price ?? 0);
      chart.current.setCrosshairPosition(displayPrice ?? 0, time, candle.current);
    } catch {}
  }, [crosshairTime]);

  const emaMap       = useRef({});
  const bars         = useRef([]);
  const dead         = useRef(false);
  const rangeSetRef  = useRef(false);
  const [hover, setHover] = useState(null);
  const innerH = height - 24;

  // chartData.bars is authoritative; keep refs in sync for LW callbacks (effect deps are narrow).
  const barListRef = useRef([]);
  if (chartData?.bars?.length) {
    barListRef.current = chartData.bars;
    bars.current = chartData.bars;
  }
  const barList = barListRef.current;

  useEffect(() => {
    if (!el.current || width <= 0 || innerH <= 0) return;
    dead.current     = false;
    rangeSetRef.current = false;

    const c = createChart(el.current, {
      ...baseChartOpts(width, innerH, timeframe),
      rightPriceScale: {
        borderColor:  '#30363d',
        scaleMargins: { top: 0.08, bottom: 0.15 },
      },
    });
    chart.current = c;

    const cs = c.addSeries(CandlestickSeries, {
      upColor: '#3fb950', downColor: '#f85149',
      borderUpColor: '#3fb950', borderDownColor: '#f85149',
      wickUpColor: '#3fb950', wickDownColor: '#f85149',
    });
    candle.current = cs;

    const vs = c.addSeries(HistogramSeries, {
      priceScaleId: 'vol', priceLineVisible: false, lastValueVisible: false,
    });
    c.priceScale('vol').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });
    vol.current = vs;

    c.subscribeCrosshairMove(p => {
      if (dead.current) return;
      if (!p?.point || !p?.time) {
        setHover(null);
        syncRef.current.forEach(entry => {
          if (entry.chart === c) return;
          try { entry.chart.clearCrosshairPosition(); } catch {}
        });
        if (onHoverTime) onHoverTime(null);
        return;
      }
      const list = barListRef.current;
      const resolved = resolveHoverFromCrosshair(p, cs, list);
      if (!resolved) {
        const last = list.length ? list[list.length - 1] : null;
        setHover(last ? { ...last } : null);
        return;
      }
      setHover(resolved);
      if (onHoverTime) onHoverTime(p.time);
      if (onCrosshairMove) {
        // Get the actual mouse Y coordinate price from this panel's price scale
        const price = candle.current
          ? candle.current.coordinateToPrice(p.point.y)
          : null;
        onCrosshairMove({ time: p.time, price });
      }
      syncRef.current.forEach(entry => {
        if (entry.chart === c || !entry.series) return;
        let y = 0;
        if (entry.indicatorKind === 'stoch') {
          const k = seriesValueAtTime(chartData?.stochrsi?.k, p.time);
          const d = seriesValueAtTime(chartData?.stochrsi?.d, p.time);
          y = k != null && Number.isFinite(k) ? k : (d != null && Number.isFinite(d) ? d : 50);
        } else if (entry.indicatorKind === 'macd') {
          const m = seriesValueAtTime(chartData?.macd?.macd, p.time);
          y = m != null && Number.isFinite(m) ? m : 0;
        }
        try { entry.chart.setCrosshairPosition(y, p.time, entry.series); } catch {}
      });
    });

    // Price is master — broadcasts to indicators only
    c.timeScale().subscribeVisibleLogicalRangeChange(r => {
      if (dead.current || !r || syncMutedRef.current) return;
      syncRef.current.forEach(entry => {
        if (entry.chart === c || entry.isPriceMaster) return;
        const adjusted = { from: r.from - entry.offset, to: r.to - entry.offset };
        try { entry.chart.timeScale().setVisibleLogicalRange(adjusted); } catch {}
      });
      setMarkerLayoutVersion(v => v + 1);
    });

    syncRef.current.push({
      chart: c, offset: 0, series: cs, isPriceMaster: true, indicatorKind: 'price',
    });

    return () => {
      dead.current = true;
      syncRef.current = syncRef.current.filter(e => e.chart !== c);
      try { c.remove(); } catch {}
      chart.current     = null;
      candle.current    = null;
      vol.current       = null;
      emaMap.current    = {};
      rangeSetRef.current = false;
    };
  }, [width, timeframe]);

  useEffect(() => {
    if (!chart.current || innerH <= 0) return;
    try { chart.current.applyOptions({ height: innerH }); } catch {}
    if (!panelResizeDragRef?.current) setMarkerLayoutVersion(v => v + 1);
  }, [innerH]);

  useEffect(() => {
    if (!markerRelayoutEpoch) return;
    setMarkerLayoutVersion(v => v + 1);
  }, [markerRelayoutEpoch]);

  useEffect(() => {
    if (!candle.current || !chartData?.bars?.length) return;
    bars.current = chartData.bars;
    candle.current.setData(chartData.bars);
    if (!rangeSetRef.current) {
      rangeSetRef.current = true;
      const total = chartData.bars.length;
      chart.current?.timeScale().setVisibleLogicalRange({
        from: total - INITIAL_BARS - 10,
        to:   total + 15,
      });
    }
    setMarkerLayoutVersion(v => v + 1);
  }, [candle.current, chartData?.bars]);

  useEffect(() => {
    if (!vol.current || !chartData?.bars?.length) return;
    vol.current.setData(volumeVisible
      ? chartData.bars.map(b => ({
          time: b.time, value: b.volume,
          color: b.close >= b.open ? '#3fb95033' : '#f8514933',
        }))
      : []
    );
  }, [vol.current, chartData?.bars, volumeVisible]);

  useEffect(() => {
    if (!chart.current || !candle.current) return;
    Object.values(emaMap.current).forEach(s => {
      try { chart.current.removeSeries(s); } catch {}
    });
    emaMap.current = {};
    if (!chartData?.ema) return;
    emas.forEach((ema, idx) => {
      if (!ema.visible) return;
      const data = chartData.ema[String(ema.period)];
      if (!data?.length) return;
      const s = chart.current.addSeries(LineSeries, {
        color: ema.color || EMA_COLOR_BY_PERIOD[ema.period] || '#f6c90e', lineWidth: 1,
        priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(data);
      emaMap.current[idx] = s;
    });
  }, [candle.current, emas, chartData?.ema]);

  const lastBar = barList.length ? barList[barList.length - 1] : null;
  const displayBar = hover ?? lastBar;
  const anchoredEarningsEvents = useMemo(
    () => buildAnchoredEarningsEvents(earningsEvents, barList.map(bar => bar.time)),
    [earningsEvents, barList],
  );
  const earningsLookup = useMemo(
    () => buildEarningsEventLookup(anchoredEarningsEvents),
    [anchoredEarningsEvents],
  );
  const displayEarningsEvent = displayBar
    ? earningsLookup.get(normalizeChartTime(displayBar.time)) || null
    : null;
  const visibleEarningsEvents = useMemo(() => {
    const visibleDates = new Set(barList.map(bar => normalizeChartTime(bar.time)).filter(Boolean));
    return Array.from(earningsLookup.values())
      .filter(event => visibleDates.has(event.chart_anchor_date))
      .sort((a, b) => b.earnings_release_date.localeCompare(a.earnings_release_date));
  }, [earningsLookup, barList]);
  const latestVisibleEarningsEvent = visibleEarningsEvents[0] || null;
  const bottomChartMarkers = useMemo(() => {
    if (!chart.current) return [];
    return buildBottomEarningsMarkers(
      visibleEarningsEvents,
      barList.map(bar => bar.time),
      (time) => chart.current?.timeScale().timeToCoordinate(time) ?? null,
      width,
    );
  }, [visibleEarningsEvents, barList, width, markerLayoutVersion]);
  let displayIdx = -1;
  if (displayBar && barList.length >= 2) {
    if (!hover) {
      displayIdx = barList.length - 1;
    } else {
      displayIdx = barIndexAtTime(barList, displayBar.time);
      if (displayIdx < 0 && lastBar?.close != null && displayBar.close != null
        && Math.abs(Number(displayBar.close) - Number(lastBar.close)) < 0.05) {
        displayIdx = barList.length - 1;
      }
    }
  }
  const candleChange = displayBar && displayIdx >= 1
    ? changePctAtBarIndex(barList, displayIdx, chartData, dayChangePctOverride, timeframe)
    : null;

  const items = displayBar ? [
    { label: 'O', value: `₹${Number(displayBar.open ?? 0).toFixed(2)}`,  color: 'var(--text-primary)'  },
    { label: 'H', value: `₹${Number(displayBar.high ?? 0).toFixed(2)}`,  color: 'var(--accent-green)'  },
    { label: 'L', value: `₹${Number(displayBar.low ?? 0).toFixed(2)}`,   color: 'var(--accent-red)'    },
    { label: 'C', value: `₹${Number(displayBar.close ?? 0).toFixed(2)}`, color: 'var(--text-primary)'  },
    ...(displayEarningsEvent ? [{
      kind: 'badge',
      label: 'E',
      value: 'E',
      color: getEarningsMarkerColor(displayEarningsEvent.outcome_kind),
    }] : []),
    { label: 'V', value: displayBar.volume != null
        ? formatVolume(displayBar.volume) : '—',
      color: 'var(--text-secondary)' },
    ...(candleChange != null && Number.isFinite(candleChange) ? [{
      label: '%',
      value: `${candleChange >= 0 ? '+' : ''}${candleChange.toFixed(2)}%`,
      color: candleChange >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
    }] : []),
  ] : [];

  return (
    <div style={{
      height,
      minHeight: MIN_PANEL_H,
      flexShrink: 0,
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden', position: 'relative',
    }}>
      <PanelHeader title={pricePanelTitle ?? '—'} />
      <HoverLegend items={items} />

      <div
        style={{ position: 'relative', width, height: innerH, flexShrink: 0 }}
        onMouseDownCapture={onPriceSurfaceMouseDownCapture}
      >
        <div ref={el} style={{ width, height: innerH, overflow: 'hidden' }} />
        {(latestVisibleEarningsEvent || earningsPlusHelper) && (
          <div
            role="group"
            aria-label="Visible earnings helpers"
            style={{
              position: 'absolute',
              top: 56,
              left: 8,
              right: 8,
              zIndex: 21,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: 6,
              pointerEvents: 'auto',
            }}
          >
            {latestVisibleEarningsEvent && (
              <button
                key={latestVisibleEarningsEvent.earnings_release_date}
                type="button"
                onClick={() => onEarningsMarkerSelect && onEarningsMarkerSelect(latestVisibleEarningsEvent)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '2px 8px',
                  borderRadius: 999,
                  border: `1px solid ${getEarningsMarkerColor(latestVisibleEarningsEvent.outcome_kind)}`,
                  backgroundColor: 'rgba(13,17,23,0.92)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  lineHeight: 1.2,
                }}
                aria-label={
                  `Open earnings details for ${latestVisibleEarningsEvent.earnings_release_date}`
                  + (getEarningsStatusLabel(latestVisibleEarningsEvent.comparison_status)
                    ? `. ${getEarningsStatusLabel(latestVisibleEarningsEvent.comparison_status)}`
                    : '')
                  + (latestVisibleEarningsEvent.comparison_note ? `. ${latestVisibleEarningsEvent.comparison_note}` : '')
                }
                title={latestVisibleEarningsEvent.comparison_note || ''}
              >
                <span
                  aria-hidden="true"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minWidth: 16,
                    height: 16,
                    borderRadius: 3,
                    backgroundColor: getEarningsMarkerColor(latestVisibleEarningsEvent.outcome_kind),
                    color: '#ffffff',
                    fontWeight: 700,
                  }}
                >
                  E
                </span>
                <span>{formatEarningsBadgeDate(latestVisibleEarningsEvent.earnings_release_date)}</span>
                {getEarningsStatusLabel(latestVisibleEarningsEvent.comparison_status) && (
                  <span style={{ color: EARNINGS_MARKER_STATUS_COLOR }}>
                    {getEarningsStatusLabel(latestVisibleEarningsEvent.comparison_status)}
                  </span>
                )}
              </button>
            )}
            {earningsPlusHelper && (
              <div
                role="note"
                aria-label={earningsPlusHelper.note || 'Earnings+ quality badge'}
                title={earningsPlusHelper.note || ''}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '2px 8px',
                  borderRadius: 999,
                  border: `1px solid ${EARNINGS_PLUS_COLOR}`,
                  backgroundColor: 'rgba(13,17,23,0.92)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  lineHeight: 1.2,
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minWidth: 16,
                    height: 16,
                    borderRadius: 3,
                    backgroundColor: EARNINGS_PLUS_COLOR,
                    color: '#0d1117',
                    fontWeight: 700,
                  }}
                >
                  E+
                </span>
                <span>Earnings+</span>
              </div>
            )}
          </div>
        )}
        {bottomChartMarkers.map((marker) => (
          <button
            key={marker.id}
            type="button"
            onClick={() => onEarningsMarkerSelect && onEarningsMarkerSelect(marker.event)}
            aria-label={
              `Open earnings details for ${marker.event.earnings_release_date}`
              + (marker.event.comparison_note ? `. ${marker.event.comparison_note}` : '')
            }
            title={marker.event.comparison_note || ''}
            style={{
              position: 'absolute',
              left: marker.x,
              bottom: 28,
              transform: 'translateX(-50%)',
              zIndex: 19,
              minWidth: 18,
              height: 18,
              padding: '0 5px',
              borderRadius: 4,
              border: '1px solid rgba(0,0,0,0.35)',
              backgroundColor: marker.color,
              color: '#ffffff',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              fontSize: 11,
              lineHeight: 1,
              boxShadow: '0 1px 4px rgba(0,0,0,0.35)',
            }}
          >
            E
          </button>
        ))}
        {drawingEnabled && (
          <DrawingOverlay
            chartRef={chart}
            seriesRef={candle}
            width={width}
            height={innerH}
            drawings={drawings}
            setDrawings={setDrawings}
            activeTool={activeTool}
            lineColor={lineColor}
            lineWidth={lineWidth}
            selectedId={selectedDrawingId}
            setSelectedId={setSelectedDrawingId}
            isDrawingTarget={isDrawingTarget}
            onRequestToolbarUpdate={onRequestToolbarUpdate}
          />
        )}
      </div>
    </div>
  );
}

// ─── StochRSIPanel ────────────────────────────────────────────────────────────

function findClosest(data, time) {
  if (!data || !data.length || !time) return null;
  const exact = data.find(d => String(d.time) === String(time));
  if (exact) return exact;
  // Find closest by date string comparison
  let closest = null;
  let minDiff = Infinity;
  for (const d of data) {
    const diff = chartTimeDiffMs(d.time, time);
    if (diff < minDiff) { minDiff = diff; closest = d; }
  }
  return closest;
}

function StochRSIPanel({ width, height, chartData, timeframe = '1D', offset, onClose, onMoveUp, onMoveDown, syncRef, hoverTime }) {
  const el    = useRef(null);
  const chart = useRef(null);
  const kS    = useRef(null);
  const dS    = useRef(null);
  const dead  = useRef(false);
  const [hover, setHover] = useState(null);
  const innerH = height - 24;

  useEffect(() => {
    if (!el.current || width <= 0 || innerH <= 0) return;
    dead.current = false;

    const c = createChart(el.current, {
      ...baseChartOpts(width, innerH, timeframe),
      // Fixed 0–100 band with vertical inset so the 100 guide + axis labels are not clipped at pane edges.
      rightPriceScale: {
        borderColor: '#30363d',
        scaleMargins: { top: 0.12, bottom: 0.1 },
      },
    });
    chart.current = c;

    /** Keep StochRSI scale locked to 0–100 so 0/100 guides never shift when K/D move. */
    const stochRsiAutoscale = () => ({
      priceRange: { minValue: 0, maxValue: 100 },
    });

    kS.current = c.addSeries(LineSeries, {
      color: '#2196f3', lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
      autoscaleInfoProvider: stochRsiAutoscale,
    });
    dS.current = c.addSeries(LineSeries, {
      color: '#ff9800', lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
      lastPriceAnimation: 0,
      autoscaleInfoProvider: stochRsiAutoscale,
    });

    kS.current.createPriceLine({
      price: 0,
      color: '#8b949e44',
      lineWidth: 1,
      lineStyle: 1,
      axisLabelVisible: true,
    });
    kS.current.createPriceLine({
      price: 100,
      color: '#8b949e44',
      lineWidth: 1,
      lineStyle: 1,
      axisLabelVisible: true,
    });

    c.subscribeCrosshairMove(p => {
      if (dead.current) return;
      if (!p?.point || !p?.time) {
        setHover(null);
        syncRef.current.forEach(entry => {
          if (entry.chart === c) return;
          try { entry.chart.clearCrosshairPosition(); } catch {}
        });
        return;
      }
      syncRef.current.forEach(entry => {
        if (entry.chart === c || !entry.series) return;
        let y = 0;
        if (entry.indicatorKind === 'price') {
          y = barCloseAtTime(chartData?.bars, p.time) ?? 0;
        } else if (entry.indicatorKind === 'macd') {
          const m = seriesValueAtTime(chartData?.macd?.macd, p.time);
          y = m != null && Number.isFinite(m) ? m : 0;
        }
        try { entry.chart.setCrosshairPosition(y, p.time, entry.series); } catch {}
      });
      const k = kS.current ? p.seriesData?.get(kS.current) : null;
      const d = dS.current ? p.seriesData?.get(dS.current) : null;
      setHover({ k: k?.value ?? null, d: d?.value ?? null });
    });

    // Indicator only broadcasts to price master — never to other indicators
    c.timeScale().subscribeVisibleLogicalRangeChange(r => {
      if (dead.current || !r) return;
      const priceEntry = syncRef.current.find(e => e.isPriceMaster);
      if (!priceEntry) return;
      const adjusted = { from: r.from + offset, to: r.to + offset };
      try { priceEntry.chart.timeScale().setVisibleLogicalRange(adjusted); } catch {}
    });

    syncRef.current.push({
      chart: c, offset, series: kS.current, isPriceMaster: false, indicatorKind: 'stoch',
    });

    // Snap to price chart's current range on mount
    const priceEntry = syncRef.current.find(e => e.isPriceMaster);
    if (priceEntry) {
      try {
        const r = priceEntry.chart.timeScale().getVisibleLogicalRange();
        if (r) c.timeScale().setVisibleLogicalRange({ from: r.from - offset, to: r.to - offset });
      } catch {}
    }

    return () => {
      dead.current = true;
      syncRef.current = syncRef.current.filter(e => e.chart !== c);
      try { c.remove(); } catch {}
      chart.current = null; kS.current = null; dS.current = null;
    };
  }, [width, timeframe]);

  useEffect(() => {
    if (!chart.current || innerH <= 0) return;
    try { chart.current.applyOptions({ height: innerH }); } catch {}
  }, [innerH]);

  useEffect(() => {
    if (!kS.current || !dS.current) return;
    if (chartData?.stochrsi?.k?.length) kS.current.setData(chartData.stochrsi.k);
    if (chartData?.stochrsi?.d?.length) dS.current.setData(chartData.stochrsi.d);
  }, [kS.current, chartData?.stochrsi]);

  const displayK = hoverTime && chartData?.stochrsi?.k
    ? findClosest(chartData.stochrsi.k, hoverTime)?.value ?? null
    : hover?.k ?? null;
  const displayD = hoverTime && chartData?.stochrsi?.d
    ? findClosest(chartData.stochrsi.d, hoverTime)?.value ?? null
    : hover?.d ?? null;
  const items = (hoverTime || hover) ? [
    { label: '%K', value: displayK != null ? displayK.toFixed(2) : '—', color: '#2196f3' },
    { label: '%D', value: displayD != null ? displayD.toFixed(2) : '—', color: '#ff9800' },
  ] : [];

  return (
    <div style={{
      height, flexShrink: 0,
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden', position: 'relative',
    }}>
      <PanelHeader title="StochRSI" titleUppercase onClose={onClose} onMoveUp={onMoveUp} onMoveDown={onMoveDown} />
      <HoverLegend items={items} />
      <div ref={el} style={{ width, height: innerH, overflow: 'hidden', flexShrink: 0 }} />
    </div>
  );
}

// ─── MACDPanel ───────────────────────────────────────────────────────────────

function MACDPanel({ width, height, chartData, timeframe = '1D', offset, onClose, onMoveUp, onMoveDown, syncRef, hoverTime }) {
  const el    = useRef(null);
  const chart = useRef(null);
  const macdS = useRef(null);
  const sigS  = useRef(null);
  const histS = useRef(null);
  const dead  = useRef(false);
  const [hover, setHover] = useState(null);
  const innerH = height - 24;

  useEffect(() => {
    if (!el.current || width <= 0 || innerH <= 0) return;
    dead.current = false;

    const c = createChart(el.current, {
      ...baseChartOpts(width, innerH, timeframe),
      rightPriceScale: { borderColor: '#30363d', scaleMargins: { top: 0.1, bottom: 0.1 } },
    });
    chart.current = c;

    histS.current = c.addSeries(HistogramSeries, {
      priceLineVisible: false, lastValueVisible: false,
    });
    macdS.current = c.addSeries(LineSeries, {
      color: '#2196f3', lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
    });
    sigS.current = c.addSeries(LineSeries, {
      color: '#ff9800', lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
      lastPriceAnimation: 0,
    });

    c.subscribeCrosshairMove(p => {
      if (dead.current) return;
      if (!p?.point || !p?.time) {
        setHover(null);
        syncRef.current.forEach(entry => {
          if (entry.chart === c) return;
          try { entry.chart.clearCrosshairPosition(); } catch {}
        });
        return;
      }
      syncRef.current.forEach(entry => {
        if (entry.chart === c || !entry.series) return;
        let y = 0;
        if (entry.indicatorKind === 'price') {
          y = barCloseAtTime(chartData?.bars, p.time) ?? 0;
        } else if (entry.indicatorKind === 'stoch') {
          const k = seriesValueAtTime(chartData?.stochrsi?.k, p.time);
          const d = seriesValueAtTime(chartData?.stochrsi?.d, p.time);
          y = k != null && Number.isFinite(k) ? k : (d != null && Number.isFinite(d) ? d : 50);
        }
        try { entry.chart.setCrosshairPosition(y, p.time, entry.series); } catch {}
      });
      const m = macdS.current ? p.seriesData?.get(macdS.current) : null;
      const s = sigS.current  ? p.seriesData?.get(sigS.current)  : null;
      const h = histS.current ? p.seriesData?.get(histS.current) : null;
      setHover({ macd: m?.value ?? null, signal: s?.value ?? null, hist: h?.value ?? null });
    });

    // Indicator only broadcasts to price master — never to other indicators
    c.timeScale().subscribeVisibleLogicalRangeChange(r => {
      if (dead.current || !r) return;
      const priceEntry = syncRef.current.find(e => e.isPriceMaster);
      if (!priceEntry) return;
      const adjusted = { from: r.from + offset, to: r.to + offset };
      try { priceEntry.chart.timeScale().setVisibleLogicalRange(adjusted); } catch {}
    });

    syncRef.current.push({
      chart: c, offset, series: macdS.current, isPriceMaster: false, indicatorKind: 'macd',
    });

    // Snap to price chart's current range on mount
    const priceEntry = syncRef.current.find(e => e.isPriceMaster);
    if (priceEntry) {
      try {
        const r = priceEntry.chart.timeScale().getVisibleLogicalRange();
        if (r) c.timeScale().setVisibleLogicalRange({ from: r.from - offset, to: r.to - offset });
      } catch {}
    }

    return () => {
      dead.current = true;
      syncRef.current = syncRef.current.filter(e => e.chart !== c);
      try { c.remove(); } catch {}
      chart.current = null; macdS.current = null; sigS.current = null; histS.current = null;
    };
  }, [width, timeframe]);

  useEffect(() => {
    if (!chart.current || innerH <= 0) return;
    try { chart.current.applyOptions({ height: innerH }); } catch {}
  }, [innerH]);

  useEffect(() => {
    if (!macdS.current) return;
    if (chartData?.macd?.histogram?.length) {
      const hist = chartData.macd.histogram;
      histS.current.setData(hist.map((d, i) => {
        const prev      = i > 0 ? hist[i - 1].value : d.value;
        const expanding = Math.abs(d.value) >= Math.abs(prev);
        let color;
        if (d.value >= 0) {
          color = expanding ? '#3fb950cc' : '#3fb95055';
        } else {
          color = expanding ? '#f85149cc' : '#f8514955';
        }
        return { ...d, color };
      }));
    }
    if (chartData?.macd?.macd?.length)   macdS.current.setData(chartData.macd.macd);
    if (chartData?.macd?.signal?.length) sigS.current.setData(chartData.macd.signal);
  }, [macdS.current, chartData?.macd]);

  const displayMacd = hoverTime && chartData?.macd?.macd
    ? findClosest(chartData.macd.macd, hoverTime)?.value ?? null
    : hover?.macd ?? null;
  const displaySig = hoverTime && chartData?.macd?.signal
    ? findClosest(chartData.macd.signal, hoverTime)?.value ?? null
    : hover?.signal ?? null;
  const displayHist = hoverTime && chartData?.macd?.histogram
    ? findClosest(chartData.macd.histogram, hoverTime)?.value ?? null
    : hover?.hist ?? null;
  const items = (hoverTime || hover) ? [
    { label: 'MACD',   value: displayMacd != null ? displayMacd.toFixed(2) : '—', color: '#2196f3' },
    { label: 'Signal', value: displaySig  != null ? displaySig.toFixed(2)  : '—', color: '#ff9800' },
    { label: 'Hist',   value: displayHist != null ? displayHist.toFixed(2) : '—',
      color: displayHist != null
        ? displayHist >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'
        : 'var(--text-muted)',
    },
  ] : [];

  return (
    <div style={{
      height, flexShrink: 0,
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden', position: 'relative',
    }}>
      <PanelHeader title="MACD" titleUppercase onClose={onClose} onMoveUp={onMoveUp} onMoveDown={onMoveDown} />
      <HoverLegend items={items} />
      <div ref={el} style={{ width, height: innerH, overflow: 'hidden', flexShrink: 0 }} />
    </div>
  );
}

// ─── ChartContainer ───────────────────────────────────────────────────────────

export default function ChartContainer({
  symbol, timeframe, emas, volumeVisible,
  visiblePanels, panelOrder, onTogglePanel, onMovePanel,
  onLastChange, onHeightsChange,
  preloadedData, preloadedLoading, preloadedError,
  panelHeights,
  columnIndex = 0,
  independentHeights = false,
  columnCount = 1,
  neighborHeightsLeft = null,
  neighborHeightsRight = null,
  heightsRevision = 0,
  onCrosshairMove, crosshairTime,
  dayChangePctOverride = null,
  liveToday = false,
  liveRefreshKey = null,
  drawingScopeId = null,
  drawingAutoFocus = true,
  pricePanelTitle = null,
}) {
  const isPreloaded = preloadedData !== undefined;
  const intraday = useIntradayPatchOptional();
  const [_chartData, _setChartData] = useState(null);
  const [_loading,   _setLoading]   = useState(true);
  const [_error,     _setError]     = useState(null);
  const chartData = isPreloaded ? preloadedData : _chartData;
  const loading   = isPreloaded ? (preloadedLoading ?? true) : _loading;
  const error     = isPreloaded ? (preloadedError ?? null)   : _error;

  const displayChartData = useMemo(() => {
    if (!chartData?.bars?.length) return chartData;
    let bars = sanitizeBarsForDisplay(chartData.bars);
    let dayChangePct = chartData.day_change_pct;
    let liveTodayBar = chartData.live_today_bar;

    if (liveToday && intraday?.enabled && symbol) {
      const merged = intraday.applyToChartBars(bars, symbol, timeframe);
      const hasLiveBar = merged.bars?.some((b) => b.live);
      if (hasLiveBar || merged.dayChangePct != null) {
        bars = sanitizeBarsForDisplay(merged.bars);
        dayChangePct = merged.dayChangePct ?? dayChangePct;
        liveTodayBar = hasLiveBar ?? liveTodayBar;
      }
    }

    if (bars === chartData.bars && dayChangePct === chartData.day_change_pct) {
      return chartData;
    }
    return {
      ...chartData,
      bars,
      day_change_pct: dayChangePct,
      live_today_bar: liveTodayBar,
    };
  }, [chartData, liveToday, intraday, intraday?.refreshTick, symbol, timeframe]);
  const syncRef      = useRef([]);
  const syncMutedRef = useRef(false);
  const panelResizeDragRef = useRef(false);
  const snapNeighborsRef = useRef({ left: null, right: null });
  const activeResizeEdgeRef = useRef(null);
  const dimsRef = useRef({ width: 0, height: 0 });
  const [markerRelayoutEpoch, setMarkerRelayoutEpoch] = useState(0);

  const [hoverTime, setHoverTime] = useState(null);
  const [earningsEvents, setEarningsEvents] = useState([]);
  const [earningsPlusHelper, setEarningsPlusHelper] = useState(null);
  const [selectedEarningsEvent, setSelectedEarningsEvent] = useState(null);
  const shouldLoadChartEarningsMarkers = shouldShowEarningsMarkers(timeframe);

  const effectiveDrawingScope = CHART_DRAWINGS_ENABLED ? drawingScopeId : null;
  const { drawings, setDrawings } = useChartDrawings(effectiveDrawingScope);

  const dw = useDrawingWorkspace();
  const dwRef = useRef(dw);
  dwRef.current = dw;
  const drawingWsActive = !!effectiveDrawingScope && dw;
  const activeTool = dw?.activeTool ?? null;
  const lineColor = dw?.lineColor ?? '#58a6ff';
  const lineWidth = dw?.lineWidth ?? 2;
  const isDrawingTarget = !dw
    || !effectiveDrawingScope
    || dw.focusedScopeId == null
    || dw.focusedScopeId === effectiveDrawingScope;

  const [selectedDrawingId, setSelectedDrawingId] = useState(null);
  const selectedDrawingIdRef = useRef(null);
  selectedDrawingIdRef.current = selectedDrawingId;

  const drawingEnabled = !!effectiveDrawingScope;

  useEffect(() => {
    if (!drawingWsActive || !effectiveDrawingScope || !dw) return;
    return dw.mountChart(effectiveDrawingScope, {
      clearAll: () => {
        setDrawings([]);
        setSelectedDrawingId(null);
        dw.notifyToolbar();
      },
      deleteSelected: () => {
        const sid = selectedDrawingIdRef.current;
        if (!sid) return;
        setDrawings((prev) => prev.filter((d) => d.id !== sid));
        setSelectedDrawingId(null);
        dw.notifyToolbar();
      },
      hasSelection: () => !!selectedDrawingIdRef.current,
    });
  }, [drawingWsActive, effectiveDrawingScope, dw, setDrawings]);

  useEffect(() => {
    setSelectedDrawingId(null);
    dwRef.current?.setActiveTool(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveDrawingScope]);

  useEffect(() => {
    if (!dw || !effectiveDrawingScope || !drawingAutoFocus) return;
    dw.setFocusedScopeId(effectiveDrawingScope);
  }, [dw, effectiveDrawingScope, drawingAutoFocus]);

  const reloadEarningsEvents = useCallback(() => {
    if (!symbol || !shouldLoadChartEarningsMarkers) {
      setEarningsEvents([]);
      setEarningsPlusHelper(null);
      return;
    }
    fetchEarningsChartEvents(symbol)
      .then((data) => {
        setEarningsEvents(Array.isArray(data?.rows) ? data.rows : []);
        setEarningsPlusHelper(data?.earnings_plus_helper || null);
      })
      .catch(() => {
        setEarningsEvents([]);
        setEarningsPlusHelper(null);
      });
  }, [symbol, shouldLoadChartEarningsMarkers]);

  useEffect(() => {
    setSelectedEarningsEvent(null);
  }, [symbol]);

  // Sync charts when crosshair arrives from sibling panel (split layouts). Stock `price`
  // must only apply to the candle series — never to StochRSI (0–100) or MACD scales.
  useEffect(() => {
    if (!crosshairTime) {
      syncRef.current.forEach(entry => {
        try { entry.chart.clearCrosshairPosition(); } catch {}
      });
      return;
    }
    const t = typeof crosshairTime === 'object' ? crosshairTime.time : crosshairTime;
    const p = typeof crosshairTime === 'object' ? crosshairTime.price : null;
    if (!t) return;
    setHoverTime(t);
    syncRef.current.forEach(entry => {
      if (!entry.chart || !entry.series) return;
      if (entry.isPriceMaster) {
        try { entry.chart.setCrosshairPosition(p ?? 0, t, entry.series); } catch {}
        return;
      }
      let y = 50;
      if (entry.indicatorKind === 'stoch') {
        const k = seriesValueAtTime(chartData?.stochrsi?.k, t);
        const d = seriesValueAtTime(chartData?.stochrsi?.d, t);
        y = k != null && Number.isFinite(k) ? k : (d != null && Number.isFinite(d) ? d : 50);
      } else if (entry.indicatorKind === 'macd') {
        const m = seriesValueAtTime(chartData?.macd?.macd, t);
        y = m != null && Number.isFinite(m) ? m : 0;
      } else {
        y = 0;
      }
      try { entry.chart.setCrosshairPosition(y, t, entry.series); } catch {}
    });
  }, [crosshairTime, chartData]);

  const wrapperRef   = useRef(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });

  const INDICATOR_H = 130;
  const HANDLE_H    = 4;

  const [manualHeights, setManualHeights] = useState(() => (
    panelHeights
      ? { stochrsi: panelHeights.stochrsi ?? INDICATOR_H, macd: panelHeights.macd ?? INDICATOR_H }
      : { ...globalPanelHeights }
  ));

  useEffect(() => {
    if (panelResizeDragRef.current) return;
    if (independentHeights) return;
    if (!panelHeights) return;
    const next = {
      stochrsi: panelHeights.stochrsi ?? INDICATOR_H,
      macd: panelHeights.macd ?? INDICATOR_H,
    };
    setManualHeights(prev => {
      if (prev.stochrsi === next.stochrsi && prev.macd === next.macd) return prev;
      syncMutedRef.current = true;
      setTimeout(() => { syncMutedRef.current = false; }, 150);
      return next;
    });
  }, [independentHeights, panelHeights?.stochrsi, panelHeights?.macd]);

  useEffect(() => {
    if (panelResizeDragRef.current) return;
    if (!independentHeights) return;
    if (panelHeights) {
      setManualHeights({
        stochrsi: panelHeights.stochrsi ?? INDICATOR_H,
        macd: panelHeights.macd ?? INDICATOR_H,
      });
    }
  }, [independentHeights, heightsRevision, panelHeights?.stochrsi, panelHeights?.macd]);

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      window.requestAnimationFrame(() => {
        const { width, height } = entries[0].contentRect;
        if (width <= 0 || height <= 0) return;
        const floorW = Math.floor(width);
        const floorH = Math.floor(height);
        if (panelResizeDragRef.current) {
          if (floorW > 0 && floorW !== dimsRef.current.width) {
            dimsRef.current = { width: floorW, height: dimsRef.current.height || floorH };
            setDims(prev => ({ width: floorW, height: prev.height || floorH }));
          }
          return;
        }
        dimsRef.current = { width: floorW, height: floorH };
        setDims({ width: floorW, height: floorH });
      });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const emaKey = emas.map(e => e.period).join(',');
  const onLastChangeRef = useRef(onLastChange);
  onLastChangeRef.current = onLastChange;
  const dayChangeOverrideRef = useRef(dayChangePctOverride);
  dayChangeOverrideRef.current = dayChangePctOverride;

  const reloadChart = useCallback(({ background = false } = {}) => {
    if (isPreloaded) return;
    if (!symbol) return;
    if (!background) {
      _setLoading(true);
      _setError(null);
      _setChartData(null);
    }
    const emaPeriods = emas.map(e => e.period);
    fetchChartData(symbol, timeframe, emaPeriods, 700, liveToday)
      .then((data) => {
        if (liveToday && intraday?.enabled) {
          const merged = intraday.applyToChartBars(data.bars, symbol, timeframe);
          data = {
            ...data,
            bars: merged.bars,
            day_change_pct: merged.dayChangePct ?? data.day_change_pct,
            live_today_bar: merged.bars?.some((b) => b.live) ?? data.live_today_bar,
          };
        }
        _setChartData(data);
        _setLoading(false);
        if (data.bars?.length) dispatchChromeIntroReadyOnce();
        const cb = onLastChangeRef.current;
        if (cb && data.bars && data.bars.length >= 2) {
          const last = data.bars[data.bars.length - 1];
          const pct = pickDayOverDayPctFromChartPayload(data, dayChangeOverrideRef.current);
          if (pct != null && Number.isFinite(pct) && last?.close != null) {
            cb(Math.round(pct * 100) / 100, last.close);
          }
        }
      })
      .catch(err => { _setError(err.message || 'Failed to load'); _setLoading(false); });
  }, [isPreloaded, symbol, timeframe, emaKey, liveToday, intraday]);

  useEffect(() => {
    if (!liveToday || !intraday?.enabled || intraday.refreshTick == null) return undefined;
    reloadChart({ background: true });
    return undefined;
  }, [intraday?.refreshTick, intraday?.enabled, liveToday, reloadChart]);

  useEffect(() => {
    reloadChart();
  }, [reloadChart]);

  useEffect(() => {
    reloadEarningsEvents();
  }, [reloadEarningsEvents]);

  useEffect(() => {
    if (!liveToday || liveRefreshKey == null) return undefined;
    reloadChart({ background: true });
    return undefined;
  }, [liveRefreshKey, liveToday, reloadChart]);

  useEffect(() => {
    if (!isPreloaded || loading || error || !displayChartData?.bars?.length) return;
    dispatchChromeIntroReadyOnce();
    const cb = onLastChangeRef.current;
    if (!cb) return;
    const pct = pickDayOverDayPctFromChartPayload(displayChartData, dayChangeOverrideRef.current);
    const last = displayChartData.bars[displayChartData.bars.length - 1];
    if (pct == null || !Number.isFinite(pct) || last?.close == null) return;
    cb(Math.round(pct * 100) / 100, last.close);
  }, [isPreloaded, loading, error, displayChartData, liveToday, intraday?.refreshTick]);

  useEffect(() => {
    if (!onLastChange || dayChangePctOverride == null || !Number.isFinite(Number(dayChangePctOverride))) return;
    onLastChange(Math.round(Number(dayChangePctOverride) * 100) / 100, null);
  }, [onLastChange, dayChangePctOverride, symbol]);

  useEffect(() => {
    const onChartDataUpdated = () => reloadChart({ background: true });
    window.addEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
    return () => window.removeEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
  }, [reloadChart]);

  useEffect(() => {
    const onChartDataUpdated = () => reloadEarningsEvents();
    window.addEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
    return () => window.removeEventListener(CHART_DATA_UPDATED_EVENT, onChartDataUpdated);
  }, [reloadEarningsEvents]);

  const activePanels = panelOrder.filter(k => visiblePanels[k]);

  function handleResizePanel(panelKey, nextPanelKey, delta) {
    setManualHeights(prev => {
      const next = {
        ...prev,
        [panelKey]:     Math.max(MIN_PANEL_H, (prev[panelKey]     || INDICATOR_H) + delta),
        [nextPanelKey]: Math.max(MIN_PANEL_H, (prev[nextPanelKey] || INDICATOR_H) - delta),
      };
      if (!independentHeights && !panelHeights) Object.assign(globalPanelHeights, next);
      return next;
    });
  }

  function handleResizeStart(upperKey) {
    panelResizeDragRef.current = true;
    syncMutedRef.current = true;
    emitChartPanelResizeDrag(true);
    if (!independentHeights || columnCount <= 1) return;
    activeResizeEdgeRef.current = upperKey;
    snapNeighborsRef.current = {
      left: neighborHeightsLeft ? { ...neighborHeightsLeft } : null,
      right: neighborHeightsRight ? { ...neighborHeightsRight } : null,
    };
  }

  function handleResizeEnd() {
    const upperKey = activeResizeEdgeRef.current;
    const { left, right } = snapNeighborsRef.current;
    syncMutedRef.current = true;
    setManualHeights(prev => {
      let next = prev;
      if (independentHeights && columnCount > 1 && upperKey) {
        next = snapDraggedColumnOnEdgeRelease(
          prev,
          columnIndex,
          columnCount,
          left,
          right,
          upperKey,
          {
            containerHeight: dimsRef.current.height || dims.height,
            panelKeys: activePanels,
            handleH: HANDLE_H,
            defaultH: INDICATOR_H,
          },
        );
      }
      activeResizeEdgeRef.current = null;
      if (!independentHeights && !panelHeights) Object.assign(globalPanelHeights, next);
      if (onHeightsChange) onHeightsChange(next, columnIndex);
      return next;
    });
    panelResizeDragRef.current = false;
    emitChartPanelResizeDrag(false);
    setMarkerRelayoutEpoch(e => e + 1);
    setTimeout(() => { syncMutedRef.current = false; }, 150);
  }

  const indicatorTotal = activePanels.reduce(
    (sum, k) => sum + (manualHeights[k] || INDICATOR_H) + HANDLE_H, 0
  );
  const priceH = Math.max(MIN_PANEL_H, dims.height - indicatorTotal);

  const priceLen    = displayChartData?.bars?.length        || 0;
  const stochLen    = displayChartData?.stochrsi?.k?.length || 0;
  const macdLen     = displayChartData?.macd?.macd?.length  || 0;
  const stochOffset = Math.max(0, priceLen - stochLen);
  const macdOffset  = Math.max(0, priceLen - macdLen);

  if (loading) return (
    <div ref={wrapperRef} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
      Loading {symbol}...
    </div>
  );

  if (error) return (
    <div ref={wrapperRef} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-red)', fontSize: 13 }}>
      {error}
    </div>
  );

  const onPriceSurfaceMouseDownCapture = drawingWsActive && effectiveDrawingScope
    ? () => { dw.setFocusedScopeId(effectiveDrawingScope); }
    : undefined;

  return (
    <div ref={wrapperRef} style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
      {dims.width > 0 && dims.height > 0 && (
        <>
          <PricePanel
            key={`price-${dims.width}-${timeframe}`}
            width={dims.width}
            height={priceH}
            chartData={displayChartData}
            timeframe={timeframe}
            emas={emas}
            volumeVisible={volumeVisible}
            earningsEvents={earningsEvents}
            earningsPlusHelper={earningsPlusHelper}
            onEarningsMarkerSelect={setSelectedEarningsEvent}
            syncRef={syncRef}
            syncMutedRef={syncMutedRef}
            panelResizeDragRef={panelResizeDragRef}
            markerRelayoutEpoch={markerRelayoutEpoch}
            onCrosshairMove={onCrosshairMove}
            crosshairTime={crosshairTime}
            onHoverTime={setHoverTime}
            onLastChange={onLastChange}
            dayChangePctOverride={dayChangePctOverride}
            pricePanelTitle={pricePanelTitle}
            drawingEnabled={drawingEnabled}
            drawings={drawings}
            setDrawings={setDrawings}
            activeTool={activeTool}
            lineColor={lineColor}
            lineWidth={lineWidth}
            selectedDrawingId={selectedDrawingId}
            setSelectedDrawingId={setSelectedDrawingId}
            isDrawingTarget={isDrawingTarget}
            onPriceSurfaceMouseDownCapture={onPriceSurfaceMouseDownCapture}
            onRequestToolbarUpdate={dw ? dw.notifyToolbar : undefined}
          />
          {activePanels.map((key, idx) => {
            const prevKey = idx === 0 ? 'price' : activePanels[idx - 1];
            const isFirst = idx === 0;
            const isLast  = idx === activePanels.length - 1;
            const h       = manualHeights[key] || INDICATOR_H;
            const offset  = key === 'stochrsi' ? stochOffset
                          : key === 'macd'     ? macdOffset : 0;
            const commonProps = {
              width:      dims.width,
              height:     h,
              chartData:  displayChartData,
              timeframe,
              offset,
              syncRef,
              onClose:    () => onTogglePanel(key),
              onMoveUp:   !isFirst ? () => onMovePanel(key, 'up')   : null,
              onMoveDown: !isLast  ? () => onMovePanel(key, 'down') : null,
            };
            return (
              <React.Fragment key={key}>
                <PanelResizeHandle
                  onResize={d => handleResizePanel(prevKey, key, d)}
                  onResizeStart={() => handleResizeStart(prevKey)}
                  onResizeEnd={handleResizeEnd}
                />
                {key === 'stochrsi' && <StochRSIPanel key={`stochrsi-${dims.width}-${timeframe}`} {...commonProps} hoverTime={hoverTime} />}
                {key === 'macd'     && <MACDPanel     key={`macd-${dims.width}-${timeframe}`}     {...commonProps} hoverTime={hoverTime} />}
              </React.Fragment>
            );
          })}
        </>
      )}
      {selectedEarningsEvent && (
        <PortfolioEarningsModal
          symbol={symbol}
          variant={getEarningsModalVariant(selectedEarningsEvent.outcome_kind)}
          earningsDate={selectedEarningsEvent.earnings_release_date}
          daysSinceReport={daysSinceYmd(selectedEarningsEvent.earnings_release_date)}
          comparisonStatus={selectedEarningsEvent.comparison_status}
          comparisonNote={selectedEarningsEvent.comparison_note || ''}
          onClose={() => setSelectedEarningsEvent(null)}
        />
      )}
    </div>
  );
}
