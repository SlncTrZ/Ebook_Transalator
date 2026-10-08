"""Packaged desktop backend entry point used by the Tauri sidecar.

Updated: 2026-10-08 20:04
"""

from __future__ import annotations

import os

import uvicorn

from ebook_translator.server import app


def main() -> None:
    """Đọc ET_PORT và khởi chạy Uvicorn trên 127.0.0.1.

    Params:
        Không có tham số; đọc biến môi trường ET_PORT (mặc định "8080",
        ép kiểu int, rơi về 8080 khi TypeError/ValueError).

    Returns:
        None — hàm chặn luồng khi server chạy với log_level "info".
    """
    try:
        port = int(os.environ.get("ET_PORT", "8080"))
    except (TypeError, ValueError):
        port = 8080
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
