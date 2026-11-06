"""Pure geometry: which side of a line a point is on, segment intersection,
and point-in-polygon. No heavy dependencies, so it is unit-tested without a GPU.

All coordinates are (x, y) in pixels.
"""
from __future__ import annotations

Point = tuple[float, float]


def _cross(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    """Cross product (b-a) x (p-a). Sign = which side of line a->b point p is on."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def side(p: Point, a: Point, b: Point) -> float:
    """> 0, 0, or < 0 depending on which side of the directed line a->b p lies."""
    return _cross(a[0], a[1], b[0], b[1], p[0], p[1])


def _orient(a: Point, b: Point, c: Point) -> int:
    v = _cross(a[0], a[1], b[0], b[1], c[0], c[1])
    return 0 if v == 0 else (1 if v > 0 else -1)


def _on_seg(a: Point, b: Point, c: Point) -> bool:
    """c is colinear with a-b; is it inside the segment's bounding box?"""
    return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])


def segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """Do segment p1-p2 and segment p3-p4 cross (including touching)?"""
    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    if d1 != d2 and d3 != d4:
        return True
    if d1 == 0 and _on_seg(p3, p4, p1):
        return True
    if d2 == 0 and _on_seg(p3, p4, p2):
        return True
    if d3 == 0 and _on_seg(p1, p2, p3):
        return True
    if d4 == 0 and _on_seg(p1, p2, p4):
        return True
    return False


def point_in_polygon(p: Point, poly: list[Point]) -> bool:
    """Ray casting. poly is a list of (x, y); the polygon is implicitly closed."""
    x, y = p
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside
