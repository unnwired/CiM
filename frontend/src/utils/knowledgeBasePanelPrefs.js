const STORAGE_KEY = 'cim.knowledgeBase.widthRatio';

export const KB_DEFAULT_WIDTH_RATIO = 0.33;
export const KB_MIN_WIDTH_PX = 280;
export const KB_MAX_WIDTH_RATIO = 0.5;
export const KB_SIDEBAR_CHROME_PX = 16;

export function clampKnowledgeBaseWidthPx(widthPx, mainColumnWidth) {
  const col = Math.max(1, Number(mainColumnWidth) || 1);
  const min = Math.min(KB_MIN_WIDTH_PX, col);
  const max = Math.max(min, Math.floor(col * KB_MAX_WIDTH_RATIO));
  const w = Math.round(Number(widthPx) || 0);
  return Math.max(min, Math.min(max, w));
}

export function widthPxFromRatio(mainColumnWidth, ratio = KB_DEFAULT_WIDTH_RATIO) {
  const col = Math.max(1, Number(mainColumnWidth) || 1);
  const r = Number(ratio);
  const safeRatio = Number.isFinite(r) ? r : KB_DEFAULT_WIDTH_RATIO;
  const clampedRatio = Math.max(
    KB_MIN_WIDTH_PX / col,
    Math.min(KB_MAX_WIDTH_RATIO, safeRatio),
  );
  return clampKnowledgeBaseWidthPx(Math.floor(col * clampedRatio), col);
}

export function loadKnowledgeBaseWidthRatio() {
  if (typeof window === 'undefined') return KB_DEFAULT_WIDTH_RATIO;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw == null) return KB_DEFAULT_WIDTH_RATIO;
    const n = Number(raw);
    if (!Number.isFinite(n)) return KB_DEFAULT_WIDTH_RATIO;
    return Math.max(KB_MIN_WIDTH_PX / 800, Math.min(KB_MAX_WIDTH_RATIO, n));
  } catch {
    return KB_DEFAULT_WIDTH_RATIO;
  }
}

export function saveKnowledgeBaseWidthRatio(panelWidthPx, mainColumnWidth) {
  if (typeof window === 'undefined') return;
  const col = Math.max(1, Number(mainColumnWidth) || 1);
  const w = clampKnowledgeBaseWidthPx(panelWidthPx, col);
  const ratio = w / col;
  try {
    window.localStorage.setItem(STORAGE_KEY, String(ratio));
  } catch {
    // ignore quota errors
  }
}
