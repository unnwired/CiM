import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import api from '../api/http';
import { useWheelHorizontalScroll } from '../hooks/useWheelHorizontalScroll';

const GEOM_KEY = 'cim.universalNotes.geom.v1';
const PANEL_MIN = { w: 300, h: 200 };
const Z_PANEL = 300000;
const DEFAULT_NAME_RE = /^Note \d+$/;

function loadGeometry() {
  try {
    const raw = localStorage.getItem(GEOM_KEY);
    if (raw) {
      const g = JSON.parse(raw);
      if (g && typeof g.w === 'number' && typeof g.h === 'number'
        && typeof g.left === 'number' && typeof g.top === 'number') {
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        return {
          w: Math.max(PANEL_MIN.w, Math.min(g.w, vw - 24)),
          h: Math.max(PANEL_MIN.h, Math.min(g.h, vh - 24)),
          left: Math.max(0, Math.min(g.left, vw - 80)),
          top: Math.max(0, Math.min(g.top, vh - 60)),
        };
      }
    }
  } catch (_) {}
  return { w: 420, h: 300, left: Math.max(12, window.innerWidth - 460), top: 64 };
}

function saveGeometry(geom) {
  try { localStorage.setItem(GEOM_KEY, JSON.stringify(geom)); } catch (_) {}
}

function newTabTitle(tabs) {
  let n = 1;
  const titles = new Set(tabs.map(t => t.title));
  while (titles.has(`Note ${n}`)) n += 1;
  return `Note ${n}`;
}

function makeTab(tabs) {
  return {
    id: (window.crypto?.randomUUID?.() || `t-${Date.now()}-${Math.random().toString(36).slice(2)}`),
    title: newTabTitle(tabs),
    text: '',
    archived: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function suggestName(text) {
  const words = String(text || '').trim().split(/\s+/).slice(0, 5).join(' ');
  return words.slice(0, 40);
}

const MAX_IMPORT_TABS = 300;
const MAX_TITLE_LEN = 200;
const MAX_TEXT_LEN = 200000;

/** Normalize one tab from an import file; returns null if unusable. */
export function normalizeImportedTab(raw) {
  if (!raw || typeof raw !== 'object') return null;
  if (raw.title != null && typeof raw.title !== 'string') return null;
  if (raw.text != null && typeof raw.text !== 'string') return null;
  const title = String(raw.title || '').trim().slice(0, MAX_TITLE_LEN);
  let text = raw.text == null ? '' : String(raw.text);
  if (text.length > MAX_TEXT_LEN) text = text.slice(0, MAX_TEXT_LEN);
  const id = String(raw.id || '').trim()
    || (typeof window !== 'undefined' && window.crypto?.randomUUID?.())
    || `t-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return {
    id,
    title,
    text,
    archived: !!raw.archived,
    created_at: String(raw.created_at || ''),
    updated_at: String(raw.updated_at || ''),
  };
}

/** Parse export JSON into a tabs array. Accepts `{ tabs }` or a bare array. */
export function parseNotesImportPayload(parsed) {
  const rawTabs = Array.isArray(parsed) ? parsed : (parsed && Array.isArray(parsed.tabs) ? parsed.tabs : null);
  if (!rawTabs) {
    throw new Error('No notes found in this file (expected a tabs list).');
  }
  const tabs = [];
  const seen = new Set();
  for (const item of rawTabs) {
    if (tabs.length >= MAX_IMPORT_TABS) break;
    const tab = normalizeImportedTab(item);
    if (!tab) continue;
    if (seen.has(tab.id)) {
      tab.id = (typeof window !== 'undefined' && window.crypto?.randomUUID?.())
        || `t-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }
    seen.add(tab.id);
    tabs.push(tab);
  }
  if (!tabs.length) {
    throw new Error('No valid notes found in this file.');
  }
  return tabs;
}

/**
 * Reorder open (non-archived) note tabs by visible-strip indices.
 * Archived tabs keep their relative slots in the full list.
 */
export function reorderVisibleNoteTabs(tabs, fromVisibleIdx, toVisibleIdx) {
  if (!Array.isArray(tabs) || fromVisibleIdx === toVisibleIdx) return tabs;
  if (fromVisibleIdx < 0 || toVisibleIdx < 0) return tabs;
  const visible = tabs.filter((t) => !t.archived);
  if (fromVisibleIdx >= visible.length || toVisibleIdx >= visible.length) return tabs;
  const nextVisible = [...visible];
  const [moved] = nextVisible.splice(fromVisibleIdx, 1);
  nextVisible.splice(toVisibleIdx, 0, moved);
  let vi = 0;
  return tabs.map((t) => (t.archived ? t : nextVisible[vi++]));
}

/** Merge imported tabs into current: same id → imported wins; others kept. */
export function mergeNotesTabs(current, imported) {
  const byId = new Map();
  for (const t of current || []) {
    if (t && t.id) byId.set(t.id, t);
  }
  for (const t of imported || []) {
    if (t && t.id) byId.set(t.id, t);
  }
  return Array.from(byId.values());
}

/**
 * Universal per-account notes: "Notes" toggle button (top bar) + floating tabbed panel.
 * Contents stored on this install (per signed-in email); use Export/Import to move between devices.
 * Geometry stored locally in the browser.
 */
export default function UniversalNotes() {
  const [open, setOpen] = useState(false);
  const [tabs, setTabs] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [nameDialog, setNameDialog] = useState(null); // { tabId, value }
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [geom, setGeom] = useState(() => (typeof window !== 'undefined' ? loadGeometry() : { w: 420, h: 300, left: 40, top: 64 }));

  const panelRef = useRef(null);
  const importRef = useRef(null);
  const tabStripScrollRef = useRef(null);
  useWheelHorizontalScroll(tabStripScrollRef);
  const tabDragIdx = useRef(null);
  const dragRef = useRef({ active: false, sx: 0, sy: 0, sl: 0, st: 0 });
  const resizeRef = useRef({ active: false, sx: 0, sy: 0, sw: 0, sh: 0 });
  const saveTimerRef = useRef(null);
  const tabsRef = useRef(tabs);
  const dirtyRef = useRef(false);
  useEffect(() => { tabsRef.current = tabs; }, [tabs]);

  const visibleTabs = useMemo(() => tabs.filter(t => !t.archived), [tabs]);
  const archivedTabs = useMemo(
    () => tabs.filter(t => t.archived).sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))),
    [tabs],
  );
  const activeTab = visibleTabs.find(t => t.id === activeId) || visibleTabs[0] || null;

  const persist = useCallback(async (nextTabs) => {
    try {
      await api.put('/api/user-notes', { tabs: nextTabs });
      dirtyRef.current = false;
    } catch (_) { /* retried on next change/flush */ }
  }, []);

  const scheduleSave = useCallback(() => {
    dirtyRef.current = true;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveTimerRef.current = null;
      persist(tabsRef.current);
    }, 800);
  }, [persist]);

  const flushSave = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (dirtyRef.current) persist(tabsRef.current);
  }, [persist]);

  useEffect(() => () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    if (dirtyRef.current) persist(tabsRef.current);
  }, [persist]);

  const updateTabs = useCallback((updater) => {
    setTabs(prev => {
      const next = updater(prev);
      tabsRef.current = next;
      return next;
    });
    scheduleSave();
  }, [scheduleSave]);

  // (Re)load from server on every open — picks up account switches.
  const loadDoc = useCallback(async () => {
    try {
      const r = await api.get('/api/user-notes');
      let nextTabs = Array.isArray(r.data?.tabs) ? r.data.tabs : [];
      if (!nextTabs.some(t => !t.archived)) {
        nextTabs = [...nextTabs, makeTab(nextTabs)];
      }
      setTabs(nextTabs);
      tabsRef.current = nextTabs;
      setActiveId(prev => {
        const vis = nextTabs.filter(t => !t.archived);
        return vis.some(t => t.id === prev) ? prev : (vis[0]?.id ?? null);
      });
      setLoaded(true);
    } catch (_) {
      if (!tabsRef.current.length) {
        const seed = [makeTab([])];
        setTabs(seed);
        tabsRef.current = seed;
        setActiveId(seed[0].id);
      }
      setLoaded(true);
    }
  }, []);

  const toggleOpen = useCallback(() => {
    setOpen(prev => {
      if (prev) {
        flushSave();
        setArchiveOpen(false);
        setRenamingId(null);
        setNameDialog(null);
        setConfirmDeleteId(null);
        return false;
      }
      loadDoc();
      return true;
    });
  }, [flushSave, loadDoc]);

  // ── tab operations ──
  const addTab = useCallback(() => {
    const tab = makeTab(tabsRef.current);
    updateTabs(prev => [...prev, tab]);
    setActiveId(tab.id);
    setArchiveOpen(false);
    setConfirmDeleteId(null);
  }, [updateTabs]);

  const setTabText = useCallback((tabId, text) => {
    updateTabs(prev => prev.map(t => (t.id === tabId ? { ...t, text, updated_at: new Date().toISOString() } : t)));
  }, [updateTabs]);

  const renameTab = useCallback((tabId, title) => {
    const clean = String(title || '').trim().slice(0, 200);
    if (!clean) return;
    updateTabs(prev => prev.map(t => (t.id === tabId ? { ...t, title: clean, updated_at: new Date().toISOString() } : t)));
  }, [updateTabs]);

  const ensureActiveAfterRemoval = useCallback((removedId, nextTabs) => {
    const vis = nextTabs.filter(t => !t.archived);
    if (!vis.length) {
      const tab = makeTab(nextTabs);
      setActiveId(tab.id);
      return [...nextTabs, tab];
    }
    setActiveId(prev => (prev === removedId || !vis.some(t => t.id === prev) ? vis[0].id : prev));
    return nextTabs;
  }, []);

  const archiveTab = useCallback((tabId, title) => {
    updateTabs(prev => {
      const next = prev.map(t => (
        t.id === tabId
          ? { ...t, title: title || t.title, archived: true, updated_at: new Date().toISOString() }
          : t
      ));
      return ensureActiveAfterRemoval(tabId, next);
    });
  }, [updateTabs, ensureActiveAfterRemoval]);

  const discardTab = useCallback((tabId) => {
    updateTabs(prev => ensureActiveAfterRemoval(tabId, prev.filter(t => t.id !== tabId)));
  }, [updateTabs, ensureActiveAfterRemoval]);

  const requestCloseTab = useCallback((tab) => {
    const unnamed = DEFAULT_NAME_RE.test(tab.title) || !tab.title.trim();
    if (!tab.text.trim() && unnamed) {
      discardTab(tab.id);
      return;
    }
    if (unnamed) {
      setNameDialog({ tabId: tab.id, value: suggestName(tab.text) });
      return;
    }
    archiveTab(tab.id);
  }, [discardTab, archiveTab]);

  const reopenTab = useCallback((tabId) => {
    updateTabs(prev => prev.map(t => (t.id === tabId ? { ...t, archived: false, updated_at: new Date().toISOString() } : t)));
    setActiveId(tabId);
    setArchiveOpen(false);
  }, [updateTabs]);

  const deleteForever = useCallback((tabId) => {
    updateTabs(prev => prev.filter(t => t.id !== tabId));
    setConfirmDeleteId(null);
  }, [updateTabs]);

  const reorderTabs = useCallback((fromVisibleIdx, toVisibleIdx) => {
    if (fromVisibleIdx === toVisibleIdx) return;
    updateTabs(prev => reorderVisibleNoteTabs(prev, fromVisibleIdx, toVisibleIdx));
  }, [updateTabs]);

  const applyImportedTabs = useCallback((nextTabs) => {
    let finalTabs = nextTabs;
    if (!finalTabs.some(t => !t.archived)) {
      finalTabs = [...finalTabs, makeTab(finalTabs)];
    }
    setTabs(finalTabs);
    tabsRef.current = finalTabs;
    dirtyRef.current = true;
    const vis = finalTabs.filter(t => !t.archived);
    setActiveId(vis[0]?.id ?? null);
    setArchiveOpen(false);
    setConfirmDeleteId(null);
    setRenamingId(null);
    setNameDialog(null);
    persist(finalTabs);
  }, [persist]);

  const handleExportNotes = useCallback(() => {
    flushSave();
    const current = tabsRef.current || [];
    if (!current.length) {
      window.alert('No notes available to export.');
      return;
    }
    try {
      const payload = {
        version: 1,
        kind: 'cim-user-notes',
        exported_at: new Date().toISOString(),
        tabs: current,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      const a = document.createElement('a');
      a.href = url;
      a.download = `cim-notes-${stamp}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      window.alert(`Failed to export notes: ${e?.message || 'Unknown error'}`);
    }
  }, [flushSave]);

  const handleImportNotesFile = useCallback(async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const imported = parseNotesImportPayload(parsed);
      const replaceAll = window.confirm(
        `Import ${imported.length} note(s)?\n\n` +
        'Click OK to REPLACE all notes on this device.\n' +
        'Click Cancel to MERGE (keep existing notes; overwrite notes with the same id).',
      );
      const next = replaceAll
        ? imported
        : mergeNotesTabs(tabsRef.current || [], imported);
      applyImportedTabs(next);
    } catch (err) {
      window.alert(`Failed to import notes: ${err?.message || 'Unknown error'}`);
    }
  }, [applyImportedTabs]);

  // ── drag / resize ──
  useEffect(() => {
    function onMove(e) {
      if (dragRef.current.active) {
        const dx = e.clientX - dragRef.current.sx;
        const dy = e.clientY - dragRef.current.sy;
        setGeom(g => {
          const left = Math.max(0, Math.min(dragRef.current.sl + dx, window.innerWidth - 80));
          const top = Math.max(0, Math.min(dragRef.current.st + dy, window.innerHeight - 40));
          return { ...g, left, top };
        });
      } else if (resizeRef.current.active) {
        const dx = e.clientX - resizeRef.current.sx;
        const dy = e.clientY - resizeRef.current.sy;
        setGeom(g => ({
          ...g,
          w: Math.max(PANEL_MIN.w, Math.min(resizeRef.current.sw + dx, window.innerWidth - 24)),
          h: Math.max(PANEL_MIN.h, Math.min(resizeRef.current.sh + dy, window.innerHeight - 24)),
        }));
      }
    }
    function onUp() {
      if (dragRef.current.active || resizeRef.current.active) {
        dragRef.current.active = false;
        resizeRef.current.active = false;
        setGeom(g => { saveGeometry(g); return g; });
      }
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const startDrag = useCallback((e) => {
    if (e.button !== 0) return;
    dragRef.current = { active: true, sx: e.clientX, sy: e.clientY, sl: geom.left, st: geom.top };
    e.preventDefault();
  }, [geom.left, geom.top]);

  const startResize = useCallback((e) => {
    if (e.button !== 0) return;
    resizeRef.current = { active: true, sx: e.clientX, sy: e.clientY, sw: geom.w, sh: geom.h };
    e.preventDefault();
    e.stopPropagation();
  }, [geom.w, geom.h]);

  // ── render ──
  const btn = (
    <div
      onClick={toggleOpen}
      title={open ? 'Hide notes' : 'Show notes (saved on this device — use Export/Import to move between desktop and web)'}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '0 12px', height: '100%', cursor: 'pointer', userSelect: 'none',
        borderRight: '1px solid var(--border)', fontSize: 12, fontWeight: 600,
        color: open ? 'var(--accent-green, #238636)' : 'var(--text-muted)',
        flexShrink: 0,
      }}
      onMouseEnter={e => { if (!open) e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
      onMouseLeave={e => { if (!open) e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.backgroundColor = 'transparent'; }}
    >
      Notes
    </div>
  );

  if (!open) return btn;

  const tabButtonBase = {
    display: 'flex', alignItems: 'center', gap: 4, padding: '3px 6px 3px 8px',
    fontSize: 11, borderRadius: '4px 4px 0 0', flexShrink: 0,
    border: '1px solid var(--border)', borderBottom: 'none', maxWidth: 160,
  };

  const onTabDragStart = (e, idx) => {
    if (renamingId) {
      e.preventDefault();
      return;
    }
    tabDragIdx.current = idx;
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', String(idx)); } catch (_) { /* IE/Safari */ }
  };

  const onTabDrop = (e, idx) => {
    e.preventDefault();
    const from = tabDragIdx.current;
    tabDragIdx.current = null;
    if (from == null || from === idx) return;
    reorderTabs(from, idx);
  };


  const panel = createPortal(
    <div
      ref={panelRef}
      style={{
        position: 'fixed', left: geom.left, top: geom.top, width: geom.w, height: geom.h,
        zIndex: Z_PANEL, display: 'flex', flexDirection: 'column',
        backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)',
        borderRadius: 6, boxShadow: '0 8px 28px rgba(0,0,0,0.5)', overflow: 'hidden',
      }}
    >
      {/* header: drag handle */}
      <div
        onMouseDown={startDrag}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
          padding: '6px 10px', cursor: 'move', userSelect: 'none',
          borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-primary)', flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>Notes</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }} onMouseDown={e => e.stopPropagation()}>
          <button
            type="button"
            onClick={handleExportNotes}
            title="Download all notes as a JSON file (for desktop ↔ web)"
            style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 4, cursor: 'pointer',
              border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)',
            }}
          >Export</button>
          <button
            type="button"
            onClick={() => importRef.current?.click()}
            title="Import notes from a JSON backup"
            style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 4, cursor: 'pointer',
              border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)',
            }}
          >Import</button>
          <button
            type="button"
            aria-label="Hide notes"
            title="Hide notes"
            onClick={toggleOpen}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 15, lineHeight: 1, cursor: 'pointer', padding: '0 2px' }}
          >×</button>
        </div>
      </div>
      <input
        ref={importRef}
        type="file"
        accept="application/json,.json"
        style={{ display: 'none' }}
        onChange={handleImportNotesFile}
      />

      {/* tab strip */}
      <div
        ref={tabStripScrollRef}
        style={{ display: 'flex', alignItems: 'flex-end', gap: 3, padding: '6px 8px 0 8px', borderBottom: '1px solid var(--border)', overflowX: 'auto', flexShrink: 0 }}
      >
        {visibleTabs.map((t, idx) => {
          const isActive = activeTab && t.id === activeTab.id;
          const canDrag = renamingId !== t.id;
          return (
            <div
              key={t.id}
              draggable={canDrag}
              onDragStart={e => onTabDragStart(e, idx)}
              onDragOver={e => e.preventDefault()}
              onDrop={e => onTabDrop(e, idx)}
              onDragEnd={() => { tabDragIdx.current = null; }}
              onClick={() => { setActiveId(t.id); setArchiveOpen(false); setConfirmDeleteId(null); }}
              onDoubleClick={() => { setRenamingId(t.id); setRenameValue(t.title); }}
              title={`${t.title} — drag to reorder`}
              style={{
                ...tabButtonBase,
                cursor: canDrag ? 'grab' : 'text',
                backgroundColor: isActive ? 'var(--bg-secondary)' : 'var(--bg-primary)',
                color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                fontWeight: isActive ? 600 : 400,
              }}
            >
              {renamingId === t.id ? (
                <input
                  autoFocus
                  value={renameValue}
                  onChange={e => setRenameValue(e.target.value)}
                  onClick={e => e.stopPropagation()}
                  onKeyDown={e => {
                    if (e.key === 'Enter') { renameTab(t.id, renameValue); setRenamingId(null); }
                    if (e.key === 'Escape') setRenamingId(null);
                  }}
                  onBlur={() => { renameTab(t.id, renameValue); setRenamingId(null); }}
                  style={{
                    width: 100, fontSize: 11, padding: '1px 3px',
                    backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)',
                    border: '1px solid var(--accent-blue)', borderRadius: 3, outline: 'none',
                  }}
                />
              ) : (
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</span>
              )}
              <span
                role="button"
                aria-label={`Close ${t.title}`}
                title="Close (archive)"
                draggable={false}
                onMouseDown={e => e.stopPropagation()}
                onClick={e => { e.stopPropagation(); requestCloseTab(t); }}
                style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1, padding: '0 1px', cursor: 'pointer' }}
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)'; }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; }}
              >×</span>
            </div>
          );
        })}
        <button
          type="button"
          onClick={addTab}
          title="New note tab"
          aria-label="New note tab"
          style={{
            ...tabButtonBase, padding: '3px 8px', background: 'var(--bg-primary)',
            color: 'var(--text-muted)', fontWeight: 700,
          }}
        >+</button>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          onClick={() => { setArchiveOpen(v => !v); setConfirmDeleteId(null); }}
          title="Closed notes (reopen or delete)"
          style={{
            ...tabButtonBase, padding: '3px 8px', background: archiveOpen ? 'var(--bg-secondary)' : 'var(--bg-primary)',
            color: archivedTabs.length ? 'var(--text-secondary)' : 'var(--text-muted)',
          }}
        >
          Closed{archivedTabs.length ? ` (${archivedTabs.length})` : ''}
        </button>
      </div>

      {/* body */}
      <div style={{ flex: 1, minHeight: 0, position: 'relative', display: 'flex', flexDirection: 'column' }}>
        {archiveOpen ? (
          <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
            {archivedTabs.length === 0 ? (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: 8 }}>No closed notes.</div>
            ) : archivedTabs.map(t => (
              <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderBottom: '1px solid var(--border-light)' }}>
                <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.title}>{t.title}</span>
                <button
                  type="button"
                  onClick={() => reopenTab(t.id)}
                  style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', cursor: 'pointer' }}
                >Reopen</button>
                {confirmDeleteId === t.id ? (
                  <button
                    type="button"
                    onClick={() => deleteForever(t.id)}
                    style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, border: '1px solid var(--accent-red, #da3633)', background: 'var(--accent-red, #da3633)', color: '#fff', cursor: 'pointer' }}
                  >Confirm delete</button>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmDeleteId(t.id)}
                    style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--accent-red, #da3633)', cursor: 'pointer' }}
                  >Delete</button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <textarea
            value={activeTab?.text ?? ''}
            onChange={e => activeTab && setTabText(activeTab.id, e.target.value)}
            placeholder={loaded ? 'Type your note…' : 'Loading…'}
            disabled={!activeTab}
            style={{
              flex: 1, width: '100%', resize: 'none', border: 'none', outline: 'none',
              backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)',
              fontSize: 12.5, lineHeight: 1.5, padding: 10, fontFamily: 'inherit',
            }}
          />
        )}

        {/* name-before-archive dialog */}
        {nameDialog && (
          <div style={{
            position: 'absolute', inset: 0, backgroundColor: 'rgba(0,0,0,0.45)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
          }}>
            <div style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, padding: 14, width: '100%', maxWidth: 320 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>Name this note before saving</div>
              <input
                autoFocus
                value={nameDialog.value}
                onChange={e => setNameDialog(d => ({ ...d, value: e.target.value }))}
                onKeyDown={e => {
                  if (e.key === 'Enter' && nameDialog.value.trim()) {
                    archiveTab(nameDialog.tabId, nameDialog.value.trim());
                    setNameDialog(null);
                  }
                  if (e.key === 'Escape') setNameDialog(null);
                }}
                placeholder="Note name"
                style={{
                  width: '100%', boxSizing: 'border-box', fontSize: 12, padding: '5px 8px',
                  backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)',
                  border: '1px solid var(--border)', borderRadius: 4, outline: 'none', marginBottom: 10,
                }}
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  type="button"
                  title="Discard this note permanently"
                  onClick={() => {
                    discardTab(nameDialog.tabId);
                    setNameDialog(null);
                  }}
                  style={{
                    fontSize: 11, padding: '3px 10px', borderRadius: 4,
                    border: '1px solid var(--accent-red, #da3633)',
                    background: 'transparent', color: 'var(--accent-red, #da3633)', cursor: 'pointer',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-red, #da3633)'; e.currentTarget.style.color = '#fff'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--accent-red, #da3633)'; }}
                >Delete</button>
                <div style={{ flex: 1 }} />
                <button
                  type="button"
                  onClick={() => setNameDialog(null)}
                  style={{ fontSize: 11, padding: '3px 10px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)', cursor: 'pointer' }}
                >Cancel</button>
                <button
                  type="button"
                  disabled={!nameDialog.value.trim()}
                  onClick={() => {
                    archiveTab(nameDialog.tabId, nameDialog.value.trim());
                    setNameDialog(null);
                  }}
                  style={{
                    fontSize: 11, padding: '3px 10px', borderRadius: 4,
                    border: '1px solid var(--accent-green, #238636)',
                    background: 'var(--accent-green, #238636)', color: '#fff',
                    cursor: nameDialog.value.trim() ? 'pointer' : 'not-allowed',
                    opacity: nameDialog.value.trim() ? 1 : 0.6,
                  }}
                >Save note</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* resize handle */}
      <div
        onMouseDown={startResize}
        title="Resize"
        style={{
          position: 'absolute', right: 0, bottom: 0, width: 16, height: 16, cursor: 'nwse-resize',
          background: 'linear-gradient(135deg, transparent 50%, var(--border) 50%)',
          borderBottomRightRadius: 6,
        }}
      />
    </div>,
    document.body,
  );

  return (
    <>
      {btn}
      {panel}
    </>
  );
}
