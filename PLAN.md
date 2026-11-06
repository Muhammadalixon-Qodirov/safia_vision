# Store camera analytics — build plan

Case study for the Safia AI team (round 2). Build a small service that turns
store-like video into the numbers and alerts a branch manager needs: door
in/out counts, queue and counter-zone occupancy, two alert types, several
streams at once, honest measurement.

Deadline: 2026-11-12 23:59 Tashkent. Sized for 5–6 working days. Submission:
a public GitHub repo + a short write-up (the README).

Reuses what the applicant already built in `sv_demo` (YOLO + ByteTrack person
tracking in `tracking_demo.py`; the `ZAL_SANASH` research on counting accuracy,
licensing and privacy). The vision core is familiar; the new work is the
counting/alert logic, multi-stream engineering, config, output, and honest
measurement.

## Design decisions (and why)

- **Detector + tracker:** Ultralytics YOLO (`yolov8n`/`yolo11n`) with its
  built-in ByteTrack (`model.track(..., persist=True, tracker="bytetrack.yaml")`).
  One dependency, person class only. Small model so it runs on an 8 GB RTX 3050
  and leaves room for several streams.
- **Counting / zones / alerts written by hand (pure Python + numpy), not from a
  library.** The task allows "your own". This makes the logic unit-testable
  **without a GPU or torch**, and explainable line-by-line in the interview —
  the same evidence-first discipline as the applicant's security project.
- **Everything from one config file.** Lines, zones, thresholds, sources, model
  settings. Nothing hard-coded.
- **Video time, not wall-clock.** Counts, alerts and per-minute rows are driven
  by each frame's timestamp, so results are deterministic and reproducible on
  recorded clips.
- **One worker thread per source**, each with capture → detect+track → count →
  sample zones/alerts. If a source drops, that worker reconnects with backoff;
  the others keep running. (Scaling to ~50 cameras — batched inference, NVDEC —
  is discussed in the README, not built.)
- **Privacy by construction.** No face recognition, no identfrom. Published
  frames/GIF blur the head region of every detected person.

## Architecture

```
run.py                         one-command entry: python run.py --config config/config.yaml
config/config.yaml             sources, lines, zones, thresholds, model, output
analytics/
  config.py      load + validate the YAML into typed objects
  geometry.py    line-crossing + point-in-polygon  (pure, tested)
  counter.py     LineCounter: in/out per tracker crossing, anti-double-count (tested)
  zones.py       ZoneOccupancy: people inside each polygon per sample (tested)
  alerts.py      AlertManager: queue + empty-counter state machines, debounced (tested)
  aggregator.py  MinuteAggregator: per-minute CSV rows (tested)
  detector.py    YOLO wrapper (ultralytics) + FakeDetector for tests
  annotate.py    draw line, zones, boxes+IDs, counts, alert banner (cv2)
  privacy.py     blur head region of each person box
  stream.py      StreamWorker thread: capture, reconnect, run the pipeline
  service.py     start N workers concurrently, clean shutdown
  state.py       shared live state (for the optional web page)
app/web.py       optional FastAPI: GET / live counts + open alerts, GET /api/state
scripts/
  download_models.py   fetch YOLO weights
  download_videos.py   fetch public clips (Pexels/Pixabay) + print licences
measurement/
  templates + compare.py   system output vs hand labels -> error tables for README
tests/           unit tests for the pure-Python logic (run without a GPU)
docker/          Dockerfile + docker-compose.yml
```

## Required features → where

| Requirement | Module | Status |
|---|---|---|
| 1. Person detection + tracking (YOLO + ByteTrack) | detector, stream | to build |
| 2. Door line counting IN/OUT, no double count | geometry, counter | to build |
| 3. Queue + counter zones, per-second, 2 alerts, start/end/peak, no flicker | zones, alerts | to build |
| 4. ≥2 streams concurrently, reconnect without crashing others | stream, service | to build |
| 5. Per-minute CSV per source + alert JSONL, all from config | aggregator, alerts, config | to build |
| 6. One command / `docker compose up` | run.py, docker/ | to build |

## Measurement (README) → where

| Item | How |
|---|---|
| Door counts vs hand count, per clip | user hand-counts; `measurement/compare.py` tabulates |
| Queue MAE (hand-label every 10 s, ≥2 min) | user labels template; compare.py computes MAE |
| Alerts expected vs found/missed/wrong | user lists expected; compare.py matches |
| Speed: FPS/stream + total, GPU, VRAM, res, model, precision | the service prints/logs it; user records the numbers |
| Known failure cases with timestamps | user notes while watching the annotated output |
| Scaling note (~½ page, 50 cameras) | written in the README |

## Optional bonuses (only if time)

TensorRT/ONNX export + FPS/accuracy comparison; NVDEC decode; batched inference
across streams; staff-vs-customer by apron/uniform colour; the tiny web page.

## Who does what

- **I build:** every module above, the config, tests, download scripts, docker,
  the web page, the measurement tooling, and the README skeleton.
- **Only the applicant can:** pick and download 2+ public clips and confirm
  their licence and content; run it on the GPU and record the real FPS/VRAM;
  hand-label the clips (door count, queue every 10 s, expected alerts) — these
  labels are the honest-measurement core and must be the applicant's own; record
  a blurred GIF/screenshots; and understand every part for the live interview.

## Order of work

1. Core logic + tests (geometry, counter, zones, alerts, aggregator) — runs with no GPU.
2. Detector + stream worker + service + run.py — the live pipeline.
3. Config, annotate, privacy, output (CSV/JSONL).
4. Download scripts, README skeleton, docker.
5. Measurement tooling + the optional web page.
6. Applicant runs on the GPU, hand-labels, fills the measurement tables, records the GIF.
```
