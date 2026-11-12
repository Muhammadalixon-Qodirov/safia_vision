"""Per-source pipeline: turn a stream of tracked boxes into counts, zone
occupancy, alerts and per-minute rows. This is the orchestration logic, kept
free of OpenCV and the GPU so it is unit-tested with synthetic tracks.

A track is (track_id, x1, y1, x2, y2, conf). The reference point of a person is
the bottom-centre of the box (the feet), used for line crossing and, by default,
for zone membership. Each zone may choose another point with `ref`:
  feet   (default) bottom-centre: right for overhead / high cameras
  head   near the top of the box: right when the camera looks over a counter and
         customers' legs are hidden or their boxes run off the bottom of the frame
  center box centre
"""
from __future__ import annotations

from statistics import median_low

from .counter import LineCounter
from .geometry import point_in_polygon
from .alerts import AlertManager
from .aggregator import MinuteAggregator

REF_POINTS = ("feet", "head", "center")


def _ref(track):
    _tid, x1, _y1, x2, y2 = track[0], track[1], track[2], track[3], track[4]
    return ((x1 + x2) / 2.0, y2)


def _point(track, ref="feet"):
    x1, y1, x2, y2 = track[1], track[2], track[3], track[4]
    cx = (x1 + x2) / 2.0
    if ref == "head":
        return (cx, y1 + 0.15 * (y2 - y1))
    if ref == "center":
        return (cx, (y1 + y2) / 2.0)
    return (cx, y2)


class StreamPipeline:
    def __init__(self, source: dict, alerts_cfg: dict, sample_hz: float = 1.0):
        self.name = source["name"]
        line = source.get("line")
        self.counter = None
        if line:
            self.counter = LineCounter(line["a"], line["b"], line.get("in_direction"),
                                       margin=line.get("margin", 4.0))
        zones = source.get("zones") or {}
        self.has_queue = "queue" in zones
        self.has_staff = "staff" in zones
        # zone name -> (polygon, which point of the box decides membership)
        self.zones = {k: (v["polygon"], v.get("ref", "feet")) for k, v in zones.items()} or None
        self.alerts = None
        if zones:
            self.alerts = AlertManager(self.name, alerts_cfg["queue"], alerts_cfg["empty_counter"],
                                       grace=alerts_cfg.get("grace_seconds", 2.0))
        self.sample_hz = float(sample_hz)
        self.agg = MinuteAggregator(self.sample_hz)
        self._last_step = -1
        self._rows_written = 0
        self.last_occ = {}
        self._frame_occ = {}          # zone -> per-frame counts since the last sample

    def process(self, t: float, tracks: list) -> dict:
        """Feed one frame's tracks at video time t (seconds). Returns what changed:
        crossings, finished alert episodes, and any completed minute rows."""
        crossings = []
        if self.counter is not None:
            crossings = self.counter.update([(tk[0], *_ref(tk)) for tk in tracks])

        finished_alerts, new_rows, sample = [], [], None
        # count the zones on every frame; the per-second value is the median of the
        # frames in that second, so one frame where a person is hidden does not count
        if self.zones:
            for k, (poly, ref) in self.zones.items():
                n = sum(1 for tk in tracks if point_in_polygon(_point(tk, ref), poly))
                self._frame_occ.setdefault(k, []).append(n)
        step = int(t * self.sample_hz)
        if step != self._last_step:                 # take a sample on the configured cadence
            self._last_step = step
            occ = {k: int(median_low(v)) for k, v in self._frame_occ.items() if v}
            self._frame_occ = {}
            self.last_occ = occ
            queue = occ.get("queue", 0)
            staff = occ.get("staff", -1)             # -1 = no staff zone -> never "empty"
            if self.alerts is not None:
                finished_alerts = self.alerts.update(t, queue, staff)
            sample = {"t": round(t, 2),
                      "queue": queue if self.has_queue else "",
                      "staff": staff if self.has_staff else "",
                      "in": self.counter.in_count if self.counter else 0,
                      "out": self.counter.out_count if self.counter else 0}
            self.agg.sample(
                t,
                in_total=self.counter.in_count if self.counter else 0,
                out_total=self.counter.out_count if self.counter else 0,
                queue_count=queue if self.has_queue else 0,
                staff_count=staff if self.has_staff else 1,   # 1 = never counts as empty
            )
            if len(self.agg.rows) > self._rows_written:
                new_rows = self.agg.rows[self._rows_written:]
                self._rows_written = len(self.agg.rows)
        return {"crossings": crossings, "alerts": finished_alerts, "minute_rows": new_rows,
                "sample": sample, "occ": self.last_occ}

    def finalize(self) -> dict:
        """Close the stream: flush the last minute and any still-open alerts."""
        alerts = self.alerts.flush() if self.alerts is not None else []
        if self.counter is not None:             # include crossings after the last 1 Hz sample
            self.agg._last = (self.counter.in_count, self.counter.out_count)
        self.agg.flush()
        rows = self.agg.rows[self._rows_written:]
        self._rows_written = len(self.agg.rows)
        return {"alerts": alerts, "minute_rows": rows}

    def totals(self) -> dict:
        return {
            "in": self.counter.in_count if self.counter else 0,
            "out": self.counter.out_count if self.counter else 0,
            "queue": self.last_occ.get("queue", 0),
            "staff": self.last_occ.get("staff", 0),
            "active_alerts": self.alerts.active_alerts() if self.alerts else [],
        }

    def reset(self):
        """Zero the counts, zone occupancy, alerts and per-minute rows (live 'reset')."""
        if self.counter is not None:
            self.counter.reset_counts()
        if self.alerts is not None:
            self.alerts.reset()
        self.agg = MinuteAggregator(self.sample_hz)
        self._last_step = -1
        self._rows_written = 0
        self.last_occ = {}
        self._frame_occ = {}

    def set_thresholds(self, **kw):
        """Change alert thresholds live. No-op if this source has no zones."""
        if self.alerts is not None:
            self.alerts.set_thresholds(**kw)
