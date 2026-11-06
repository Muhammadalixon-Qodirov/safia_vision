"""Occupancy of named polygon zones (queue, staff/counter, ...).

A person counts toward a zone when their reference point is inside the polygon.
The reference point is the bottom-centre of the box (the feet), which is where a
standing person meets the floor the polygon is drawn on.
"""
from __future__ import annotations

from .geometry import point_in_polygon


class ZoneOccupancy:
    def __init__(self, zones):
        # zones: {name: [[x, y], ...]}
        self.zones = {name: [(float(px), float(py)) for px, py in poly] for name, poly in zones.items()}

    def count(self, points):
        """points: iterable of (x, y) reference points. Returns {zone_name: count}."""
        pts = [(float(x), float(y)) for x, y in points]
        out = {}
        for name, poly in self.zones.items():
            out[name] = sum(1 for p in pts if point_in_polygon(p, poly))
        return out
