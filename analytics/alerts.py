"""Queue and empty-counter alerts, driven by video time (seconds), not wall clock.

Each alert fires once per episode (no on/off flicker) and records its start, end
and peak. Definitions:

- queue alert: at least N people in the queue zone for at least T seconds.
- empty-counter alert: nobody in the staff zone for at least T seconds while at
  least one person waits in the queue zone.

start = the moment the condition first became true in that episode (the queue
reached N / the counter went empty with someone waiting); the alert is only
*emitted* once the condition has held for T seconds, but its recorded start is
when the situation began. end = the last moment the condition held. An episode
ends only after the condition has been false for ``grace`` seconds, so a brief
dip does not split one episode into two. peak = the largest number of people
waiting in the queue during the episode.
"""
from __future__ import annotations


class _Alert:
    def __init__(self, atype: str, min_seconds: float, grace: float):
        self.atype = atype
        self.min_seconds = float(min_seconds)
        self.grace = float(grace)
        self.active = False
        self._since = None       # condition continuously true since this time (pre-emit)
        self._last_true = None   # last time the condition held
        self._false_since = None
        self.start = None
        self.peak = 0.0

    def update(self, t: float, cond: bool, metric: float):
        """A dip shorter than ``grace`` never resets anything: not the running
        T-second timer before the alert starts, and not an open episode. People
        hidden behind each other for a second are a detector gap, not the queue
        disappearing."""
        finished = None
        if cond:
            self._false_since = None
            if self._since is None:
                self._since = t
                self.peak = metric
            self._last_true = t
            self.peak = max(self.peak, metric)
            if not self.active and (t - self._since) >= self.min_seconds:
                self.active = True
                self.start = self._since
        elif self._since is not None:            # the condition was building or active
            if self._false_since is None:
                self._false_since = t
            if (t - self._false_since) >= self.grace:
                if self.active:
                    finished = self._record()
                self._reset()
        return finished

    def _record(self):
        return {"type": self.atype, "start": round(self.start, 2),
                "end": round(self._last_true, 2),
                "duration": round(self._last_true - self.start, 2),
                "peak": self.peak}

    def _reset(self):
        self.active = False
        self._since = None
        self._last_true = None
        self._false_since = None
        self.start = None
        self.peak = 0.0


class AlertManager:
    def __init__(self, source: str, queue_cfg: dict, empty_cfg: dict, grace: float = 2.0):
        self.source = source
        self.queue_n = int(queue_cfg["min_people"])
        self.q = _Alert("queue", queue_cfg["min_seconds"], grace)
        self.e = _Alert("empty_counter", empty_cfg["min_seconds"], grace)
        self.finished = []

    def update(self, t: float, queue_count: int, staff_count: int):
        """Returns the list of alert episodes that ended on this sample."""
        out = []
        f = self.q.update(t, queue_count >= self.queue_n, queue_count)
        if f:
            out.append({**f, "source": self.source})
        f = self.e.update(t, staff_count == 0 and queue_count >= 1, queue_count)
        if f:
            out.append({**f, "source": self.source})
        self.finished.extend(out)
        return out

    def flush(self):
        """Close any still-active alerts (end of stream)."""
        out = []
        for a in (self.q, self.e):
            if a.active:
                out.append({**a._record(), "source": self.source})
                a._reset()
        self.finished.extend(out)
        return out

    def active_alerts(self):
        return [a.atype for a in (self.q, self.e) if a.active]

    def set_thresholds(self, queue_n=None, queue_seconds=None, empty_seconds=None, grace=None):
        """Change alert thresholds live (from the web controls). None = leave as is."""
        if queue_n is not None:
            self.queue_n = max(1, int(queue_n))
        if queue_seconds is not None:
            self.q.min_seconds = max(0.0, float(queue_seconds))
        if empty_seconds is not None:
            self.e.min_seconds = max(0.0, float(empty_seconds))
        if grace is not None:
            self.q.grace = self.e.grace = max(0.0, float(grace))

    def reset(self):
        """Clear alert state (used by the live 'reset' control). Thresholds are kept."""
        self.q._reset()
        self.e._reset()
        self.finished = []
