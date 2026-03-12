(() => {
  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || payload.msg || `请求失败(${response.status})`);
    }
    return payload;
  }

  async function ensureAuth() {
    try {
      const status = await fetchJson('./api/auth/status');
      if (status.authenticated) return;
    } catch (_) {
      // fall through to login page
    }
    const current = `${window.location.pathname}${window.location.search || ''}`;
    const next = encodeURIComponent(current || '/index.html');
    window.location.replace(`./login.html?next=${next}`);
  }

  async function logout(event) {
    if (event) event.preventDefault();
    try {
      await fetchJson('./api/auth/logout', { method: 'POST' });
    } catch (_) {
      // ignore and redirect anyway
    }
    window.location.replace('./login.html');
  }

  document.addEventListener('DOMContentLoaded', () => {
    const logoutBtn = document.getElementById('logoutBtn');
    const logoutLink = document.getElementById('logoutLink');
    if (logoutBtn) logoutBtn.addEventListener('click', logout);
    if (logoutLink) logoutLink.addEventListener('click', logout);
  });

  ensureAuth();
})();
