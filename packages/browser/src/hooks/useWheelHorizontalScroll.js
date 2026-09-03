import { useEffect } from 'react';

/**
 * Map vertical mouse-wheel to horizontal scroll when the element overflows.
 * Use on overflow-x:auto strips (top tab bar, toolbars) so users need not drag the scrollbar.
 */
export function useWheelHorizontalScroll(ref) {
  useEffect(() => {
    const el = ref?.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      if (el.scrollWidth <= el.clientWidth + 0.5) return;
      const dy = e.deltaY;
      const dx = e.deltaX;
      // Prefer vertical wheel → horizontal; allow trackpad horizontal delta as-is.
      const delta = Math.abs(dy) >= Math.abs(dx) ? dy : dx;
      if (!delta) return;
      e.preventDefault();
      el.scrollLeft += delta;
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [ref]);
}
