"""Thread-safe live state: each worker publishes its latest counts; the optional
web page reads a snapshot. Kept tiny and lock-protected."""
from __future__ import annotations

import threading


class SharedState:
    def __init__(self):
        self._d = {}
        self._frames = {}            # name -> latest annotated JPEG bytes (for the live page)
        self._controls = {}          # name -> control dict the worker applies (pause/blur/reset/thresholds)
        self._alert_log = {}         # name -> list of finished alert episodes
        self._lock = threading.Lock()

    def update(self, name: str, data: dict):
        with self._lock:
            self._d[name] = data

    def snapshot(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self._d.items()}

    def set_frame(self, name: str, jpg: bytes):
        with self._lock:
            self._frames[name] = jpg

    def get_frame(self, name: str):
        with self._lock:
            return self._frames.get(name)

    # --- live controls (web -> worker) ---
    def set_control(self, name: str, **kw):
        with self._lock:
            self._controls.setdefault(name, {}).update(kw)

    def controls(self, name: str) -> dict:
        with self._lock:
            return dict(self._controls.get(name, {}))

    # --- alert history (worker -> web) ---
    def add_alert(self, name: str, episode: dict):
        with self._lock:
            self._alert_log.setdefault(name, []).append(episode)

    def alerts_all(self) -> dict:
        with self._lock:
            return {k: list(v) for k, v in self._alert_log.items()}
