/** @typedef {'trendline'|'h_line'|'h_ray'|'v_line'|'cross'|'channel'|'ray'|'fib'|'price_range'} DrawingTool */

export const DRAWING_TOOLS = [
  { id: 'trendline', label: 'Trendline', short: '∠', steps: 2 },
  { id: 'h_line', label: 'Horizontal', short: 'H', steps: 1 },
  { id: 'h_ray', label: 'H. Ray', short: 'HR', steps: 2 },
  { id: 'v_line', label: 'Vertical', short: 'V', steps: 1 },
  { id: 'cross', label: 'Cross', short: '+', steps: 1 },
  { id: 'channel', label: 'Channel', short: '⫽', steps: 3 },
  { id: 'ray', label: 'Ray', short: '›', steps: 2 },
  { id: 'fib', label: 'Fib', short: 'φ', steps: 2 },
  { id: 'price_range', label: 'Price Range', short: '═↑═', steps: 2 },
];

/** Default Fibonacci retracement ratios (as decimals 0–1) */
export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

export const DEFAULT_LINE_COLOR = '#58a6ff';
export const DEFAULT_LINE_WIDTH = 2;

export function newDrawingId() {
  return `dr_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * @param {DrawingTool} type
 * @param {{ time: *, price: number }[]} points
 * @param {{ color?: string, lineWidth?: number }} style
 */
export function createDrawing(type, points, style = {}) {
  return {
    id: newDrawingId(),
    type,
    points: points.map(p => ({ time: p.time, price: Number(p.price) })),
    color: style.color || DEFAULT_LINE_COLOR,
    lineWidth: style.lineWidth != null ? style.lineWidth : DEFAULT_LINE_WIDTH,
  };
}
