"""Load and validate the YAML config into a plain dict with defaults filled.
Fails early with a clear message, so a bad line/zone is caught before the model
loads rather than deep inside a stream."""
from __future__ import annotations

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
            _require("polygon" in z and len(z["polygon"]) >= 3,
                     f"source {s['name']!r}: zone {zname!r} needs a polygon of >= 3 points")
    return cfg
