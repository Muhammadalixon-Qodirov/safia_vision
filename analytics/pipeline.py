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

Optional per-zone rules (all off by default) for crowded or awkward views:
  min_dwell  seconds a person must stay in the zone before counting, so someone
             walking through or briefly stepping in to look at shelves is not queued
  hold       seconds a counted person keeps counting after the detector loses them,
             so a customer hidden behind others for a moment is not dropped
  merge      0-1: boxes in the zone that overlap this much (intersection over the
             smaller box) are one person - e.g. a bending cashier split into a
             head box and a shoulder box, or two boxes on the same person
  count      "tracks" (default) or "detections": count every person box the
             detector found in this frame with conf >= min_conf (default 0.1),
             not only confirmed tracks. For a dense crowd: a hidden person scores
             0.1-0.25, too low for the tracker to start a track, so a track-based
             count misses them. Occupancy needs no IDs, so this is safe for a zone
             count; the door line always uses tracks. (No min_dwell / hold then.)
  smooth     seconds: the zone's per-second value is the median of the per-frame
             counts over this many seconds instead of over one second. A blurred or
             compressed frame can make the count drop from 12 to 3 for a moment, and
             a doubled box can add one; a 3 s median removes both.
"""
from __future__ import annotations

from collections import deque
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


def zone_polygons(z: dict) -> list:
    """A zone's polygons: `polygons` (a list of polygons) or the single `polygon`."""
    return list(z["polygons"]) if z.get("polygons") else [z["polygon"]]


def _inter_over_smaller(a, b):
    iw = min(a[3], b[3]) - max(a[1], b[1])
    ih = min(a[4], b[4]) - max(a[2], b[2])
    if iw <= 0 or ih <= 0:
        return 0.0
    small = min((a[3] - a[1]) * (a[4] - a[2]), (b[3] - b[1]) * (b[4] - b[2]))
    return iw * ih / small if small > 0 else 0.0


def _merge_boxes(tracks, thr):
    """Keep the largest box of each group of boxes overlapping >= thr."""
    kept = []
    for tk in sorted(tracks, key=lambda k: -(k[3] - k[1]) * (k[4] - k[2])):
        if all(_inter_over_smaller(tk, k) < thr for k in kept):
            kept.append(tk)
    return kept


class _Zone:
    """Per-frame head count of one zone, with the optional dwell / hold / merge rules."""

    def __init__(self, cfg: dict):
        # one polygon, or several (`polygons`) counted together as one zone - e.g. the
        # queue lanes of two tills seen by one camera
        self.polys = zone_polygons(cfg)
        self.ref = cfg.get("ref", "feet")
        self.min_dwell = float(cfg.get("min_dwell", 0) or 0)
        self.hold = float(cfg.get("hold", 0) or 0)
        self.merge = cfg.get("merge")
        self.use_detections = cfg.get("count", "tracks") == "detections"
        self.min_conf = float(cfg.get("min_conf", 0.1))
        self.smooth = float(cfg.get("smooth", 0) or 0)
        self.history = deque()             # (t, per-frame count) over the last `smooth` s
        self._first, self._last = {}, {}   # track id -> start of current stay, last seen inside
        self._box = {}                     # track id -> its last box inside the zone

    def _inside(self, box) -> bool:
        p = _point(box, self.ref)
        return any(point_in_polygon(p, poly) for poly in self.polys)

    def count(self, t: float, tracks: list, detections: list | None = None) -> int:
        if self.use_detections and detections is not None:
            boxes = [d for d in detections if d[5] >= self.min_conf]
            inside = [d for d in boxes if self._inside(d)]
            if self.merge:
                inside = _merge_boxes(inside, float(self.merge))
            return len(inside)
        inside = [tk for tk in tracks if self._inside(tk)]
        if self.merge:
            inside = _merge_boxes(inside, float(self.merge))
        if not self.min_dwell and not self.hold:
            return len(inside)
        gap = self.hold + 0.5                    # a longer absence starts a new stay
        for tk in inside:
            tid = tk[0]
            if tid not in self._last or t - self._last[tid] > gap:
                self._first[tid] = t
            self._last[tid] = t
            self._box[tid] = tk
        for tid in [k for k, v in self._last.items() if t - v > gap]:
            del self._last[tid], self._first[tid], self._box[tid]

        def dwelt(tid):
            return self._last[tid] - self._first[tid] >= self.min_dwell

        seen_now = [tk for tk in inside if dwelt(tk[0])]
        n = len(seen_now)
        visible_ids = {tk[0] for tk in tracks}
        for tid, last in self._last.items():
            if last == t or t - last > self.hold or not dwelt(tid):
                continue
            # a held (currently unseen) person counts only if really unseen:
            if tid in visible_ids:               # seen outside the zone -> they left it
                continue
            # the tracker often gives a person who reappears a NEW id; if a counted
            # box now stands where this one was last seen, it is the same person
            if any(_inter_over_smaller(self._box[tid], tk) >= 0.5 for tk in seen_now):
                continue
            n += 1
        return n

    def reset(self):
        self._first, self._last, self._box = {}, {}, {}
        self.history.clear()


class StreamPipeline:
    def __init__(self, source: dict, alerts_cfg: dict, sample_hz: float = 1.0):
        self.name = source["name"]
        line = source.get("line")
        self.counter = None
        if line:
            self.counter = LineCounter(line["a"], line["b"], line.get("in_direction"),
                                       margin=line.get("margin", 4.0), commit=line.get("commit"))
        zones = source.get("zones") or {}
        self.has_queue = "queue" in zones
        self.has_staff = "staff" in zones
        self.zones = {k: _Zone(v) for k, v in zones.items()} or None
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

    def process(self, t: float, tracks: list, detections: list | None = None) -> dict:
        """Feed one frame's tracks at video time t (seconds). Returns what changed:
        crossings, finished alert episodes, and any completed minute rows.
        `detections` (optional): all person boxes of the frame, for zones that use
        count: detections."""
        crossings = []
        if self.counter is not None:
            crossings = self.counter.update([(tk[0], *_ref(tk)) for tk in tracks])

        finished_alerts, new_rows, sample = [], [], None
        # count the zones on every frame; the per-second value is the median of the
        # frames in that second, so one frame where a person is hidden does not count
        if self.zones:
            for k, zone in self.zones.items():
                n = zone.count(t, tracks, detections)
                self._frame_occ.setdefault(k, []).append(n)
                if zone.smooth:
                    h = zone.history
                    h.append((t, n))
                    while h and h[0][0] <= t - zone.smooth:
                        h.popleft()
        step = int(t * self.sample_hz)
        if step != self._last_step:                 # take a sample on the configured cadence
            self._last_step = step
            occ = {}
            for k, v in self._frame_occ.items():
                zone = self.zones[k]
                if zone.smooth and zone.history:    # median over the last `smooth` seconds
                    occ[k] = int(median_low([n for _, n in zone.history]))
                elif v:
                    occ[k] = int(median_low(v))
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
        for zone in (self.zones or {}).values():
            zone.reset()

    def set_thresholds(self, **kw):
        """Change alert thresholds live. No-op if this source has no zones."""
        if self.alerts is not None:
            self.alerts.set_thresholds(**kw)
