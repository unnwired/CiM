import { useLayoutEffect, useRef } from 'react';

/**
 * Keep a separate stock-list header strip horizontally synced with the rows scroller.
 * Header uses overflowX:hidden; rows own horizontal scroll; header.scrollLeft tracks rows.
 *
 * @param {unknown[]} [syncDeps] — remount/realign when columns or layout change
 * @returns {{ headerScrollRef: React.RefObject<HTMLElement|null>, rowsScrollRef: React.RefObject<HTMLElement|null> }}
 */
export function useSyncedHeaderScroll(syncDeps = []) {
  const headerScrollRef = useRef(null);
  const rowsScrollRef = useRef(null);

  useLayoutEffect(() => {
    const headerEl = headerScrollRef.current;
    const rowsEl = rowsScrollRef.current;
    if (!headerEl || !rowsEl) return undefined;

    const syncHeader = () => {
      if (headerEl.scrollLeft !== rowsEl.scrollLeft) {
        headerEl.scrollLeft = rowsEl.scrollLeft;
      }
    };
    syncHeader();
    rowsEl.addEventListener('scroll', syncHeader, { passive: true });
    return () => rowsEl.removeEventListener('scroll', syncHeader);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller passes layout deps
  }, syncDeps);

  return { headerScrollRef, rowsScrollRef };
}
