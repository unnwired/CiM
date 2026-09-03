/** Shared MIME + helpers for Basket drag-and-drop. */

export const BASKET_MIME = 'application/x-cim-basket-symbol';

export function normalizeBasketSymbol(raw) {
  return String(raw || '').trim().toUpperCase();
}

export function normalizeBasketKind(raw) {
  const k = String(raw || 'stock').trim().toLowerCase();
  return k === 'index' ? 'index' : 'stock';
}

/** Put symbol payload on a drag event (HTML5 DnD). */
export function startBasketSymbolDrag(e, symbol, kind = 'stock') {
  const sym = normalizeBasketSymbol(symbol);
  if (!sym || !e?.dataTransfer) return false;
  const payload = JSON.stringify({
    symbol: sym,
    kind: normalizeBasketKind(kind),
  });
  try {
    e.dataTransfer.setData(BASKET_MIME, payload);
    e.dataTransfer.setData('text/plain', sym);
    e.dataTransfer.effectAllowed = 'copy';
  } catch {
    try {
      e.dataTransfer.setData('text/plain', sym);
    } catch {
      return false;
    }
  }
  return true;
}

export function readBasketSymbolDrag(e) {
  if (!e?.dataTransfer) return null;
  let raw = '';
  try {
    raw = e.dataTransfer.getData(BASKET_MIME) || '';
  } catch {
    raw = '';
  }
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      const symbol = normalizeBasketSymbol(parsed?.symbol);
      if (!symbol) return null;
      return { symbol, kind: normalizeBasketKind(parsed?.kind) };
    } catch {
      /* fall through */
    }
  }
  try {
    const plain = normalizeBasketSymbol(e.dataTransfer.getData('text/plain'));
    if (plain && /^[A-Z0-9._-]+$/.test(plain) && plain.length <= 32) {
      return { symbol: plain, kind: 'stock' };
    }
  } catch {
    /* ignore */
  }
  return null;
}
