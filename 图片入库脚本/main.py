from __future__ import annotations

import argparse
import csv
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageOps
from pyzbar.pyzbar import ZBarSymbol, decode


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
DEFAULT_BASE_URL = os.getenv("BOOKMANAGER_API_BASE", "https://shuijing.site:8081").rstrip("/")
DEFAULT_OPERATOR = os.getenv("BOOKMANAGER_OPERATOR", "image-importer")
DEFAULT_QUANTITY = int(os.getenv("BOOKMANAGER_IMPORT_QUANTITY", "1"))
DEFAULT_TIMEOUT = float(os.getenv("BOOKMANAGER_API_TIMEOUT", "15"))
DEFAULT_VERIFY_SSL = os.getenv("BOOKMANAGER_VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no"}
DEFAULT_SCRIPT_TOKEN = os.getenv("SCRIPT_API_TOKEN", "bookmanager-script-token").strip()
DEFAULT_SSH_HOST = os.getenv("BOOKMANAGER_SSH_HOST", "shuijing.site").strip()
DEFAULT_SSH_PORT = int(os.getenv("BOOKMANAGER_SSH_PORT", "12222"))
DEFAULT_SSH_USER = os.getenv("BOOKMANAGER_SSH_USER", "shuijing").strip()
DEFAULT_SSH_KEY = os.getenv("BOOKMANAGER_SSH_KEY", str(Path.home() / "Documents" / "id_rsa_macos")).strip()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PENDING_DIR = BASE_DIR / "未入库"
DEFAULT_FAILURE_DIR = BASE_DIR / "入库失败"


class ImportErrorDetail(Exception):
    pass


@dataclass
class ProcessResult:
    file_name: str
    isbn: str | None
    success: bool
    detail: str


@dataclass
class RuntimeOptions:
    base_url: str
    verify_ssl: bool
    tunnel_process: subprocess.Popen[str] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从未入库图片中识别 ISBN 并调用 BookManager 入库。")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="BookManager 服务地址。")
    parser.add_argument("--operator", default=DEFAULT_OPERATOR, help="入库操作人。")
    parser.add_argument("--quantity", type=int, default=DEFAULT_QUANTITY, help="每张图片默认入库数量。")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="API 请求超时时间（秒）。")
    parser.add_argument("--pending-dir", type=Path, default=DEFAULT_PENDING_DIR, help="待处理图片目录。")
    parser.add_argument("--failure-dir", type=Path, default=DEFAULT_FAILURE_DIR, help="失败报告输出目录。")
    parser.add_argument("--script-token", default=DEFAULT_SCRIPT_TOKEN, help="后端脚本专用 token。")
    parser.add_argument("--ssh-host", default=DEFAULT_SSH_HOST, help="SSH 隧道主机。")
    parser.add_argument("--ssh-port", type=int, default=DEFAULT_SSH_PORT, help="SSH 端口。")
    parser.add_argument("--ssh-user", default=DEFAULT_SSH_USER, help="SSH 用户。")
    parser.add_argument("--ssh-key", default=DEFAULT_SSH_KEY, help="SSH 私钥路径。")
    parser.add_argument(
        "--verify-ssl",
        dest="verify_ssl",
        action="store_true",
        default=DEFAULT_VERIFY_SSL,
        help="校验 HTTPS 证书。",
    )
    parser.add_argument(
        "--no-verify-ssl",
        dest="verify_ssl",
        action="store_false",
        help="跳过 HTTPS 证书校验。",
    )
    return parser.parse_args()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(port: int, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def can_reach_health(session: requests.Session, base_url: str, verify_ssl: bool, timeout: float) -> bool:
    try:
        response = session.get(f"{base_url.rstrip('/')}/health", timeout=max(3.0, min(timeout, 8.0)), verify=verify_ssl)
        return response.ok
    except requests.RequestException:
        return False


def start_ssh_tunnel(args: argparse.Namespace) -> RuntimeOptions:
    key_path = Path(args.ssh_key)
    if not key_path.exists():
        raise ImportErrorDetail(f"SSH 私钥不存在: {key_path}")
    local_port = find_free_port()
    command = [
        "ssh",
        "-i",
        str(key_path),
        "-p",
        str(args.ssh_port),
        "-N",
        "-L",
        f"127.0.0.1:{local_port}:127.0.0.1:8081",
        f"{args.ssh_user}@{args.ssh_host}",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if not wait_for_port(local_port):
        process.terminate()
        raise ImportErrorDetail("SSH 隧道启动失败，未监听本地端口")
    return RuntimeOptions(base_url=f"https://127.0.0.1:{local_port}", verify_ssl=False, tunnel_process=process)


def prepare_runtime(session: requests.Session, args: argparse.Namespace) -> RuntimeOptions:
    if can_reach_health(session, args.base_url, args.verify_ssl, args.timeout):
        return RuntimeOptions(base_url=args.base_url.rstrip("/"), verify_ssl=args.verify_ssl)
    print("直连目标服务失败，准备切换到 SSH 隧道...")
    runtime = start_ssh_tunnel(args)
    if not can_reach_health(session, runtime.base_url, runtime.verify_ssl, args.timeout):
        if runtime.tunnel_process is not None:
            runtime.tunnel_process.terminate()
        raise ImportErrorDetail("SSH 隧道已建立，但仍无法访问服务器本机 8081")
    print(f"已切换到 SSH 隧道: {runtime.base_url}")
    return runtime


def normalize_isbn(text: str) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", str(text or "")).upper()
    if len(cleaned) in {10, 13}:
        return cleaned
    return None


def iter_image_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda item: item.name.lower(),
    )


def build_candidate_images(image: Image.Image) -> list[Image.Image]:
    base = ImageOps.exif_transpose(image).convert("RGB")
    candidates: list[Image.Image] = []
    for rotated in (base, base.rotate(90, expand=True), base.rotate(180, expand=True), base.rotate(270, expand=True)):
        gray = ImageOps.grayscale(rotated)
        high_contrast = ImageOps.autocontrast(gray)
        candidates.extend(
            [
                rotated,
                gray,
                high_contrast,
                gray.resize((max(1, gray.width * 2), max(1, gray.height * 2))),
                high_contrast.resize((max(1, high_contrast.width * 2), max(1, high_contrast.height * 2))),
            ]
        )
    return candidates


def decode_isbn_from_image(image_path: Path) -> str:
    try:
        with Image.open(image_path) as image:
            candidates = build_candidate_images(image)
    except Exception as exc:
        raise ImportErrorDetail(f"图片打开失败: {exc}") from exc

    symbols = [ZBarSymbol.EAN13, ZBarSymbol.UPCA, ZBarSymbol.CODE128]
    for candidate in candidates:
        try:
            results = decode(candidate, symbols=symbols)
        except Exception:
            continue
        for item in results:
            isbn = normalize_isbn(item.data.decode("utf-8", errors="ignore"))
            if isbn:
                return isbn
    raise ImportErrorDetail("未识别到有效 ISBN 条形码")


def _read_json(response: requests.Response) -> dict:
    try:
        return response.json()
    except ValueError as exc:
        snippet = response.text[:200].strip()
        raise ImportErrorDetail(f"接口未返回 JSON，HTTP {response.status_code}: {snippet}") from exc


def powershell_request_json(
    method: str,
    url: str,
    payload: dict | None,
    timeout: float,
    verify_ssl: bool,
    script_token: str,
) -> dict:
    escaped_url = url.replace("'", "''")
    escaped_payload = json.dumps(payload or {}, ensure_ascii=False).replace("'", "''")
    escaped_token = script_token.replace("'", "''")
    command = """
$ProgressPreference='SilentlyContinue'
$headers = @{
  'Content-Type'='application/json'
  'Accept'='application/json'
  'X-Bookmanager-Token'='{script_token}'
}
$body = '{payload}'
try {
  $resp = Invoke-WebRequest -Uri '{url}' -Method '{method}' -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec {timeout_sec} -SkipCertificateCheck:{skip_verify} -UseBasicParsing
  $result = [pscustomobject]@{ ok=$true; status=[int]$resp.StatusCode; body=$resp.Content }
} catch {
  $response = $_.Exception.Response
  if ($null -ne $response) {
    $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
    $content = $reader.ReadToEnd()
    $result = [pscustomobject]@{ ok=$false; status=[int]$response.StatusCode; body=$content }
  } else {
    $result = [pscustomobject]@{ ok=$false; status=0; body=$_.Exception.Message }
  }
}
$result | ConvertTo-Json -Compress
""".format(
        script_token=escaped_token,
        payload=escaped_payload,
        url=escaped_url,
        method=method,
        timeout_sec=max(1, int(timeout)),
        skip_verify="$true" if not verify_ssl else "$false",
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    raw = (completed.stdout or "").strip()
    if not raw:
        raise ImportErrorDetail(f"PowerShell 请求失败: {(completed.stderr or '').strip() or '无输出'}")
    try:
        wrapper = json.loads(raw)
    except ValueError as exc:
        raise ImportErrorDetail(f"PowerShell 返回无法解析: {raw[:200]}") from exc

    body_text = wrapper.get("body") or ""
    try:
        body = json.loads(body_text)
    except ValueError as exc:
        raise ImportErrorDetail(f"接口未返回 JSON，HTTP {wrapper.get('status')}: {body_text[:200]}") from exc

    if not wrapper.get("ok"):
        detail = body.get("detail") or body.get("msg") or str(body)
        raise ImportErrorDetail(f"HTTP {wrapper.get('status')}: {detail}")
    return body


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    timeout: float,
    verify_ssl: bool,
    payload: dict | None,
    script_token: str,
) -> dict:
    try:
        response = session.request(method, url, json=payload, timeout=timeout, verify=verify_ssl)
    except requests.exceptions.SSLError as exc:
        if os.name == "nt":
            return powershell_request_json(method, url, payload, timeout, verify_ssl, script_token)
        raise ImportErrorDetail(f"请求失败: {exc}") from exc
    except requests.RequestException as exc:
        raise ImportErrorDetail(f"请求失败: {exc}") from exc

    body = _read_json(response)
    if not response.ok:
        detail = body.get("detail") or body.get("msg") or str(body)
        raise ImportErrorDetail(f"HTTP {response.status_code}: {detail}")
    return body


def query_book_by_isbn(
    session: requests.Session,
    base_url: str,
    isbn: str,
    timeout: float,
    verify_ssl: bool,
    script_token: str,
) -> dict:
    return request_json(
        session,
        "POST",
        f"{base_url}/api/inventory/isbn-query",
        timeout,
        verify_ssl,
        {"isbn": isbn},
        script_token,
    )


def confirm_inventory(
    session: requests.Session,
    base_url: str,
    operator: str,
    isbn: str,
    quantity: int,
    book: dict,
    timeout: float,
    verify_ssl: bool,
    script_token: str,
) -> dict:
    title = (book.get("title") or "").strip()
    if not title:
        raise ImportErrorDetail("图书查询成功但缺少书名，无法入库")
    payload = {
        "action": "in",
        "isbn": isbn,
        "quantity": quantity,
        "operator_name": operator,
        "title": title,
        "author": book.get("author"),
        "publisher": book.get("publisher"),
        "pubdate": book.get("pubdate") or book.get("publish_year"),
        "gist": book.get("gist"),
        "price": book.get("price"),
        "page": book.get("page"),
    }
    return request_json(
        session,
        "POST",
        f"{base_url}/api/inventory/confirm",
        timeout,
        verify_ssl,
        payload,
        script_token,
    )


def write_failure_report(failure_dir: Path, results: list[ProcessResult]) -> Path | None:
    failed = [item for item in results if not item.success]
    if not failed:
        return None
    failure_dir.mkdir(parents=True, exist_ok=True)
    report_path = failure_dir / f"import_failures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file_name", "isbn", "detail"])
        writer.writeheader()
        for item in failed:
            writer.writerow({"file_name": item.file_name, "isbn": item.isbn or "", "detail": item.detail})
    return report_path


def process_one(
    session: requests.Session,
    image_path: Path,
    base_url: str,
    operator: str,
    quantity: int,
    timeout: float,
    verify_ssl: bool,
    script_token: str,
) -> ProcessResult:
    isbn: str | None = None
    try:
        isbn = decode_isbn_from_image(image_path)
        book = query_book_by_isbn(session, base_url, isbn, timeout, verify_ssl, script_token)
        confirm_inventory(session, base_url, operator, isbn, quantity, book, timeout, verify_ssl, script_token)
        image_path.unlink()
        return ProcessResult(image_path.name, isbn, True, "入库成功，已删除图片")
    except Exception as exc:
        return ProcessResult(image_path.name, isbn, False, str(exc))


def main() -> int:
    args = parse_args()
    if args.quantity <= 0:
        print("quantity 必须大于 0", file=sys.stderr)
        return 2
    pending_dir: Path = args.pending_dir
    failure_dir: Path = args.failure_dir
    pending_dir.mkdir(parents=True, exist_ok=True)
    failure_dir.mkdir(parents=True, exist_ok=True)

    image_files = iter_image_files(pending_dir)
    if not image_files:
        print(f"未找到待处理图片: {pending_dir}")
        return 0

    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "BookManager-ImageImporter/1.0",
            "X-Bookmanager-Token": args.script_token,
        }
    )
    tunnel_process: subprocess.Popen[str] | None = None

    try:
        runtime = prepare_runtime(session, args)
        tunnel_process = runtime.tunnel_process
        print(f"开始处理 {len(image_files)} 张图片，目录: {pending_dir}")
        print(f"目标服务: {runtime.base_url}")
        results: list[ProcessResult] = []
        for index, image_path in enumerate(image_files, start=1):
            result = process_one(
                session=session,
                image_path=image_path,
                base_url=runtime.base_url,
                operator=args.operator,
                quantity=args.quantity,
                timeout=args.timeout,
                verify_ssl=runtime.verify_ssl,
                script_token=args.script_token,
            )
            results.append(result)
            status = "SUCCESS" if result.success else "FAILED"
            isbn_text = result.isbn or "-"
            print(f"[{index}/{len(image_files)}] {status} {image_path.name} ISBN={isbn_text} {result.detail}")

        report_path = write_failure_report(failure_dir, results)
        success_count = sum(1 for item in results if item.success)
        failed_count = len(results) - success_count
        print(f"处理完成: 成功 {success_count}，失败 {failed_count}")
        if report_path is not None:
            print(f"失败报告: {report_path}")
            print("失败图片已保留在未入库目录，修正后可再次运行。")
        return 0 if failed_count == 0 else 1
    except ImportErrorDetail as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        return 2
    finally:
        if tunnel_process is not None:
            tunnel_process.terminate()
            try:
                tunnel_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                tunnel_process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
