from __future__ import annotations

import os
import re
import sys
import csv
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests


# 默认配置（从main.py复制）
DEFAULT_BASE_URL = os.getenv("BOOKMANAGER_API_BASE", "https://shuijing.site:8081").rstrip("/")
DEFAULT_OPERATOR = os.getenv("BOOKMANAGER_OPERATOR", "image-importer")
DEFAULT_QUANTITY = int(os.getenv("BOOKMANAGER_IMPORT_QUANTITY", "1"))
DEFAULT_TIMEOUT = float(os.getenv("BOOKMANAGER_API_TIMEOUT", "15"))
DEFAULT_REQUEST_INTERVAL = float(os.getenv("BOOKMANAGER_REQUEST_INTERVAL", "0.5"))
DEFAULT_RETRY_COUNT = int(os.getenv("BOOKMANAGER_REQUEST_RETRY_COUNT", "2"))
DEFAULT_RETRY_DELAY = float(os.getenv("BOOKMANAGER_REQUEST_RETRY_DELAY", "1.0"))
DEFAULT_VERIFY_SSL = os.getenv("BOOKMANAGER_VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no"}
DEFAULT_SCRIPT_TOKEN = os.getenv("SCRIPT_API_TOKEN", "bookmanager-script-token").strip()
DEFAULT_SSH_HOST = os.getenv("BOOKMANAGER_SSH_HOST", "shuijing.site").strip()
DEFAULT_SSH_PORT = int(os.getenv("BOOKMANAGER_SSH_PORT", "12222"))
DEFAULT_SSH_USER = os.getenv("BOOKMANAGER_SSH_USER", "shuijing").strip()
DEFAULT_SSH_KEY = os.getenv("BOOKMANAGER_SSH_KEY", str(Path.home() / "Documents" / "id_rsa_macos")).strip()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ISBN_FILE = BASE_DIR / "ISBN.txt"
DEFAULT_FAILURE_DIR = BASE_DIR / "入库失败"


class ImportErrorDetail(Exception):
    pass


@dataclass
class ProcessResult:
    isbn: str
    success: bool
    detail: str


@dataclass
class RuntimeOptions:
    base_url: str
    verify_ssl: bool
    tunnel_process: subprocess.Popen[str] | None = None


@dataclass
class RequestThrottle:
    # 控制两次请求之间的最小间隔，避免短时间内把接口打得太快。
    min_interval: float
    last_request_at: float = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self.last_request_at
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self.last_request_at = time.monotonic()


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


def start_ssh_tunnel(ssh_key: str, ssh_port: int, ssh_user: str, ssh_host: str) -> RuntimeOptions:
    key_path = Path(ssh_key)
    if not key_path.exists():
        raise ImportErrorDetail(f"SSH 私钥不存在: {key_path}")
    local_port = find_free_port()
    command = [
        "ssh",
        "-i",
        str(key_path),
        "-p",
        str(ssh_port),
        "-N",
        "-L",
        f"127.0.0.1:{local_port}:127.0.0.1:8081",
        f"{ssh_user}@{ssh_host}",
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


def prepare_runtime(session: requests.Session, base_url: str, verify_ssl: bool, timeout: float,
                   ssh_host: str, ssh_port: int, ssh_user: str, ssh_key: str) -> RuntimeOptions:
    if can_reach_health(session, base_url, verify_ssl, timeout):
        return RuntimeOptions(base_url=base_url.rstrip("/"), verify_ssl=verify_ssl)
    print("直连目标服务失败，准备切换到 SSH 隧道...")
    runtime = start_ssh_tunnel(ssh_key, ssh_port, ssh_user, ssh_host)
    if not can_reach_health(session, runtime.base_url, runtime.verify_ssl, timeout):
        if runtime.tunnel_process is not None:
            runtime.tunnel_process.terminate()
        raise ImportErrorDetail("SSH 隧道已建立，但仍无法访问服务器本机 8081")
    print(f"已切换到 SSH 隧道: {runtime.base_url}")
    return runtime


def read_isbn_file(isbn_file: Path) -> list[str]:
    """从ISBN.txt文件读取ISBN列表"""
    isbns = []
    if not isbn_file.exists():
        print(f"ISBN文件不存在: {isbn_file}", file=sys.stderr)
        return isbns
    
    try:
        with isbn_file.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                # 格式可能是 "文件名: ISBN" 或 "ISBN"
                if ":" in line:
                    # 提取冒号后面的部分作为ISBN
                    parts = line.split(":", 1)
                    isbn = parts[1].strip()
                else:
                    isbn = line.strip()
                
                # 清理ISBN（移除非数字和X之外的字符）
                cleaned = re.sub(r"[^0-9Xx]", "", isbn).upper()
                if len(cleaned) in (10, 13):
                    isbns.append(cleaned)
                else:
                    print(f"第{line_num}行: 无效的ISBN格式: {isbn}", file=sys.stderr)
    except OSError as exc:
        print(f"无法读取ISBN文件 {isbn_file}: {exc}", file=sys.stderr)
    
    return isbns


def get_isbn_lines(isbn_file: Path) -> list[str]:
    """读取ISBN文件的原始行（保留格式）"""
    lines = []
    if not isbn_file.exists():
        return lines
    try:
        with isbn_file.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        print(f"无法读取ISBN文件 {isbn_file}: {exc}", file=sys.stderr)
    return lines


def remove_successful_isbn(isbn_file: Path, successful_isbns: set[str]) -> int:
    """从ISBN文件中删除已成功的ISBN记录，返回删除的数量"""
    if not successful_isbns:
        return 0
    
    lines = get_isbn_lines(isbn_file)
    new_lines = []
    removed_count = 0
    
    for line in lines:
        original_line = line.strip()
        if not original_line or original_line.startswith("#"):
            new_lines.append(line)
            continue
        
        # 提取ISBN
        if ":" in original_line:
            parts = original_line.split(":", 1)
            isbn = parts[1].strip()
        else:
            isbn = original_line.strip()
        
        cleaned = re.sub(r"[^0-9Xx]", "", isbn).upper()
        
        if cleaned in successful_isbns:
            # 这个ISBN已成功入库，删除这一行
            removed_count += 1
            continue
        
        new_lines.append(line)
    
    # 写回文件
    try:
        with isbn_file.open("w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except OSError as exc:
        print(f"无法写入ISBN文件 {isbn_file}: {exc}", file=sys.stderr)
        return 0
    
    return removed_count


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    timeout: float,
    verify_ssl: bool,
    payload: dict | None,
    script_token: str,
    throttle: RequestThrottle | None = None,
    retry_count: int = DEFAULT_RETRY_COUNT,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    verbose: bool = False,
) -> dict:
    # 所有接口请求都经过这里，统一做限速和临时性错误重试。
    last_error: Exception | None = None
    for attempt in range(retry_count + 1):
        if throttle is not None:
            throttle.wait()
        try:
            response = session.request(method, url, json=payload, timeout=timeout, verify=verify_ssl)
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retry_count:
                time.sleep(max(0.0, retry_delay) * (attempt + 1))
                continue
            raise ImportErrorDetail(f"请求失败: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            snippet = response.text[:200].strip()
            raise ImportErrorDetail(f"接口未返回 JSON，HTTP {response.status_code}: {snippet}") from exc

        # 详细模式下打印响应
        if verbose:
            print(f"  API响应: status={response.status_code}, body={body}")

        if response.ok:
            # 检查响应中是否有错误标志
            if body.get("error") or body.get("code") == "error":
                detail = body.get("detail") or body.get("message") or body.get("msg") or str(body)
                raise ImportErrorDetail(f"业务错误: {detail}")
            # 检查常见的失败字段
            if body.get("success") is False:
                detail = body.get("detail") or body.get("message") or body.get("msg") or str(body)
                raise ImportErrorDetail(f"业务失败: {detail}")
            # 返回简洁的成功信息，不包含完整的书籍详情
            return {"success": True, "message": body.get("message", "操作成功")}

        detail = body.get("detail") or body.get("msg") or str(body)
        last_error = ImportErrorDetail(f"HTTP {response.status_code}: {detail}")
        if response.status_code in {502, 503, 504} and attempt < retry_count:
            # 502 这类网关错误通常是暂时性的，稍等后再试。
            time.sleep(max(0.0, retry_delay) * (attempt + 1))
            continue
        raise last_error

    raise ImportErrorDetail(f"请求失败: {last_error}")


def direct_confirm_inventory(
    session: requests.Session,
    base_url: str,
    operator: str,
    isbn: str,
    quantity: int,
    timeout: float,
    verify_ssl: bool,
    script_token: str,
    throttle: RequestThrottle | None = None,
    retry_count: int = DEFAULT_RETRY_COUNT,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    verbose: bool = False,
) -> dict:
    """直接确认入库，不使用查询API"""
    payload = {
        "action": "in",
        "isbn": isbn,
        "quantity": quantity,
        "operator_name": operator,
        "title": "未查询书名",  # 固定书名
        "author": None,
        "publisher": None,
        "pubdate": None,
        "gist": None,
        "price": None,
        "page": None,
    }
    return request_json(
        session,
        "POST",
        f"{base_url}/api/inventory/confirm",
        timeout,
        verify_ssl,
        payload,
        script_token,
        throttle,
        retry_count,
        retry_delay,
        verbose,
    )


def process_one_isbn(
    session: requests.Session,
    isbn: str,
    base_url: str,
    operator: str,
    quantity: int,
    timeout: float,
    verify_ssl: bool,
    script_token: str,
    throttle: RequestThrottle | None = None,
    retry_count: int = DEFAULT_RETRY_COUNT,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    verbose: bool = False,
) -> ProcessResult:
    """处理单个ISBN的入库"""
    try:
        result = direct_confirm_inventory(
            session, base_url, operator, isbn, quantity, timeout, 
            verify_ssl, script_token, throttle, retry_count, retry_delay, verbose
        )
        return ProcessResult(isbn, True, f"入库成功: {result}")
    except Exception as exc:
        return ProcessResult(isbn, False, str(exc))


def write_failure_report(failure_dir: Path, results: list[ProcessResult]) -> Path | None:
    failed = [item for item in results if not item.success]
    if not failed:
        return None
    failure_dir.mkdir(parents=True, exist_ok=True)
    report_path = failure_dir / f"import_failures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["isbn", "detail"])
        writer.writeheader()
        for item in failed:
            writer.writerow({"isbn": item.isbn, "detail": item.detail})
    return report_path


def main() -> int:
    # 默认设置
    isbn_file = DEFAULT_ISBN_FILE
    failure_dir = DEFAULT_FAILURE_DIR
    
    # 检查ISBN文件
    isbns = read_isbn_file(isbn_file)
    if not isbns:
        print(f"未找到有效的ISBN: {isbn_file}", file=sys.stderr)
        return 1
    
    total_isbns = len(isbns)
    print(f"从 '{isbn_file}' 中找到 {total_isbns} 个ISBN")
    print()
    
    # 显示菜单
    while True:
        print("=" * 50)
        print("请选择处理模式:")
        print("1. 处理全部ISBN（默认）")
        print("2. 只处理前 N 个ISBN")
        print("3. 启用详细模式处理全部ISBN")
        print("4. 退出")
        print("=" * 50)
        
        try:
            choice = input("请输入选择 (1-4): ").strip()
            if not choice:
                choice = "1"  # 默认选择1
            
            if choice == "1":
                limit = 0
                verbose = False
                break
            elif choice == "2":
                while True:
                    try:
                        limit_input = input(f"请输入要处理的ISBN数量 (1-{total_isbns}): ").strip()
                        if not limit_input:
                            print("使用默认值: 10")
                            limit = 10
                        else:
                            limit = int(limit_input)
                        
                        if 1 <= limit <= total_isbns:
                            break
                        else:
                            print(f"请输入 1 到 {total_isbns} 之间的数字")
                    except ValueError:
                        print("请输入有效的数字")
                verbose = False
                break
            elif choice == "3":
                limit = 0
                verbose = True
                break
            elif choice == "4":
                print("退出程序")
                return 0
            else:
                print("无效的选择，请重新输入")
        except KeyboardInterrupt:
            print("\n退出程序")
            return 0
    
    # 应用数量限制
    if limit > 0:
        isbns = isbns[:limit]
        print(f"将处理前 {limit} 个ISBN")
    
    print(f"开始处理 {len(isbns)} 个ISBN...")
    if verbose:
        print("详细模式已启用")
    
    # 创建session
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "BookManager-ISBNAgent/1.0",
            "X-Bookmanager-Token": DEFAULT_SCRIPT_TOKEN,
        }
    )
    
    # 准备运行时环境
    tunnel_process = None
    try:
        runtime = prepare_runtime(
            session, 
            DEFAULT_BASE_URL, 
            DEFAULT_VERIFY_SSL, 
            DEFAULT_TIMEOUT,
            DEFAULT_SSH_HOST,
            DEFAULT_SSH_PORT,
            DEFAULT_SSH_USER,
            DEFAULT_SSH_KEY
        )
        tunnel_process = runtime.tunnel_process
        
        # 创建限速器
        throttle = RequestThrottle(min_interval=DEFAULT_REQUEST_INTERVAL)
        
        results = []
        try:
            for idx, isbn in enumerate(isbns, start=1):
                result = process_one_isbn(
                    session=session,
                    isbn=isbn,
                    base_url=runtime.base_url,
                    operator=DEFAULT_OPERATOR,
                    quantity=DEFAULT_QUANTITY,
                    timeout=DEFAULT_TIMEOUT,
                    verify_ssl=runtime.verify_ssl,
                    script_token=DEFAULT_SCRIPT_TOKEN,
                    throttle=throttle,
                    retry_count=DEFAULT_RETRY_COUNT,
                    retry_delay=DEFAULT_RETRY_DELAY,
                    verbose=verbose,
                )
                results.append(result)
                
                # 显示进度
                if verbose:
                    status = "SUCCESS" if result.success else "FAILED"
                    print(f"[{idx}/{len(isbns)}] {status} ISBN={isbn} {result.detail}")
                else:
                    if idx % 10 == 0 or idx == len(isbns):
                        print(f"已处理 {idx}/{len(isbns)} 个ISBN...")
        
        except KeyboardInterrupt:
            print("\n处理被用户中断")
        
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
    
    if not results:
        print("没有处理任何ISBN")
        return 1
    
    # 生成失败报告
    report_path = write_failure_report(failure_dir, results)
    
    # 统计信息
    success_count = sum(1 for item in results if item.success)
    failed_count = len(results) - success_count
    
    # 删除已成功的ISBN记录
    if success_count > 0:
        successful_isbns = {item.isbn for item in results if item.success}
        removed = remove_successful_isbn(isbn_file, successful_isbns)
        print(f"处理完成: 成功 {success_count}，失败 {failed_count}，已从ISBN.txt中移除 {removed} 条记录")
    else:
        print(f"处理完成: 成功 {success_count}，失败 {failed_count}")
    
    if report_path is not None:
        print(f"失败报告: {report_path}")
        print("失败的ISBN已记录在报告中，可修正后重新运行。")
    
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())