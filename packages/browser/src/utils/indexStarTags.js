/** Star tag colors for Indices equity list (user-defined meaning). */

/** Priority order: picker left→right and list sort top→bottom. */
export const STAR_PRIORITY_ORDER = ['golden', 'green', 'blue', 'red'];

export const STAR_COLORS = STAR_PRIORITY_ORDER;

/** Cycle order: none → red → green → blue → golden → none (low → high priority). */
const CYCLE = [null, 'red', 'green', 'blue', 'golden'];

/** Sort rank (lower = higher in list). */
const TIER_RANK = {
  golden: 0,
  green: 1,
  blue: 2,
  red: 3,
};

export const STAR_COLOR_CSS = {
  red: 'var(--accent-red)',
  green: 'var(--accent-green)',
  blue: 'var(--accent-blue)',
  golden: 'var(--accent-gold)',
};

export function isValidStarTag(tag) {
  return tag == null || STAR_COLORS.includes(tag);
}

export function getStarTier(tag) {
  if (tag == null || !STAR_COLORS.includes(tag)) return 4;
  return TIER_RANK[tag] ?? 4;
}

/** Advance tag on cycle-click. Returns null for untagged. */
export function cycleStarTag(current) {
  const idx = CYCLE.indexOf(current ?? null);
  const nextIdx = idx === -1 ? 0 : (idx + 1) % CYCLE.length;
  return CYCLE[nextIdx];
}

/**
 * Sort items by star tier (golden first), preserving manual order within each tier.
 * @param {Array} items
 * @param {Object} starTags map symbol → tag
 * @param {(item) => string} getKey
 */
export function sortIndicesByStarTier(items, starTags, getKey) {
  if (!items || items.length === 0) return items || [];
  const tags = starTags && typeof starTags === 'object' ? starTags : {};
  const indexMap = new Map(items.map((it, i) => [getKey(it), i]));
  return [...items].sort((a, b) => {
    const ta = getStarTier(tags[getKey(a)]);
    const tb = getStarTier(tags[getKey(b)]);
    if (ta !== tb) return ta - tb;
    return (indexMap.get(getKey(a)) ?? 0) - (indexMap.get(getKey(b)) ?? 0);
  });
}

/** Normalize persisted tag map — drop invalid entries. */
export function normalizeStarTags(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const out = {};
  for (const [sym, tag] of Object.entries(raw)) {
    if (typeof sym === 'string' && sym && STAR_COLORS.includes(tag)) {
      out[sym] = tag;
    }
  }
  return out;
}
