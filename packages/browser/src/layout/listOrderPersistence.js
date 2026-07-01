import api from '../api/http';
import { saveChartPrefs } from '../chartPrefs/chartPrefsStore';

/** Canonical layout.json / local backup keys for user-defined list ordering. */
export const LIST_ORDER_KEYS = {
  equityIndexSymbolOrder: 'equityIndexSymbolOrder',
  indexStarTags: 'indexStarTags',
  portfolioRowOrder: 'portfolioRowOrder',
  portfolioUseCustomRowOrder: 'portfolioUseCustomRowOrder',
  watchlistItemOrder: 'watchlistItemOrder',
};

const LEGACY_EQUITY_INDEX_KEYS = ['indicesEquitySymbolOrder', 'marketMapIndexOrder'];
const LOCAL_STORAGE_PREFIX = 'cim.layoutOrders.v1::';
export const SAVED_AT_KEY = 'layoutOrdersSavedAt';

function emailSafe(email) {
  return String(email || '').trim().toLowerCase().replace(/[^a-z0-9@._-]/g, '_');
}

function storageKey(email) {
  const safe = emailSafe(email);
  return safe ? `${LOCAL_STORAGE_PREFIX}${safe}` : `${LOCAL_STORAGE_PREFIX}local`;
}

function parseTime(value) {
  if (!value) return 0;
  const t = Date.parse(String(value));
  return Number.isFinite(t) ? t : 0;
}

function hasArrayContent(value) {
  return Array.isArray(value) && value.length > 0;
}

function hasObjectContent(value) {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

export function hasStarTagsContent(value) {
  return hasObjectContent(value) && Object.keys(value).length > 0;
}

export function loadLocalListOrders(email = null) {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(storageKey(email));
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function saveLocalListOrders(email, fields = {}) {
  if (typeof window === 'undefined') return;
  const key = storageKey(email);
  const current = loadLocalListOrders(email);
  const next = {
    ...current,
    ...fields,
    [SAVED_AT_KEY]: fields[SAVED_AT_KEY] || new Date().toISOString(),
  };
  try {
    window.localStorage.setItem(key, JSON.stringify(next));
  } catch {
    // quota / private mode
  }
}

function pickListOrdersSnapshot(email, fields = {}) {
  const current = loadLocalListOrders(email);
  const merged = { ...current, ...fields };
  const out = {};
  Object.values(LIST_ORDER_KEYS).forEach((key) => {
    if (merged[key] != null) out[key] = merged[key];
  });
  if (merged[SAVED_AT_KEY]) out[SAVED_AT_KEY] = merged[SAVED_AT_KEY];
  return out;
}

function pickEquityIndexOrder(server = {}, local = {}, preferLocal, onUsedLocal) {
  const tryPick = (source, key) => {
    if (hasArrayContent(source[key])) return source[key];
    return null;
  };

  if (preferLocal) {
    const fromLocal = tryPick(local, LIST_ORDER_KEYS.equityIndexSymbolOrder)
      || LEGACY_EQUITY_INDEX_KEYS.map((k) => tryPick(local, k)).find(Boolean);
    if (fromLocal) {
      onUsedLocal();
      return fromLocal;
    }
  }

  const fromServer = tryPick(server, LIST_ORDER_KEYS.equityIndexSymbolOrder)
    || LEGACY_EQUITY_INDEX_KEYS.map((k) => tryPick(server, k)).find(Boolean);
  if (fromServer) return fromServer;

  const fromLocal = tryPick(local, LIST_ORDER_KEYS.equityIndexSymbolOrder)
    || LEGACY_EQUITY_INDEX_KEYS.map((k) => tryPick(local, k)).find(Boolean);
  if (fromLocal) {
    onUsedLocal();
    return fromLocal;
  }
  return null;
}

function pickIndexStarTags(server = {}, local = {}, preferLocal, onUsedLocal) {
  const serverTags = server[LIST_ORDER_KEYS.indexStarTags];
  const localTags = local[LIST_ORDER_KEYS.indexStarTags];
  const serverHas = hasStarTagsContent(serverTags);
  const localHas = hasStarTagsContent(localTags);

  if (preferLocal && localHas) {
    onUsedLocal();
    return localTags;
  }
  if (serverHas) return serverTags;
  if (localHas) {
    onUsedLocal();
    return localTags;
  }
  if (preferLocal && hasObjectContent(localTags)) {
    onUsedLocal();
    return localTags;
  }
  if (hasObjectContent(serverTags)) return serverTags;
  return null;
}

/**
 * Merge server layout with chart-prefs / local backup (local wins when newer or server field missing).
 * backupData — e.g. chart prefs listOrders merged under server fields.
 * Returns { orders, usedLocal, needsStarTagsServerSync }.
 */
export function hydrateListOrderFields(serverData = {}, email = null, backupData = {}) {
  const mergedServer = { ...backupData, ...serverData };
  const local = loadLocalListOrders(email);
  const serverAt = parseTime(mergedServer[SAVED_AT_KEY]);
  const localAt = parseTime(local[SAVED_AT_KEY]);
  const preferLocal = localAt > 0 && (serverAt === 0 || localAt > serverAt);
  let usedLocal = false;
  const markLocal = () => { usedLocal = true; };

  const serverHadStarTags = hasStarTagsContent(serverData[LIST_ORDER_KEYS.indexStarTags]);

  const pickScalar = (key, hasVal) => {
    const s = mergedServer[key];
    const l = local[key];
    if (preferLocal && hasVal(l)) {
      markLocal();
      return l;
    }
    if (hasVal(s)) return s;
    if (hasVal(l)) {
      markLocal();
      return l;
    }
    return null;
  };

  const portfolioUseCustomRowOrder = pickScalar(
    LIST_ORDER_KEYS.portfolioUseCustomRowOrder,
    (v) => typeof v === 'boolean',
  );

  const orders = {
    [LIST_ORDER_KEYS.equityIndexSymbolOrder]: pickEquityIndexOrder(
      mergedServer, local, preferLocal, markLocal,
    ),
    [LIST_ORDER_KEYS.portfolioRowOrder]: pickScalar(
      LIST_ORDER_KEYS.portfolioRowOrder,
      hasArrayContent,
    ),
    [LIST_ORDER_KEYS.watchlistItemOrder]: pickScalar(
      LIST_ORDER_KEYS.watchlistItemOrder,
      hasObjectContent,
    ),
    [LIST_ORDER_KEYS.indexStarTags]: pickIndexStarTags(
      mergedServer, local, preferLocal, markLocal,
    ),
  };

  if (typeof portfolioUseCustomRowOrder === 'boolean') {
    orders[LIST_ORDER_KEYS.portfolioUseCustomRowOrder] = portfolioUseCustomRowOrder;
  }

  const needsStarTagsServerSync = hasStarTagsContent(orders[LIST_ORDER_KEYS.indexStarTags])
    && !serverHadStarTags;

  return { orders, usedLocal, needsStarTagsServerSync };
}

export function buildListOrderPayload(fields = {}) {
  const stamp = new Date().toISOString();
  const payload = { [SAVED_AT_KEY]: stamp };

  if (hasArrayContent(fields[LIST_ORDER_KEYS.equityIndexSymbolOrder])) {
    payload[LIST_ORDER_KEYS.equityIndexSymbolOrder] = fields[LIST_ORDER_KEYS.equityIndexSymbolOrder];
  }
  if (hasArrayContent(fields[LIST_ORDER_KEYS.portfolioRowOrder])) {
    payload[LIST_ORDER_KEYS.portfolioRowOrder] = fields[LIST_ORDER_KEYS.portfolioRowOrder];
  }
  if (typeof fields[LIST_ORDER_KEYS.portfolioUseCustomRowOrder] === 'boolean') {
    payload[LIST_ORDER_KEYS.portfolioUseCustomRowOrder] = fields[LIST_ORDER_KEYS.portfolioUseCustomRowOrder];
  }
  if (hasObjectContent(fields[LIST_ORDER_KEYS.watchlistItemOrder])) {
    payload[LIST_ORDER_KEYS.watchlistItemOrder] = fields[LIST_ORDER_KEYS.watchlistItemOrder];
  }
  if (LIST_ORDER_KEYS.indexStarTags in fields && hasObjectContent(fields[LIST_ORDER_KEYS.indexStarTags])) {
    payload[LIST_ORDER_KEYS.indexStarTags] = fields[LIST_ORDER_KEYS.indexStarTags];
  }

  return { payload, stamp };
}

/**
 * Dual-write list order fields to chart prefs, localStorage, and POST /api/layout (merged server-side).
 */
export function persistLayoutOrderFields(email, fields = {}, { quiet = true } = {}) {
  const { payload, stamp } = buildListOrderPayload(fields);
  if (Object.keys(payload).length <= 1) return Promise.resolve();

  const snapshot = pickListOrdersSnapshot(email, { ...fields, [SAVED_AT_KEY]: stamp });
  saveLocalListOrders(email, snapshot);
  if (email) {
    saveChartPrefs(email, { listOrders: snapshot });
  }

  return api.post('/api/layout', payload)
    .catch(() => {
      if (!quiet) {
        window.dispatchEvent(new CustomEvent('cim-toast', { detail: 'Failed to save list order.' }));
      }
    });
}

/** After hydrate, push local / prefs-only orders back to the server quietly. */
export function syncListOrdersToServerIfNeeded(email, orders, usedLocalOrOpts) {
  if (!orders) return Promise.resolve();
  const usedLocal = typeof usedLocalOrOpts === 'object' && usedLocalOrOpts != null
    ? !!usedLocalOrOpts.usedLocal
    : !!usedLocalOrOpts;
  const needsStarTagsServerSync = typeof usedLocalOrOpts === 'object' && usedLocalOrOpts != null
    ? !!usedLocalOrOpts.needsStarTagsServerSync
    : false;
  if (!usedLocal && !needsStarTagsServerSync) return Promise.resolve();
  return persistLayoutOrderFields(email, orders, { quiet: true });
}
