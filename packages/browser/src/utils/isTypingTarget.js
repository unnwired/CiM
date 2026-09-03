/** True when keyboard events should stay with a focused form control (search, notes, % fields, etc.). */
export function isTypingTarget(el) {
  if (!el || typeof el !== 'object') return false;
  try {
    if (el.isContentEditable) return true;
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    if (typeof el.closest === 'function') {
      const host = el.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]');
      if (host) return true;
    }
  } catch (_) { /* ignore */ }
  return false;
}

/** Prefer activeElement — capture-phase window handlers can see a mismatched target in edge cases. */
export function isTypingContext(eventOrEl) {
  if (isTypingTarget(eventOrEl)) return true;
  if (eventOrEl && typeof eventOrEl === 'object' && eventOrEl.target != null) {
    if (isTypingTarget(eventOrEl.target)) return true;
  }
  if (typeof document !== 'undefined' && isTypingTarget(document.activeElement)) return true;
  return false;
}

/**
 * True when global letter/digit typeahead must NOT open.
 * Covers focused inputs and UI regions marked data-cim-no-typeahead
 * (Alerts panel, portfolio % controls) — including clicks on disabled fields
 * where focus never moves into the input.
 */
export function shouldBlockGlobalSearchTypeahead(event, lastPointerDownTarget) {
  if (isTypingContext(event)) return true;
  try {
    const ae = typeof document !== 'undefined' ? document.activeElement : null;
    if (ae && typeof ae.closest === 'function' && ae.closest('[data-cim-no-typeahead]')) {
      return true;
    }
    const t = event?.target;
    if (t && typeof t.closest === 'function' && t.closest('[data-cim-no-typeahead]')) {
      return true;
    }
    if (
      lastPointerDownTarget
      && typeof lastPointerDownTarget.closest === 'function'
      && lastPointerDownTarget.closest('[data-cim-no-typeahead]')
    ) {
      return true;
    }
  } catch (_) { /* ignore */ }
  return false;
}

/** Attach to number/% inputs so bubble-phase page shortcuts cannot steal keys. */
export function typingFieldKeyProps() {
  return {
    onKeyDownCapture: (e) => {
      e.stopPropagation();
    },
    onKeyUpCapture: (e) => {
      e.stopPropagation();
    },
    onKeyDown: (e) => {
      e.stopPropagation();
    },
  };
}
