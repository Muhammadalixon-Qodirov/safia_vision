"""Door line counting: IN and OUT, once per genuine crossing.

Uses hysteresis around the line. For each track we remember the last side it was
*clearly* on (perpendicular distance greater than ``margin`` pixels). A crossing
is counted only when the track moves clearly to the other side. So jitter at the
line, a person who stops on the line, turns back before crossing, or walks along
it, is never counted, and one crossing is never counted twice. A genuine
cross-and-return is counted as one IN and one OUT.

``commit`` (>= margin, default = margin, i.e. off) handles a person who walks onto
the threshold and STANDS there: while standing, the feet point can drift a little
past the band (shop1 @ 1:32 ended 6-22 px past the line and stayed there for 6 s).
With ``commit`` set, reaching the other side only makes the crossing *pending*; it
is counted when the person is clearly through - at least ``commit`` px past the
line - or walks away from the door (leaves the line segment) or disappears from
view for ``lost_frames`` frames, as people who walk in do. A pending crossing whose
track comes back to its first side is cancelled (turned back on the threshold), and
one that just stands on the line is never counted. A distance alone cannot do this:
on shop1 people who walked in got only ~22 px past the line before leaving the door
area, the same as the woman who stood on it - what differs is that they left.

Direction (IN vs OUT) is fixed by ``in_direction``: the movement vector that
should count as entering. It is compared once to the line's normal, so the
decision is stable and does not depend on the exact per-frame step.
"""
from __future__ import annotations

from math import hypot

from .geometry import side


class LineCounter:
    def __init__(self, a, b, in_direction=None, margin=4.0, ttl=30, commit=None, lost_frames=4):
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
        self.commit = max(float(commit), self.margin) if commit is not None else self.margin
        self.lost_frames = int(lost_frames)
        self.ttl = int(ttl)
        self.in_count = 0
        self.out_count = 0
        self._frame = 0
        self._side: dict[int, int] = {}     # tid -> last clearly-committed side (+1/-1)
        self._seen: dict[int, int] = {}     # tid -> last frame seen
        self._pending: dict[int, int] = {}  # tid -> side it is crossing to, not yet confirmed

    def reset_counts(self):
        """Zero the counts and the per-track memory (used by the live 'reset' control)."""
        self.in_count = 0
        self.out_count = 0
        self._frame = 0
        self._side.clear()
        self._seen.clear()
        self._pending.clear()

    def _count(self, tid, sgn, events):
        if sgn == self._in_sign:
            self.in_count += 1
            events.append((tid, "in"))
        else:
            self.out_count += 1
            events.append((tid, "out"))
        self._side[tid] = sgn
        self._pending.pop(tid, None)

    def update(self, detections):
        """detections: iterable of (track_id, x, y). Returns [(track_id, 'in'|'out'), ...]."""
        self._frame += 1
        events = []
        ax, ay = self.a
        dx, dy = self.b[0] - ax, self.b[1] - ay
        tol = self.margin / self._len                  # allow a margin's worth past each end
        for tid, x, y in detections:
            # Only the segment a-b is the door. A person beside its ends (past a or b) is
            # not at the door: forget their side, so walking around an end never counts.
            # A pending crossing is confirmed here: they went through and walked away.
            t = ((float(x) - ax) * dx + (float(y) - ay) * dy) / (self._len * self._len)
            if t < -tol or t > 1.0 + tol:
                if tid in self._pending:
                    self._count(tid, self._pending[tid], events)
                self._side.pop(tid, None)
                self._seen[tid] = self._frame
                continue
            d = side((float(x), float(y)), self.a, self.b) / self._len   # signed px distance
            if abs(d) > self.margin:
                sgn = 1 if d > 0 else -1
                prev = self._side.get(tid)
                if prev is None:
                    self._side[tid] = sgn
                elif sgn != prev:
                    if abs(d) >= self.commit:          # clearly through
                        self._count(tid, sgn, events)
                    else:                              # on the far edge of the threshold
                        self._pending[tid] = sgn
                else:                                  # back on its first side: turned back
                    self._pending.pop(tid, None)
            self._seen[tid] = self._frame
        for tid, sgn in list(self._pending.items()):   # walked through and out of view
            if self._frame - self._seen.get(tid, self._frame) > self.lost_frames:
                self._count(tid, sgn, events)
        for tid, f in list(self._seen.items()):      # forget tracks gone for a while
            if self._frame - f > self.ttl:
                self._seen.pop(tid, None)
                self._side.pop(tid, None)
                self._pending.pop(tid, None)
        return events
