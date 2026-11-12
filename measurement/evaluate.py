"""Compare a measurement run with the ground truth in measurement/hand/labels.json and
write the README tables to measurement/RESULTS.md.

    python run.py --config config/measure.yaml        # every frame of every clip
    python measurement/evaluate.py                     # -> measurement/RESULTS.md

Door: each labelled crossing is matched one-to-one to a system crossing in the same
direction within +-2 s (system times come from the per-second occupancy log).
Queue: error at each labelled time = distance from the system count to the labelled
[low, high] range (0 inside it). Alerts: a system episode matches an expected one of
the same type if they overlap (5 s tolerance); unmatched system episodes are "wrong".
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

TOL_DOOR = 2.0
TOL_ALERT = 5.0


def occupancy(out: Path, src: str) -> list[dict]:
    p = out / f"{src}_occupancy.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return [{"t": float(r["t"]), "queue": r["queue"], "staff": r["staff"],
                 "in": int(r["in"] or 0), "out": int(r["out"] or 0)} for r in csv.DictReader(f)]


def crossings(occ: list[dict]) -> list[tuple[float, str]]:
    """(time, direction) per system crossing. The 1 Hz log only shows that the count
    went up between two samples, so each event gets the EARLIER sample's time; with
    the +-2 s tolerance that covers the whole interval it happened in."""
    ev, pi, po, pt = [], 0, 0, 0.0
    for r in occ:
        ev += [(pt, "in")] * (r["in"] - pi) + [(pt, "out")] * (r["out"] - po)
        pi, po, pt = r["in"], r["out"], r["t"]
    return ev


def door_table(out: Path, labels: dict) -> list[str]:
    rows = ["| Clip | direction | hand count | system | matched (+-2 s) | missed | extra |",
            "|---|---|---|---|---|---|---|"]
    notes = []
    for src, d in labels["door"].items():
        sys_ev = crossings(occupancy(out, src))
        for direction in ("in", "out"):
            truth = [e["t"] for e in d["events"] if e["dir"] == direction]
            sysd = [t for t, k in sys_ev if k == direction]
            used, hit = set(), 0
            for t in truth:
                j = next((i for i, s in enumerate(sysd) if i not in used and abs(s - t) <= TOL_DOOR), None)
                if j is not None:
                    used.add(j)
                    hit += 1
            extra = [round(s) for i, s in enumerate(sysd) if i not in used]
            missed = [t for t in truth if not any(abs(sysd[i] - t) <= TOL_DOOR for i in used)]
            rows.append(f"| {src} | {direction.upper()} | {len(truth)} | {len(sysd)} | {hit} | "
                        f"{len(truth) - hit} | {len(sysd) - len(used)} |")
            if extra:
                notes.append(f"{src} {direction.upper()} extra at {extra} s")
            if len(truth) - hit:
                notes.append(f"{src} {direction.upper()} missed near {missed[:len(truth) - hit]} s")
    return rows + [""] + [f"- {n}" for n in notes]


def queue_table(out: Path, labels: dict) -> list[str]:
    rows = ["| Clip | labelled points | span | MAE (people) | exact (inside range) | worst |",
            "|---|---|---|---|---|---|"]
    for src, q in labels["queue"].items():
        occ = [r for r in occupancy(out, src) if r["queue"] != ""]
        if not occ:
            continue
        errs = []
        for t, (lo, hi) in q["points"].items():
            t = float(t)
            n = int(min(occ, key=lambda r: abs(r["t"] - t))["queue"])
            e = 0 if lo <= n <= hi else (n - hi if n > hi else n - lo)
            errs.append((t, e))
        mae = sum(abs(e) for _, e in errs) / len(errs)
        exact = sum(e == 0 for _, e in errs)
        worst = max(errs, key=lambda x: abs(x[1]))
        span = f"{min(t for t, _ in errs):.0f}-{max(t for t, _ in errs):.0f} s"
        rows.append(f"| {src} | {len(errs)} | {span} | {mae:.2f} | {exact}/{len(errs)} | "
                    f"{worst[1]:+d} at {worst[0]:.0f} s |")
    return rows


def alert_table(out: Path, labels: dict) -> list[str]:
    rows = ["| Clip | type | expected | system | found | missed | wrong |", "|---|---|---|---|---|---|---|"]
    detail = []
    for src in ("shop1", "market"):
        exp = labels["alerts"].get(src, [])
        p = out / f"{src}_alerts.jsonl"
        sysa = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
        for atype in ("queue", "empty_counter"):
            e = [a for a in exp if a["type"] == atype]
            s = [a for a in sysa if a["type"] == atype]
            used, found = set(), 0
            for a in e:
                j = next((i for i, b in enumerate(s) if i not in used
                          and a["start"] - TOL_ALERT <= b["end"] and b["start"] - TOL_ALERT <= a["end"]), None)
                if j is not None:
                    used.add(j)
                    found += 1
            rows.append(f"| {src} | {atype} | {len(e)} | {len(s)} | {found} | {len(e) - found} | {len(s) - len(used)} |")
            for b in s:
                detail.append(f"{src} {atype}: system {b['start']:.0f}-{b['end']:.0f} s, peak {b['peak']}")
            for a in e:
                detail.append(f"{src} {atype}: expected {a['start']}-{a['end']} s")
    return rows + [""] + [f"- {d}" for d in sorted(detail)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="output_measure")
    ap.add_argument("--labels", default="measurement/hand/labels.json")
    ap.add_argument("--write", default="measurement/RESULTS.md")
    a = ap.parse_args()
    out, labels = Path(a.output), json.loads(Path(a.labels).read_text(encoding="utf-8"))
    text = "\n".join(["## Door (IN / OUT)", ""] + door_table(out, labels)
                     + ["", "## Queue count", ""] + queue_table(out, labels)
                     + ["", "## Alerts", ""] + alert_table(out, labels)) + "\n"
    print(text)
    Path(a.write).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
