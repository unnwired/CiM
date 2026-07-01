(function () {
  const API = '';
  const AUTH_ATTEMPT_KEY = 'cim.authAttempt';
  const OPERATOR_SESSION_KEY = 'cim.operator.session';

  function isLoopbackHost() {
    const h = window.location.hostname;
    return h === '127.0.0.1' || h === 'localhost' || h === '[::1]';
  }

  function captureOperatorFromUrl() {
    if (!isLoopbackHost()) return false;
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

  function applyOperatorSignInShell() {
    if (!captureOperatorFromUrl()) return;
    const banner = $('#operator-banner');
    if (banner) banner.classList.remove('hidden');
    const h1 = document.querySelector('header h1');
    const sub = document.querySelector('header .sub');
    if (h1) h1.textContent = 'Operator sign-in';
    if (sub) {
      sub.textContent = 'Host PC only — sign in to manage shared market data and run updates.';
    }
    document.title = 'Charts In Motion — Operator sign-in';
  }

  function $(sel) { return document.querySelector(sel); }
  function showMsg(text, kind) {
    const el = $('#message');
    el.textContent = text || '';
    el.className = 'message' + (kind ? ' ' + kind : '');
  }

  let pollTimer = null;

  function mapHealthToDot(health, fetchOk) {
    if (!fetchOk) return 'red';
    if (health && health.status === 'ok' && health.db_exists === true) return 'green';
    if (health) return 'amber';
    return 'red';
  }

  function setHealthDot(state) {
    document.querySelectorAll('.health-dot').forEach((dot) => {
      dot.className = 'health-dot health-dot--' + state;
    });
  }

  function setUsersOnlineCount(value) {
    const text = (typeof value === 'number' && Number.isFinite(value)) ? String(value) : '—';
    document.querySelectorAll('.users-online-count').forEach((el) => {
      el.textContent = text;
    });
  }

  async function fetchHealth() {
    try {
      const res = await fetch(API + '/api/health', {
        method: 'GET',
        credentials: 'omit',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      });
      const data = await res.json().catch(() => ({}));
      return { ok: res.ok, data };
    } catch {
      return { ok: false, data: null };
    }
  }

  async function fetchSocialProof() {
    try {
      const res = await fetch(API + '/api/auth/social-proof', {
        method: 'GET',
        credentials: 'omit',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) return null;
      const data = await res.json().catch(() => ({}));
      const n = Number(data.users_online);
      return Number.isFinite(n) ? n : null;
    } catch {
      return null;
    }
  }

  async function refreshAuthStatus() {
    const [health, usersOnline] = await Promise.all([
      fetchHealth(),
      fetchSocialProof(),
    ]);
    setHealthDot(mapHealthToDot(health.data, health.ok));
    setUsersOnlineCount(usersOnline);
  }

  function scheduleNextPoll() {
    if (pollTimer) clearTimeout(pollTimer);
    const delayMs = 30000 + Math.random() * 15000;
    pollTimer = setTimeout(async () => {
      await refreshAuthStatus();
      scheduleNextPoll();
    }, delayMs);
  }

  function startAuthStatusPolling() {
    refreshAuthStatus();
    scheduleNextPoll();
    window.addEventListener('pagehide', () => {
      if (pollTimer) clearTimeout(pollTimer);
    });
  }

  async function api(method, path, body) {
    const res = await fetch(API + path, {
      method,
      credentials: 'include',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      let detail = data.detail;
      if (detail && typeof detail === 'object') detail = detail.detail || JSON.stringify(detail);
      const err = new Error(detail || res.statusText || 'Request failed');
      err.needTotp = res.headers.get('X-Need-Totp') === '1' || data.need_totp
        || (data.detail && data.detail.need_totp);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function showSignInTab(email) {
    document.querySelector('.tab[data-tab="signin"]').click();
    const form = $('#form-signin');
    const emailInput = form.querySelector('input[name="email"]');
    const passwordInput = form.querySelector('input[name="password"]');
    if (emailInput) emailInput.value = email || '';
    if (passwordInput) passwordInput.value = '';
    $('#totp-wrap').classList.add('hidden');
  }

  function appEntryUrl() {
    let url = '/?_cim=' + Date.now();
    try {
      if (sessionStorage.getItem(OPERATOR_SESSION_KEY) === '1') url += '&operator=1';
    } catch {
      // ignore
    }
    return url;
  }

  async function waitForAppReady() {
    let lastErr = null;
    for (let attempt = 0; attempt < 10; attempt += 1) {
      try {
        const enter = await api('GET', '/api/auth/enter-check');
        if (enter && enter.app_ready) return enter;
      } catch (err) {
        lastErr = err;
        await new Promise((resolve) => setTimeout(resolve, 150));
      }
    }
    throw lastErr || new Error(
      'Your browser did not keep the sign-in session. Open the HTTPS showcase link and allow cookies for this site.',
    );
  }

  async function completeAuth() {
    showMsg('Starting Charts In Motion…', 'ok');
    await waitForAppReady();
    try {
      await api('POST', '/api/auth/complete', {});
    } catch {
      // Web showcase does not need a backend restart; enter-check already validated the session.
    }
    sessionStorage.setItem(AUTH_ATTEMPT_KEY, String(Date.now()));
    window.location.replace(appEntryUrl());
  }

  function maybeRecoverFromFailedEntry() {
    const ts = sessionStorage.getItem(AUTH_ATTEMPT_KEY);
    if (!ts) return;
    const age = Date.now() - Number(ts);
    if (!Number.isFinite(age) || age > 20000) {
      sessionStorage.removeItem(AUTH_ATTEMPT_KEY);
      return;
    }
    sessionStorage.removeItem(AUTH_ATTEMPT_KEY);
    showMsg('Checking your session…', 'ok');
    waitForAppReady()
      .then(() => {
        sessionStorage.setItem(AUTH_ATTEMPT_KEY, String(Date.now()));
        window.location.replace(appEntryUrl());
      })
      .catch((err) => {
        showMsg(
          err.message || 'Sign-in worked but Charts In Motion did not open. Allow cookies and use the HTTPS link.',
          'error',
        );
      });
  }

  document.querySelectorAll('.tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      $('#panel-' + btn.dataset.tab).classList.add('active');
      showMsg('');
    });
  });

  $('#form-signin').addEventListener('submit', async (e) => {
    e.preventDefault();
    showMsg('');
    const fd = new FormData(e.target);
    const body = {
      email: fd.get('email'),
      password: fd.get('password'),
      totp_code: fd.get('totp_code') || undefined,
    };
    try {
      await api('POST', '/api/auth/login', body);
      await refreshAuthStatus();
      await completeAuth();
    } catch (err) {
      if (err.needTotp) {
        $('#totp-wrap').classList.remove('hidden');
        showMsg('Enter the 6-digit code from your authenticator app.', 'error');
        return;
      }
      showMsg(err.message || 'Sign in failed', 'error');
    }
  });

  $('#form-signup').addEventListener('submit', async (e) => {
    e.preventDefault();
    showMsg('');
    const fd = new FormData(e.target);
    if (fd.get('password') !== fd.get('confirm')) {
      showMsg('Passwords do not match', 'error');
      return;
    }
    const email = String(fd.get('email') || '').trim();
    const password = String(fd.get('password') || '');
    try {
      const data = await api('POST', '/api/auth/signup', { email, password });
      const dlg = $('#recovery-dialog');
      $('#recovery-codes').textContent = (data.recovery_codes || []).join('\n');
      $('#recovery-saved').checked = false;
      $('#recovery-continue').disabled = true;
      dlg.showModal();
      $('#recovery-saved').onchange = () => {
        $('#recovery-continue').disabled = !$('#recovery-saved').checked;
      };
      $('#recovery-continue').onclick = () => {
        dlg.close();
        showSignInTab(email);
        showMsg('Account created. Sign in with your email and password.', 'ok');
      };
    } catch (err) {
      showMsg(err.message || 'Sign up failed', 'error');
    }
  });

  $('#form-reset').addEventListener('submit', async (e) => {
    e.preventDefault();
    showMsg('');
    const fd = new FormData(e.target);
    try {
      await api('POST', '/api/auth/reset-with-recovery-code', {
        email: fd.get('email'),
        recovery_code: fd.get('recovery_code'),
        new_password: fd.get('new_password'),
      });
      showMsg('Password reset — sign in with your new password.', 'ok');
      showSignInTab(String(fd.get('email') || '').trim());
    } catch (err) {
      showMsg(err.message || 'Reset failed', 'error');
    }
  });

  maybeRecoverFromFailedEntry();
  applyOperatorSignInShell();
  startAuthStatusPolling();
})();
