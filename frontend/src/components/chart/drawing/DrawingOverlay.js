/* eslint-disable react-hooks/exhaustive-deps */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createDrawing } from './drawingTypes';
import { hitTestSegments } from './hitTest';
import { segmentsForDrawing, handlePositions } from './drawingSegments';
import { xToTime, yToPrice, timeToX as tx, priceToY as py } from './drawingGeometry';

/**
 * @param {{
 *   chartRef: React.MutableRefObject<any>,
 *   seriesRef: React.MutableRefObject<any>,
 *   width: number,
 *   height: number,
 *   drawings: any[],
 *   setDrawings: (fn: any) => void,
 *   activeTool: string | null,
 *   lineColor: string,
 *   lineWidth: number,
 *   selectedId: string | null,
 *   setSelectedId: (id: string | null) => void,
 *   isDrawingTarget: boolean,
 *   drawingScopeId: string | null,
 *   onRequestToolbarUpdate?: () => void,
 * }} props
 */
export default function DrawingOverlay({
  chartRef,
  seriesRef,
  width,
  height,
  drawings,
  setDrawings,
  activeTool,
  lineColor,
  lineWidth,
  selectedId,
  setSelectedId,
  isDrawingTarget,
  drawingScopeId,
  onRequestToolbarUpdate,
}) {
  const [, setRepaint] = useState(0);
  const [draftPoints, setDraftPoints] = useState([]);
  const [pointerPoint, setPointerPoint] = useState(null);

  const chart = chartRef?.current;
  const series = seriesRef?.current;

  useEffect(() => {
    if (!chart) return;
    const ts = chart.timeScale();
    const u = () => setRepaint((x) => x + 1);
    ts.subscribeVisibleLogicalRangeChange(u);
    return () => ts.unsubscribeVisibleLogicalRangeChange(u);
  }, [chartRef, chart]);

  useEffect(() => {
    setDraftPoints([]);
    setPointerPoint(null);
  }, [activeTool]);

  const allSegs = useMemo(() => {
    if (!chart || !series || width <= 0 || height <= 0) return [];
    const acc = [];
    for (const d of drawings) {
      acc.push(...segmentsForDrawing(d, chart, series, width, height));
    }
    return acc;
  }, [chart, series, width, height, drawings, chartRef, seriesRef]);

  const rangeLabels = useMemo(() => {
    if (!chart || !series || width <= 0 || height <= 0) return [];
    return drawings
      .filter((d) => d?.type === 'price_range' && (d.points || []).length >= 2)
      .map((d) => {
        const p1 = Number(d.points[0].price);
        const p2 = Number(d.points[1].price);
        const x1 = tx(chart, series, d.points[0].time);
        const y1 = py(series, p1);
        const x2 = tx(chart, series, d.points[1].time);
        const y2 = py(series, p2);
        if ([x1, y1, x2, y2].some((v) => v == null || Number.isNaN(v))) return null;
        const delta = p2 - p1;
        const pct = p1 !== 0 ? (delta / p1) * 100 : null;
        const color = delta >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
        const xa = Math.min(x1, x2);
        const xb = Math.max(x1, x2);
        const yTop = Math.min(y1, y2);
        const yLabel = Math.max(10, yTop - 12);
        const label = `${delta >= 0 ? '+' : ''}${delta.toFixed(2)} • ${pct == null ? '—' : `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`}`;
        return { id: d.id, x: xa + (xb - xa) / 2, y: yLabel, label, color };
      })
      .filter(Boolean);
  }, [chart, series, width, height, drawings]);

  const hitTest = useCallback(
    (px, py) => {
      if (!chart || !series) return null;
      for (let i = drawings.length - 1; i >= 0; i--) {
        const d = drawings[i];
        const segs = segmentsForDrawing(d, chart, series, width, height)
          .filter((s) => s.type === 'line')
          .map((s) => ({ x1: s.x1, y1: s.y1, x2: s.x2, y2: s.y2 }));
        const idx = hitTestSegments(px, py, segs, 10);
        if (idx >= 0) return d.id;
      }
      return null;
    },
    [chart, series, width, height, drawings],
  );

  const mapClick = (clientX, clientY, el) => {
    const r = el.getBoundingClientRect();
    return { x: clientX - r.left, y: clientY - r.top };
  };

  const pushPoint = (time, price) => {
    const next = [...draftPoints, { time, price }];
    setDraftPoints(next);
    return next;
  };

  const finishPlacement = (tool, points) => {
    if (!tool || tool === 'select' || points.length === 0) return;
    const def = createDrawing(tool, points, { color: lineColor, lineWidth });
    setDrawings((prev) => [...prev, def]);
    setDraftPoints([]);
    setPointerPoint(null);
    setSelectedId(tool === 'price_range' ? null : def.id);
    if (tool === 'price_range') {
      window.dispatchEvent(new CustomEvent('flowx-drawing-set-tool', { detail: { tool: null } }));
    }
    onRequestToolbarUpdate?.();
  };

  const stepsNeeded = (tool) => {
    const m = { trendline: 2, h_line: 1, h_ray: 2, v_line: 1, cross: 1, channel: 3, ray: 2, fib: 2, price_range: 2 };
    return m[tool] || 0;
  };

  const placing = isDrawingTarget && !!activeTool && activeTool !== 'select';
  const selectingByTool = isDrawingTarget && activeTool === 'select';
  const selecting = isDrawingTarget && (!activeTool || activeTool === 'select');

  const overlayEl = (e) => e.currentTarget.closest('[data-drawing-overlay]');

  const onPointerDown = (e) => {
    if (!chart || !series || width <= 0) return;
    const root = overlayEl(e);
    if (!root) return;
    const { x, y } = mapClick(e.clientX, e.clientY, root);
    const time = xToTime(chart, x);
    const price = yToPrice(series, y);
    if (time == null || price == null) return;

    if (!isDrawingTarget) return;

    if (activeTool === 'select' || !activeTool) {
      const hid = hitTest(x, y);
      setSelectedId(hid);
      onRequestToolbarUpdate?.();
      return;
    }

    const need = stepsNeeded(activeTool);
    const next = pushPoint(time, price);
    setPointerPoint({ time, price });
    if (next.length >= need) {
      if (activeTool === 'h_ray') {
        const p0 = next[0];
        const p1 = { time: next[1].time, price: p0.price };
        finishPlacement('h_ray', [p0, p1]);
      } else {
        finishPlacement(activeTool, next);
      }
    }
  };

  const onPointerMove = (e) => {
    if (!placing || !chart || !series || draftPoints.length === 0) return;
    const root = overlayEl(e);
    if (!root) return;
    const { x, y } = mapClick(e.clientX, e.clientY, root);
    const time = xToTime(chart, x);
    const price = yToPrice(series, y);
    if (time == null || price == null) return;
    setPointerPoint({ time, price });
  };

  const selected = drawings.find((d) => d.id === selectedId);
  const handles = selected && chart && series ? handlePositions(selected, chart, series) : [];

  const onHandleDrag = (e, ptIdx) => {
    e.stopPropagation();
    if (!selected || !chart || !series) return;
    const el = e.currentTarget.closest('[data-drawing-overlay]');
    const move = (ev) => {
      const r = el.getBoundingClientRect();
      const mx = ev.clientX - r.left;
      const my = ev.clientY - r.top;
      const t = xToTime(chart, mx);
      const pr = yToPrice(series, my);
      if (t == null || pr == null) return;
      setDrawings((prev) =>
        prev.map((d) => {
          if (d.id !== selectedId) return d;
          const pts = [...d.points];
          if (d.type === 'h_ray' && ptIdx === 1) {
            pts[1] = { time: t, price: pts[0].price };
          } else {
            pts[ptIdx] = { time: t, price: pr };
          }
          return { ...d, points: pts };
        }),
      );
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      onRequestToolbarUpdate?.();
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };

  const onDrawingDrag = (e, drawingId) => {
    if (!selecting || !chart || !series) return;
    e.stopPropagation();
    const el = e.currentTarget.closest('[data-drawing-overlay]');
    if (!el) return;
    const base = drawings.find((d) => d.id === drawingId);
    if (!base) return;
    setSelectedId(drawingId);
    const startX = e.clientX;
    const startY = e.clientY;
    const originalPts = (base.points || []).map((p) => ({ ...p }));
    const move = (ev) => {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      setDrawings((prev) =>
        prev.map((d) => {
          if (d.id !== drawingId) return d;
          const nextPts = originalPts.map((p) => {
            const px = tx(chart, series, p.time);
            const py0 = py(series, p.price);
            if (px == null || py0 == null) return p;
            const nextTime = xToTime(chart, px + dx);
            const nextPrice = yToPrice(series, py0 + dy);
            if (nextTime == null || nextPrice == null) return p;
            return { time: nextTime, price: nextPrice };
          });
          return { ...d, points: nextPts };
        }),
      );
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      onRequestToolbarUpdate?.();
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };

  useEffect(() => {
    if (!isDrawingTarget) return;
    const del = (ev) => {
      if (ev.key !== 'Delete' && ev.key !== 'Backspace') return;
      if (!selectedId) return;
      ev.preventDefault();
      setDrawings((prev) => prev.filter((d) => d.id !== selectedId));
      setSelectedId(null);
      onRequestToolbarUpdate?.();
    };
    window.addEventListener('keydown', del);
    return () => window.removeEventListener('keydown', del);
  }, [isDrawingTarget, selectedId, setDrawings, setSelectedId, onRequestToolbarUpdate]);

  const showDraft = draftPoints.length > 0 && placing;
  const draftSegments = useMemo(() => {
    if (!showDraft || !activeTool || !pointerPoint || !chart || !series || width <= 0 || height <= 0) return [];
    const need = stepsNeeded(activeTool);
    if (draftPoints.length >= need) return [];
    const previewPoints = [...draftPoints, pointerPoint];
    if (activeTool === 'h_ray' && previewPoints.length >= 2) {
      previewPoints[1] = { ...previewPoints[1], price: previewPoints[0].price };
    }
    const previewDrawing = {
      id: '__draft__',
      type: activeTool,
      points: previewPoints,
      color: lineColor,
      lineWidth,
    };
    return segmentsForDrawing(previewDrawing, chart, series, width, height);
  }, [showDraft, activeTool, pointerPoint, chart, series, width, height, draftPoints, lineColor, lineWidth]);

  const svgPointerEvents =
    isDrawingTarget && (placing || selectingByTool) ? 'auto' : 'none';

  return (
    <svg
      data-drawing-overlay
      width={width}
      height={height}
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        pointerEvents: svgPointerEvents,
        zIndex: 15,
      }}
      onMouseDown={selectingByTool ? onPointerDown : undefined}
      onContextMenu={placing ? (e) => {
        e.preventDefault();
        setDraftPoints([]);
        setPointerPoint(null);
        window.dispatchEvent(new CustomEvent('flowx-drawing-set-tool', { detail: { tool: null } }));
      } : undefined}
    >
      {allSegs.map((s, i) => {
        const d = drawings.find((row) => row.id === s.drawingId);
        const baseWidth = d?.lineWidth || 2;
        const strokeWidth = d?.type === 'price_range' ? Math.max(1, baseWidth - 1) : baseWidth;
        return (
          <line
            key={`${s.drawingId}-${i}`}
            x1={s.x1}
            y1={s.y1}
            x2={s.x2}
            y2={s.y2}
            stroke={d?.color || '#58a6ff'}
            strokeWidth={strokeWidth}
            strokeOpacity={selectedId === s.drawingId ? 1 : 0.92}
            style={{ pointerEvents: selecting ? 'stroke' : 'none', cursor: selecting ? 'grab' : 'default' }}
            onMouseDown={(e) => onDrawingDrag(e, s.drawingId)}
          />
        );
      })}
      {rangeLabels.map((r) => (
        <g key={`range-label-${r.id}`} style={{ pointerEvents: 'none' }}>
          <rect
            x={Math.max(2, r.x - 58)}
            y={Math.max(2, r.y - 10)}
            width={116}
            height={18}
            rx={4}
            fill="rgba(13,17,23,0.86)"
            stroke={r.color}
            strokeOpacity={0.55}
          />
          <text
            x={r.x}
            y={r.y + 2}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={r.color}
            fontSize={10}
            fontFamily="var(--font-mono)"
            fontWeight={700}
          >
            {r.label}
          </text>
        </g>
      ))}
      {showDraft &&
        draftPoints.map((p, idx) => {
          const x = tx(chart, series, p.time);
          const y = py(series, p.price);
          if (x == null || y == null) return null;
          return <circle key={idx} cx={x} cy={y} r={4} fill="var(--accent-blue)" style={{ pointerEvents: 'none' }} />;
        })}
      {draftSegments.map((s, i) => (
        <line
          key={`draft-${i}`}
          x1={s.x1}
          y1={s.y1}
          x2={s.x2}
          y2={s.y2}
          stroke={lineColor}
          strokeWidth={lineWidth}
          strokeDasharray="4 3"
          strokeOpacity={0.9}
          style={{ pointerEvents: 'none' }}
        />
      ))}
      {handles.map((h) => (
        <circle
          key={h.idx}
          cx={h.x}
          cy={h.y}
          r={5}
          fill="#fff"
          stroke="var(--accent-blue)"
          strokeWidth={2}
          style={{
            pointerEvents: selecting && isDrawingTarget ? 'auto' : 'none',
            cursor: 'grab',
          }}
          onMouseDown={(e) => onHandleDrag(e, h.idx)}
        />
      ))}
      {placing && (
        <rect
          width={width}
          height={height}
          fill="transparent"
          style={{ pointerEvents: 'all' }}
          onMouseDown={onPointerDown}
          onMouseMove={onPointerMove}
        />
      )}
    </svg>
  );
}
