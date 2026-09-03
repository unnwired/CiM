/**
 * Pure FIFO helpers for chart-tab replacement order.
 * Creation order is independent of visual tab order (drag-reorder must not redefine age).
 */

export function appendChartCreationOrder(order, tabId) {
  const id = String(tabId || '');
  if (!id) return [...order];
  return [...order.filter((x) => x !== id), id];
}

export function replaceOldestChartCreationOrder(order, oldestId, newId) {
  const drop = String(oldestId || '');
  const add = String(newId || '');
  const next = order.filter((id) => id !== drop && id !== add);
  if (add) next.push(add);
  return next;
}

export function removeChartCreationOrder(order, closedId) {
  const id = String(closedId || '');
  if (!id) return [...order];
  return order.filter((x) => x !== id);
}

/**
 * Resolve which visual index to replace when at max capacity.
 * Falls back to 0 if oldest id is missing from tabs.
 */
export function resolveOldestChartReplaceIndex(tabs, creationOrder) {
  const oldestId = creationOrder[0];
  if (oldestId == null) return 0;
  const idx = tabs.findIndex((t) => t.id === oldestId);
  return idx !== -1 ? idx : 0;
}

/**
 * Shrink an open tab set to a lowered max, keeping the chart the user is looking at
 * and then the newest remaining ones. Surviving tabs keep their visual order.
 */
export function trimChartTabsToMax(tabs, creationOrder, activeIdx, max) {
  const limit = Math.max(1, Number(max) || 1);
  if (tabs.length <= limit) {
    return { tabs: [...tabs], creationOrder: [...creationOrder], activeIdx };
  }
  const age = new Map(creationOrder.map((id, i) => [id, i]));
  const activeTab = tabs[activeIdx];
  const kept = new Set(activeTab ? [activeTab.id] : []);
  // Tabs absent from the creation order sort as oldest, so they are dropped first.
  const newestFirst = [...tabs].sort((a, b) => (age.get(b.id) ?? -1) - (age.get(a.id) ?? -1));
  for (const tab of newestFirst) {
    if (kept.size >= limit) break;
    kept.add(tab.id);
  }
  const nextTabs = tabs.filter((t) => kept.has(t.id));
  const nextActive = activeTab ? nextTabs.findIndex((t) => t.id === activeTab.id) : -1;
  return {
    tabs: nextTabs,
    creationOrder: creationOrder.filter((id) => kept.has(id)),
    activeIdx: nextActive !== -1 ? nextActive : nextTabs.length - 1,
  };
}
