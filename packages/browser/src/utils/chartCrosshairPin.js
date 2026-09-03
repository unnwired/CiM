/** Crosshair stability helpers for live chart updates. */

export const CROSSHAIR_RESTORE_GUARD_MS = 250;
export const POINTER_STALE_MS = 80;
export const SPURIOUS_Y_EPSILON_PX = 1.5;

export function shouldIgnoreCrosshairEvent(guardUntilMs, now = Date.now()) {
  return guardUntilMs > 0 && now < guardUntilMs;
}

/** True when LW fired a move without a recent native pointermove (live bar update snap). */
export function isSpuriousCrosshairMove({
  pointerActive,
  lastPointerAt,
  lastPointerY,
  eventPointY,
  now = Date.now(),
  staleMs = POINTER_STALE_MS,
  yEpsilon = SPURIOUS_Y_EPSILON_PX,
}) {
  if (!pointerActive) return true;
  if (!lastPointerAt || now - lastPointerAt > staleMs) return true;
  if (lastPointerY == null || eventPointY == null) return false;
  return Math.abs(Number(eventPointY) - Number(lastPointerY)) > yEpsilon;
}

export function shouldBroadcastCrosshair(prev, next, pointEpsilon = 0.5) {
  if (!next) return true;
  if (!prev) return true;
  if (String(prev.time ?? '') !== String(next.time ?? '')) return true;
  if (String(prev.source ?? '') !== String(next.source ?? '')) return true;
  const py0 = Number(prev.pointY);
  const py1 = Number(next.pointY);
  if (!Number.isFinite(py0) || !Number.isFinite(py1)) return true;
  return Math.abs(py0 - py1) >= pointEpsilon;
}

export function restoreCrosshairAtPointY(chart, series, pin) {
  if (!chart || !series || !pin || pin.time == null || pin.pointY == null) return false;
  try {
    const price = series.coordinateToPrice(pin.pointY);
    if (price == null || !Number.isFinite(Number(price))) return false;
    chart.setCrosshairPosition(Number(price), pin.time, series);
    return true;
  } catch {
    return false;
  }
}
