"""Door line counting: IN and OUT, once per genuine crossing.

Uses hysteresis around the line. For each track we remember the last side it was
*clearly* on (perpendicular distance greater than ``margin`` pixels). A crossing
is counted only when the track moves clearly to the other side. So jitter at the
line, a person who stops on the line, turns back before crossing, or walks along
it, is never counted, and one crossing is never counted twice. A genuine
cross-and-return is counted as one IN and one OUT.

Direction (IN vs OUT) is fixed by ``in_direction``: the movement vector that
should count as entering. It is compared once to the line's normal, so the
decision is stable and does not depend on the exact per-frame step.
"""
from __future__ import annotations

from math import hypot

from .geometry import side


class LineCounter:
    def __init__(self, a, b, in_direction=None, margin=4.0, ttl=30):
        self.a = (float(a[0]), float(a[1]))
        self.b = (float(b[0]), float(b[1]))
        self._len = hypot(self.b[0] - self.a[0], self.b[1] - self.a[1]) or 1.0
        # left-hand normal of a->b; `side()` grows in this direction.
        normal = (-(self.b[1] - self.a[1]), (self.b[0] - self.a[0]))
        if in_direction is None:
            in_direction = normal
        dot = in_direction[0] * normal[0] + in_direction[1] * normal[1]
        # +1 if entering means moving to the positive-distance side, else -1.
        self._in_sign = 1 if dot > 0 else -1
        self.margin = float(margin)
        self.ttl = int(ttl)
        self.in_count = 0
        self.out_count = 0
        self._frame = 0
        self._side: dict[int, int] = {}     # tid -> last clearly-committed side (+1/-1)
        self._seen: dict[int, int] = {}     # tid -> last frame seen

    def reset_counts(self):
        """Zero the counts and the per-track memory (used by the live 'reset' control)."""
        self.in_count = 0
        self.out_count = 0
        self._frame = 0
        self._side.clear()
        self._seen.clear()

    def update(self, detections):
        """detections: iterable of (track_id, x, y). Returns [(track_id, 'in'|'out'), ...]."""
        self._frame += 1
        events = []
        for tid, x, y in detections:
            d = side((float(x), float(y)), self.a, self.b) / self._len   # signed px distance
            if abs(d) > self.margin:
                sgn = 1 if d > 0 else -1
                prev = self._side.get(tid)
                if prev is None:
                    self._side[tid] = sgn
                elif sgn != prev:
                    if sgn == self._in_sign:
                        self.in_count += 1
                        events.append((tid, "in"))
                    else:
                        self.out_count += 1
                        events.append((tid, "out"))
                    self._side[tid] = sgn
            self._seen[tid] = self._frame
        for tid, f in list(self._seen.items()):      # forget tracks gone for a while
            if self._frame - f > self.ttl:
                self._seen.pop(tid, None)
                self._side.pop(tid, None)
        return events
