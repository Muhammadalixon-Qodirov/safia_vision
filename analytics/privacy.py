"""Privacy: blur the head region of every detected person before a frame is
written to disk. The case study forbids face recognition and asks for blurred
faces in any published output. Blurring the top part of each person box needs no
face model and never identifies anyone.
"""
from __future__ import annotations

import cv2


def blur_heads(frame, tracks, head_fraction: float = 0.33):
    """frame: BGR image (modified in place and returned). tracks: (tid,x1,y1,x2,y2,conf)."""
    h, w = frame.shape[:2]
    for tk in tracks:
        x1, y1, x2, y2 = tk[1], tk[2], tk[3], tk[4]
        bx1, by1 = max(0, int(x1)), max(0, int(y1))
        bx2 = min(w, int(x2))
        by2 = min(h, int(y1 + (y2 - y1) * head_fraction))
        if bx2 - bx1 < 2 or by2 - by1 < 2:
            continue
        roi = frame[by1:by2, bx1:bx2]
        k = max(11, (min(roi.shape[0], roi.shape[1]) // 2) | 1)   # odd kernel
        frame[by1:by2, bx1:bx2] = cv2.GaussianBlur(roi, (k, k), 0)
    return frame
