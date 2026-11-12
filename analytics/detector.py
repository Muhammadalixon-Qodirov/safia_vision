"""Person detection + tracking via Ultralytics YOLO with its built-in ByteTrack.

Each stream gets its OWN detector instance, because ByteTrack keeps per-stream
track state inside the model; sharing one model across streams would mix their
IDs. For ~2 streams of a nano model this costs little VRAM. Scaling to many
cameras with one shared, batched model is discussed in the README.

Isolated here so the rest of the code (and the tests) need neither torch nor a
GPU. `FakeDetector` returns scripted tracks for tests.
"""
from __future__ import annotations


class YoloDetector:
    """`conf` is the floor for boxes handed to the tracker, NOT the track threshold.
    ByteTrack keeps a partly hidden person alive by matching LOW-score boxes
    (track_low_thresh 0.1) to existing tracks, and only starts a new track at
    new_track_thresh (0.25). A detector conf of 0.3 throws those low boxes away before
    the tracker sees them, so occluded/distant people blink in and out. Keep ~0.1."""

    def __init__(self, weights, device=0, imgsz=640, conf=0.1, half=True,
                 tracker="bytetrack.yaml"):
        from ultralytics import YOLO
        self.model = YOLO(weights)
        self.device = device
        self.kw = dict(
            device=device, imgsz=imgsz, conf=conf,
            half=bool(half) and device != "cpu",
            classes=[0],            # person only
            tracker=tracker, persist=True, verbose=False,
        )
        # Every person box the model found in the last frame, BEFORE the tracker
        # filters them, as (-1, x1, y1, x2, y2, conf). A hidden person in a crowd often
        # scores 0.1-0.25: too low for ByteTrack to start a track, but a real person.
        # Zones that only need "how many people now" (no IDs) can count these.
        # The callback is added before the tracker's own (registered on the first
        # track() call), so it sees the detections before they are replaced by tracks.
        self.last_detections = []
        self.model.add_callback("on_predict_postprocess_end", self._keep_detections)

    def _keep_detections(self, predictor):
        try:
            b = predictor.results[0].boxes
            self.last_detections = [(-1, *map(float, xyxy), float(c))
                                    for xyxy, c in zip(b.xyxy.tolist(), b.conf.tolist())]
        except Exception:                       # noqa: BLE001 - never break tracking
            self.last_detections = []

    def track(self, frame):
        """Returns [(track_id, x1, y1, x2, y2, conf), ...] for people in the frame."""
        r = self.model.track(frame, **self.kw)[0]
        boxes = r.boxes
        if boxes is None or boxes.id is None:
            return []
        ids = boxes.id.int().tolist()
        xyxy = boxes.xyxy.tolist()
        confs = boxes.conf.tolist()
        return [(int(t), float(a), float(b), float(c), float(d), float(p))
                for t, (a, b, c, d), p in zip(ids, xyxy, confs)]

    def warmup(self):
        try:
            import numpy as np
            self.track(np.zeros((self.kw["imgsz"], self.kw["imgsz"], 3), dtype="uint8"))
        except Exception:
            pass


def build_detector(model_cfg: dict) -> "YoloDetector":
    return YoloDetector(
        weights=model_cfg["weights"],
        device=model_cfg.get("device", 0),
        imgsz=model_cfg.get("imgsz", 640),
        conf=model_cfg.get("conf", 0.1),
        half=model_cfg.get("half", True),
        tracker=model_cfg.get("tracker", "bytetrack.yaml"),
    )


class FakeDetector:
    """Replays scripted frames of tracks. frames: list of [(tid,x1,y1,x2,y2,conf), ...]."""
    def __init__(self, frames):
        self.frames = list(frames)
        self.i = 0

    def track(self, frame):
        if self.i >= len(self.frames):
            return []
        out = self.frames[self.i]
        self.i += 1
        return out
