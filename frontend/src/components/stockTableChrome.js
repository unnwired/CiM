/**
 * Shared layout for Pulse / Portfolio / Watchlist stock list panes (header + rows + footer).
 * Keep these in sync when adjusting any of those tables.
 */
export const STOCK_LIST_HEADER_HEIGHT = 36;
export const STOCK_LIST_ROW_HEIGHT = 32;
export const STOCK_LIST_FOOTER_HEIGHT = 30;

export const stockListHeaderStripStyle = {
  display: 'flex',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '2px solid var(--border)',
  flexShrink: 0,
};

export const stockListFooterStripStyle = {
  height: STOCK_LIST_FOOTER_HEIGHT,
  flexShrink: 0,
  backgroundColor: 'var(--bg-secondary)',
  borderTop: '1px solid var(--border)',
  display: 'flex',
  alignItems: 'center',
  padding: '0 10px',
  fontSize: 11,
  color: 'var(--text-muted)',
};
