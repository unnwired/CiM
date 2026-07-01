/**
 * Open http(s) links in the OS default browser when running inside Charts In Motion Desktop.
 * Falls back to window.open in a normal browser tab.
 */
export function openExternalUrl(url, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  const target = String(url || '').trim();
  if (!target) return;

  const desktop = typeof window !== 'undefined' ? window.cimDesktop : null;
  if (desktop?.openExternal) {
    desktop.openExternal(target).catch(() => {
      window.open(target, '_blank', 'noopener,noreferrer');
    });
    return;
  }
  window.open(target, '_blank', 'noopener,noreferrer');
}
