/**
 * Chart tab stacks — multiple charts share one tab-bar slot.
 * Hover expands a vertical list; the face shows the last-selected chart.
 */

import {
  appendChartCreationOrder,
  removeChartCreationOrder,
  replaceOldestChartCreationOrder,
  resolveOldestChartReplaceIndex,
} from './chartTabFifo';

export function normalizeChartSymbol(symbol) {
  return String(symbol || '').trim().toUpperCase();
}

export function activeChart(stack) {
  if (!stack?.charts?.length) return null;
  const idx = Math.min(
    Math.max(0, Number(stack.activeIdx) || 0),
    stack.charts.length - 1,
  );
  return stack.charts[idx] || null;
}

export function findChartInStacks(stacks, symbol) {
  const sym = normalizeChartSymbol(symbol);
  if (!sym) return null;
  for (let stackIdx = 0; stackIdx < stacks.length; stackIdx += 1) {
    const chartIdx = stacks[stackIdx].charts.findIndex(
      (c) => normalizeChartSymbol(c.symbol) === sym,
    );
    if (chartIdx !== -1) return { stackIdx, chartIdx };
  }
  return null;
}

export function makeChartEntry(symbol, originView, now = Date.now(), entryMeta = null) {
  const sym = normalizeChartSymbol(symbol);
  const base = {
    symbol: sym,
    id: `${sym}-${now}`,
    returnView: originView || null,
  };
  if (!entryMeta || typeof entryMeta !== 'object') return base;
  // Preserve caller fields (e.g. index name for constituents) without clobbering identity keys.
  const { symbol: _s, id: _i, returnView: _r, ...rest } = entryMeta;
  return { ...rest, ...base };
}

export function makeChartStack(chart, now = Date.now()) {
  return {
    id: `stack-${now}`,
    charts: [chart],
    activeIdx: 0,
  };
}

/**
 * Open a symbol into stacks.
 * - Already open → focus that chart
 * - Any stack already open → append onto the active stack (not a new side-by-side tab)
 * - No stacks yet → create the first stack slot
 * - At max stack slots with nowhere to append → FIFO-replace oldest stack (only when creating a new slot)
 */
export function openChartInStacks({
  stacks,
  creationOrder,
  activeStackIdx,
  viewIsChart: _viewIsChart, // kept for callers; stacking no longer depends on current view
  symbol,
  originView,
  maxStacks,
  now = Date.now(),
  entryMeta = null,
}) {
  const sym = normalizeChartSymbol(symbol);
  if (!sym) {
    return { stacks, creationOrder, activeStackIdx };
  }

  const found = findChartInStacks(stacks, sym);
  if (found) {
    const next = stacks.map((s, i) => {
      if (i !== found.stackIdx) return s;
      const charts = s.charts.map((c, j) => {
        if (j !== found.chartIdx) return c;
        let nextEntry = c;
        if (originView) nextEntry = { ...nextEntry, returnView: originView };
        if (entryMeta && typeof entryMeta === 'object') {
          const { symbol: _s, id: _i, returnView: _r, ...rest } = entryMeta;
          nextEntry = { ...nextEntry, ...rest };
        }
        return nextEntry;
      });
      return { ...s, charts, activeIdx: found.chartIdx };
    });
    return {
      stacks: next,
      creationOrder: [...creationOrder],
      activeStackIdx: found.stackIdx,
    };
  }

  const chart = makeChartEntry(sym, originView, now, entryMeta);

  // Prefer stacking onto an existing slot — matches “open next to / under the open chart”.
  if (stacks.length > 0) {
    const targetIdx = (
      activeStackIdx != null
      && activeStackIdx >= 0
      && activeStackIdx < stacks.length
    )
      ? activeStackIdx
      : stacks.length - 1;
    const next = stacks.map((s, i) => {
      if (i !== targetIdx) return s;
      const charts = [...s.charts, chart];
      return { ...s, charts, activeIdx: charts.length - 1 };
    });
    return {
      stacks: next,
      creationOrder: [...creationOrder],
      activeStackIdx: targetIdx,
    };
  }

  const stack = makeChartStack(chart, now);
  const limit = Math.max(1, Number(maxStacks) || 1);

  if (stacks.length < limit) {
    const next = [...stacks, stack];
    return {
      stacks: next,
      creationOrder: appendChartCreationOrder(creationOrder, stack.id),
      activeStackIdx: next.length - 1,
    };
  }

  const replaceAt = resolveOldestChartReplaceIndex(stacks, creationOrder);
  const oldestId = creationOrder[0];
  const next = [...stacks];
  next[replaceAt] = stack;
  return {
    stacks: next,
    creationOrder: replaceOldestChartCreationOrder(creationOrder, oldestId, stack.id),
    activeStackIdx: replaceAt,
  };
}

/** Close the active chart in a stack; remove the stack if it becomes empty. */
export function closeActiveChartInStack(stacks, creationOrder, stackIdx) {
  const stack = stacks[stackIdx];
  if (!stack) {
    return {
      stacks,
      creationOrder,
      removedStack: false,
      closedReturnView: null,
      nextActiveStackIdxHint: stackIdx,
    };
  }

  const closed = stack.charts[stack.activeIdx];
  const charts = stack.charts.filter((_, i) => i !== stack.activeIdx);

  if (charts.length === 0) {
    const next = stacks.filter((_, i) => i !== stackIdx);
    return {
      stacks: next,
      creationOrder: removeChartCreationOrder(creationOrder, stack.id),
      removedStack: true,
      closedReturnView: closed?.returnView ?? null,
      nextActiveStackIdxHint: Math.min(stackIdx, Math.max(0, next.length - 1)),
    };
  }

  const activeIdx = Math.min(stack.activeIdx, charts.length - 1);
  const next = stacks.map((s, i) => (
    i === stackIdx ? { ...s, charts, activeIdx } : s
  ));
  return {
    stacks: next,
    creationOrder: [...creationOrder],
    removedStack: false,
    closedReturnView: null,
    nextActiveStackIdxHint: stackIdx,
  };
}

/** Close a specific chart in a stack (e.g. from the hover list). */
export function closeChartInStack(stacks, creationOrder, stackIdx, chartIdx) {
  const stack = stacks[stackIdx];
  if (!stack || chartIdx < 0 || chartIdx >= stack.charts.length) {
    return {
      stacks,
      creationOrder,
      removedStack: false,
      closedReturnView: null,
      nextActiveStackIdxHint: stackIdx,
    };
  }

  if (chartIdx === stack.activeIdx) {
    return closeActiveChartInStack(stacks, creationOrder, stackIdx);
  }

  const closed = stack.charts[chartIdx];
  const charts = stack.charts.filter((_, i) => i !== chartIdx);
  if (charts.length === 0) {
    const next = stacks.filter((_, i) => i !== stackIdx);
    return {
      stacks: next,
      creationOrder: removeChartCreationOrder(creationOrder, stack.id),
      removedStack: true,
      closedReturnView: closed?.returnView ?? null,
      nextActiveStackIdxHint: Math.min(stackIdx, Math.max(0, next.length - 1)),
    };
  }

  let activeIdx = stack.activeIdx;
  if (chartIdx < activeIdx) activeIdx -= 1;
  const next = stacks.map((s, i) => (
    i === stackIdx ? { ...s, charts, activeIdx } : s
  ));
  return {
    stacks: next,
    creationOrder: [...creationOrder],
    removedStack: false,
    closedReturnView: null,
    nextActiveStackIdxHint: stackIdx,
  };
}

export function activateChartInStack(stacks, stackIdx, chartIdx) {
  if (!stacks[stackIdx]) return stacks;
  const stack = stacks[stackIdx];
  if (chartIdx < 0 || chartIdx >= stack.charts.length) return stacks;
  return stacks.map((s, i) => (
    i === stackIdx ? { ...s, activeIdx: chartIdx } : s
  ));
}

/** Update the active chart's symbol (split-chart focus change). */
export function setActiveChartSymbol(stacks, stackIdx, symbol) {
  const sym = normalizeChartSymbol(symbol);
  if (!sym || !stacks[stackIdx]) return stacks;
  return stacks.map((s, i) => {
    if (i !== stackIdx) return s;
    const charts = s.charts.map((c, j) => (
      j === s.activeIdx ? { ...c, symbol: sym } : c
    ));
    return { ...s, charts };
  });
}
