/**
 * Shared layout for list + chart split pages (header + rows + full-width status footer).
 * Keep these in sync when adjusting any of those tables.
 *
 * Body shell: StockListSplitBody — column → [list|divider|chart] → full-width footer.
 */
export const STOCK_LIST_HEADER_HEIGHT = 36;
export const STOCK_LIST_ROW_HEIGHT = 32;
export const STOCK_LIST_FOOTER_HEIGHT = 30;

export const stockListHeaderStripStyle = {
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '2px solid var(--border)',
  flexShrink: 0,
};

/** Outer column wrapping the split row + page-wide footer. */
export const stockListSplitColumnStyle = {
  flex: 1,
  minHeight: 0,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
};

/** Horizontal list | divider | chart row (put wrapperRef / resize measurements here). */
export const stockListSplitRowStyle = {
  flex: 1,
  minHeight: 0,
  display: 'flex',
  overflow: 'hidden',
};

/** Full-width status bar under the split (not nested in the list pane). */
export const stockListFooterStripStyle = {
  height: STOCK_LIST_FOOTER_HEIGHT,
  flexShrink: 0,
  width: '100%',
  boxSizing: 'border-box',
  backgroundColor: 'var(--bg-secondary)',
  borderTop: '1px solid var(--border)',
  display: 'flex',
  alignItems: 'center',
  padding: '0 10px',
  fontSize: 11,
  color: 'var(--text-muted)',
};

export const STOCK_LIST_COL_BORDER = '1px solid var(--border-light)';

/** Build a shared grid template so header + every row share identical column tracks. */
export function stockListGridTemplateColumns(columns, getWidth) {
  return columns.map((col) => `${getWidth(col)}px`).join(' ');
}

/** Outer grid row (header track or data row) — same template on both for aligned dividers. */
export function stockListGridTrackStyle(gridTemplateColumns, extra = {}) {
  return {
    display: 'grid',
    gridTemplateColumns,
    width: 'max-content',
    minWidth: '100%',
    boxSizing: 'border-box',
    ...extra,
  };
}

/** Grid cell — vertical divider on the right edge only (continuous line top-to-bottom). */
export function stockListGridCellStyle({ isLast = false } = {}) {
  return {
    minWidth: 0,
    overflow: 'hidden',
    boxSizing: 'border-box',
    borderRight: isLast ? 'none' : STOCK_LIST_COL_BORDER,
  };
}

export function stockListCellPad(colKey, { compact = false } = {}) {
  if (compact) return '0 4px 0 6px';
  if (colKey === 'note' || colKey === 'act') return '0 4px';
  return '0 8px';
}

/** Selection rail without shifting column tracks (replaces borderLeft on rows). */
export function stockListRowSelectShadow(borderLeftCss) {
  if (!borderLeftCss || borderLeftCss.includes('transparent')) return {};
  const match = borderLeftCss.match(/^(\d+)px\s+solid\s+(.+)$/);
  if (!match) return {};
  return { boxShadow: `inset ${match[1]}px 0 0 ${match[2]}` };
}

/** @deprecated Prefer grid cells — kept for non-grid call sites. */
export function stockListColWidthStyle(width, extra = {}) {
  return {
    width,
    minWidth: width,
    maxWidth: width,
    flexShrink: 0,
    overflow: 'hidden',
    boxSizing: 'border-box',
    ...extra,
  };
}
