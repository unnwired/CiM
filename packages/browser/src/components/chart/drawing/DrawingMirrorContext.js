import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  loadPack,
  debouncedSave,
  storageKeyForMirror,
  loadMirrorToggle,
  saveMirrorToggle,
} from './drawingStorage';

const Ctx = createContext(null);

/**
 * @param {{ children: React.ReactNode, mirrorStorageKey: string | null, mirrorContextId?: string }} props
 */
export function DrawingMirrorProvider({ children, mirrorStorageKey, mirrorContextId = 'dash' }) {
  const [mirrorEnabled, setMirrorEnabledState] = useState(() => loadMirrorToggle(mirrorContextId));
  const [sharedDrawings, setSharedDrawings] = useState([]);
  const [sharedRevision, setSharedRevision] = useState(0);

  const effectiveMirrorKey = mirrorStorageKey && mirrorEnabled ? mirrorStorageKey : null;

  useEffect(() => {
    if (!effectiveMirrorKey) return;
    const k = storageKeyForMirror(effectiveMirrorKey);
    const { drawings } = loadPack(k);
    setSharedDrawings(drawings);
    setSharedRevision((r) => r + 1);
  }, [effectiveMirrorKey, mirrorStorageKey, mirrorEnabled]);

  const persistShared = useCallback((drawings) => {
    if (!effectiveMirrorKey) return;
    const k = storageKeyForMirror(effectiveMirrorKey);
    debouncedSave(k, { drawings, favorites: [] });
  }, [effectiveMirrorKey]);

  const setMirrorEnabled = useCallback((on) => {
    setMirrorEnabledState(!!on);
    saveMirrorToggle(mirrorContextId, !!on);
  }, [mirrorContextId]);

  const updateShared = useCallback((drawings) => {
    setSharedDrawings(drawings);
    persistShared(drawings);
    setSharedRevision((r) => r + 1);
  }, [persistShared]);

  const value = useMemo(() => ({
    mirrorEnabled,
    setMirrorEnabled,
    mirrorStorageKey,
    effectiveMirrorKey,
    sharedDrawings,
    updateShared,
    sharedRevision,
    mirrorContextId,
  }), [
    mirrorEnabled,
    setMirrorEnabled,
    mirrorStorageKey,
    effectiveMirrorKey,
    sharedDrawings,
    updateShared,
    sharedRevision,
    mirrorContextId,
  ]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDrawingMirror() {
  return useContext(Ctx);
}
