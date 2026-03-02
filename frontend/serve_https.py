import io
import os
import ssl
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


HOST = "0.0.0.0"
PORT = 18080
BACKEND_BASE = os.getenv("BOOKMANAGER_BACKEND_BASE", "http://127.0.0.1:18081")
BASE_DIR = Path(__file__).resolve().parent
CERT_DIR = BASE_DIR / ".cert"
CERT_FILE = CERT_DIR / "local.crt"
KEY_FILE = CERT_DIR / "local.key"


def ensure_self_signed_cert() -> None:
    if CERT_FILE.exists() and KEY_FILE.exists():
        return

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BookManager Local"),
            x509.NameAttribute(NameOID.COMMON_NAME, "192.168.1.40"),
        ]
    )
    san = x509.SubjectAlternativeName(
        [
            x509.DNSName("localhost"),
            x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
            x509.IPAddress(__import__("ipaddress").ip_address("192.168.1.40")),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )

    KEY_FILE.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy()
            return
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self.send_error(405, "Method Not Allowed")

    def do_PUT(self):
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self.send_error(405, "Method Not Allowed")

    def do_HEAD(self):
        if self.path.startswith("/api/"):
            self._proxy(head_only=True)
            return
        super().do_HEAD()

    def _proxy(self, head_only: bool = False):
        target = f"{BACKEND_BASE}{self.path}"
        content_len = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_len) if content_len > 0 else None

        headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "connection"}}
        req = Request(url=target, data=body, method=self.command, headers=headers)
        try:
            with urlopen(req, timeout=10) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() in {"transfer-encoding", "connection", "content-encoding"}:
                        continue
                    self.send_header(key, value)
                self.end_headers()
                if not head_only:
                    self.wfile.write(payload)
        except HTTPError as err:
            payload = err.read() or b""
            self.send_response(err.code)
            self.send_header("Content-Type", err.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload and not head_only:
                self.wfile.write(payload)
        except URLError as err:
            payload = io.BytesIO(str(err).encode("utf-8"))
            data = payload.getvalue()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not head_only:
                self.wfile.write(data)


def main():
    ensure_self_signed_cert()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(CERT_FILE), keyfile=str(KEY_FILE))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"https://{HOST}:{PORT} serving {BASE_DIR}")
    print(f"/api -> {BACKEND_BASE}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
