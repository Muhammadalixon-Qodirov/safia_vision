"""One command to run everything:

    python run.py                          # uses config/config.yaml
    python run.py --config my.yaml --web   # also serve the live page

Processes every source in the config concurrently and writes per-minute CSVs and
alert JSONL files into the output directory. Ctrl-C stops cleanly.
"""
from __future__ import annotations

import argparse
import threading
import time

from analytics.config import load_config
from analytics.service import start_service
from analytics.state import SharedState


def main():
    ap = argparse.ArgumentParser(description="Store camera analytics")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--web", action="store_true", help="serve a live counts/alerts page")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    cfg = load_config(args.config)
    shared = SharedState()
    stop = threading.Event()
    workers, _, _ = start_service(cfg, shared, stop)
    print(f"started {len(workers)} stream(s); outputs -> {cfg['output']['dir']}", flush=True)

    if args.web:
        from app.web import serve
        threading.Thread(target=serve, args=(shared, args.host, args.port), daemon=True).start()
        print(f"live page: http://{args.host}:{args.port}", flush=True)

    try:
        while any(w.is_alive() for w in workers):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nstopping...", flush=True)
        stop.set()
    for w in workers:
        w.join(timeout=15)
    print(f"all streams finished. outputs in {cfg['output']['dir']}", flush=True)


if __name__ == "__main__":
    main()
