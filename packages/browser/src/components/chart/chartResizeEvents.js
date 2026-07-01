/** Broadcast chart indicator height drag so heavy pages can pause live table overlays. */
const EVENT = 'cim-chart-panel-resize';

export function emitChartPanelResizeDrag(active) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { active: !!active } }));
}

export function subscribeChartPanelResizeDrag(listener) {
  if (typeof window === 'undefined') return () => {};
  const handler = (e) => listener(!!e.detail?.active);
  window.addEventListener(EVENT, handler);
  return () => window.removeEventListener(EVENT, handler);
}
