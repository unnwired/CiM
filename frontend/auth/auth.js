(function () {
  const API = '';

  function $(sel) { return document.querySelector(sel); }
  function showMsg(text, kind) {
    const el = $('#message');
    el.textContent = text || '';
    el.className = 'message' + (kind ? ' ' + kind : '');
  }

  async function api(method, path, body) {
    const res = await fetch(API + path, {
      method,
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

  document.querySelectorAll('.tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      $('#panel-' + btn.dataset.tab).classList.add('active');
      showMsg('');
    });
  });

  async function completeAuth() {
    showMsg('Starting Charts In Motion…', 'ok');
    await api('POST', '/api/auth/complete', {});
    if (window.cimDesktop && window.cimDesktop.restartBackend) {
      try {
        await window.cimDesktop.restartBackend({ forAuth: true });
      } catch {
        // Session is saved; reload still upgrades auth-only → full app in-process.
      }
    }
    window.location.reload();
  }

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
})();
