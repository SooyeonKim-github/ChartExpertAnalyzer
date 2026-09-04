from __future__ import annotations

import threading
import time


class RateLimiter:
    """Simple per-client minimum interval limiter."""

    def __init__(self, min_interval_sec: float = 0.2):
        self.min_interval_sec = max(0.0, float(min_interval_sec))
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self.min_interval_sec - (now - self._last_call)
            if delay > 0:
                time.sleep(delay)
            self._last_call = time.monotonic()
