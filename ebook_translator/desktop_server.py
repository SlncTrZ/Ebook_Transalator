"""Packaged desktop backend entry point used by the Tauri sidecar."""

from __future__ import annotations

import os

import uvicorn

from ebook_translator.server import app


def main() -> None:
    try:
        port = int(os.environ.get("ET_PORT", "8080"))
    except (TypeError, ValueError):
        port = 8080
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
