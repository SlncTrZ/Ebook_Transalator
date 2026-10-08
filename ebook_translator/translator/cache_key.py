"""Stable context fingerprinting for exact-response cache isolation.

Updated: 2026-10-08 20:04
"""

from __future__ import annotations

import hashlib
import json


def prompt_fingerprint(messages: list[dict]) -> str:
    """Băm SHA-256 danh sách message thành vân tay ổn định.

    Params:
        messages: Danh sách dict message prompt đem serialize JSON
            (ensure_ascii=False, sort_keys=True, separators (",", ":"),
            encode UTF-8).

    Returns:
        Chuỗi hexdigest SHA-256 của payload JSON.
    """
    payload = json.dumps(
        messages,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
