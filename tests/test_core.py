"""Unit tests for the pure-Python core logic. Run without a GPU or torch:

    python tests/test_core.py        # plain runner, prints PASS/FAIL
    pytest tests/test_core.py        # also works if pytest is installed
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.geometry import point_in_polygon, segments_intersect, side
from analytics.counter import LineCounter
from analytics.zones import ZoneOccupancy
from analytics.alerts import AlertManager
from analytics.aggregator import MinuteAggregator


# ----------------------------------------------------------------- geometry
def test_side_and_intersection():
    a, b = (0, 100), (200, 100)
    assert side((50, 120), a, b) > 0        # below a horizontal left-to-right line
    assert side((50, 80), a, b) < 0         # above
    assert segments_intersect((50, 80), (50, 120), a, b)       # vertical move crosses
    assert not segments_intersect((50, 80), (50, 90), a, b)    # stays above


def test_point_in_polygon():
    sq = [(0, 0), (100, 0), (100, 100), (0, 100)]
    assert point_in_polygon((50, 50), sq)
    assert not point_in_polygon((150, 50), sq)
    assert not point_in_polygon((-1, -1), sq)


# ----------------------------------------------------------------- line counting
def _run(counter, track):
    """Feed one track's positions, one per frame."""
    for x, y in track:
        counter.update([(1, x, y)])


def test_counts_in_once_going_down():
    c = LineCounter((0, 100), (200, 100), in_direction=(0, 1))
    _run(c, [(50, 70), (50, 85), (50, 115), (50, 130)])
    assert (c.in_count, c.out_count) == (1, 0)


def test_counts_out_going_up():
    c = LineCounter((0, 100), (200, 100), in_direction=(0, 1))
    _run(c, [(50, 130), (50, 115), (50, 85), (50, 70)])
    assert (c.in_count, c.out_count) == (0, 1)


def test_stopping_on_the_line_is_not_counted():
    c = LineCounter((0, 100), (200, 100), in_direction=(0, 1))
    _run(c, [(50, 98), (50, 100), (50, 101), (50, 99), (50, 100), (50, 98)])
    assert (c.in_count, c.out_count) == (0, 0)


def test_walking_along_the_line_is_not_counted():
    c = LineCounter((0, 100), (200, 100), in_direction=(0, 1))
    _run(c, [(10, 100), (60, 100), (120, 100), (190, 100)])
    assert (c.in_count, c.out_count) == (0, 0)


def test_turn_back_counts_one_in_and_one_out():
    c = LineCounter((0, 100), (200, 100), in_direction=(0, 1))
    _run(c, [(50, 70), (50, 130),                 # in
             (50, 131), (50, 132),                 # lingering past the line
             (50, 129), (50, 70)])                 # back out
    assert (c.in_count, c.out_count) == (1, 1)


def test_crossing_beside_the_end_of_the_line_is_not_counted():
    # the door is only the segment x in [0, 200]; crossing y=100 at x=260 is not the door
    c = LineCounter((0, 100), (200, 100), in_direction=(0, 1))
    _run(c, [(260, 70), (260, 85), (260, 115), (260, 130)])
    assert (c.in_count, c.out_count) == (0, 0)


def test_walking_around_the_end_is_not_counted():
    # starts above the door, walks round its right end, ends below it: not a crossing
    c = LineCounter((0, 100), (200, 100), in_direction=(0, 1))
    _run(c, [(150, 70), (190, 70), (260, 70), (260, 130), (190, 130), (150, 130)])
    assert (c.in_count, c.out_count) == (0, 0)


def test_two_people_counted_separately():
    c = LineCounter((0, 100), (200, 100), in_direction=(0, 1))
    c.update([(1, 50, 70), (2, 150, 130)])
    c.update([(1, 50, 130), (2, 150, 70)])
    assert (c.in_count, c.out_count) == (1, 1)


# ----------------------------------------------------------------- zones
def test_zone_occupancy():
    z = ZoneOccupancy({"queue": [[0, 0], [100, 0], [100, 100], [0, 100]]})
    assert z.count([(50, 50), (150, 150), (10, 90)]) == {"queue": 2}


# ----------------------------------------------------------------- alerts
def test_queue_alert_fires_after_T_and_records_peak():
    m = AlertManager("counter", {"min_people": 3, "min_seconds": 10}, {"min_seconds": 15}, grace=2)
    done = []
    for t in range(0, 40):
        qc = (5 if t == 20 else 3) if 5 <= t <= 29 else 0
        done += m.update(t, queue_count=qc, staff_count=2)
    assert len(done) == 1
    a = done[0]
    assert a["type"] == "queue" and a["source"] == "counter"
    assert a["start"] == 5 and a["end"] == 29 and a["peak"] == 5


def test_brief_dip_does_not_split_the_episode():
    m = AlertManager("counter", {"min_people": 3, "min_seconds": 5}, {"min_seconds": 15}, grace=2)
    done = []
    for t in range(0, 30):
        qc = 0 if t == 21 else (3 if 2 <= t <= 25 else 0)   # 1-second dip, below grace
        done += m.update(t, queue_count=qc, staff_count=2)
    assert len(done) == 1 and done[0]["start"] == 2 and done[0]["end"] == 25


def test_brief_dip_before_T_does_not_restart_the_timer():
    # queue >= 3 from t=0..14 except a 1 s detector gap at t=6: still one alert from t=0
    m = AlertManager("counter", {"min_people": 3, "min_seconds": 10}, {"min_seconds": 15}, grace=2)
    done = []
    for t in range(0, 25):
        qc = 2 if t == 6 else (3 if t <= 14 else 0)
        done += m.update(t, queue_count=qc, staff_count=2)
    assert len(done) == 1 and done[0]["start"] == 0 and done[0]["end"] == 14


def test_long_dip_before_T_does_restart_the_timer():
    # a 3 s gap (> grace) really breaks the queue: neither 6 s run reaches T=10
    m = AlertManager("counter", {"min_people": 3, "min_seconds": 10}, {"min_seconds": 15}, grace=2)
    done = []
    for t in range(0, 25):
        qc = 3 if (t <= 5 or 9 <= t <= 14) else 0
        done += m.update(t, queue_count=qc, staff_count=2)
    done += m.flush()
    assert done == []


def test_empty_counter_needs_a_waiting_person():
    m = AlertManager("counter", {"min_people": 3, "min_seconds": 10}, {"min_seconds": 15}, grace=2)
    done = []
    for t in range(0, 30):
        done += m.update(t, queue_count=0, staff_count=0)   # empty but nobody waiting
    done += m.flush()
    assert done == []

    m = AlertManager("counter", {"min_people": 3, "min_seconds": 10}, {"min_seconds": 15}, grace=2)
    done = []
    for t in range(0, 40):
        staff = 0 if t <= 30 else 2
        done += m.update(t, queue_count=2, staff_count=staff)
    assert len(done) == 1 and done[0]["type"] == "empty_counter" and done[0]["start"] == 0


# ----------------------------------------------------------------- aggregator
def test_minute_rows():
    agg = MinuteAggregator()
    for t in range(0, 60):
        in_total = (1 if t >= 10 else 0) + (1 if t >= 40 else 0)
        queue = 4 if 20 <= t < 30 else 1
        staff = 0 if t < 15 else 1
        agg.sample(t, in_total=in_total, out_total=0, queue_count=queue, staff_count=staff)
    agg.sample(60, in_total=2, out_total=0, queue_count=1, staff_count=1)   # triggers minute-0 flush
    rows = agg.flush()
    r0 = rows[0]
    assert r0["minute"] == 0 and r0["in"] == 2 and r0["out"] == 0
    assert r0["avg_queue"] == 1.5 and r0["max_queue"] == 4
    assert r0["empty_counter_seconds"] == 15


# ----------------------------------------------------------------- runner
if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e!r}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
