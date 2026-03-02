const { createApp, nextTick } = Vue;

const API_BASE = window.BOOKMANAGER_API_BASE || window.location.origin;

createApp({
  data() {
    return {
      form: {
        action: "in",
        isbn: "",
        quantity: "",
        title: "",
        author: "",
        publisher: "",
        pubdate: "",
        gist: "",
        price: "",
        page: "",
        operator_name: "admin",
      },
      queryLoading: false,
      submitLoading: false,
      queriedBook: null,
      scanStatus: "",
      scanStatusType: "info",
      cameraDialogVisible: false,
      scanner: null,
      scannerRunning: false,
      scanLocked: false,
      cameraDetectedIsbn: "",
      viewportWidth: window.innerWidth || 390,
    };
  },
  computed: {
    isMobileScreen() {
      return this.viewportWidth <= 768;
    },
    cameraDialogWidth() {
      return this.isMobileScreen ? "96vw" : "660px";
    },
  },
  methods: {
    setStatus(message, type = "info") {
      this.scanStatus = message;
      this.scanStatusType = type;
    },
    normalizeIsbn(raw) {
      return String(raw || "").replace(/[^0-9Xx]/g, "").toUpperCase();
    },
    async fetchJSON(url, options = {}) {
      const resp = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || "请求失败");
      return data;
    },
    openCameraDialog() {
      this.cameraDetectedIsbn = "";
      this.cameraDialogVisible = true;
    },
    async startCameraScan() {
      if (this.scannerRunning) return;
      await nextTick();
      this.scanLocked = false;
      this.scanner = new Html5Qrcode("reader");

      const config = {
        fps: this.isMobileScreen ? 16 : 12,
        qrbox: {
          width: Math.max(200, Math.min(320, Math.floor(this.viewportWidth * 0.86))),
          height: Math.max(80, Math.min(140, Math.floor(this.viewportWidth * 0.36))),
        },
        aspectRatio: 1.777,
        experimentalFeatures: { useBarCodeDetectorIfSupported: true },
      };
      const formats = window.Html5QrcodeSupportedFormats;
      if (formats) {
        config.formatsToSupport = [
          formats.EAN_13,
          formats.EAN_8,
          formats.UPC_A,
          formats.UPC_E,
          formats.CODE_128,
          formats.CODE_39,
        ];
      }

      try {
        const onSuccess = async (decodedText) => {
          if (this.scanLocked) return;
          const isbn = this.normalizeIsbn(decodedText);
          if (!isbn) return;
          this.scanLocked = true;
          this.cameraDetectedIsbn = isbn;
          await this.stopCameraScan();
        };
        const onError = () => {};

        await this.scanner.start({ facingMode: "environment" }, config, onSuccess, onError);
        this.scannerRunning = true;
      } catch (err) {
        this.setStatus(`摄像头启动失败：${err}`, "error");
      }
    },
    async stopCameraScan() {
      if (!this.scanner) return;
      try {
        if (this.scannerRunning) await this.scanner.stop();
        await this.scanner.clear();
      } catch (err) {
        console.warn(err);
      } finally {
        this.scannerRunning = false;
        this.scanner = null;
      }
    },
    async rescanCamera() {
      this.cameraDetectedIsbn = "";
      await this.stopCameraScan();
      await this.startCameraScan();
    },
    confirmCameraIsbn() {
      if (!this.cameraDetectedIsbn) {
        this.setStatus("请先扫码", "warning");
        return;
      }
      this.form.isbn = this.cameraDetectedIsbn;
      this.cameraDialogVisible = false;
      this.setStatus(`已填入 ISBN：${this.form.isbn}`, "success");
    },
    async queryByIsbn() {
      const isbn = this.normalizeIsbn(this.form.isbn);
      if (!isbn) {
        this.setStatus("请先输入或扫码 ISBN", "warning");
        return;
      }

      this.queryLoading = true;
      try {
        const data = await this.fetchJSON(`${API_BASE}/api/inventory/isbn-query`, {
          method: "POST",
          body: JSON.stringify({ isbn }),
        });
        this.queriedBook = data;
        this.form.isbn = data.isbn || isbn;
        this.form.title = data.title || this.form.title;
        this.form.author = data.author || this.form.author;
        this.form.publisher = data.publisher || this.form.publisher;
        this.form.pubdate = data.pubdate || data.publish_year || this.form.pubdate;
        this.form.gist = data.gist || this.form.gist;
        this.form.price = data.price || this.form.price;
        this.form.page = data.page || this.form.page;
        this.setStatus("外部接口查询成功，已自动填入字段", "success");
      } catch (err) {
        this.setStatus(`查询失败：${err.message}`, "error");
      } finally {
        this.queryLoading = false;
      }
    },
    async submitInventory() {
      const isbn = this.normalizeIsbn(this.form.isbn);
      if (!isbn) {
        this.setStatus("ISBN 不能为空", "warning");
        return;
      }
      const qty = Number(this.form.quantity);
      if (!Number.isInteger(qty) || qty <= 0) {
        this.setStatus("数量必须填写正整数", "warning");
        return;
      }

      this.submitLoading = true;
      try {
        const payload = {
          isbn,
          action: this.form.action,
          quantity: qty,
          operator_name: (this.form.operator_name || "").trim() || "admin",
        };
        if (this.form.action === "in") {
          payload.title = (this.form.title || "").trim() || null;
          payload.author = (this.form.author || "").trim() || null;
          payload.publisher = (this.form.publisher || "").trim() || null;
          payload.pubdate = (this.form.pubdate || "").trim() || null;
          payload.gist = (this.form.gist || "").trim() || null;
          payload.price = (this.form.price || "").trim() || null;
          payload.page = (this.form.page || "").trim() || null;
        }

        const resp = await this.fetchJSON(`${API_BASE}/api/inventory/confirm`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        this.queriedBook = resp.book || this.queriedBook;
        this.setStatus(
          `${this.form.action === "in" ? "入库" : "出库"}成功：当前库存 ${resp.book.current_quantity}`,
          "success",
        );
        this.form.quantity = "";
      } catch (err) {
        this.setStatus(`提交失败：${err.message}`, "error");
      } finally {
        this.submitLoading = false;
      }
    },
    onResize() {
      this.viewportWidth = window.innerWidth || 390;
    },
  },
  mounted() {
    window.addEventListener("resize", this.onResize);
  },
  beforeUnmount() {
    window.removeEventListener("resize", this.onResize);
    this.stopCameraScan();
  },
}).use(ElementPlus).mount("#app");
