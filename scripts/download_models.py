"""Download the YOLO weights into models/ (kept out of git). Run once:

    python scripts/download_models.py
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

# Small detectors to compare on YOUR clips. yolov8n is the fast default for the
# demo configs; config/shop.yaml uses yolov8s because on that CCTV clip it found
# distant/occluded people (kids, people behind displays) much more steadily.
# Do not assume a newer name is better - measure on your footage.
MODELS = ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolo11n.pt", "yolo11s.pt"]


def main():
    Path("models").mkdir(exist_ok=True)
    from ultralytics import YOLO
    for name in MODELS:
        dst = Path("models") / name
        if dst.exists():
            print(f"have {dst}")
            continue
        print(f"downloading {name} ...")
        YOLO(name)                      # ultralytics fetches to the current dir
        if os.path.exists(name):
            shutil.move(name, dst)
        print(f"-> {dst}")


if __name__ == "__main__":
    main()
