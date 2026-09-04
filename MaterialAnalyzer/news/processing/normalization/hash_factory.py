from __future__ import annotations

import hashlib


def sha256_text(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
