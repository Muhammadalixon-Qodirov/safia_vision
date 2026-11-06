"""Per-minute CSV rows per source: in, out, average queue, max queue, and
seconds with an empty counter.

Samples are taken at a fixed rate (``sample_hz`` in the config, default 1 Hz),
so ``empty_counter_seconds`` is simply the number of samples in the minute where
the staff zone was empty. ``in``/``out`` are the crossings during the minute,
computed from the running totals.
"""
from __future__ import annotations

FIELDS = ["minute", "in", "out", "avg_queue", "max_queue", "empty_counter_seconds"]


class MinuteAggregator:
    def __init__(self, sample_hz: float = 1.0):
        self.sample_hz = float(sample_hz) or 1.0
        self.rows = []
        self._minute = None
        self._in0 = 0
        self._out0 = 0
        self._q = []
        self._empty = 0
        self._last = (0, 0)

    def sample(self, t: float, in_total: int, out_total: int, queue_count: int, staff_count: int):
        m = int(t // 60)
        if self._minute is None:
            self._minute = m
            self._in0, self._out0 = in_total, out_total
        elif m != self._minute:
            self._flush(in_total, out_total)
            self._minute = m
            self._in0, self._out0 = in_total, out_total
        self._q.append(queue_count)
        if staff_count == 0:
            self._empty += 1
        self._last = (in_total, out_total)

    def _flush(self, in_total: int, out_total: int):
        avgq = sum(self._q) / len(self._q) if self._q else 0.0
        self.rows.append({
            "minute": self._minute,
            "in": in_total - self._in0,
            "out": out_total - self._out0,
            "avg_queue": round(avgq, 2),
            "max_queue": max(self._q) if self._q else 0,
            "empty_counter_seconds": int(round(self._empty / self.sample_hz)),
        })
        self._q = []
        self._empty = 0

    def flush(self):
        if self._minute is not None and self._q:
            self._flush(*self._last)
        return self.rows
