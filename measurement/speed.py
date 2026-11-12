"""Speed of the measurement setup: all four clips at once, every frame (config/measure.yaml).
Prints each stream's FPS while all four run, the total, GPU memory (PyTorch peak) and
model sizes. Run with nothing else on the GPU.

    python measurement/speed.py
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import torch  # noqa: E402

from analytics.config import load_config  # noqa: E402
from analytics.service import start_service  # noqa: E402


def main():
    cfg = load_config("config/measure.yaml")
    cfg["output"]["dir"] = "output_speed"
    shutil.rmtree("output_speed", ignore_errors=True)
    from ultralytics import YOLO
    for w in ("yolov8s.pt", "yolov8m.pt"):
        p = Path("models") / w
        n = sum(x.numel() for x in YOLO(str(p)).model.parameters())
        print(f"{w}: {p.stat().st_size / 1e6:.1f} MB, {n / 1e6:.1f} M parameters")
    frames = {}
    for s in cfg["sources"]:
        c = cv2.VideoCapture(s["uri"])
        frames[s["name"]] = (int(c.get(cv2.CAP_PROP_FRAME_COUNT)), int(c.get(3)), int(c.get(4)))
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
        print("GPU:", torch.cuda.get_device_name(0))
    t0 = time.time()
    workers, shared, _stop = start_service(cfg)
    t_start = time.time()
    done_at, fps_all = {}, {}
    while any(w.is_alive() for w in workers):
        time.sleep(2)
        snap = shared.snapshot()
        alive = sum(w.is_alive() for w in workers)
        for w in workers:
            name = w.source["name"]
            if not w.is_alive():
                done_at.setdefault(name, time.time() - t_start)
            elif alive == len(workers) and snap.get(name, {}).get("fps"):
                fps_all.setdefault(name, []).append(snap[name]["fps"])
    wall = time.time() - t_start
    total = sum(n for n, _, _ in frames.values())
    print(f"\nall four started after {t_start - t0:.0f} s of model loading")
    print("| stream | resolution | frames | FPS while all 4 ran (median) | finished after |")
    print("|---|---|---|---|---|")
    for name, (n, w, h) in frames.items():
        v = sorted(fps_all.get(name, [0]))
        print(f"| {name} | {w}x{h} | {n} | {v[len(v) // 2]:.1f} | {done_at.get(name, wall):.0f} s |")
    print(f"\ntotal: {total} frames in {wall:.0f} s = {total / wall:.1f} frames/s")
    if torch.cuda.is_available():
        print(f"PyTorch peak GPU memory: allocated {torch.cuda.max_memory_allocated() / 1e9:.2f} GB, "
              f"reserved {torch.cuda.max_memory_reserved() / 1e9:.2f} GB (4 models in one process)")


if __name__ == "__main__":
    main()
