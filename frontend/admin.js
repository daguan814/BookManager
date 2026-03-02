const API_BASE = window.BOOKMANAGER_API_BASE || window.location.origin;

const state = {
  booksRows: [],
  editingBook: null,
};

const errorBox = document.getElementById('errorBox');
const panes = {
  books: document.getElementById('tab-books'),
  logs: document.getElementById('tab-logs'),
};

const editModal = document.getElementById('editModal');
const editFields = {
  isbn: document.getElementById('editIsbn'),
  title: document.getElementById('editTitle'),
  author: document.getElementById('editAuthor'),
  publisher: document.getElementById('editPublisher'),
  pubdate: document.getElementById('editPubdate'),
  gist: document.getElementById('editGist'),
  price: document.getElementById('editPrice'),
  page: document.getElementById('editPage'),
  publish_year: document.getElementById('editPublishYear'),
  cover_url: document.getElementById('editCoverUrl'),
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove('hidden');
}

function clearError() {
  errorBox.textContent = '';
  errorBox.classList.add('hidden');
}

function fmtTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN');
}

function emptyRow(colspan, text = '暂无数据') {
  return `<tr><td colspan="${colspan}" class="empty">${escapeHtml(text)}</td></tr>`;
}

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

async function fetchAllBooks(keyword = '') {
  const all = [];
  let page = 1;
  const pageSize = 100;
  while (true) {
    const query = keyword
      ? `?keyword=${encodeURIComponent(keyword)}&page=${page}&page_size=${pageSize}`
      : `?page=${page}&page_size=${pageSize}`;
    const data = await fetchJson(`${API_BASE}/api/books${query}`);
    const items = Array.isArray(data.items) ? data.items : [];
    all.push(...items);
    if (all.length >= (data.total || 0) || items.length < pageSize) break;
    page += 1;
  }
  return all;
}

function renderBooksTable() {
  const tbody = document.getElementById('booksBody');
  if (state.booksRows.length === 0) {
    tbody.innerHTML = emptyRow(11);
    return;
  }
  tbody.innerHTML = state.booksRows
    .map((item) => `
      <tr>
        <td>${escapeHtml(item.id)}</td>
        <td>${escapeHtml(item.isbn || '-')}</td>
        <td>${escapeHtml(item.title || '-')}</td>
        <td>${escapeHtml(item.author || '-')}</td>
        <td>${escapeHtml(item.publisher || '-')}</td>
        <td>${escapeHtml(item.pubdate || '-')}</td>
        <td>${escapeHtml(item.price || '-')}</td>
        <td>${escapeHtml(item.page || '-')}</td>
        <td class="gist-cell" title="${escapeHtml(item.gist || '-')} ">${escapeHtml(item.gist || '-')}</td>
        <td>${escapeHtml(item.quantity ?? '-')}</td>
        <td>
          <button class="mini-btn" data-action="edit" data-id="${item.id}">修改</button>
          <button class="mini-btn danger" data-action="delete" data-id="${item.id}">删除</button>
        </td>
      </tr>
    `)
    .join('');
}

async function loadBooks() {
  const keyword = (document.getElementById('keyword').value || '').trim();
  state.booksRows = await fetchAllBooks(keyword);
  renderBooksTable();
}

async function loadLogs() {
  const limit = Number(document.getElementById('logLimit').value || 100);
  const data = await fetchJson(`${API_BASE}/api/inventory/logs?limit=${limit}`);
  const tbody = document.getElementById('logsBody');
  if (!Array.isArray(data) || data.length === 0) {
    tbody.innerHTML = emptyRow(7);
    return;
  }
  tbody.innerHTML = data
    .map((item) => `
      <tr>
        <td>${escapeHtml(fmtTime(item.created_at))}</td>
        <td>${escapeHtml(item.isbn || '-')}</td>
        <td>${escapeHtml(item.title || '-')}</td>
        <td>${item.action === 'in' ? '入库' : '出库'}</td>
        <td>${escapeHtml(item.quantity ?? '-')}</td>
        <td>${escapeHtml(item.operator_name || '-')}</td>
        <td>${escapeHtml(item.remark || '-')}</td>
      </tr>
    `)
    .join('');
}

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach((button) => {
    button.classList.toggle('active', button.dataset.tab === name);
  });
  Object.entries(panes).forEach(([key, pane]) => {
    pane.classList.toggle('hidden', key !== name);
  });
}

function toCsvValue(value) {
  const text = String(value ?? '');
  if (text.includes(',') || text.includes('"') || text.includes('\n')) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}

function exportBooksCsv() {
  if (state.booksRows.length === 0) {
    showError('没有可导出的图书数据');
    return;
  }
  const headers = ['ID', 'ISBN', '书名', '作者', '出版社', '出版时间', '简介', '定价', '页数', '出版年', '封面链接', '库存', '创建时间', '更新时间'];
  const rows = state.booksRows.map((item) => [
    item.id,
    item.isbn,
    item.title,
    item.author,
    item.publisher,
    item.pubdate,
    item.gist,
    item.price,
    item.page,
    item.publish_year,
    item.cover_url,
    item.quantity,
    fmtTime(item.created_at),
    fmtTime(item.updated_at),
  ]);
  const csv = [headers, ...rows].map((line) => line.map(toCsvValue).join(',')).join('\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `图书管理导出_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function openEditModal(bookId) {
  const book = state.booksRows.find((x) => Number(x.id) === Number(bookId));
  if (!book) return;
  state.editingBook = book;
  Object.keys(editFields).forEach((key) => {
    editFields[key].value = book[key] ?? '';
  });
  editModal.classList.remove('hidden');
}

function closeEditModal() {
  state.editingBook = null;
  editModal.classList.add('hidden');
}

async function saveEdit() {
  if (!state.editingBook) return;
  const payload = {
    title: (editFields.title.value || '').trim(),
    author: (editFields.author.value || '').trim() || null,
    publisher: (editFields.publisher.value || '').trim() || null,
    pubdate: (editFields.pubdate.value || '').trim() || null,
    gist: (editFields.gist.value || '').trim() || null,
    price: (editFields.price.value || '').trim() || null,
    page: (editFields.page.value || '').trim() || null,
    publish_year: (editFields.publish_year.value || '').trim() || null,
    cover_url: (editFields.cover_url.value || '').trim() || null,
  };
  if (!payload.title) {
    showError('书名不能为空');
    return;
  }
  await fetchJson(`${API_BASE}/api/books/${state.editingBook.id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  closeEditModal();
  await loadBooks();
}

async function deleteBook(bookId) {
  const book = state.booksRows.find((x) => Number(x.id) === Number(bookId));
  if (!book) return;
  const ok = window.confirm(`确认删除《${book.title || book.isbn}》吗？删除后库存和日志会级联删除。`);
  if (!ok) return;
  await fetchJson(`${API_BASE}/api/books/${bookId}`, { method: 'DELETE' });
  await loadBooks();
}

async function safeRun(task) {
  clearError();
  try {
    await task();
  } catch (error) {
    showError(error.message || String(error));
  }
}

document.querySelectorAll('.tab-btn').forEach((button) => {
  button.addEventListener('click', async () => {
    const tab = button.dataset.tab;
    switchTab(tab);
    if (tab === 'books') await safeRun(loadBooks);
    if (tab === 'logs') await safeRun(loadLogs);
  });
});

document.getElementById('searchBooks').addEventListener('click', () => safeRun(loadBooks));
document.getElementById('reloadBooks').addEventListener('click', () => safeRun(loadBooks));
document.getElementById('reloadLogs').addEventListener('click', () => safeRun(loadLogs));
document.getElementById('exportBooksCsv').addEventListener('click', exportBooksCsv);
document.getElementById('keyword').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') safeRun(loadBooks);
});

document.getElementById('booksBody').addEventListener('click', (event) => {
  const btn = event.target.closest('button[data-action]');
  if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.action === 'edit') safeRun(() => openEditModal(id));
  if (btn.dataset.action === 'delete') safeRun(() => deleteBook(id));
});

document.getElementById('cancelEdit').addEventListener('click', closeEditModal);
document.getElementById('saveEdit').addEventListener('click', () => safeRun(saveEdit));
document.getElementById('logoutBtn').addEventListener('click', () => {
  sessionStorage.removeItem('bm_access_ok');
  window.location.href = './login.html';
});

safeRun(async () => {
  await Promise.all([loadBooks(), loadLogs()]);
});
