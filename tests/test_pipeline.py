"""End-to-end test of the per-source pipeline with synthetic tracks (no GPU, no
OpenCV): a person crosses the door IN, a queue of 3 builds while the counter is
empty, triggering both alerts; then it clears. Checks counts, both alert
episodes, and the per-minute row.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.pipeline import StreamPipeline

SOURCE = {
    "name": "counter",
    "line": {"a": [0, 100], "b": [200, 100], "in_direction": [0, 1]},
    "zones": {
        "queue": {"polygon": [[0, 200], [100, 200], [100, 400], [0, 400]]},
        "staff": {"polygon": [[120, 200], [200, 200], [200, 400], [120, 400]]},
    },
}
ALERTS = {"queue": {"min_people": 3, "min_seconds": 10},
          "empty_counter": {"min_seconds": 15}, "grace_seconds": 2}


def person(tid, rx, ry):
    return (tid, rx - 10, ry - 120, rx + 10, ry, 0.9)


QUEUE3 = [person(11, 30, 350), person(12, 50, 350), person(13, 70, 350)]


def test_full_pipeline():
    pipe = StreamPipeline(SOURCE, ALERTS, sample_hz=1)
    alerts, rows = [], []

    def step(t, tracks):
        r = pipe.process(t, tracks)
        alerts.extend(r["alerts"])
        rows.extend(r["minute_rows"])

    # person #1 crosses the line downward (IN) while the queue of 3 is present
    step(1.00, [person(1, 50, 70)] + QUEUE3)
    step(1.04, [person(1, 50, 130)] + QUEUE3)
    for t in range(2, 36):                       # queue stays, counter empty
        step(float(t), [person(1, 50, 130)] + QUEUE3)
    for t in range(36, 43):                       # queue clears
        step(float(t), [person(1, 50, 130)])

    fin = pipe.finalize()
    alerts.extend(fin["alerts"])
    rows.extend(fin["minute_rows"])

    assert pipe.counter.in_count == 1 and pipe.counter.out_count == 0

    kinds = sorted(a["type"] for a in alerts)
    assert kinds == ["empty_counter", "queue"], kinds
    q = next(a for a in alerts if a["type"] == "queue")
    assert q["start"] == 1 and q["end"] == 35 and q["peak"] == 3 and q["source"] == "counter"
    e = next(a for a in alerts if a["type"] == "empty_counter")
    assert e["start"] == 1 and e["end"] == 35

    assert rows and rows[0]["minute"] == 0 and rows[0]["in"] == 1
    assert rows[0]["max_queue"] == 3


def test_last_minute_includes_a_crossing_after_the_final_sample():
    src = {"name": "entrance", "line": {"a": [0, 100], "b": [200, 100], "in_direction": [0, 1]}, "zones": {}}
    pipe = StreamPipeline(src, ALERTS, sample_hz=1)
    pipe.process(0.0, [person(1, 50, 70)])          # sampled at step 0 (in_total still 0)
    pipe.process(0.5, [person(1, 50, 130)])         # crosses IN, same step -> not resampled
    fin = pipe.finalize()
    assert pipe.counter.in_count == 1
    assert fin["minute_rows"] and fin["minute_rows"][0]["in"] == 1   # the minute row must include it


def _run_all():
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {e!r}")
            except Exception as e:
                failed += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
