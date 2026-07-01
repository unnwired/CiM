/** Host-operator session — set via Admin-Showcase.bat (?operator=1 on loopback only). */
export const OPERATOR_SESSION_KEY = 'cim.operator.session';

export function isLoopbackHost() {
  if (typeof window === 'undefined') return false;
  const h = window.location.hostname;
  return h === '127.0.0.1' || h === 'localhost' || h === '[::1]';
}

export function captureOperatorFromUrl() {
  if (typeof window === 'undefined' || !isLoopbackHost()) return false;
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get('operator') === '1') {
      sessionStorage.setItem(OPERATOR_SESSION_KEY, '1');
      return true;
    }
  } catch {
    // ignore
  }
  return false;
}

export function isOperatorSessionActive() {
  if (!isLoopbackHost()) return false;
  try {
    return sessionStorage.getItem(OPERATOR_SESSION_KEY) === '1';
  } catch {
    return false;
  }
}

export function clearOperatorSession() {
  try {
    sessionStorage.removeItem(OPERATOR_SESSION_KEY);
  } catch {
    // ignore
  }
}
