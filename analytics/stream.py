"""One worker thread per video source: open it, run detection+tracking and the
per-source pipeline, write the per-minute CSV and the alert JSONL, and (if
enabled) an annotated video with blurred heads. If the source drops it
reconnects with backoff; if it is a file it stops at the end. A failure in one
worker never stops the others.
"""
from __future__ import annotations

import csv
import json
import os
import threading
import time

import cv2

from . import annotate, privacy
from .aggregator import FIELDS
from .pipeline import StreamPipeline

_STREAM_PREFIXES = ("rtsp://", "http://", "https://", "tcp://", "udp://")


def _is_file(uri) -> bool:
    return isinstance(uri, str) and not uri.lower().startswith(_STREAM_PREFIXES)


class StreamWorker(threading.Thread):
    def __init__(self, source, model_cfg, output_cfg, alerts_cfg, sample_hz, detector, shared, stop_event,
                 open_capture=None):
        super().__init__(daemon=True, name=source["name"])
        self.source = source
        self.output_cfg = output_cfg
        self.alerts_cfg = alerts_cfg
        self.sample_hz = sample_hz
        self.detector = detector
        self.shared = shared
        self.stop = stop_event
        self._fps_est = 0.0
        self._ctl_applied = {}       # last-applied live controls (reset seq, thresholds)
        # how to open a source; injectable so the reconnect path can be tested without a real stream
        self._open = open_capture or (lambda uri: cv2.VideoCapture(uri))

    def _log(self, msg):
        print(f"[{self.source['name']}] {msg}", flush=True)

    def run(self):
        name = self.source["name"]
        uri = self.source["uri"]
        outdir = self.output_cfg["dir"]
        os.makedirs(os.path.join(outdir, name), exist_ok=True)
        pipe = StreamPipeline(self.source, self.alerts_cfg, self.sample_hz)

        cf = open(os.path.join(outdir, f"{name}_minutes.csv"), "w", newline="", encoding="utf-8")
        writer = csv.DictWriter(cf, fieldnames=FIELDS)
        writer.writeheader()
        cf.flush()
        af = open(os.path.join(outdir, f"{name}_alerts.jsonl"), "w", encoding="utf-8")
        occf = open(os.path.join(outdir, f"{name}_occupancy.csv"), "w", newline="", encoding="utf-8")
        occ_writer = csv.DictWriter(occf, fieldnames=["t", "queue", "staff", "in", "out"])
        occ_writer.writeheader()
        vid = None

        is_file = _is_file(uri)
        loop = bool(self.source.get("loop", False))
        realtime = bool(self.source.get("realtime", True))
        max_retries = int(self.source.get("max_retries", 10))
        backoff = float(self.source.get("reconnect_backoff", 2.0))
        max_frames = self.source.get("max_frames")       # optional: stop after N frames
        live_view = bool(self.output_cfg.get("live_view", False))  # publish JPEGs for the web page
        retries = 0
        frame_idx = 0
        fps = 25.0
        cap = None
        try:
            while not self.stop.is_set():
                if cap is None:
                    cap = self._open(uri)
                    if not cap.isOpened():
                        cap = None
                        retries += 1
                        self._log(f"cannot open (try {retries}/{max_retries})")
                        if retries > max_retries:
                            break
                        time.sleep(min(backoff * retries, 10))
                        continue
                    f = cap.get(cv2.CAP_PROP_FPS)
                    fps = f if 1 < f <= 240 else 25.0

                if max_frames and frame_idx >= int(max_frames):
                    self._log(f"reached max_frames={max_frames}")
                    break

                # --- apply live controls from the web page ---
                ctl = self.shared.controls(name)
                rseq = ctl.get("reset_seq", 0)
                if rseq != self._ctl_applied.get("reset", 0):
                    pipe.reset()
                    self._ctl_applied["reset"] = rseq
                th = (ctl.get("queue_n"), ctl.get("queue_seconds"), ctl.get("empty_seconds"))
                if th != self._ctl_applied.get("th"):
                    pipe.set_thresholds(queue_n=ctl.get("queue_n"),
                                        queue_seconds=ctl.get("queue_seconds"),
                                        empty_seconds=ctl.get("empty_seconds"))
                    self._ctl_applied["th"] = th
                if ctl.get("paused"):
                    time.sleep(0.08)            # freeze on the current frame
                    continue
                blur = bool(ctl.get("blur", self.output_cfg.get("blur_faces", True)))

                t_start = time.monotonic()
                ok, frame = cap.read()
                if not ok:
                    cap.release()
                    cap = None
                    if is_file:
                        if loop:
                            frame_idx = 0            # replay from the start, no retry penalty
                            continue
                        self._log("end of file")
                        break
                    retries += 1
                    if retries > max_retries:
                        self._log("source gone, giving up (other streams keep running)")
                        break
                    self._log(f"dropped, reconnecting ({retries}/{max_retries})")
                    time.sleep(min(backoff * retries, 10))
                    continue
                retries = 0

                t = frame_idx / fps
                tracks = self.detector.track(frame)
                res = pipe.process(t, tracks)
                for row in res["minute_rows"]:
                    writer.writerow(row)
                    cf.flush()
                for al in res["alerts"]:
                    af.write(json.dumps(al) + "\n")
                    af.flush()
                    self.shared.add_alert(name, al)
                if res["sample"] is not None:
                    occ_writer.writerow(res["sample"])

                totals = pipe.totals()
                meta = {"fps": round(self._fps_est, 1), "t": round(t, 1),
                        "n_people": len(tracks),
                        "has_line": pipe.counter is not None,
                        "has_zones": pipe.alerts is not None}
                if pipe.alerts is not None:
                    meta["queue_n"] = pipe.alerts.queue_n
                    meta["queue_seconds"] = pipe.alerts.q.min_seconds
                    meta["empty_seconds"] = pipe.alerts.e.min_seconds
                self.shared.update(name, {**totals, **meta})

                if self.output_cfg.get("annotated_video") or live_view:
                    vis = frame.copy()
                    if blur:
                        privacy.blur_heads(vis, tracks)
                    annotate.draw(vis, tracks, self.source, totals)
                    if self.output_cfg.get("annotated_video"):
                        if vid is None:
                            h, w = frame.shape[:2]
                            vid = cv2.VideoWriter(os.path.join(outdir, name, "annotated.mp4"),
                                                  cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
                        vid.write(vis)
                    if live_view:
                        h, w = vis.shape[:2]
                        disp = vis if w <= 960 else cv2.resize(vis, (960, int(h * 960 / w)))
                        ok_enc, buf = cv2.imencode(".jpg", disp, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                        if ok_enc:
                            self.shared.set_frame(name, buf.tobytes())

                frame_idx += 1
                dt = time.monotonic() - t_start
                if dt > 0:
                    inst = 1.0 / dt
                    self._fps_est = inst if self._fps_est == 0 else 0.9 * self._fps_est + 0.1 * inst
                if realtime:
                    sleep = (1.0 / fps) - (time.monotonic() - t_start)
                    if sleep > 0:
                        time.sleep(sleep)

            fin = pipe.finalize()
            for row in fin["minute_rows"]:
                writer.writerow(row)
            for al in fin["alerts"]:
                af.write(json.dumps(al) + "\n")
        except Exception as exc:                 # noqa: BLE001 - one worker must not kill the others
            self._log(f"ERROR: {type(exc).__name__}: {exc}")
        finally:
            cf.close()
            af.close()
            occf.close()
            if vid is not None:
                vid.release()
            if cap is not None:
                cap.release()
            tt = pipe.totals()
            self._log(f"done. IN {tt['in']} OUT {tt['out']}")
