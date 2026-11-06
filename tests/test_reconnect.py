"""Reconnect test (no GPU, no real stream): a source delivers 5 frames, drops,
then a second connection delivers 5 more. The worker must reconnect, keep
processing, and count the crossing that spans the drop - proving one stream's
failure is handled without losing continuity or crashing.

    python tests/test_reconnect.py
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from analytics.detector import FakeDetector
from analytics.state import SharedState
from analytics.stream import StreamWorker


class FakeCap:
    def __init__(self, n_ok):
        self.n_ok, self.i, self.opened = n_ok, 0, True

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return 25.0                      # CAP_PROP_FPS

    def read(self):
        if self.i < self.n_ok:
            self.i += 1
            return True, np.zeros((120, 200, 3), np.uint8)
        return False, None               # the drop / end of this connection

    def release(self):
        self.opened = False


class ClosedCap(FakeCap):
    def __init__(self):
        super().__init__(0)
        self.opened = False


def _person(y):
    return [(1, 40, y - 100, 60, y, 0.9)]   # ref bottom-centre = (50, y)


def main():
    import tempfile
    src = {"name": "cam", "uri": "rtsp://fake", "realtime": False,
           "max_retries": 5, "reconnect_backoff": 0.01,
           "line": {"a": [0, 100], "b": [200, 100], "in_direction": [0, 1]}, "zones": {}}
    out = {"dir": str(Path(tempfile.mkdtemp()) / "out"), "annotated_video": False, "blur_faces": False}
    alerts = {"queue": {"min_people": 3, "min_seconds": 10}, "empty_counter": {"min_seconds": 15}, "grace_seconds": 2}

    # two connections of 5 frames each; then opens keep failing -> worker gives up
    caps = [FakeCap(5), FakeCap(5)]
    open_capture = lambda uri: caps.pop(0) if caps else ClosedCap()

    # person is above the line for 5 frames, then below for 5 -> crosses across the reconnect
    detector = FakeDetector([_person(70)] * 5 + [_person(130)] * 5)

    shared, stop = SharedState(), threading.Event()
    w = StreamWorker(src, {}, out, alerts, 1, detector, shared, stop, open_capture=open_capture)
    w.start()
    w.join(timeout=20)

    assert not w.is_alive(), "worker did not finish"
    assert detector.i == 10, f"only {detector.i}/10 frames processed - reconnect failed"
    st = shared.snapshot().get("cam", {})
    assert st.get("in") == 1, f"crossing across the reconnect not counted: {st}"
    print(f"PASS  test_reconnect  |  processed {detector.i} frames across 2 connections, counted IN={st.get('in')}")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL  test_reconnect: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR test_reconnect: {type(e).__name__}: {e}")
        sys.exit(1)
