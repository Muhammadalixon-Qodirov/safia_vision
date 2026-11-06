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
    def __init__(self, source, model_cfg, output_cfg, alerts_cfg, sample_hz, detector, shared, stop_event):
        super().__init__(daemon=True, name=source["name"])
        self.source = source
        self.output_cfg = output_cfg
        self.alerts_cfg = alerts_cfg
        self.sample_hz = sample_hz
        self.detector = detector
        self.shared = shared
        self.stop = stop_event
        self._fps_est = 0.0

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
        vid = None

        is_file = _is_file(uri)
        loop = bool(self.source.get("loop", False))
        realtime = bool(self.source.get("realtime", True))
        max_retries = int(self.source.get("max_retries", 10))
        retries = 0
        frame_idx = 0
        fps = 25.0
        cap = None
        try:
            while not self.stop.is_set():
                if cap is None:
                    cap = cv2.VideoCapture(uri)
                    if not cap.isOpened():
                        cap = None
                        retries += 1
                        self._log(f"cannot open (try {retries}/{max_retries})")
                        if retries > max_retries:
                            break
                        time.sleep(min(2 * retries, 10))
                        continue
                    f = cap.get(cv2.CAP_PROP_FPS)
                    fps = f if 1 < f <= 240 else 25.0

                t_start = time.monotonic()
                ok, frame = cap.read()
                if not ok:
                    cap.release()
                    cap = None
                    if is_file and not loop:
                        self._log("end of file")
                        break
                    retries += 1
                    if retries > max_retries:
                        self._log("source gone, giving up (other streams keep running)")
                        break
                    self._log(f"dropped, reconnecting ({retries}/{max_retries})")
                    time.sleep(min(2 * retries, 10))
                    if loop and is_file:
                        frame_idx = 0
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

                totals = pipe.totals()
                self.shared.update(name, {**totals, "fps": round(self._fps_est, 1), "t": round(t, 1)})

                if self.output_cfg.get("annotated_video"):
                    if vid is None:
                        h, w = frame.shape[:2]
                        vid = cv2.VideoWriter(os.path.join(outdir, name, "annotated.mp4"),
                                              cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
                    vis = frame.copy()
                    if self.output_cfg.get("blur_faces", True):
                        privacy.blur_heads(vis, tracks)
                    annotate.draw(vis, tracks, self.source, totals)
                    vid.write(vis)

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
            if vid is not None:
                vid.release()
            if cap is not None:
                cap.release()
            tt = pipe.totals()
            self._log(f"done. IN {tt['in']} OUT {tt['out']}")
