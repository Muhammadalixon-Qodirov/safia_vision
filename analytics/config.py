"""Load and validate the YAML config into a plain dict with defaults filled.
Fails early with a clear message, so a bad line/zone is caught before the model
loads rather than deep inside a stream."""
from __future__ import annotations

import os
from pathlib import Path

import yaml


def _require(cond, msg):
    if not cond:
        raise ValueError(f"config: {msg}")


def load_config(path: str) -> dict:
    p = Path(path)
    _require(p.is_file(), f"file not found: {path}")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    model = cfg.setdefault("model", {})
    _require("weights" in model, "model.weights is required")
    model.setdefault("device", 0)
    model.setdefault("imgsz", 640)
    model.setdefault("conf", 0.3)
    model.setdefault("half", True)
    model.setdefault("tracker", "bytetrack.yaml")
    # ANALYTICS_DEVICE=cpu (e.g. in a CPU-only container) overrides every model's
    # device, including per-camera overrides below
    env_device = os.environ.get("ANALYTICS_DEVICE")
    if env_device:
        dev = int(env_device) if env_device.isdigit() else env_device
        model["device"] = dev
        for s in cfg.get("sources") or []:
            if isinstance(s.get("model"), dict):
                s["model"]["device"] = dev

    out = cfg.setdefault("output", {})
    out.setdefault("dir", "output")
    out.setdefault("annotated_video", True)
    out.setdefault("blur_faces", True)

    al = cfg.setdefault("alerts", {})
    q = al.setdefault("queue", {})
    q.setdefault("min_people", 3)
    q.setdefault("min_seconds", 10)
    e = al.setdefault("empty_counter", {})
    e.setdefault("min_seconds", 15)
    al.setdefault("grace_seconds", 2)
    cfg.setdefault("sample_hz", 1)

    srcs = cfg.get("sources") or []
    _require(len(srcs) >= 1, "at least one source is required")
    names = set()
    for i, s in enumerate(srcs):
        _require("name" in s, f"sources[{i}].name is required")
        _require(s["name"] not in names, f"duplicate source name {s['name']!r}")
        names.add(s["name"])
        _require("uri" in s, f"source {s['name']!r}: uri is required")
        line = s.get("line")
        if line:
            _require("a" in line and "b" in line, f"source {s['name']!r}: line needs a and b")
            _require(len(line["a"]) == 2 and len(line["b"]) == 2,
                     f"source {s['name']!r}: line a/b must be [x, y]")
        for zname, z in (s.get("zones") or {}).items():
            polys = z.get("polygons") or ([z["polygon"]] if "polygon" in z else [])
            _require(polys and all(len(p) >= 3 for p in polys),
                     f"source {s['name']!r}: zone {zname!r} needs a polygon (or polygons) "
                     f"of >= 3 points each")
            _require(z.get("ref", "feet") in ("feet", "head", "center"),
                     f"source {s['name']!r}: zone {zname!r} ref must be feet, head or center")
            for key in ("min_dwell", "hold", "smooth"):
                _require(float(z.get(key, 0) or 0) >= 0,
                         f"source {s['name']!r}: zone {zname!r} {key} must be >= 0 seconds")
            _require(z.get("count", "tracks") in ("tracks", "detections"),
                     f"source {s['name']!r}: zone {zname!r} count must be tracks or detections")
            if z.get("count") == "detections":
                _require(not z.get("min_dwell") and not z.get("hold"),
                         f"source {s['name']!r}: zone {zname!r}: min_dwell/hold need track IDs, "
                         f"not available with count: detections")
            if z.get("merge") is not None:
                _require(0 < float(z["merge"]) <= 1,
                         f"source {s['name']!r}: zone {zname!r} merge must be in (0, 1]")
    return cfg
