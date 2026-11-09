"""Draw the overlay for the annotated output video: the door line, the zones,
each tracked person with its ID, the live IN/OUT and zone counts, and a banner
for any active alert. Used only for the demo/GIF output, not for the numbers.
"""
from __future__ import annotations

import cv2
import numpy as np

_GREEN = (80, 220, 80)
_BLUE = (230, 160, 60)
_RED = (60, 60, 230)
_YELLOW = (40, 210, 240)
_WHITE = (255, 255, 255)


def _poly(frame, pts, color):
    arr = np.array(pts, dtype=np.int32)
    overlay = frame.copy()
    cv2.fillPoly(overlay, [arr], color)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
    cv2.polylines(frame, [arr], True, color, 2)


def draw(frame, tracks, source, totals):
    # zones
    for name, z in (source.get("zones") or {}).items():
        _poly(frame, z["polygon"], _YELLOW if name == "queue" else _BLUE)
        p0 = z["polygon"][0]
        cv2.putText(frame, name, (int(p0[0]) + 4, int(p0[1]) + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, _WHITE, 2)
    # door line
    line = source.get("line")
    if line:
        a, b = line["a"], line["b"]
        cv2.line(frame, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), _GREEN, 3)
    # people (box + ID). Heads are blurred separately by privacy.blur_heads.
    for tk in tracks:
        x1, y1, x2, y2, tid = int(tk[1]), int(tk[2]), int(tk[3]), int(tk[4]), tk[0]
        cv2.rectangle(frame, (x1, y1), (x2, y2), _GREEN, 2)
        cv2.putText(frame, f"#{tid}", (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, _GREEN, 2)
    # HUD (o'zbekcha)
    _AT = {"queue": "navbat to'lgan", "empty_counter": "bo'sh kassa"}
    lines = [f"{source['name']}  KIRDI {totals['in']}  CHIQDI {totals['out']}"]
    if source.get("zones"):
        lines.append(f"navbat {totals['queue']}   sotuvchi {totals['staff']}")
    y = 30
    for s in lines:
        cv2.putText(frame, s, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, _WHITE, 2)
        y += 32
    for a in totals.get("active_alerts", []):
        cv2.putText(frame, f"ALERT: {_AT.get(a, a)}", (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, _RED, 2)
        y += 34
    return frame
