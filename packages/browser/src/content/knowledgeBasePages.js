/** Knowledge Base page ids — order matches the main tab bar (see App.js TabBar). */
export const KNOWLEDGE_BASE_PAGE_GROUPS = [
  { key: 'main', label: 'Main tabs' },
  { key: 'opened', label: 'Opened tabs' },
];

/** @type {{ id: string, label: string, group: 'main' | 'opened' }[]} */
export const KNOWLEDGE_BASE_PAGES = [
  { id: 'dashboard', label: 'NSE', group: 'main' },
  { id: 'indices', label: 'Indices', group: 'main' },
  { id: 'funds', label: 'Funds', group: 'main' },
  { id: 'market-map', label: 'Market Map', group: 'main' },
  { id: 'market-pulse', label: 'Market Pulse', group: 'main' },
  { id: 'market-movers', label: 'Market Movers', group: 'main' },
  { id: 'earnings-beats', label: 'Earnings', group: 'main' },
  { id: 'watchlist', label: 'Watchlist', group: 'main' },
  { id: 'portfolio', label: 'Portfolio', group: 'main' },
  { id: 'pnl', label: 'P&L', group: 'main' },
  { id: 'potential-swings', label: 'Potential Swings', group: 'main' },
  { id: 'index-chart', label: 'Index Chart', group: 'opened' },
  { id: 'constituents', label: 'Index Constituents', group: 'opened' },
  { id: 'chart', label: 'Stock Chart', group: 'opened' },
];

export function resolveKnowledgeBaseGuideId(view) {
  const v = String(view || '').trim();
  if (!v) return 'dashboard';
  if (v.startsWith('index_')) return 'index-chart';
  if (v.startsWith('constituents_')) return 'constituents';
  if (v === 'chart') return 'chart';
  if (KNOWLEDGE_BASE_PAGES.some((p) => p.id === v)) return v;
  return 'dashboard';
}
