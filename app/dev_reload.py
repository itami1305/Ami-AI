"""
# Auto-reload supervisor cho Win App
Mô phỏng `uvicorn --reload`: spawn `python -m app.main` làm subprocess,
watch thư mục `app/` (file `.py`) và restart subprocess khi có thay đổi.

Chạy:
    python -m app.dev_reload
Hoặc thông qua `run_app.ps1`.

Tham số (positional):
    --no-watch        Chạy app 1 lần, không reload
    --watch <path>    Thêm thư mục để watch (lặp lại nhiều lần được)
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Iterable

try:
    from watchfiles import Change, watch
except ImportError as exc:  # pragma: no cover - thông báo rõ khi thiếu dep
    print(
        "[reload] Thiếu thư viện 'watchfiles'. Hãy cài đặt:\n"
        "    pip install watchfiles\n"
        "hoặc:\n"
        "    pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WATCH_DIRS = [PROJECT_ROOT / "app"]
APP_MODULE = "app.main"

# Khoảng dồn sự kiện để nhiều file save liên tiếp không trigger nhiều restart
DEBOUNCE_MS = 400


# ============================================================================ #
# Subprocess helpers
# ============================================================================ #
def _spawn() -> subprocess.Popen:
    """Khởi chạy Win App như 1 subprocess (kế thừa stdout/stderr của parent)."""
    creationflags = 0
    if os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP để có thể gửi CTRL_BREAK riêng cho child
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [sys.executable, "-m", APP_MODULE],
        cwd=str(PROJECT_ROOT),
        creationflags=creationflags,
    )


def _terminate(proc: subprocess.Popen, timeout: float = 3.0) -> None:
    """Dừng subprocess (terminate → kill nếu quá hạn)."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass


# ============================================================================ #
# Filter
# ============================================================================ #
def _py_filter(_change: Change, path: str) -> bool:
    """Chỉ phản ứng với file .py thật, bỏ qua cache."""
    if "__pycache__" in path:
        return False
    if path.endswith((".pyc", ".pyo", ".swp", ".tmp")):
        return False
    return path.endswith(".py")


def _relpath(p: str) -> str:
    try:
        return str(Path(p).resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return p


# ============================================================================ #
# CLI parsing (minimal — không cần argparse)
# ============================================================================ #
def _parse_args(argv: list[str]) -> tuple[bool, list[Path]]:
    """Trả (no_watch, watch_dirs)."""
    no_watch = False
    extra_dirs: list[Path] = []

    it = iter(argv)
    for token in it:
        if token == "--no-watch":
            no_watch = True
        elif token == "--watch":
            try:
                value = next(it)
            except StopIteration:
                print("[reload] --watch yêu cầu 1 đường dẫn", file=sys.stderr)
                raise SystemExit(2)
            extra_dirs.append(Path(value).resolve())
        elif token in ("-h", "--help"):
            print(__doc__)
            raise SystemExit(0)
        else:
            print(f"[reload] Tham số không hỗ trợ: {token}", file=sys.stderr)
            raise SystemExit(2)

    dirs = list(DEFAULT_WATCH_DIRS) + extra_dirs
    return no_watch, dirs


# ============================================================================ #
# Main loop
# ============================================================================ #
def _run_once() -> int:
    """Chạy app 1 lần, không reload — return exit code."""
    proc = _spawn()
    try:
        return proc.wait()
    except KeyboardInterrupt:
        _terminate(proc)
        return 130


def _run_with_reload(watch_dirs: Iterable[Path]) -> int:
    watch_dirs = [str(p) for p in watch_dirs]
    print("[reload] Watching:")
    for d in watch_dirs:
        print(f"  · {d}")
    print(f"[reload] Run: {sys.executable} -m {APP_MODULE}")
    print("[reload] Nhấn Ctrl+C để dừng.\n")

    proc = _spawn()
    print(f"[reload] App khởi động (pid={proc.pid}).")

    try:
        for changes in watch(
            *watch_dirs,
            watch_filter=_py_filter,
            debounce=DEBOUNCE_MS,
            recursive=True,
        ):
            files = sorted({_relpath(p) for _, p in changes})
            print(f"\n[reload] Phát hiện thay đổi: {', '.join(files)}")
            _terminate(proc)
            proc = _spawn()
            print(f"[reload] App restart (pid={proc.pid}).")
    except KeyboardInterrupt:
        print("\n[reload] Dừng theo yêu cầu (Ctrl+C).")
    finally:
        _terminate(proc)

    return 0


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    no_watch, watch_dirs = _parse_args(argv)

    # Cảnh báo nếu thư mục watch không tồn tại
    valid_dirs = []
    for d in watch_dirs:
        if d.exists():
            valid_dirs.append(d)
        else:
            print(f"[reload] Cảnh báo: thư mục không tồn tại, bỏ qua: {d}")

    if not valid_dirs and not no_watch:
        print("[reload] Không có thư mục hợp lệ để watch — chạy 1 lần không reload.")
        no_watch = True

    code = _run_once() if no_watch else _run_with_reload(valid_dirs)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
