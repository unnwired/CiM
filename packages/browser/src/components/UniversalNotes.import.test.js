import {
  mergeNotesTabs,
  normalizeImportedTab,
  parseNotesImportPayload,
  reorderVisibleNoteTabs,
} from './UniversalNotes';

describe('UniversalNotes import/export helpers', () => {
  test('normalizeImportedTab keeps fields and truncates title', () => {
    const tab = normalizeImportedTab({
      id: 'a1',
      title: `${'x'.repeat(250)}`,
      text: 'hello',
      archived: 1,
      created_at: '2026-01-01',
      updated_at: '2026-01-02',
    });
    expect(tab.id).toBe('a1');
    expect(tab.title).toHaveLength(200);
    expect(tab.text).toBe('hello');
    expect(tab.archived).toBe(true);
  });

  test('parseNotesImportPayload accepts wrapped and bare array', () => {
    const wrapped = parseNotesImportPayload({
      version: 1,
      kind: 'cim-user-notes',
      tabs: [{ id: '1', title: 'A', text: 'x' }],
    });
    expect(wrapped).toHaveLength(1);
    expect(wrapped[0].title).toBe('A');

    const bare = parseNotesImportPayload([{ id: '2', title: 'B', text: 'y' }]);
    expect(bare[0].id).toBe('2');
  });

  test('parseNotesImportPayload rejects empty/invalid files', () => {
    expect(() => parseNotesImportPayload({})).toThrow(/No notes found/);
    expect(() => parseNotesImportPayload({ tabs: [null, 3] })).toThrow(/No valid notes/);
  });

  test('mergeNotesTabs overwrites same id and keeps others', () => {
    const current = [
      { id: '1', title: 'Old', text: 'a' },
      { id: '2', title: 'Keep', text: 'b' },
    ];
    const imported = [
      { id: '1', title: 'New', text: 'c' },
      { id: '3', title: 'Added', text: 'd' },
    ];
    const merged = mergeNotesTabs(current, imported);
    expect(merged).toHaveLength(3);
    expect(merged.find(t => t.id === '1').title).toBe('New');
    expect(merged.find(t => t.id === '2').title).toBe('Keep');
    expect(merged.find(t => t.id === '3').title).toBe('Added');
  });

  test('reorderVisibleNoteTabs reorders open tabs and preserves archived slots', () => {
    const tabs = [
      { id: 'a', title: 'A', archived: false },
      { id: 'x', title: 'X', archived: true },
      { id: 'b', title: 'B', archived: false },
      { id: 'c', title: 'C', archived: false },
    ];
    // Move first visible (A) after second visible (B) → visible order B, A, C
    const next = reorderVisibleNoteTabs(tabs, 0, 1);
    expect(next.map(t => t.id)).toEqual(['b', 'x', 'a', 'c']);
  });
});
