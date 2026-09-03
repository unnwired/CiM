/**
 * Group flat closed trades by symbol for expandable P&L panes.
 */

function computeGroupTotals(trades) {
  let qtySold = 0;
  let qtyBought = 0;
  let plSum = 0;
  let entryWeighted = 0;
  let exitWeighted = 0;
  let plPctWeighted = 0;
  let latestMktCap = null;
  let maxSaleDate = '';

  for (const t of trades) {
    const qs = Number(t.qty_sold) || 0;
    const qb = Number(t.qty_bought) || 0;
    const entry = Number(t.entry_price) || 0;
    const exit = Number(t.exit_price) || 0;
    const pl = Number(t.realized_pl) || 0;
    qtySold += qs;
    qtyBought += qb;
    plSum += pl;
    if (qs > 0) {
      entryWeighted += entry * qs;
      exitWeighted += exit * qs;
      const pct = Number(t.realized_pl_pct);
      if (Number.isFinite(pct)) plPctWeighted += pct * qs;
    }
    if (t.market_cap != null) latestMktCap = t.market_cap;
    const sd = String(t.sale_date || '');
    if (sd > maxSaleDate) maxSaleDate = sd;
  }

  return {
    qty_sold: qtySold,
    qty_bought: qtyBought,
    realized_pl: plSum,
    entry_price: qtySold > 0 ? entryWeighted / qtySold : null,
    exit_price: qtySold > 0 ? exitWeighted / qtySold : null,
    realized_pl_pct: qtySold > 0 ? plPctWeighted / qtySold : null,
    market_cap: latestMktCap,
    max_sale_date: maxSaleDate,
  };
}

export function buildSymbolGroups(trades) {
  const bySymbol = new Map();
  for (const t of trades) {
    if (!t || typeof t !== 'object') continue;
    const sym = String(t.symbol || '').trim().toUpperCase();
    if (!sym) continue;
    if (!bySymbol.has(sym)) bySymbol.set(sym, []);
    bySymbol.get(sym).push(t);
  }

  const groups = [];
  for (const [symbol, list] of bySymbol) {
    const sortedTrades = [...list].sort((a, b) => {
      const da = String(a.sale_date || '');
      const db = String(b.sale_date || '');
      if (da !== db) return da.localeCompare(db);
      return String(a.booked_at || '').localeCompare(String(b.booked_at || ''));
    });
    groups.push({
      id: `group-${symbol}`,
      symbol,
      trades: sortedTrades,
      totals: computeGroupTotals(sortedTrades),
    });
  }
  return groups;
}

export function groupSortValue(group, key) {
  const t = group.totals || {};
  switch (key) {
    case 'symbol':
      return group.symbol ?? '';
    case 'broker': {
      const tags = [...new Set((group.trades || []).map((t) => String(t.broker || 'manual').toLowerCase()))];
      return tags.length === 1 ? tags[0] : tags.sort().join(',');
    }
    case 'market_cap':
      return t.market_cap;
    case 'entry':
      return t.entry_price;
    case 'exit':
      return t.exit_price;
    case 'qty_bought':
      return t.qty_bought;
    case 'qty_sold':
      return t.qty_sold;
    case 'realized_pl':
      return t.realized_pl;
    case 'realized_pl_pct':
      return t.realized_pl_pct;
    case 'sale_date':
      return t.max_sale_date ?? '';
    default:
      return null;
  }
}

export function cycleDividerLabel(trade) {
  const sd = trade?.sale_date;
  if (!sd) return 'Re-opened';
  try {
    const d = new Date(`${sd}T12:00:00`);
    if (Number.isNaN(d.getTime())) return 'Re-opened';
    return `Re-opened ${d.toLocaleString('en-IN', { month: 'short', year: 'numeric' })}`;
  } catch {
    return 'Re-opened';
  }
}

/**
 * Flatten groups into render rows: parent, optional cycle dividers, children.
 */
export function buildGroupDisplayList(groups, expandedMap) {
  const out = [];
  for (const group of groups) {
    const expanded = expandedMap[group.symbol] === true;
    out.push({ type: 'parent', group, expanded });
    if (!expanded) continue;
    let prevCycle = null;
    for (const trade of group.trades) {
      const cycleId = trade.cycle_id ?? 1;
      if (prevCycle != null && cycleId !== prevCycle) {
        out.push({ type: 'divider', group, trade, label: cycleDividerLabel(trade) });
      }
      out.push({ type: 'child', group, trade });
      prevCycle = cycleId;
    }
  }
  return out;
}

export function sectionTotalFromTrades(trades, isLoss) {
  let sum = 0;
  for (const t of trades) {
    const pl = Number(t?.realized_pl);
    if (!Number.isFinite(pl)) continue;
    sum += isLoss ? Math.abs(pl) : pl;
  }
  return sum;
}
