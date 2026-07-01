import { useEffect } from 'react';
import { LIST_ORDER_KEYS, persistLayoutOrderFields } from './listOrderPersistence';

/**
 * Debounced server backup for Indices equity order + star tags (all users / accounts).
 */
export function useIndicesListOrderAutoSave({
  email,
  ready,
  indexStarTags,
  equitySymbolOrder,
}) {
  useEffect(() => {
    if (!ready) return undefined;
    const timer = window.setTimeout(() => {
      const fields = {
        [LIST_ORDER_KEYS.indexStarTags]: indexStarTags,
      };
      if (Array.isArray(equitySymbolOrder) && equitySymbolOrder.length > 0) {
        fields[LIST_ORDER_KEYS.equityIndexSymbolOrder] = equitySymbolOrder;
      }
      persistLayoutOrderFields(email, fields);
    }, 600);
    return () => window.clearTimeout(timer);
  }, [email, ready, indexStarTags, equitySymbolOrder]);
}
