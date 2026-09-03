import {
  CROSSHAIR_RESTORE_GUARD_MS,
  isSpuriousCrosshairMove,
  restoreCrosshairAtPointY,
  shouldBroadcastCrosshair,
  shouldIgnoreCrosshairEvent,
} from './chartCrosshairPin';

describe('chartCrosshairPin', () => {
  test('shouldIgnoreCrosshairEvent respects guard window', () => {
    expect(shouldIgnoreCrosshairEvent(0, 100)).toBe(false);
    expect(shouldIgnoreCrosshairEvent(150, 100)).toBe(true);
    expect(shouldIgnoreCrosshairEvent(150, 200)).toBe(false);
  });

  test('shouldBroadcastCrosshair dedupes same time and pointY', () => {
    const prev = { time: 1700000000, pointY: 120, source: 'a' };
    const next = { time: 1700000000, pointY: 120.2, source: 'a' };
    expect(shouldBroadcastCrosshair(prev, next)).toBe(false);
    expect(shouldBroadcastCrosshair(prev, { ...next, pointY: 125 })).toBe(true);
    expect(shouldBroadcastCrosshair(prev, { ...next, time: 1700003600 })).toBe(true);
  });

  test('isSpuriousCrosshairMove detects stale pointer / Y snap', () => {
    expect(isSpuriousCrosshairMove({
      pointerActive: true,
      lastPointerAt: 1000,
      lastPointerY: 200,
      eventPointY: 200,
      now: 1020,
    })).toBe(false);
    expect(isSpuriousCrosshairMove({
      pointerActive: true,
      lastPointerAt: 1000,
      lastPointerY: 200,
      eventPointY: 250,
      now: 1020,
    })).toBe(true);
    expect(isSpuriousCrosshairMove({
      pointerActive: true,
      lastPointerAt: 1000,
      lastPointerY: 200,
      eventPointY: 200,
      now: 1200,
    })).toBe(true);
    expect(isSpuriousCrosshairMove({
      pointerActive: false,
      lastPointerAt: 1000,
      lastPointerY: 200,
      eventPointY: 200,
      now: 1010,
    })).toBe(true);
  });

  test('restoreCrosshairAtPointY calls setCrosshairPosition', () => {
    const setCrosshairPosition = jest.fn();
    const series = {
      coordinateToPrice: (y) => (y === 100 ? 2500.5 : null),
    };
    const chart = { setCrosshairPosition };
    const ok = restoreCrosshairAtPointY(chart, series, { time: 99, pointY: 100 });
    expect(ok).toBe(true);
    expect(setCrosshairPosition).toHaveBeenCalledWith(2500.5, 99, series);
  });

  test('CROSSHAIR_RESTORE_GUARD_MS is positive', () => {
    expect(CROSSHAIR_RESTORE_GUARD_MS).toBeGreaterThan(0);
  });
});
