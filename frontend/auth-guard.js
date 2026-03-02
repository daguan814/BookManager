(() => {
  const KEY = 'bm_access_ok';
  const current = window.location.pathname.split('/').pop() || 'index.html';
  if (sessionStorage.getItem(KEY) !== '1') {
    const next = encodeURIComponent(`./${current}${window.location.search || ''}`);
    window.location.replace(`./login.html?next=${next}`);
  }
})();
