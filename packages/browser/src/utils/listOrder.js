/** Stable keys and merge helpers for persisted sidebar / table ordering. */

export function wlItemKey(it) {
  return `${String(it.type).toLowerCase()}:${String(it.symbol).toUpperCase()}`;
}

export function portfolioRowKey(row) {
  const t = row.instrumentType === 'index' ? 'index' : 'stock';
  return `${t}:${String(row.Symbol)}`;
}

export function pnlOpenRowKey(row) {
  return String(row?.id || row?.symbol || '');
}

/**
 * Keep open-position row order after id changes (placeholder → real lot) or reload.
 * prevKeys aligns with prevRows by index.
 */
export function reconcilePnlRowOrder(prevKeys, newRows, prevRows = []) {
  if (!newRows?.length) return [];
  if (!prevKeys?.length) return newRows.map(pnlOpenRowKey);

  const byKey = new Map(newRows.map((r) => [pnlOpenRowKey(r), r]));
  const bySymbol = new Map();
  for (const r of newRows) {
    const sym = String(r.symbol || '').toUpperCase();
    if (!bySymbol.has(sym)) bySymbol.set(sym, []);
    bySymbol.get(sym).push(r);
  }

  const keyToPrevRow = new Map();
  prevKeys.forEach((k, i) => {
    const row = prevRows[i];
    if (k) keyToPrevRow.set(k, row);
  });

  const used = new Set();
  const out = [];

  for (const key of prevKeys) {
    if (byKey.has(key) && !used.has(key)) {
      out.push(key);
      used.add(key);
      continue;
    }

    let sym = null;
    if (String(key).startsWith('placeholder-')) {
      sym = String(key).slice('placeholder-'.length).toUpperCase();
    } else {
      const prevRow = keyToPrevRow.get(key);
      if (prevRow?.symbol) sym = String(prevRow.symbol).toUpperCase();
    }

    if (!sym) continue;

    const pool = (bySymbol.get(sym) || []).filter((r) => !used.has(pnlOpenRowKey(r)));
    if (!pool.length) continue;

    let pick = pool[0];
    const prevRow = keyToPrevRow.get(key);
    if (prevRow && pool.length > 1) {
      const prevEntry = prevRow.entry_price != null ? Number(prevRow.entry_price) : null;
      const prevQty = prevRow.qty != null ? Number(prevRow.qty) : null;
      const match = pool.find((r) => {
        const e = r.entry_price != null ? Number(r.entry_price) : null;
        const q = r.qty != null ? Number(r.qty) : null;
        if (prevEntry != null && e != null && prevEntry !== e) return false;
        if (prevQty != null && q != null && prevQty !== q) return false;
        return true;
      });
      if (match) pick = match;
    }

    const nk = pnlOpenRowKey(pick);
    out.push(nk);
    used.add(nk);
  }

  for (const r of newRows) {
    const k = pnlOpenRowKey(r);
    if (!used.has(k)) out.push(k);
  }

  return out;
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

/** Chip `chipIndex` in a horizontal rail: left half → insert before; right half → insert after. */
export function insertionGapFromChipHover(clientX, chipElement, chipIndex, listLength) {
  const r = chipElement.getBoundingClientRect();
  const mid = r.left + r.width / 2;
  const gap = clientX < mid ? chipIndex : chipIndex + 1;
  return Math.max(0, Math.min(listLength, gap));
}

/** Stable React key for filter chips; assigns chip_id when missing (e.g. legacy presets). */
export function ensureFilterChipIds(filters) {
  if (!Array.isArray(filters)) return [];
  return filters.map((f) => {
    if (!f || typeof f !== 'object') return f;
    if (f.chip_id) return f;
    const id = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `chip-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    return { ...f, chip_id: id };
  });
}

export function newFilterChipId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `chip-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}
