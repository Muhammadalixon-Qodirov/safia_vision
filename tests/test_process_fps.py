"""process_fps test (no GPU): a 30 fps source with process_fps: 10 must run the
detector on every 3rd frame only, and still keep video time correct (a crossing
is counted, and the pipeline sees t advancing at the source's real rate).

    python tests/test_process_fps.py
"""
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from analytics.detector import FakeDetector
from analytics.state import SharedState
from analytics.stream import StreamWorker


class Cap30:
    def __init__(self, n):
        self.n, self.i, self.opened = n, 0, True

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return 30.0

    def read(self):
        if self.i < self.n:
            self.i += 1
            return True, np.zeros((120, 200, 3), np.uint8)
        return False, None

    def release(self):
        self.opened = False


def main():
    src = {"name": "cam", "uri": "clip.mp4", "realtime": False, "process_fps": 10,
           "line": {"a": [0, 100], "b": [200, 100], "in_direction": [0, 1]}, "zones": {}}
    out = {"dir": str(Path(tempfile.mkdtemp()) / "out"), "annotated_video": False, "blur_faces": False}
    alerts = {"queue": {"min_people": 3, "min_seconds": 10}, "empty_counter": {"min_seconds": 15}, "grace_seconds": 2}
    # 30 source frames -> 10 analysed; the person is above the line for 5 analysed frames, then below
    det = FakeDetector([[(1, 40, -30, 60, 70, 0.9)]] * 5 + [[(1, 40, 30, 60, 130, 0.9)]] * 5)
    shared = SharedState()
    w = StreamWorker(src, {}, out, alerts, 1, det, shared, threading.Event(), open_capture=lambda u: Cap30(30))
    w.start()
    w.join(timeout=20)
    st = shared.snapshot()["cam"]
    assert det.i == 10, f"detector ran {det.i} times, expected 10 (every 3rd of 30 frames)"
    assert st["in"] == 1, f"crossing not counted: {st}"
    assert abs(st["t"] - 0.9) < 0.05, f"video time wrong: last analysed t={st['t']} (expected 27/30=0.9 s)"
    print(f"PASS  test_process_fps  |  30 frames -> detector x{det.i}, IN={st['in']}, last t={st['t']}s")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL  test_process_fps: {e}")
        sys.exit(1)
