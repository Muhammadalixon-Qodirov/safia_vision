# Store camera analytics

A small service that turns store-like video into the numbers and alerts a branch
manager needs: **door IN/OUT counts**, **queue** and **counter-zone** occupancy
with two kinds of **alert**, **several streams at once**, and **honest
measurement** against hand labels. Built for the Safia AI team case study.

It runs a YOLO person detector with ByteTrack tracking, and all the
counting/alert logic is written here (not pulled from a library) so every
decision is explainable and unit-tested without a GPU.

> **Status:** the software is complete and tested. The numbers in the
> *Measurement* tables are filled in after running on public clips — see
> [What you still need to do](#what-you-still-need-to-do).

---

## What it does

- **Detection + tracking** — Ultralytics YOLO (`yolov8n`) with its built-in
  ByteTrack, person class only. One tracker per stream.
- **Door counting** — counts people crossing a line, separately IN and OUT.
  Uses hysteresis around the line, so a person who stops on the line, turns back
  before crossing, or walks along it is never counted, and one crossing is never
  counted twice; a genuine cross-and-return is one IN and one OUT.
- **Queue / counter zones** — from polygons in the config, every second it
  measures how many people are in the `queue` zone and whether anyone is in the
  `staff` zone, and raises:
  - **queue alert:** at least `N` people in the queue for at least `T` seconds;
  - **empty-counter alert:** nobody in the staff zone for at least `T` seconds
    while at least one person waits.
  Each alert fires once per episode (no on/off flicker — a brief dip shorter than
  `grace_seconds` does not split it) and records its start, end and peak.
- **Several streams at once** — one worker thread per source in one process. If a
  source drops it reconnects with backoff; a failure in one stream never stops
  the others. A file source is played at real-time speed and stops at its end.
- **Output** — a per-minute CSV per source (`in, out, avg_queue, max_queue,
  empty_counter_seconds`), alert events as JSON lines, and a 1 Hz occupancy log
  for measurement. Everything — lines, zones, thresholds — comes from one config
  file; nothing is hard-coded.
- **One command** — `python run.py`, or `docker compose up`.
- **Privacy** — no face recognition. Any written frame has every person's head
  region blurred.

## How the logic works (the interesting part)

- `analytics/geometry.py` — side-of-line, segment intersection, point-in-polygon.
- `analytics/counter.py` — line crossing with a hysteresis band of `margin`
  pixels: a crossing counts only when a track moves from clearly one side to
  clearly the other. Direction is fixed once from `in_direction` against the
  line's normal.
- `analytics/zones.py` — a person is in a zone when the bottom-centre of its box
  (the feet) is inside the polygon.
- `analytics/alerts.py` — a small state machine per alert: it starts timing when
  the condition becomes true, *emits* only after `T` seconds, and ends only after
  the condition has been false for `grace` seconds; it records start/end/peak.
- `analytics/aggregator.py` — rolls the 1 Hz samples into per-minute rows.
- `analytics/pipeline.py` — ties these together per source; `stream.py` adds
  capture, reconnect, annotation and output; `service.py` runs the streams.

All of the above is covered by unit tests that run **without a GPU**
(`tests/test_core.py`, `tests/test_pipeline.py`, `tests/test_stream_io.py`).

## Quick start

```bash
# 1. create an environment and install
python -m venv .venv && . .venv/Scripts/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
#    GPU torch (optional, much faster): install the CUDA wheel for your CUDA
#    version, e.g.  pip install torch --index-url https://download.pytorch.org/whl/cu121

# 2. get the model weights and two public clips
python scripts/download_models.py
#    fill config/videos.json with public clips (Pexels/Pixabay) + licences, then:
python scripts/download_videos.py

# 3. set the line and zones to match your clips
python scripts/show_frame.py videos/counter.mp4 --at 2 --out counter_frame.jpg
#    open the image, read pixel coordinates, edit config/config.yaml

# 4. run
python run.py                       # or: python run.py --web   (live page on :8000)
#    or one command in a container:
docker compose -f docker/docker-compose.yml up --build
```

Outputs appear in `output/`.

## Configuration (`config/config.yaml`)

One file controls everything. Key parts:

- `model` — weights, `device` (`0` GPU / `"cpu"`), `imgsz`, `conf`, `half`
  (FP16), tracker.
- `alerts` — `queue.min_people` (N), `queue.min_seconds` (T),
  `empty_counter.min_seconds` (T), `grace_seconds`.
- `sample_hz` — how often zones/alerts are sampled (1 = once per video second).
- `sources[]` — each has a `name`, `uri` (file / RTSP / webcam index), optional
  `line` (`a`, `b`, `in_direction`), and optional `zones` (`queue`, `staff`
  polygons). `realtime: true` plays a file at its real frame rate; `loop` and
  `max_retries` control reconnect behaviour.

## Outputs

| File | Contents |
|---|---|
| `output/<src>_minutes.csv` | per minute: `minute, in, out, avg_queue, max_queue, empty_counter_seconds` |
| `output/<src>_alerts.jsonl` | one JSON object per alert episode: `type, source, start, end, duration, peak` |
| `output/<src>_occupancy.csv` | 1 Hz log: `t, queue, staff, in, out` (used for measurement) |
| `output/<src>/annotated.mp4` | the video with line, zones, IDs, counts and alert banner; heads blurred |

## Measurement

Produced by `python measurement/compare.py` after you fill the hand labels in
`measurement/hand/` (see its README) and run the system once. Honest numbers
against your own labels — fill these in:

### Door counts vs hand count
<!-- paste the table from measurement/compare.py -->
_fill after running on your clips_

### Queue count - mean absolute error
_fill after running on your clips_

### Alerts - expected vs system
_fill after running on your clips_

### Speed
| Metric | Value |
|---|---|
| GPU / CPU | _e.g. RTX 3050 8 GB / Ryzen ..._ |
| per-stream FPS | _printed in the live state / log_ |
| total FPS (all streams) | _..._ |
| input resolution | _..._ |
| model / precision | yolov8n / FP16 |
| GPU memory | _..._ |

### Known failure cases (with timestamps)
_write while watching the annotated output: occlusion, groups, ID switches,
people lingering at the line, reflections, etc._

## Scaling to ~50 cameras on one GPU server

The current design is one thread and one model per stream, which is right for a
handful of cameras but will not reach 50. What changes:

- **Decode on the GPU (NVDEC).** At 50×1080p, CPU JPEG/H.264 decode is the first
  bottleneck. Decode on the GPU (FFmpeg/NVDEC or DeepStream) and keep frames on
  the GPU to avoid copies.
- **One shared model, batched inference.** Replace per-stream models with a
  single model and a batching worker that gathers the latest frame from each
  camera into one batch per tick. ByteTrack state stays per camera; only
  detection is batched. This is the biggest VRAM and throughput win.
- **Drop the frame rate per camera.** Counting and queue occupancy do not need
  30 FPS; 5-8 FPS per camera is plenty and cuts the load ~4-6×. Sample zones at
  1 Hz as now.
- **Export the detector** to TensorRT (INT8/FP16) or ONNX Runtime for 2-4× faster
  inference than plain PyTorch.
- **What breaks first:** CPU decode, then GPU memory (many models), then
  PCIe/host-to-device copies, then disk for annotated video (write it only for a
  few debug cameras, never all 50). A rough budget: one modern GPU can run
  ~40-60 cameras at 6-8 FPS with a nano/-s detector in INT8, batched, with NVDEC;
  beyond that, add a second GPU and shard cameras across processes.

## Privacy and ethics

No face recognition and no attempt to identify anyone — only anonymous counts.
Any frame written to disk has each person's head region blurred
(`analytics/privacy.py`). Only public footage with a permissive licence is used;
no Safia footage.

## Tests

```bash
python tests/test_core.py          # geometry, counting, zones, alerts, aggregation (no GPU)
python tests/test_pipeline.py      # full per-source pipeline on synthetic tracks (no GPU)
python tests/test_stream_io.py     # capture -> pipeline -> CSV/JSONL/video (needs OpenCV, no GPU)
# or, with pytest installed:  pytest -q
```

## Licences

- **Ultralytics YOLO** is **AGPL-3.0**. This repository is public and used for a
  case study, which is compatible; a closed commercial product would need an
  Ultralytics commercial licence or an Apache/MIT detector (e.g. RF-DETR).
- **Videos** are public clips; their authors and licences are listed in
  `videos/ATTRIBUTION.md` (generated by `scripts/download_videos.py`) — copy that
  list here before submitting.
- Weights and videos are not committed; they are downloaded by the scripts.

## What you still need to do

The code is done and tested. To finish the submission you (the applicant) do the
parts that must be your own work:

1. Pick and download **2+ public clips** (≥5 min total) of an entrance and/or a
   counter, with a permissive licence; fill `config/videos.json`.
2. Set the **line and zones** for your clips in `config/config.yaml`
   (`scripts/show_frame.py` helps).
3. **Run** it on your GPU and record the **speed** numbers.
4. **Hand-label** the clips (`measurement/hand/`) and run `measurement/compare.py`
   to fill the measurement tables.
5. Record a short **annotated GIF** (heads blurred) for this README.
6. Make sure you can **explain and change every part** in the live interview.
