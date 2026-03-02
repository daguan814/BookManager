import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from config import settings


def normalize_isbn(isbn: str) -> str:
    normalized = re.sub(r"[^0-9Xx]", "", isbn).upper()
    if len(normalized) not in {10, 13}:
        raise ValueError("ISBN 必须是 10 位或 13 位")
    return normalized


def _build_sign(appid: str, timestamp: str, app_security: str) -> str:
    sign_src = f"{appid}&{timestamp}&{app_security}"
    return hashlib.md5(sign_src.encode("utf-8")).hexdigest()


def query_shumaidata_by_isbn(isbn: str, timeout: float = 3.5) -> dict:
    normalized = normalize_isbn(isbn)
    appid = settings.shumaidata_appid.strip()
    app_security = settings.shumaidata_app_security.strip()
    if not appid or not app_security:
        raise ValueError("未配置 SHUMAIDATA_APPID 或 SHUMAIDATA_APP_SECURITY")

    timestamp = str(int(time.time() * 1000))
    sign = _build_sign(appid, timestamp, app_security)
    response = requests.post(
        "https://api.shumaidata.com/v10/book/isbn",
        data={
            "appid": appid,
            "timestamp": timestamp,
            "sign": sign,
            "isbn": normalized,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()

    if not body.get("success") or body.get("code") != 200:
        raise ValueError(body.get("msg") or f"接口返回异常 code={body.get('code')}")

    data_root = body.get("data") or {}
    ret_code = data_root.get("ret_code")
    if ret_code != 0:
        raise ValueError(data_root.get("remark") or f"ret_code={ret_code}")

    items = data_root.get("data") or []
    if not items:
        raise ValueError("未查询到该 ISBN 对应图书")

    item = items[0]
    return {
        "success": True,
        "source": "shumaidata",
        "code": body.get("code"),
        "msg": body.get("msg"),
        "isbn": normalized,
        "title": item.get("title") or "未知书名",
        "author": item.get("author") or None,
        "publisher": item.get("publisher") or None,
        "pubdate": item.get("pubdate") or None,
        "gist": item.get("gist") or None,
        "price": item.get("price") or None,
        "page": item.get("page") or None,
        "publish_year": item.get("pubdate") or None,
        "cover_url": item.get("img") or None,
        "raw": item,
    }


def fetch_from_shumaidata(isbn: str, timeout: float = 2.5) -> dict | None:
    try:
        result = query_shumaidata_by_isbn(isbn, timeout=timeout)
    except (requests.RequestException, ValueError):
        return None

    return {
        "isbn": result["isbn"],
        "title": result["title"],
        "author": result.get("author"),
        "publisher": result.get("publisher"),
        "pubdate": result.get("pubdate"),
        "gist": result.get("gist"),
        "price": result.get("price"),
        "page": result.get("page"),
        "publish_year": result.get("publish_year"),
        "cover_url": result.get("cover_url"),
    }


def fetch_from_open_library(isbn: str, timeout: float = 1.2) -> dict | None:
    response = requests.get(
        "https://openlibrary.org/api/books",
        params={
            "bibkeys": f"ISBN:{isbn}",
            "format": "json",
            "jscmd": "data",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()

    data = payload.get(f"ISBN:{isbn}")
    if not data:
        return None

    authors = data.get("authors") or []
    publishers = data.get("publishers") or []
    return {
        "isbn": isbn,
        "title": data.get("title") or "未知书名",
        "author": ", ".join(a.get("name", "") for a in authors if a.get("name")) or None,
        "publisher": ", ".join(p.get("name", "") for p in publishers if p.get("name")) or None,
        "publish_year": data.get("publish_date"),
        "cover_url": (data.get("cover") or {}).get("large")
        or (data.get("cover") or {}).get("medium")
        or (data.get("cover") or {}).get("small"),
    }


def fetch_from_google_books(isbn: str, timeout: float = 1.2) -> dict | None:
    response = requests.get(
        "https://www.googleapis.com/books/v1/volumes",
        params={"q": f"isbn:{isbn}"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()

    items = payload.get("items") or []
    if not items:
        return None

    volume_info = items[0].get("volumeInfo", {})
    return {
        "isbn": isbn,
        "title": volume_info.get("title") or "未知书名",
        "author": ", ".join(volume_info.get("authors") or []) or None,
        "publisher": volume_info.get("publisher") or None,
        "publish_year": volume_info.get("publishedDate"),
        "cover_url": (volume_info.get("imageLinks") or {}).get("thumbnail"),
    }


def _placeholder_book(isbn: str) -> dict:
    return {
        "isbn": isbn,
        "title": f"ISBN {isbn}",
        "author": None,
        "publisher": None,
        "pubdate": None,
        "gist": None,
        "price": None,
        "page": None,
        "publish_year": None,
        "cover_url": None,
    }


def lookup_book_by_isbn(isbn: str) -> dict:
    normalized = normalize_isbn(isbn)

    shumaidata = fetch_from_shumaidata(normalized)
    if shumaidata:
        return shumaidata

    providers = (
        lambda: fetch_from_open_library(normalized),
        lambda: fetch_from_google_books(normalized),
    )
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(provider) for provider in providers]
            for future in as_completed(futures, timeout=2.0):
                try:
                    data = future.result()
                    if data:
                        return data
                except requests.RequestException:
                    continue
    except TimeoutError:
        pass

    return _placeholder_book(normalized)
