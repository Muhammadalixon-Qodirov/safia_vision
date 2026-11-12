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


def test_zone_ref_head_counts_people_whose_box_runs_off_the_bottom():
    # over-the-counter camera: a customer's box runs to the bottom edge (y=700), so the
    # feet point is outside the queue zone (y 0-400) but the head point is inside it.
    queue = [[0, 0], [300, 0], [300, 400], [0, 400]]
    tall = (1, 50, 100, 150, 700, 0.9)            # head ~ y 190, feet y 700
    feet_src = {"name": "a", "line": None, "zones": {"queue": {"polygon": queue}}}
    head_src = {"name": "b", "line": None, "zones": {"queue": {"polygon": queue, "ref": "head"}}}
    for src, want in ((feet_src, 0), (head_src, 1)):
        pipe = StreamPipeline(src, ALERTS, sample_hz=1)
        pipe.process(0.0, [tall])
        r = pipe.process(1.0, [tall])
        assert r["sample"]["queue"] == want, (src["name"], r["sample"])


def _zone_counts(zone_cfg, frames, dt=0.5):
    """Feed frames (lists of tracks) every dt seconds; return the per-frame zone count."""
    from analytics.pipeline import _Zone
    z = _Zone(zone_cfg)
    return [z.count(i * dt, tr) for i, tr in enumerate(frames)]


BOX = [[0, 0], [300, 0], [300, 400], [0, 400]]


def test_min_dwell_ignores_a_person_passing_through():
    walker = person(1, 50, 300)
    # in the zone for 1.0 s (3 frames at 0.5 s) then gone: never reaches 2 s
    assert max(_zone_counts({"polygon": BOX, "min_dwell": 2}, [[walker]] * 3 + [[]] * 4)) == 0
    # standing 3 s: counted once the 2 s have passed
    counts = _zone_counts({"polygon": BOX, "min_dwell": 2}, [[walker]] * 7)
    assert counts[:4] == [0, 0, 0, 0] and counts[4:] == [1, 1, 1], counts


def test_hold_keeps_a_briefly_hidden_person_and_then_lets_go():
    p = person(1, 50, 300)
    frames = [[p]] * 4 + [[]] * 4 + [[p]] * 2 + [[]] * 8   # hidden 2 s, back, then left
    counts = _zone_counts({"polygon": BOX, "hold": 3}, frames)
    assert counts[:10] == [1] * 10, counts                # never dropped while hidden 2 s
    assert counts[-1] == 0, counts                        # gone for 4 s > hold -> released


def test_merge_counts_one_person_split_into_two_boxes_once():
    whole = (1, 100, 100, 280, 350, 0.8)
    head = (2, 110, 110, 180, 200, 0.4)                   # a second box inside the first
    other = (3, 10, 250, 60, 350, 0.9)                    # a different person beside them
    assert _zone_counts({"polygon": BOX}, [[whole, head, other]]) == [3]
    assert _zone_counts({"polygon": BOX, "merge": 0.6}, [[whole, head, other]]) == [2]


def test_count_detections_includes_people_too_weak_to_track():
    zone = {"polygon": BOX, "count": "detections", "min_conf": 0.1}
    tracked = (5, 20, 200, 60, 350, 0.8)
    hidden = (-1, 100, 200, 140, 350, 0.15)               # found, but too weak for a track
    noise = (-1, 200, 200, 240, 350, 0.06)                # below min_conf
    from analytics.pipeline import _Zone
    z = _Zone(zone)
    assert z.count(0.0, [tracked], [(-1, *tracked[1:]), hidden, noise]) == 2
    assert _Zone({"polygon": BOX}).count(0.0, [tracked], [hidden]) == 1   # default: tracks
    # without detections given (e.g. a fake detector) it falls back to the tracks
    assert z.count(0.0, [tracked], None) == 1


def test_smooth_ignores_a_short_drop_in_the_count():
    # 6 people in the queue zone every frame, except 1 s of blurred frames with only 2
    src = {"name": "s", "line": None,
           "zones": {"queue": {"polygon": BOX, "smooth": 3}}}
    six = [person(i, 20 + 40 * i, 300) for i in range(6)]
    pipe = StreamPipeline(src, ALERTS, sample_hz=1)
    samples = {}
    for k in range(0, 100):                     # 10 frames per second, 10 s
        t = k / 10
        r = pipe.process(t, six[:2] if 50 <= k < 60 else six)
        if r["sample"]:
            samples[int(t)] = r["sample"]["queue"]
    assert min(samples[s] for s in range(3, 10)) == 6, samples
    # without smoothing the same drop shows up
    src["zones"]["queue"].pop("smooth")
    pipe = StreamPipeline(src, ALERTS, sample_hz=1)
    low = []
    for k in range(0, 100):
        r = pipe.process(k / 10, six[:2] if 50 <= k < 60 else six)
        if r["sample"]:
            low.append(r["sample"]["queue"])
    assert min(low) == 2, low


def test_zone_with_two_polygons_counts_both_together():
    # one camera, two tills: the queue zone is two lanes, counted as one zone
    lane1 = [[0, 0], [100, 0], [100, 400], [0, 400]]
    lane2 = [[200, 0], [300, 0], [300, 400], [200, 400]]
    from analytics.pipeline import _Zone
    z = _Zone({"polygons": [lane1, lane2]})
    people = [person(1, 50, 300), person(2, 250, 300), person(3, 150, 300)]   # 3rd: between lanes
    assert z.count(0.0, people) == 2


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
