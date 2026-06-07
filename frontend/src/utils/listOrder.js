/** Stable keys and merge helpers for persisted sidebar / table ordering. */

export function wlItemKey(it) {
  return `${String(it.type).toLowerCase()}:${String(it.symbol).toUpperCase()}`;
}

export function portfolioRowKey(row) {
  const t = row.instrumentType === 'index' ? 'index' : 'stock';
  return `${t}:${String(row.Symbol)}`;
}

/**
 * Reorders `items` to match `savedOrder` where possible; unknown keys are appended in original item order.
 */
export function applySavedOrder(items, savedOrder, getKey) {
  if (!items || items.length === 0) return items || [];
  if (!savedOrder || !Array.isArray(savedOrder) || savedOrder.length === 0) return items;
  const keyToItem = new Map(items.map(it => [getKey(it), it]));
  const used = new Set();
  const out = [];
  for (const k of savedOrder) {
    if (keyToItem.has(k)) {
      out.push(keyToItem.get(k));
      used.add(k);
    }
  }
  for (const it of items) {
    const k = getKey(it);
    if (!used.has(k)) out.push(it);
  }
  return out;
}

export function reorderByIndex(items, fromIdx, toIdx) {
  if (fromIdx === toIdx || fromIdx < 0 || toIdx < 0 || fromIdx >= items.length || toIdx >= items.length) {
    return items;
  }
  const next = [...items];
  const [removed] = next.splice(fromIdx, 1);
  next.splice(toIdx, 0, removed);
  return next;
}

/**
 * Move item at `fromIdx` so it ends up **before** gap index `gap` (0…length).
 * gap === length means append at end. Uses half-row hover to pick gap in the UI.
 */
export function reorderByGap(items, fromIdx, gap) {
  const n = items.length;
  if (n === 0 || fromIdx < 0 || fromIdx >= n) return items;
  if (gap < 0 || gap > n) return items;
  const next = [...items];
  const [removed] = next.splice(fromIdx, 1);
  let insert = gap;
  if (gap > fromIdx) insert -= 1;
  next.splice(insert, 0, removed);
  return next;
}

/** Row `rowIndex`: top half → insert before row; bottom half → insert after row. */
export function insertionGapFromRowHover(clientY, rowElement, rowIndex, listLength) {
  const r = rowElement.getBoundingClientRect();
  const mid = r.top + r.height / 2;
  const gap = clientY < mid ? rowIndex : rowIndex + 1;
  return Math.max(0, Math.min(listLength, gap));
}
