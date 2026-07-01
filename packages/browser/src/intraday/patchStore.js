const DB_NAME = 'cim-intraday-patch';
const STORE = 'patches';
const DB_VERSION = 2;

function blobKey(userEmail, eodDate) {
  const email = String(userEmail || 'anon').trim().toLowerCase();
  const date = String(eodDate || 'unknown').slice(0, 10);
  return `${email}::${date}`;
}

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export function isStale(cachedEodDate, latestEodDate) {
  if (!latestEodDate) return false;
  if (!cachedEodDate) return true;
  return String(cachedEodDate).slice(0, 10) < String(latestEodDate).slice(0, 10);
}

export function isPublishStale(cachedPublishedAt, latestPublishedAt) {
  if (!latestPublishedAt) return false;
  if (!cachedPublishedAt) return false;
  return String(cachedPublishedAt) !== String(latestPublishedAt);
}

export async function loadPatchBlob(userEmail, eodDate) {
  if (!eodDate) return {};
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).get(blobKey(userEmail, eodDate));
    req.onsuccess = () => resolve(req.result && typeof req.result === 'object' ? req.result : {});
    req.onerror = () => reject(req.error);
  });
}

export async function savePatchBlob(userEmail, eodDate, symbolsMap) {
  if (!eodDate) return;
  const db = await openDb();
  const key = blobKey(userEmail, eodDate);
  const prev = await loadPatchBlob(userEmail, eodDate);
  const next = { ...prev, ...symbolsMap };
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(next, key);
    tx.oncomplete = () => resolve(next);
    tx.onerror = () => reject(tx.error);
  });
}

export async function getPatch(userEmail, eodDate, symbol) {
  const blob = await loadPatchBlob(userEmail, eodDate);
  const sym = String(symbol || '').trim().toUpperCase();
  return blob[sym] || null;
}

export async function clearAllForUser(userEmail) {
  const db = await openDb();
  const prefix = `${String(userEmail || 'anon').trim().toLowerCase()}::`;
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    const store = tx.objectStore(STORE);
    const req = store.openCursor();
    req.onsuccess = () => {
      const cursor = req.result;
      if (cursor) {
        if (String(cursor.key).startsWith(prefix)) {
          cursor.delete();
        }
        cursor.continue();
      }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
