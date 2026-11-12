# Store camera analytics

A small service that turns shop CCTV into the numbers and alerts a branch manager
needs: **door IN/OUT counts**, **queue** and **till (staff) zone** occupancy, a
**queue alert** and an **empty-till alert**, **several cameras at once**, and an
**honest measurement** against hand labels. Built for the Safia AI team case study.

YOLO finds people and ByteTrack follows them. All of the counting, zone and alert
logic is written here rather than taken from a library, so every decision can be
explained, and it is unit-tested without a GPU.

```bash
python run.py --config config/local.yaml --web --port 8010   # 4 cameras + live page (http://localhost:8010)
```

---

## Results at a glance

Measured on 4 public clips (13.4 min in total), with every frame analysed
(`config/measure.yaml`). The ground truth was labelled from the raw frames; how it
was made is described under [Measurement](#measurement).

| What | Result |
|---|---|
| Door, shop1 (5 IN, 2 OUT by hand) | IN 4/5 found, 0 extra · OUT 2/2 found, 1 extra (a person who stopped on the threshold) |
| Queue count, MAE (people) | shop1 **0.26** (19 points) · market **0.30** (30 points, every 10 s over 5 min) · cafe **0.75** (12 points, dense crowd) |
| Alerts (shop1 + market) | 3 expected → **3 found, 0 missed, 0 wrong**. Empty-till: 0 expected, 0 raised |
| Speed (RTX 3050 8 GB + i7-11700) | 4 cameras together: **26 frames/s in total**. One camera: 21-39 fps by model and size. The live demo keeps all 4 at real time |

---

## Clips

| Name | What it shows | Source (YouTube) | Author / channel | Length used |
|---|---|---|---|---|
| `shop1` | gift shop: glass entrance door + 2 tills, queue | [HD CCTV Camera video 3MP 4MP iProx ... retail store](https://youtu.be/KMJS66jBtVQ) | HDCCTV Cameras | 0:00-1:38 (whole clip) |
| `market` | supermarket, 3 checkout lanes (2 open), top-down | [HD-SDI 1080P ... Super Market Checkout Sample #1](https://youtu.be/-8zyEwAa50Q) | www.CCTVFACTORY.com | 0:00-4:59 (whole clip) |
| `cafe` | small convenience shop, 1 till, dense crowd (school children), door on the right | [Luton Shop Analouge HD iProx Counter area](https://youtu.be/qIYmiKGt220) | HDCCTV Cameras | 0:00-5:00 (whole clip) |
| `counter2` | food counter with a roped queue (demo only, not measured) | [Queue Length Monitoring with Searchlight for Retail](https://youtu.be/5rkwqp6nnr4) | March Networks | 0:00-1:45 (whole clip) |

**Licence.** All four videos are published under the **Standard YouTube
Licence**, not Creative Commons. They are CCTV makers' published sample recordings
of their cameras. They are used here only for this non-commercial evaluation, and
they are **not redistributed**: the `videos/` folder is not in the repository. The
pipeline is entirely config-driven, so it runs unchanged on any other clip.
`counter2` is a vendor's product demo with its own overlays burned in, so it is used
only in the live demo and not in the measurement. No Safia footage is used.

---

## What it does

- **Detection + tracking.** Ultralytics YOLO, person class only, with ByteTrack.
  Each camera has its own tracker. The default is `yolov8s` at 960 px. The crowded
  `cafe` camera uses `yolov8m` and a crowd tracker (a per-camera model override).
  See [Model choice](#model-choice).
- **Door counting.** IN and OUT across a line segment, with hysteresis. A crossing
  counts only when a track moves from clearly one side to clearly the other side of
  a band `margin` pixels wide. The following are not counted:
  - someone who stops on the line;
  - someone who turns back before crossing;
  - someone who walks along the line, or past either end of the segment.

  One crossing is never counted twice. A real cross-and-return counts as one IN and
  one OUT.
- **Zones and alerts.** Queue and staff polygons come from the config, and
  occupancy is measured every second.
  - **Queue alert:** at least N people in the queue for at least T seconds.
  - **Empty-till alert:** nobody in the staff zone for at least T seconds while at
    least one person waits.

  Each alert fires once per episode and records `start`, `end` and `peak`. A dip
  shorter than `grace_seconds` neither splits an episode nor restarts the timer
  before T.
- **Several cameras.** One worker thread per camera in one process. A dropped
  stream reconnects with backoff. A failure in one camera never stops the others,
  and running out of GPU memory makes a camera wait and retry instead of stopping.
- **Outputs.** For each camera:
  - a per-minute CSV;
  - alert episodes as JSON lines;
  - a 1 Hz occupancy log.

  Lines, zones, thresholds, model and frame budget all come from YAML; nothing is
  hard-coded.
- **Live page (bonus).** `--web` serves an Uzbek-language page with one tab per
  function, a camera picker and live controls: thresholds, reset, pause, face blur
  on/off, and switching the model, size and confidence while running.
- **Privacy.** There is no face recognition. Every person's head is blurred in
  every frame that is shown or written. This includes people too weak for the
  tracker to follow, so privacy does not depend on tracking.

### Zone options (for hard cameras, all off by default)

| Option | What it does | Used on |
|---|---|---|
| `ref: feet \| head \| center` | which point of the box decides membership | cafe queue (`head`): the camera looks over the counter, so 39% of customers' boxes run off the bottom of the frame |
| `polygons: [...]` | several polygons counted as one zone | market: both tills' lanes and both cashiers |
| `count: detections` + `min_conf` | count every person the detector found this frame, not only confirmed tracks | cafe queue (see [what we learned](#what-we-learned-on-the-crowded-camera)) |
| `smooth: S` | the per-second value is the median of the last S seconds | cafe queue (blurred frames) |
| `merge: 0-1` | overlapping boxes inside the zone count as one person | cafe staff: one cashier split into a head box and a shoulder box |
| `min_dwell`, `hold` | count only after staying N s; keep a hidden person for N s | implemented and tested, **rejected** on cafe (see below) |

---

## How the logic works

| File | Role |
|---|---|
| `analytics/geometry.py` | side of line, segment intersection, point in polygon |
| `analytics/counter.py` | line counter with a hysteresis band, limited to the segment between its two ends |
| `analytics/pipeline.py` | per camera: door counter, zone counting (per frame, then the per-second median), alerts, per-minute rows |
| `analytics/alerts.py` | one state machine per alert: timing → emit after T → end after `grace` s false; start / end / peak |
| `analytics/aggregator.py` | 1 Hz samples → per-minute rows |
| `analytics/detector.py` | YOLO + ByteTrack; also keeps the frame's raw detections, before tracking, for zones that need them |
| `analytics/stream.py` | capture, frame budget (`process_fps`), real-time pacing, reconnect, inference-error recovery, blur, outputs |
| `analytics/service.py` | starts one worker per camera, with an optional per-camera model |
| `app/web.py` | live page (FastAPI, MJPEG) |

Zone occupancy is counted on every frame. The value for each second is the median
over that second, or over `smooth` seconds, so one frame where a person is hidden
does not change the count.

---

## Quick start

```bash
# 1. environment
python -m venv .venv && .venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cu121   # GPU build for your CUDA

# 2. models (yolov8n/s/m, yolo11n/s) -> models/
python scripts/download_models.py

# 3. put the clips in videos/ as shop1.mp4, market.mp4, cafe.mp4, counter2.mp4 (sources above)

# 4. run
python run.py --config config/local.yaml --web --port 8010      # live demo, 4 cameras, real time
python run.py --config config/measure.yaml                      # measurement: every frame, once
python measurement/evaluate.py                                  # -> measurement/RESULTS.md
#    or one command in a container:
docker compose -f docker/docker-compose.yml up --build
```

| Config | Purpose |
|---|---|
| `config/local.yaml` | live demo: 4 cameras at real time with a frame budget per camera |
| `config/measure.yaml` | measurement: every frame of every clip, all 4 cameras concurrently |
| `config/cafe.yaml`, `config/shop.yaml` | one camera alone (cafe at its full 12 fps, needed for its door) |
| `config/bytetrack_crowd.yaml` | ByteTrack thresholds for the crowd (new tracks from 0.15 instead of 0.25) |

`scripts/show_frame.py` saves a frame so you can read pixel coordinates for new
lines and zones.

## Outputs

| File | Contents |
|---|---|
| `<out>/<cam>_minutes.csv` | per minute: `minute, in, out, avg_queue, max_queue, empty_counter_seconds` |
| `<out>/<cam>_alerts.jsonl` | one JSON object per alert episode: `type, source, start, end, duration, peak` |
| `<out>/<cam>_occupancy.csv` | 1 Hz log: `t, queue, staff, in, out` (used for the measurement) |
| `<out>/<cam>/annotated.mp4` | optional: video with line, zones, IDs, counts, alert banner; heads blurred |

---

## Measurement

**How the ground truth was made.** Labels were drafted with an AI assistant
(Claude) from frame sheets of the **raw** video (no system boxes shown). Every label
is in `measurement/hand/labels.json` with its time and a short description of the
person, and I checked them against the video myself. A `[low, high]` range marks someone standing
on the edge of a zone or mostly hidden; a system value inside the range counts as
correct.

**How the system was run.** `config/measure.yaml` analyses every frame of all four
clips once (one process, 4 streams). `measurement/evaluate.py` compares the outputs
with the labels and writes `measurement/RESULTS.md`.

### Door: shop1 (98 s, glass entrance door)

| Direction | Hand count | System | Matched (±2 s) | Missed | Extra |
|---|---|---|---|---|---|
| IN | 5 | 4 | 4 | 1 | 0 |
| OUT | 2 | 3 | 2 | 0 | 1 |

- **Missed IN at 0:20.** A woman enters at the moment a man leaves, and their
  paths cross in the doorway. The OUT is counted and the IN is not, most likely an
  ID swap while the two boxes overlap.
- **Extra OUT at 1:32.** An older woman walks onto the threshold and **stops there
  until the clip ends**. Her feet point drifts past the hysteresis band while she
  stands, so it is counted. This is exactly the "stops on the line" case: the band
  handles jitter of a few pixels but not slow drift. Fix: require the track to keep
  moving, or to be seen beyond the band for k frames.

**cafe door (not hand-measured).** At full frame rate the system counts 4 IN and 4
OUT (OUT at 1:03, 1:46, 3:32, 3:49). When we looked at the doorway frame by frame,
some exits were not counted, for example two people leaving at 0:52-0:58. People
cross the doorway in about a second and then disappear behind a pillar, so this
door needs every frame. At 6 fps it gave 0 exits, and at 4 fps it gave 1 crossing in
5 minutes. The cafe door is therefore reported here and not claimed as measured.

### Queue count (MAE, people)

| Clip | Labelled points | Span | MAE | Inside the range | Worst |
|---|---|---|---|---|---|
| shop1 | 19 (every 5 s) | 0:05-1:35 | **0.26** | 14/19 | -1 at 0:15 |
| market | 30 (every 10 s) | 0:00-4:50 | **0.30** | 23/30 | -3 at 0:00 (first second of the clip, before the tracker has started) |
| cafe | 12 (every 25 s) | 0:10-4:45 | **0.75** | 4/12 | -2 at 1:00 (dense crowd) |

On cafe, the same measurement with the plain track count gave **MAE 2.33**: it
undercounted by 3 or more people in 102 of 300 seconds. How that was fixed is
explained [below](#what-we-learned-on-the-crowded-camera).

### Alerts (N = 3 people for T = 10 s; empty till T = 15 s; grace 2 s)

| Clip | Type | Expected | System | Found | Missed | Wrong |
|---|---|---|---|---|---|---|
| shop1 | queue | 1 (0:00-1:22) | 1 (0:01-1:25, peak 7) | 1 | 0 | 0 |
| shop1 | empty till | 0 | 0 | - | 0 | 0 |
| market | queue | 2 (1:22-1:35, 1:48-2:45) | 2 (1:19-1:36, 1:47-2:42, peak 4) | 2 | 0 | 0 |
| market | empty till | 0 | 0 | - | 0 | 0 |

Each episode fired once. There was no flicker into several episodes, and each has a
start, end and peak.

**market's 1:22-1:35 episode.** The 10-second labels alone missed it: they show 2
people at 1:20 and 3 at 1:30. Checking every 3 s confirmed the system was right: a
man in yellow shorts joins lane 2 while two customers are at lane 1.

**market's empty-till edge case.** Both cashiers leave at about 3:57. The only
customer then has already paid and is packing her bags at the end of lane 1. She is
not waiting, so no alert is expected, and none was raised. If she had still been
waiting, the alert would have depended on whether her feet were inside the queue
polygon at the very end of the lane.

**cafe alerts (no hand episodes).** The queue in cafe is at least 3 for almost the
whole clip, except around 0:20-0:40. The system raised episodes at 0:00-0:15,
0:42-0:52, 1:22-3:36, 3:40-4:32 and 4:42-4:59.

### Speed

| | Value |
|---|---|
| Hardware | NVIDIA RTX 3050 8 GB, Intel i7-11700, Windows 11 |
| Precision | FP16, PyTorch (Ultralytics), 960 px input |
| yolov8s, 1920×1080 (market) | 38.6 fps detect + track, one camera alone |
| yolov8s, 1270×720 (shop1) | 24.7 fps |
| yolov8m, 640×720 (cafe crowd) | 21.4 fps |
| 4 cameras together, every frame (`measure.yaml`) | 12 528 frames in 480 s = **26.1 frames/s in total**; GPU ~44% busy on average |
| 4 cameras live (`local.yaml`, frame budget) | all 4 at **1.03-1.04× real time** |
| Video decode alone | 109 fps at 1080p, 180 fps at 720p |

**The bottleneck is the CPU, not the GPU.** With 4 streams the GPU was idle more
than half the time. CPU decode of three 1080p/720p videos, JPEG encoding for the
live page, and Python threads use it up. When the cafe camera was raised to its full
12 fps inside the 4-camera demo, everything fell to 0.4× real time. That is why the
live config gives each camera a frame budget (`process_fps`):

| Camera | Analysed fps | Why |
|---|---|---|
| shop1 | 5 | door + queue |
| counter2 | 3 | queue only; a 30 fps camera does not need 30 fps |
| market | 5 | queues only |
| cafe | 4 | queue + till. Its door needs 12 fps, so the cafe door is measured with `config/cafe.yaml` alone |

### Known failure cases (with timestamps)

| Clip @ time | What happens | Why | What would fix it |
|---|---|---|---|
| shop1 @ 1:32 | extra OUT for a woman standing on the threshold | feet point drifts past the band while she stands | require motion, or k frames beyond the band |
| shop1 @ 0:20 | missed IN, two people cross paths in the door | likely an ID swap while the boxes overlap | higher frame rate at the door; a ReID tracker (BoT-SORT) |
| shop1 (children behind the red stands) | small, partly hidden children blink in and out | low detector confidence | larger model or input; `count: detections` for the zone |
| cafe @ 1:00 | queue 2 short in a dense moment | people fully hidden behind others | a head detector trained on this view; a second camera |
| cafe @ 2:11 | (fixed) count dropped 12 → 3 for a second | motion-blurred / compressed frames | `smooth: 3` |
| cafe @ 0:52-0:58 | exits not counted | ~1 s in the doorway, then behind a pillar | full frame rate; a camera that sees the doorway |
| cafe staff zone | one cashier counted as 2 (45 s of 300) → 4 s after the fix | split boxes (head + shoulder when he bends) | `merge: 0.6` |
| counter2 @ 0:26-0:34 | cashier counted as absent | the cashier walks out of the bottom of the frame | a staff zone that covers her whole working area |
| market @ 3:57-4:41 | both cashiers away; the only customer is packing | is she "waiting"? | business rule: count only people before the till |

### What we learned on the crowded camera

The cafe clip shows a small shop full of school children, with one till and the
camera looking over the cashier's shoulder. Each step below was measured against
the labels, at the frame rate the live demo uses.

1. **Plain track count:** MAE 2.33. People hidden in the crowd **are** detected,
   but with confidence 0.1-0.25. ByteTrack starts a track only from 0.25 (0.15 with
   the crowd tracker), so these people never become tracks.
2. **"Remember hidden people" (`hold` 3-5 s) and "must stay N s" (`min_dwell`):
   rejected.** In the crowd the tracker gives people a new ID every few seconds.
   `hold` kept the old IDs alive next to the new ones, and the live page showed 7
   with 3 people in view. An offline score of 0.92 had looked like a win, but it
   came from this double counting cancelling out the undercount.
3. **Head detector** (YOLOv8 trained on SCUT-HEAD, classrooms): MAE 1.50. Wrong
   viewpoint, not used.
4. **2× zoom of the queue region:** MAE 0.75, but half the speed. Not used.
5. **Count the detections, not the tracks** (`count: detections`, conf ≥ 0.1).
   Counting occupancy needs no IDs, so the zone counts every person box in the
   frame, while the door line still uses tracks. MAE 1.00, same speed. Merging
   overlapping boxes made it worse (1.8-2.2), because people in a crowd really
   overlap.
6. **Median over 3 s** (`smooth: 3`) removes the moments when blurred frames made
   the count fall from 12 to 3: sudden drops went from 4 to 0, and jumps of 3 or
   more within one second from 33 to 2. **Final: MAE 0.75.**

The ranges of the rejected settings are also kept in the comments of
`config/cafe.yaml`.

---

## Model choice

Measured, not assumed. I ran 13 configurations on shop1 against the labels:
yolov8n/s, yolo11n/s, 640/960/1280 px and confidence 0.1/0.25.

| Config | Door matched / missed / extra | Queue MAE | Alert correct |
|---|---|---|---|
| **yolov8s 960, conf 0.1 (chosen)** | 6 / 1 / 0 | **0.26** | yes |
| yolov8s 1280 | 7 / 0 / 0 | 0.26 | no |
| yolo11s 1280 | 7 / 0 / 0 | 0.42 | yes |
| yolo11s 960 | 6 / 1 / 2 | 0.53 | yes |
| yolov8n 960 | 6 / 1 / 1 | 0.63 | yes |
| yolov8n 640 | 7 / 0 / **7** | 1.37 | no |
| yolo11n 640 | 6 / 1 / 3 | 1.53 | no |

- 640 px is not enough for small or distant people.
- The `-s` models clearly beat the `-n` models (detection recall 0.86-0.92 against
  0.77-0.82).
- yolo11 was not better than yolov8 on this footage.
- The detector `conf` is only a floor handed to ByteTrack, so it is kept at 0.1. At
  0.3 the tracker loses the low-score boxes it uses to keep a hidden person alive,
  and distant people flicker.
- The cafe crowd needs `yolov8m` (queue MAE 3.08 with `-s`, 2.17 with `-m`, before
  the zone changes above).

You can switch models live from the web page to compare.

---

## Scaling to ~50 cameras on one GPU server

The measurement above already shows the first wall: **CPU decode**. With 4 streams
the GPU was more than half idle. For 50 cameras, these things change:

- **Decode on the GPU (NVDEC)**, with FFmpeg or DeepStream, and keep frames on the
  GPU. At 50 × 1080p, CPU decode alone is beyond a server CPU.
- **One shared model with batched inference.** Today each camera has its own
  model. Instead, a batching worker takes the latest frame from each camera and runs
  one batch per tick. ByteTrack state stays per camera; only detection is batched.
  This is the biggest gain in VRAM and throughput.
- **A frame budget per camera**, as `process_fps` already does. Queues and tills
  need about 3-5 fps. Doors need more (10-12 fps, as the cafe door showed), so only
  door cameras get it.
- **TensorRT FP16/INT8** export (the ONNX export is already included), for 2-4×
  faster inference than PyTorch.
- **Processes, not threads.** Python threads share one GIL. Shard cameras across a
  few processes (or `multiprocessing` workers), each feeding the batching worker.
- **What breaks, in order:** CPU decode → GPU memory (many models; fixed by sharing
  one) → host-to-device copies → disk, if annotated video is written (do this only
  for a few debug cameras).
- **Rough budget:** one modern data-centre GPU can run about 40-60 cameras at 4-8
  fps with an `-s` detector, batched and on TensorRT, with NVDEC. Beyond that, add a
  GPU and shard cameras across them.
- **Process restarts.** After a hard CUDA error the process's GPU context can stay
  broken (seen here when another program filled the RAM). Run each worker under a
  supervisor, such as Docker `restart: unless-stopped` or systemd, so a broken
  worker restarts itself.

---

## Privacy and ethics

- No face recognition and no identification, only anonymous counts.
- Heads are blurred in every frame that is shown or saved (`analytics/privacy.py`),
  including people the tracker does not follow.
- No Safia footage and no Safia systems were used.

## Tests

```bash
python tests/test_core.py            # geometry, line counter (hysteresis, segment ends), zones, alerts, aggregation
python tests/test_pipeline.py        # pipeline on synthetic tracks; zone options: ref, polygons, detections, smooth, merge, dwell, hold
python tests/test_stream_io.py       # capture -> pipeline -> CSV / JSONL / video
python tests/test_reconnect.py       # a stream drops mid-run and reconnects without losing the count
python tests/test_process_fps.py     # frame budget: 30 frames analysed as 10, times stay right
python tests/test_inference_error.py # failed inferences are skipped; long GPU-memory outage is waited out
# or:  pytest -q
```

None of them needs a GPU.

## ONNX export (bonus)

```bash
python scripts/export_onnx.py --weights models/yolov8s.pt --imgsz 960   # add --half on GPU
#   needs: pip install onnx onnxruntime-gpu    (or onnxruntime for CPU)
```

Point `model.weights` at the `.onnx` file. Ultralytics then runs it through ONNX
Runtime. TensorRT is the next step for the 50-camera case.

## Licences

- **Ultralytics YOLO** is **AGPL-3.0**. This public repository is a case study,
  which is compatible. A closed commercial product would need an Ultralytics
  commercial licence or an Apache/MIT detector (for example RF-DETR).
- **Videos:** see [Clips](#clips). They are not committed.
- Model weights are not committed; the scripts download them.

## AI assistance

The code, the experiments and this README were written with an AI coding
assistant (Claude). I chose the clips, reviewed the results on the live page,
reported the errors I saw (for example the cafe queue and door counts), and decided
what to keep. Every number above comes from the scripts in this repository and can
be reproduced with the commands in [Quick start](#quick-start).
