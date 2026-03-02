(() => {
  const PASS = 'sgxx';
  const KEY = 'bm_access_ok';
  const next = new URLSearchParams(window.location.search).get('next') || './admin.html';
  const err = document.getElementById('err');
  const pwd = document.getElementById('pwd');

  if (sessionStorage.getItem(KEY) === '1') {
    window.location.replace(next);
    return;
  }

  function login() {
    const value = (pwd.value || '').trim();
    if (value === PASS) {
      sessionStorage.setItem(KEY, '1');
      window.location.replace(next);
      return;
    }
    err.textContent = '密码错误';
    pwd.focus();
    pwd.select();
  }

  document.getElementById('loginBtn').addEventListener('click', login);
  pwd.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') login();
  });
})();
