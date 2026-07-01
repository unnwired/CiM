import { useCallback, useEffect, useState } from 'react';
import { useDrawingMirror } from './DrawingMirrorContext';
import { debouncedSave, loadPack, storageKeyForScope } from './drawingStorage';

const noop = () => {};

export function useChartDrawings(drawingScopeId) {
  const mirror = useDrawingMirror();
  const mirrorOn = !!(mirror && mirror.mirrorEnabled && mirror.effectiveMirrorKey);

  const [localDrawings, setLocalDrawings] = useState([]);

  const enabled = !!drawingScopeId;
  const drawings = !enabled ? [] : mirrorOn ? mirror.sharedDrawings : localDrawings;

  useEffect(() => {
    if (!enabled) return;
    if (mirrorOn) return;
    const { drawings: d } = loadPack(storageKeyForScope(drawingScopeId));
    setLocalDrawings(d);
  }, [drawingScopeId, mirrorOn, enabled]);

  const setDrawings = useCallback(
    (updater) => {
      if (!enabled) return;
      if (mirrorOn && mirror) {
        const next = typeof updater === 'function' ? updater(mirror.sharedDrawings) : updater;
        mirror.updateShared(next);
      } else {
        setLocalDrawings(updater);
      }
    },
    [enabled, mirrorOn, mirror],
  );

  useEffect(() => {
    if (!enabled || mirrorOn) return;
    debouncedSave(storageKeyForScope(drawingScopeId), {
      drawings: localDrawings,
      favorites: [],
    });
  }, [localDrawings, drawingScopeId, mirrorOn, enabled]);

  if (!enabled) {
    return {
      drawings: [],
      setDrawings: noop,
      mirrorOn: false,
      mirror: null,
      mirrorAvailable: false,
    };
  }

  return {
    drawings,
    setDrawings,
    mirrorOn,
    mirror,
    mirrorAvailable: !!(mirror && mirror.mirrorStorageKey),
  };
}
