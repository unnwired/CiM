import {
  appendChartCreationOrder,
  removeChartCreationOrder,
  replaceOldestChartCreationOrder,
  resolveOldestChartReplaceIndex,
  trimChartTabsToMax,
} from './chartTabFifo';

describe('chartTabFifo', () => {
  test('replace cycles oldest → next oldest → third (not same slot)', () => {
    let order = [];
    const tabs = [];

    // Open A, B, C (max 3)
    for (const sym of ['A', 'B', 'C']) {
      const id = `${sym}-id`;
      tabs.push({ id, symbol: sym });
      order = appendChartCreationOrder(order, id);
    }
    expect(order).toEqual(['A-id', 'B-id', 'C-id']);

    // Open D → replace A (oldest)
    let replaceAt = resolveOldestChartReplaceIndex(tabs, order);
    expect(replaceAt).toBe(0);
    tabs[replaceAt] = { id: 'D-id', symbol: 'D' };
    order = replaceOldestChartCreationOrder(order, order[0], 'D-id');
    expect(order).toEqual(['B-id', 'C-id', 'D-id']);

    // Open E → replace B (next oldest), not D again
    replaceAt = resolveOldestChartReplaceIndex(tabs, order);
    expect(tabs[replaceAt].symbol).toBe('B');
    tabs[replaceAt] = { id: 'E-id', symbol: 'E' };
    order = replaceOldestChartCreationOrder(order, order[0], 'E-id');
    expect(order).toEqual(['C-id', 'D-id', 'E-id']);

    // Open F → replace C
    replaceAt = resolveOldestChartReplaceIndex(tabs, order);
    expect(tabs[replaceAt].symbol).toBe('C');
    tabs[replaceAt] = { id: 'F-id', symbol: 'F' };
    order = replaceOldestChartCreationOrder(order, order[0], 'F-id');
    expect(order).toEqual(['D-id', 'E-id', 'F-id']);
  });

  test('drag reorder does not redefine age when order is kept separately', () => {
    // Visual: [C, A, B] but creation age still A → B → C
    const tabs = [
      { id: 'C-id', symbol: 'C' },
      { id: 'A-id', symbol: 'A' },
      { id: 'B-id', symbol: 'B' },
    ];
    const order = ['A-id', 'B-id', 'C-id'];
    const replaceAt = resolveOldestChartReplaceIndex(tabs, order);
    expect(tabs[replaceAt].symbol).toBe('A');
  });

  test('remove closed id from creation order', () => {
    expect(removeChartCreationOrder(['A-id', 'B-id', 'C-id'], 'B-id')).toEqual(['A-id', 'C-id']);
  });

  describe('trimChartTabsToMax', () => {
    const tabs = [
      { id: 'A-id', symbol: 'A' },
      { id: 'B-id', symbol: 'B' },
      { id: 'C-id', symbol: 'C' },
    ];
    const order = ['A-id', 'B-id', 'C-id'];

    test('max 1 keeps the tab the user is viewing', () => {
      const res = trimChartTabsToMax(tabs, order, 0, 1);
      expect(res.tabs.map((t) => t.symbol)).toEqual(['A']);
      expect(res.creationOrder).toEqual(['A-id']);
      expect(res.activeIdx).toBe(0);
    });

    test('keeps active plus newest, in visual order', () => {
      const res = trimChartTabsToMax(tabs, order, 0, 2);
      expect(res.tabs.map((t) => t.symbol)).toEqual(['A', 'C']);
      expect(res.creationOrder).toEqual(['A-id', 'C-id']);
      expect(res.activeIdx).toBe(0);
    });

    test('no active tab falls back to newest and focuses it', () => {
      const res = trimChartTabsToMax(tabs, order, null, 1);
      expect(res.tabs.map((t) => t.symbol)).toEqual(['C']);
      expect(res.activeIdx).toBe(0);
    });

    test('raising or matching the max leaves tabs untouched', () => {
      expect(trimChartTabsToMax(tabs, order, 1, 5).tabs).toHaveLength(3);
      expect(trimChartTabsToMax(tabs, order, 1, 3).activeIdx).toBe(1);
    });

    test('drag reorder does not change which tabs survive', () => {
      const dragged = [tabs[2], tabs[0], tabs[1]];
      const res = trimChartTabsToMax(dragged, order, 1, 2);
      expect(res.tabs.map((t) => t.symbol)).toEqual(['C', 'A']);
      expect(res.activeIdx).toBe(1);
    });
  });
});
