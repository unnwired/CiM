const PREFIX = 'nsePulse.drawings.v1';

export function storageKeyForScope(drawingScopeId) {
  return `${PREFIX}.scope.${drawingScopeId}`;
}

export function storageKeyForMirror(mirrorStorageKey) {
  return `${PREFIX}.mirror.${mirrorStorageKey}`;
}

export function mirrorToggleStorageKey(contextId) {
  return `nsePulse.drawings.mirrorToggle.${contextId || 'default'}`;
}

export function loadPack(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return { drawings: [], favorites: [] };
    const j = JSON.parse(raw);
    return {
      drawings: Array.isArray(j.drawings) ? j.drawings : [],
      favorites: Array.isArray(j.favorites) ? j.favorites : [],
    };
  } catch {
    return { drawings: [], favorites: [] };
  }
}

export function savePack(key, pack) {
  try {
    localStorage.setItem(key, JSON.stringify({
      drawings: pack.drawings || [],
      favorites: pack.favorites || [],
    }));
  } catch {}
}

let debouncers = new Map();

export function debouncedSave(key, pack, ms = 200) {
  const prev = debouncers.get(key);
  if (prev) clearTimeout(prev);
  const t = setTimeout(() => {
    debouncers.delete(key);
    savePack(key, pack);
  }, ms);
  debouncers.set(key, t);
}

export function loadMirrorToggle(contextId) {
  try {
    return localStorage.getItem(mirrorToggleStorageKey(contextId)) === '1';
  } catch {
    return false;
  }
}

export function saveMirrorToggle(contextId, on) {
  try {
    localStorage.setItem(mirrorToggleStorageKey(contextId), on ? '1' : '0');
  } catch {}
}
