"""Inference-error test (no GPU): the detector raises a CUDA-out-of-memory style
error on two frames. The stream must NOT stop: it logs, backs off, skips those
frames, keeps going and still counts the crossing. (Before this, any exception in
inference ended the stream for good.)

    python tests/test_inference_error.py
"""
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from analytics.state import SharedState
from analytics.stream import StreamWorker


class Cap:
    def __init__(self, n):
        self.n, self.i, self.opened = n, 0, True

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return 25.0

    def read(self):
        if self.i < self.n:
            self.i += 1
            return True, np.zeros((120, 200, 3), np.uint8)
        return False, None

    def release(self):
        self.opened = False


class FlakyDetector:
    """Frames 0-4: person above the line, 5-9: below. Calls 3 and 4 raise."""
    def __init__(self):
        self.calls = 0

    def track(self, frame):
        i = self.calls
        self.calls += 1
        if i in (3, 4):
            raise RuntimeError("CUDA error: out of memory")
        y2 = 70 if i < 5 else 130
        return [(1, 40, y2 - 100, 60, y2, 0.9)]


class LongOutage(FlakyDetector):
    """Raises `msg` on calls 2..7 (6 in a row) - more than max_retries (2) in the test."""
    def __init__(self, msg):
        super().__init__()
        self.msg = msg

    def track(self, frame):
        i = self.calls
        if 2 <= i <= 7:
            self.calls += 1
            raise RuntimeError(self.msg)
        self.calls += 1
        return []


def _run(det, **extra):
    src = {"name": "cam", "uri": "clip.mp4", "realtime": False, "reconnect_backoff": 0.001,
           "line": {"a": [0, 100], "b": [200, 100], "in_direction": [0, 1]}, "zones": {}, **extra}
    out = {"dir": str(Path(tempfile.mkdtemp()) / "out"), "annotated_video": False, "blur_faces": False}
    alerts = {"queue": {"min_people": 3, "min_seconds": 10}, "empty_counter": {"min_seconds": 15}, "grace_seconds": 2}
    shared = SharedState()
    w = StreamWorker(src, {}, out, alerts, 1, det, shared, threading.Event(), open_capture=lambda u: Cap(12))
    w.start()
    w.join(timeout=20)


def test_long_out_of_memory_is_waited_out_other_errors_give_up():
    oom = LongOutage("CUDA error: out of memory")
    _run(oom, max_retries=2)
    assert oom.calls == 12, f"a long GPU-memory outage stopped the stream: {oom.calls}/12 frames"
    bad = LongOutage("some other error")
    _run(bad, max_retries=2)
    assert bad.calls < 12, "a persistent non-memory error should still give up"
    print("PASS  test_long_out_of_memory_is_waited_out_other_errors_give_up")


def main():
    src = {"name": "cam", "uri": "clip.mp4", "realtime": False, "reconnect_backoff": 0.01,
           "line": {"a": [0, 100], "b": [200, 100], "in_direction": [0, 1]}, "zones": {}}
    out = {"dir": str(Path(tempfile.mkdtemp()) / "out"), "annotated_video": False, "blur_faces": False}
    alerts = {"queue": {"min_people": 3, "min_seconds": 10}, "empty_counter": {"min_seconds": 15}, "grace_seconds": 2}
    det = FlakyDetector()
    shared = SharedState()
    w = StreamWorker(src, {}, out, alerts, 1, det, shared, threading.Event(), open_capture=lambda u: Cap(10))
    w.start()
    w.join(timeout=20)
    st = shared.snapshot()["cam"]
    assert det.calls == 10, f"stream stopped early: detector called {det.calls}/10 times"
    assert st["in"] == 1, f"crossing lost after the errors: {st}"
    print(f"PASS  test_inference_error  |  2 failed inferences survived, {det.calls} frames, IN={st['in']}")


if __name__ == "__main__":
    try:
        main()
        test_long_out_of_memory_is_waited_out_other_errors_give_up()
    except AssertionError as e:
        print(f"FAIL  test_inference_error: {e}")
        sys.exit(1)
