"""Grab one frame from a source and save it, and print the resolution, so you can
read pixel coordinates for the door line and the zones in config.yaml.

    python scripts/show_frame.py videos/counter.mp4 --at 2 --out counter_frame.jpg

Open the saved image in any viewer; most show the cursor's (x, y). Put those
numbers into the line a/b and the zone polygons.
"""
from __future__ import annotations

import argparse

import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uri")
    ap.add_argument("--at", type=float, default=1.0, help="seconds into the clip")
    ap.add_argument("--out", default="frame.jpg")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.uri)
    if not cap.isOpened():
        print(f"could not open {args.uri}")
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(args.at * fps))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print("could not read a frame")
        return
    cv2.imwrite(args.out, frame)
    h, w = frame.shape[:2]
    print(f"saved {args.out}   resolution {w}x{h}   (fps ~{fps:.0f})")


if __name__ == "__main__":
    main()
