/**
 * Group flat open lots by symbol for expandable P&L open grid.
 */

import { reconcilePnlRowOrder } from './listOrder';

function computeOpenGroupTotals(lots) {
  let qty = 0;
  let invested = 0;
  let unrealized = 0;
  let entryWeighted = 0;
  let plPctWeighted = 0;
  let price = null;
  let marketCap = null;
  let minEntryDate = '';
  let hasPlaceholder = false;

  for (const lot of lots) {
    if (lot.is_placeholder) {
      hasPlaceholder = true;
      continue;
    }
    const q = Number(lot.qty) || 0;
    const entry = Number(lot.entry_price) || 0;
    const inv = Number(lot.invested);
    const upl = Number(lot.unrealized_pl);
    qty += q;
    if (Number.isFinite(inv)) invested += inv;
    if (Number.isFinite(upl)) unrealized += upl;
    if (q > 0 && Number.isFinite(entry)) entryWeighted += entry * q;
    const pct = Number(lot.pl_pct);
    if (q > 0 && Number.isFinite(pct)) plPctWeighted += pct * q;
    if (lot.price != null) price = lot.price;
    if (lot.market_cap != null) marketCap = lot.market_cap;
    const ed = String(lot.entry_date || '');
    if (ed && (!minEntryDate || ed < minEntryDate)) minEntryDate = ed;
  }

  return {
    qty: qty || null,
    invested: qty > 0 ? Math.round(invested * 100) / 100 : null,
    unrealized_pl: qty > 0 ? Math.round(unrealized * 100) / 100 : null,
    entry_price: qty > 0 ? entryWeighted / qty : null,
    pl_pct: qty > 0 ? plPctWeighted / qty : null,
    price,
    market_cap: marketCap,
    min_entry_date: minEntryDate,
    has_placeholder: hasPlaceholder,
  };
}

function lotSortKey(lot) {
  const ed = String(lot.entry_date || '');
  const created = String(lot.created_at || '');
  if (ed) return `${ed}\0${created}`;
  return `z\0${created}`;
}

export function buildOpenSymbolGroups(rows) {
  const bySymbol = new Map();
  for (const row of rows || []) {
    if (!row || typeof row !== 'object') continue;
    const sym = String(row.symbol || '').trim().toUpperCase();
    if (!sym) continue;
    if (!bySymbol.has(sym)) bySymbol.set(sym, []);
    bySymbol.get(sym).push(row);
  }

  const groups = [];
  for (const [symbol, list] of bySymbol) {
    const sortedLots = [...list].sort((a, b) => lotSortKey(a).localeCompare(lotSortKey(b)));
    const isPlaceholder = sortedLots.length === 1 && sortedLots[0].is_placeholder;
    groups.push({
      id: isPlaceholder ? sortedLots[0].id : `group-${symbol}`,
      symbol,
      lots: sortedLots,
      isPlaceholder,
      totals: computeOpenGroupTotals(sortedLots),
    });
  }
  return groups;
}

export function openGroupSortValue(group, key) {
  const t = group.totals || {};
  const first = group.lots?.[0];
  switch (key) {
    case 'symbol':
      return group.symbol ?? '';
    case 'broker': {
      const tags = [...new Set((group.lots || []).map((l) => String(l.broker || 'manual').toLowerCase()))];
      return tags.length === 1 ? tags[0] : tags.sort().join(',');
    }
    case 'entry_date':
      return t.min_entry_date ?? first?.entry_date ?? '';
    case 'market_cap':
      return t.market_cap;
    case 'price':
      return t.price;
    case 'entry':
      return t.entry_price;
    case 'qty':
      return t.qty;
    case 'invested':
      return t.invested;
    case 'pl_pct':
      return t.pl_pct;
    case 'change_1d':
      return first?.change_1d;
    case 'change_1m':
      return first?.change_1m;
    case 'unrealized_pl':
      return t.unrealized_pl;
    default:
      return null;
  }
}

export function pnlOpenGroupKey(group) {
  if (!group) return '';
  if (group.isPlaceholder && group.lots?.[0]?.id) return String(group.lots[0].id);
  return `group-${String(group.symbol || '').toUpperCase()}`;
}

export function buildOpenGroupDisplayList(groups, expandedMap) {
  const out = [];
  for (const group of groups) {
    const expanded = expandedMap[group.symbol] === true;
    const multiLot = !group.isPlaceholder && group.lots.length > 1;
    out.push({ type: 'parent', group, expanded, multiLot });
    if (!multiLot || !expanded) continue;
    for (const lot of group.lots) {
      out.push({ type: 'child', group, lot });
    }
  }
  return out;
}

export function reconcilePnlGroupOrder(prevKeys, newGroups, prevGroups = []) {
  const newRows = newGroups.map((g) => ({
    id: pnlOpenGroupKey(g),
    symbol: g.symbol,
    entry_price: g.totals?.entry_price,
    qty: g.totals?.qty,
  }));
  const prevRows = prevGroups.map((g) => ({
    id: pnlOpenGroupKey(g),
    symbol: g.symbol,
    entry_price: g.totals?.entry_price,
    qty: g.totals?.qty,
  }));
  return reconcilePnlRowOrder(prevKeys, newRows, prevRows);
}
