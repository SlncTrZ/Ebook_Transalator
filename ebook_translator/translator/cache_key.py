"""Stable context fingerprinting for exact-response cache isolation."""

from __future__ import annotations

import hashlib
import json


def prompt_fingerprint(messages: list[dict]) -> str:
    payload = json.dumps(
        messages,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
