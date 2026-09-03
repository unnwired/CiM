import { useEffect, useMemo } from 'react';
import { clearPageIntradaySymbols, setPageIntradaySymbols } from './intradaySymbolRegistry';

/** Register symbols visible on a page for Refresh prices collection. */
export function useRegisterIntradaySymbols(pageId, symbols) {
  const symKey = useMemo(() => {
    const set = new Set();
    for (const raw of symbols || []) {
      const sym = String(raw || '').trim().toUpperCase();
      if (sym) set.add(sym);
    }
    return [...set].sort().join(',');
  }, [symbols]);

  useEffect(() => {
    if (!pageId) return undefined;
    setPageIntradaySymbols(pageId, symKey ? symKey.split(',') : []);
    try {
      window.dispatchEvent(new CustomEvent('cim:page-symbols-changed', {
        detail: { pageId, count: symKey ? symKey.split(',').length : 0 },
      }));
    } catch { /* ignore */ }
    return () => clearPageIntradaySymbols(pageId);
  }, [pageId, symKey]);
}
