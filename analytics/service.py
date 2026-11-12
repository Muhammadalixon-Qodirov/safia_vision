"""Start one StreamWorker per source, concurrently, in one process. Each worker
gets its own detector (so ByteTrack state is per-stream). Returns the workers so
the caller can wait and stop them."""
from __future__ import annotations

import threading

from .detector import build_detector
from .state import SharedState
from .stream import StreamWorker


def start_service(cfg: dict, shared: SharedState | None = None, stop_event: threading.Event | None = None):
    shared = shared or SharedState()
    stop = stop_event or threading.Event()
    workers = []
    for src in cfg["sources"]:
        # a source may override the global model settings (e.g. a crowded camera
        # needs a larger model): source.model is merged over the top-level model
        mcfg = {**cfg["model"], **(src.get("model") or {})}
        detector = build_detector(mcfg)
        detector.warmup()
        workers.append(StreamWorker(src, mcfg, cfg["output"], cfg["alerts"],
                                    cfg.get("sample_hz", 1), detector, shared, stop))
    for w in workers:
        w.start()
    return workers, shared, stop
