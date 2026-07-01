import { useEffect, useMemo } from 'react';
import { clearPageFocusedSymbols, setPageFocusedSymbols } from './intradaySymbolRegistry';

/** Register the symbol(s) on the active chart for Refresh prices (not whole tables). */
export function useRegisterFocusedSymbol(pageId, symbols) {
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
    setPageFocusedSymbols(pageId, symKey ? symKey.split(',') : []);
    return () => clearPageFocusedSymbols(pageId);
  }, [pageId, symKey]);
}
