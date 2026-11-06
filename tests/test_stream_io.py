"""Integration smoke test (needs OpenCV, not a GPU): write a synthetic video,
run a StreamWorker over it with a scripted FakeDetector, and check it produces
the per-minute CSV, the alert JSONL and an annotated video, and counts the one
crossing — proving the capture -> pipeline -> output path end to end.

    python tests/test_stream_io.py
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from analytics.detector import FakeDetector
from analytics.state import SharedState
from analytics.stream import StreamWorker

W, H, FPS, N = 640, 480, 25, 520

SOURCE = {
    "name": "counter",
    "uri": None,                       # filled with the synthetic file
    "realtime": False,
    "line": {"a": [0, 240], "b": [640, 240], "in_direction": [0, 1]},
    "zones": {
        "queue": {"polygon": [[0, 300], [300, 300], [300, 460], [0, 460]]},
        "staff": {"polygon": [[340, 300], [640, 300], [640, 460], [340, 460]]},
    },
}
ALERTS = {"queue": {"min_people": 3, "min_seconds": 10},
          "empty_counter": {"min_seconds": 15}, "grace_seconds": 2}
OUTPUT = {"dir": None, "annotated_video": True, "blur_faces": True}


def _person(tid, rx, ry):
    return (tid, rx - 15, ry - 110, rx + 15, ry, 0.9)


def _scripted_frames():
    queue3 = [_person(11, 50, 380), _person(12, 100, 380), _person(13, 150, 380)]
    frames = []
    for i in range(N):
        tracks = []
        if 8 <= i <= 14:                                   # #1 crosses the line downward
            y = 200 + (i - 8) * 14                          # 200 -> 284
            tracks.append(_person(1, 100, y))
        elif i > 14:
            tracks.append(_person(1, 100, 300))             # stays below the line
        if i >= 25:                                         # queue builds and stays
            tracks += queue3
        frames.append(tracks)
    return frames


def _make_video(path):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for _ in range(N):
        vw.write(np.full((H, W, 3), 40, dtype=np.uint8))
    vw.release()


def main():
    import tempfile
    import json
    import os
    tmp = Path(tempfile.mkdtemp())
    video = tmp / "synthetic.mp4"
    _make_video(video)
    assert video.exists() and video.stat().st_size > 0, "video not written"

    src = {**SOURCE, "uri": str(video)}
    out = {**OUTPUT, "dir": str(tmp / "out")}
    shared, stop = SharedState(), threading.Event()
    w = StreamWorker(src, {}, out, ALERTS, 1, FakeDetector(_scripted_frames()), shared, stop)
    w.start()
    w.join(timeout=30)
    assert not w.is_alive(), "worker did not finish"

    st = shared.snapshot().get("counter", {})
    assert st.get("in") == 1 and st.get("out") == 0, f"bad counts: {st}"

    csv_p = Path(out["dir"]) / "counter_minutes.csv"
    al_p = Path(out["dir"]) / "counter_alerts.jsonl"
    vid_p = Path(out["dir"]) / "counter" / "annotated.mp4"
    assert csv_p.exists() and csv_p.read_text().startswith("minute,in,out"), "no minute csv"
    assert vid_p.exists() and vid_p.stat().st_size > 0, "no annotated video"
    alerts = [json.loads(ln) for ln in al_p.read_text().splitlines() if ln.strip()]
    kinds = sorted(a["type"] for a in alerts)
    assert "queue" in kinds and "empty_counter" in kinds, f"alerts missing: {kinds}"
    print("PASS  test_stream_io  |  counts", st.get("in"), st.get("out"),
          "| alerts", kinds, "| annotated", vid_p.stat().st_size, "bytes")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL  test_stream_io: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR test_stream_io: {type(e).__name__}: {e}")
        sys.exit(1)
