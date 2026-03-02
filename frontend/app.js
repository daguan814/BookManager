(() => {
  const API_BASE = window.BOOKMANAGER_API_BASE || window.location.origin;
  const SCAN_CAMERA_KEY = 'bm_scan_camera_id';

  const refs = {
    form: document.getElementById('inventoryForm'),
    actionIn: document.getElementById('actionIn'),
    actionOut: document.getElementById('actionOut'),
    isbn: document.getElementById('isbnInput'),
    qty: document.getElementById('qtyInput'),
    title: document.getElementById('titleInput'),
    author: document.getElementById('authorInput'),
    publisher: document.getElementById('publisherInput'),
    pubdate: document.getElementById('pubdateInput'),
    price: document.getElementById('priceInput'),
    page: document.getElementById('pageInput'),
    gist: document.getElementById('gistInput'),
    operator: document.getElementById('operatorInput'),
    borrowerName: document.getElementById('borrowerNameInput'),
    borrowerClass: document.getElementById('borrowerClassInput'),
    queryBtn: document.getElementById('queryBtn'),
    scanBtn: document.getElementById('scanBtn'),
    submitBtn: document.getElementById('submitBtn'),
    statusBox: document.getElementById('statusBox'),
    queryCard: document.getElementById('queryCard'),
    scanModal: document.getElementById('scanModal'),
    detectedIsbn: document.getElementById('detectedIsbn'),
    torchBtn: document.getElementById('torchBtn'),
    confirmScanBtn: document.getElementById('confirmScanBtn'),
    rescanBtn: document.getElementById('rescanBtn'),
    closeScanBtn: document.getElementById('closeScanBtn'),
    inOnlyFields: Array.from(document.querySelectorAll('.in-only')),
    outOnlyFields: Array.from(document.querySelectorAll('.out-only')),
  };

  let scanner = null;
  let scannerRunning = false;
  let detected = '';
  let torchSupported = false;
  let torchOn = false;

  function getRememberedCameraId() {
    try {
      return localStorage.getItem(SCAN_CAMERA_KEY) || '';
    } catch (_) {
      return '';
    }
  }

  function rememberCameraId(cameraId) {
    if (!cameraId) return;
    try {
      localStorage.setItem(SCAN_CAMERA_KEY, cameraId);
    } catch (_) {
      // no-op
    }
  }

  async function getPreferredCameraConfig() {
    try {
      const cameras = await Html5Qrcode.getCameras();
      if (!Array.isArray(cameras) || cameras.length === 0) return { facingMode: { ideal: 'environment' } };

      const remembered = getRememberedCameraId();
      if (remembered) {
        const hit = cameras.find((x) => x.id === remembered);
        if (hit) return hit.id;
      }

      const byLabel = cameras.find((x) => /back|rear|environment|后置|广角/i.test(x.label || ''));
      if (byLabel) return byLabel.id;
      return cameras[0].id;
    } catch (_) {
      return { facingMode: { ideal: 'environment' } };
    }
  }

  function getAction() {
    return refs.actionIn.checked ? 'in' : 'out';
  }

  function normalizeIsbn(raw) {
    return String(raw || '').replace(/[^0-9Xx]/g, '').toUpperCase();
  }

  function escapeHtml(text) {
    return String(text ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function setStatus(text, type = 'info') {
    refs.statusBox.className = `status ${type}`;
    refs.statusBox.textContent = text;
    refs.statusBox.classList.remove('hidden');
  }

  function clearStatus() {
    refs.statusBox.className = 'status hidden';
    refs.statusBox.textContent = '';
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

  function updateModeUI() {
    const inMode = getAction() === 'in';
    refs.inOnlyFields.forEach((el) => el.classList.toggle('hidden', !inMode));
    refs.outOnlyFields.forEach((el) => el.classList.toggle('hidden', inMode));
    refs.submitBtn.textContent = inMode ? '确认入库' : '确认借阅';
    refs.queryCard.classList.add('hidden');
  }

  function renderQueryCard(book) {
    refs.queryCard.innerHTML = `
      <h4>查询结果</h4>
      <p><strong>ISBN：</strong>${escapeHtml(book.isbn || '-')}</p>
      <p><strong>书名：</strong>${escapeHtml(book.title || '-')}</p>
      <p><strong>作者：</strong>${escapeHtml(book.author || '-')}</p>
      <p><strong>出版社：</strong>${escapeHtml(book.publisher || '-')}</p>
      <p><strong>出版时间：</strong>${escapeHtml(book.pubdate || book.publish_year || '-')}</p>
      <p><strong>定价：</strong>${escapeHtml(book.price || '-')}</p>
      <p><strong>页数：</strong>${escapeHtml(book.page || '-')}</p>
      <p><strong>当前库存：</strong>${escapeHtml(book.current_quantity ?? '-')}</p>
    `;
    refs.queryCard.classList.remove('hidden');
  }

  async function queryByIsbn() {
    const isbn = normalizeIsbn(refs.isbn.value);
    if (!isbn) {
      setStatus('请先输入或扫码 ISBN', 'warning');
      return;
    }

    clearStatus();
    refs.queryBtn.disabled = true;
    refs.queryBtn.textContent = '查询中...';
    try {
      const book = await fetchJson(`${API_BASE}/api/inventory/isbn-query`, {
        method: 'POST',
        body: JSON.stringify({ isbn }),
      });
      refs.isbn.value = book.isbn || isbn;
      refs.title.value = book.title || refs.title.value;
      refs.author.value = book.author || refs.author.value;
      refs.publisher.value = book.publisher || refs.publisher.value;
      refs.pubdate.value = book.pubdate || book.publish_year || refs.pubdate.value;
      refs.price.value = book.price || refs.price.value;
      refs.page.value = book.page || refs.page.value;
      refs.gist.value = book.gist || refs.gist.value;
      renderQueryCard(book);
      setStatus('查询成功，已自动填入可用字段。', 'success');
    } catch (error) {
      refs.queryCard.classList.add('hidden');
      setStatus(`查询失败：${error.message}`, 'error');
    } finally {
      refs.queryBtn.disabled = false;
      refs.queryBtn.textContent = '根据 ISBN 查询';
    }
  }

  async function startScan() {
    if (scannerRunning) return;
    detected = '';
    refs.detectedIsbn.textContent = '';
    refs.detectedIsbn.classList.add('hidden');
    refs.confirmScanBtn.disabled = true;
    refs.torchBtn.classList.add('hidden');
    refs.torchBtn.textContent = '开灯';
    torchSupported = false;
    torchOn = false;

    scanner = new Html5Qrcode('reader');
    const screen = window.innerWidth || 390;
    const formats = window.Html5QrcodeSupportedFormats;
    const config = {
      fps: screen <= 768 ? 28 : 20,
      qrbox: {
        width: Math.max(240, Math.min(340, Math.floor(screen * 0.85))),
        height: Math.max(80, Math.min(110, Math.floor(screen * 0.22))),
      },
      aspectRatio: 1.777,
      experimentalFeatures: { useBarCodeDetectorIfSupported: true },
      disableFlip: true,
    };
    if (formats) {
      config.formatsToSupport = [formats.EAN_13, formats.EAN_8];
    }

    const onSuccess = async (decodedText) => {
      const isbn = normalizeIsbn(decodedText);
      if (!isbn || detected) return;
      detected = isbn;
      refs.detectedIsbn.textContent = `已识别 ISBN：${isbn}`;
      refs.detectedIsbn.classList.remove('hidden');
      refs.confirmScanBtn.disabled = false;
      await stopScan();
    };

    try {
      const cameraConfig = await getPreferredCameraConfig();
      await scanner.start(cameraConfig, config, onSuccess, () => {});
      scannerRunning = true;

      const settings = scanner.getRunningTrackSettings?.();
      if (settings && settings.deviceId) rememberCameraId(settings.deviceId);

      try {
        await scanner.applyVideoConstraints({ advanced: [{ focusMode: 'continuous' }] });
      } catch (_) {
        // no-op
      }

      try {
        const caps = scanner.getRunningTrackCapabilities?.();
        if (caps && caps.torch) {
          torchSupported = true;
          refs.torchBtn.classList.remove('hidden');
        }
      } catch (_) {
        // no-op
      }
    } catch (error) {
      setStatus(`摄像头启动失败：${error}`, 'error');
    }
  }

  async function toggleTorch() {
    if (!scannerRunning || !scanner || !torchSupported) return;
    try {
      torchOn = !torchOn;
      await scanner.applyVideoConstraints({ advanced: [{ torch: torchOn }] });
      refs.torchBtn.textContent = torchOn ? '关灯' : '开灯';
    } catch (error) {
      torchOn = false;
      refs.torchBtn.textContent = '开灯';
      setStatus(`手电筒切换失败：${error}`, 'warning');
    }
  }

  async function stopScan() {
    if (!scanner) return;
    try {
      if (scannerRunning && torchOn) {
        try {
          await scanner.applyVideoConstraints({ advanced: [{ torch: false }] });
        } catch (_) {
          // no-op
        }
      }
      if (scannerRunning) await scanner.stop();
      await scanner.clear();
    } catch (_) {
      // no-op
    } finally {
      scannerRunning = false;
      scanner = null;
      torchSupported = false;
      torchOn = false;
      refs.torchBtn.classList.add('hidden');
      refs.torchBtn.textContent = '开灯';
    }
  }

  async function openScanModal() {
    refs.scanModal.classList.remove('hidden');
    await startScan();
  }

  async function closeScanModal() {
    await stopScan();
    refs.scanModal.classList.add('hidden');
  }

  async function rescan() {
    await stopScan();
    await startScan();
  }

  async function submitInventory(event) {
    event.preventDefault();
    const action = getAction();
    const isbn = normalizeIsbn(refs.isbn.value);
    const quantity = Number(refs.qty.value);
    const operator_name = (refs.operator.value || '').trim() || 'admin';

    if (!isbn) {
      setStatus('ISBN 不能为空。', 'warning');
      return;
    }
    if (!Number.isInteger(quantity) || quantity <= 0) {
      setStatus('数量必须是正整数。', 'warning');
      return;
    }

    const payload = { action, isbn, quantity, operator_name };
    if (action === 'in') {
      const title = (refs.title.value || '').trim();
      if (!title) {
        setStatus('入库时书名必填。', 'warning');
        return;
      }
      payload.title = title;
      payload.author = (refs.author.value || '').trim() || null;
      payload.publisher = (refs.publisher.value || '').trim() || null;
      payload.pubdate = (refs.pubdate.value || '').trim() || null;
      payload.price = (refs.price.value || '').trim() || null;
      payload.page = (refs.page.value || '').trim() || null;
      payload.gist = (refs.gist.value || '').trim() || null;
    }

    clearStatus();
    refs.submitBtn.disabled = true;
    refs.submitBtn.textContent = action === 'in' ? '入库提交中...' : '借阅提交中...';
    try {
      if (action === 'out') {
        const borrower_name = (refs.borrowerName.value || '').trim();
        const borrower_class = (refs.borrowerClass.value || '').trim();
        if (!borrower_name) {
          setStatus('借阅时借阅人必填。', 'warning');
          return;
        }
        if (!borrower_class) {
          setStatus('借阅时班级必填。', 'warning');
          return;
        }
        payload.borrower_name = borrower_name;
        payload.borrower_class = borrower_class;
      }
      const resp = await fetchJson(`${API_BASE}/api/inventory/confirm`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      renderQueryCard(resp.book || { isbn, title: payload.title });
      refs.qty.value = '';
      setStatus(`${action === 'in' ? '入库' : '借阅'}成功，当前库存：${resp.book.current_quantity}`, 'success');
    } catch (error) {
      setStatus(`提交失败：${error.message}`, 'error');
    } finally {
      refs.submitBtn.disabled = false;
      refs.submitBtn.textContent = action === 'in' ? '确认入库' : '确认借阅';
    }
  }

  refs.form.addEventListener('submit', submitInventory);
  refs.queryBtn.addEventListener('click', queryByIsbn);
  refs.scanBtn.addEventListener('click', openScanModal);
  refs.closeScanBtn.addEventListener('click', closeScanModal);
  refs.rescanBtn.addEventListener('click', rescan);
  refs.torchBtn.addEventListener('click', () => {
    toggleTorch();
  });
  refs.confirmScanBtn.addEventListener('click', () => {
    if (!detected) return;
    refs.isbn.value = detected;
    closeScanModal();
    setStatus(`已填入 ISBN：${detected}`, 'success');
  });

  refs.actionIn.addEventListener('change', updateModeUI);
  refs.actionOut.addEventListener('change', updateModeUI);
  window.addEventListener('beforeunload', stopScan);

  updateModeUI();
})();
