"""Download the YOLO weights into models/ (kept out of git). Run once:

    python scripts/download_models.py
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

# Two small detectors so you can compare on YOUR clips. Default is yolov8n
# (fast); step up to a "-s" model if recall on distant/occluded people is low.
# Do not assume a newer name is better - measure on your footage.
MODELS = ["yolov8n.pt", "yolo11n.pt"]


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
