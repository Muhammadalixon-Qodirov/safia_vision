"""Thread-safe live state: each worker publishes its latest counts; the optional
web page reads a snapshot. Kept tiny and lock-protected."""
from __future__ import annotations

import threading


class SharedState:
    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()

    def update(self, name: str, data: dict):
        with self._lock:
            self._d[name] = data

    def snapshot(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self._d.items()}
