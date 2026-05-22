"""
# HTTP client dùng chung — gọi Backend API
"""

import json
from typing import Any, Iterator

import requests

from app.config import BACKEND_URL, HTTP_TIMEOUT


class ApiError(Exception):
    """Lỗi gọi API."""


def _url(path: str) -> str:
    """Ghép URL đầy đủ."""
    return f"{BACKEND_URL.rstrip('/')}{path}"


def health_check() -> bool:
    """Kiểm tra backend có sống không."""
    try:
        r = requests.get(_url("/health"), timeout=5)
        return r.status_code == 200
    except requests.RequestException:
        return False


def post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST JSON, trả dict."""
    try:
        r = requests.post(_url(path), json=payload, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise ApiError(str(exc)) from exc


def post_multipart(path: str, files: dict, data: dict | None = None) -> dict[str, Any]:
    """POST multipart (upload ảnh)."""
    try:
        r = requests.post(_url(path), files=files, data=data or {}, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise ApiError(str(exc)) from exc


def get_json(path: str, *, timeout: float | None = None) -> dict[str, Any]:
    """GET JSON, trả dict."""
    t = timeout if timeout is not None else HTTP_TIMEOUT
    try:
        r = requests.get(_url(path), timeout=t)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise ApiError(str(exc)) from exc


def delete(path: str) -> dict[str, Any]:
    """DELETE request."""
    try:
        r = requests.delete(_url(path), timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise ApiError(str(exc)) from exc


def post_stream(path: str, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """
    # POST tới endpoint NDJSON streaming
    Yield từng dict đã decode. Caller chạy trong thread riêng — request là blocking.
    Dùng `read=None` ngầm: HTTP_TIMEOUT là connect timeout, read sẽ stream lâu tùy ý.
    """
    try:
        with requests.post(
            _url(path),
            json=payload,
            stream=True,
            timeout=(10, None),  # (connect, read=None → không giới hạn read)
        ) as r:
            r.raise_for_status()
            r.encoding = "utf-8"
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # Bỏ qua dòng không hợp lệ thay vì làm sập luồng
                    continue
    except requests.RequestException as exc:
        raise ApiError(str(exc)) from exc
