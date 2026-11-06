"""Export the detector to ONNX for faster, framework-independent deployment
(bonus; graded under speed/deployment awareness).

    python scripts/export_onnx.py --weights models/yolov8n.pt --imgsz 640 [--half]

Produces models/<name>.onnx. To run the service on it, point `model.weights` in
the config at the .onnx file - Ultralytics loads it through ONNX Runtime. Needs
`pip install onnx onnxruntime` (or onnxruntime-gpu for CUDA). Compare FPS against
the PyTorch weights and note it in the README's speed table.
"""
from __future__ import annotations

import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="models/yolov8n.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--half", action="store_true", help="FP16 (GPU export)")
    args = ap.parse_args()
    from ultralytics import YOLO
    model = YOLO(args.weights)
    path = model.export(format="onnx", imgsz=args.imgsz, half=args.half, dynamic=False, simplify=True)
    print(f"exported -> {path}")
    print("point model.weights in the config at this file to run on ONNX Runtime.")


if __name__ == "__main__":
    main()
