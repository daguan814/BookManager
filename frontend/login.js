(() => {
  const next = new URLSearchParams(window.location.search).get('next') || './index.html';
  const err = document.getElementById('err');
  const pwd = document.getElementById('pwd');

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

  async function checkStatus() {
    try {
      const resp = await fetchJson('./api/auth/status');
      if (resp.authenticated) {
        window.location.replace(next);
      }
    } catch (_) {
      // ignore
    }
  }

  async function login() {
    const value = (pwd.value || '').trim();
    err.textContent = '';
    if (!value) {
      err.textContent = '请输入密码';
      pwd.focus();
      return;
    }
    try {
      await fetchJson('./api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ password: value }),
      });
      window.location.replace(next);
    } catch (error) {
      err.textContent = error.message || '登录失败';
      pwd.focus();
      pwd.select();
    }
  }

  document.getElementById('loginBtn').addEventListener('click', () => {
    login();
  });
  pwd.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') login();
  });
  checkStatus();
})();
