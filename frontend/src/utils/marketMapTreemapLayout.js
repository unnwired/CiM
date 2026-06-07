import { hierarchy, treemap, treemapSquarify } from 'd3-hierarchy';
import { treemapNodeValue } from './marketMapTileStyle';

const SECTOR_FALLBACK = 'Other';

/**
 * Build nested hierarchy: root → sectors → stocks (TradingView-style grouping).
 * Leaf area ∝ market_cap.
 */
export function buildMarketMapTreemapLayout(constituents, width, height, { groupBySector = true } = {}) {
  if (!constituents?.length || width <= 0 || height <= 0) {
    return { nodes: [], hasCapData: false };
  }

  const withCap = constituents.filter(c => {
    const v = treemapNodeValue(c);
    return Number.isFinite(v) && v > 1;
  });
  const hasCapData = withCap.length >= Math.max(3, Math.floor(constituents.length * 0.25));

  let rootData;
  if (groupBySector) {
    const sectorBuckets = new Map();
    for (const stock of constituents) {
      const sector = String(stock.nse_sector || '').trim() || SECTOR_FALLBACK;
      if (!sectorBuckets.has(sector)) sectorBuckets.set(sector, []);
      sectorBuckets.get(sector).push(stock);
    }
    rootData = {
      name: 'root',
      children: [...sectorBuckets.entries()]
        .sort((a, b) => {
          const sum = arr => arr.reduce((s, c) => s + treemapNodeValue(c), 0);
          return sum(b[1]) - sum(a[1]);
        })
        .map(([name, stocks]) => ({
          name,
          children: stocks.map(s => ({
            name: s.symbol,
            value: treemapNodeValue(s),
            stock: s,
          })),
        })),
    };
  } else {
    rootData = {
      name: 'root',
      children: constituents.map(s => ({
        name: s.symbol,
        value: treemapNodeValue(s),
        stock: s,
      })),
    };
  }

  const root = hierarchy(rootData)
    .sum(d => d.value ?? 0)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));

  const pad = groupBySector ? 3 : 2;
  treemap()
    .tile(treemapSquarify)
    .size([width, height])
    .round(true)
    .paddingOuter(4)
    .paddingTop(d => (d.depth === 1 && groupBySector ? 20 : 0))
    .paddingInner(pad)(root);

  const nodes = [];
  root.each(node => {
    if (node.depth === 0) return;
    const isLeaf = !node.children;
    const stock = node.data.stock;
    nodes.push({
      id: isLeaf ? stock?.symbol : `sector:${node.data.name}`,
      x0: node.x0,
      y0: node.y0,
      x1: node.x1,
      y1: node.y1,
      w: node.x1 - node.x0,
      h: node.y1 - node.y0,
      depth: node.depth,
      isLeaf,
      isSector: !isLeaf,
      sector: node.depth === 1 ? node.data.name : node.parent?.data?.name,
      stock: isLeaf ? stock : null,
    });
  });

  return { nodes, hasCapData };
}
