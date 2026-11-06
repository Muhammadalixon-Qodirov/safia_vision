"""Compare the system's output against your own hand labels and print Markdown
tables for the README. Honest measurement is graded, so the labels are yours:
fill the three templates in measurement/hand/, run the system, then run this.

    python measurement/compare.py --output output --hand measurement/hand

Produces: door-count errors, queue MAE, and alert found/missed/wrong, plus a
speed table you fill from the run log and the failure-case list you write.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _read_csv(p: Path):
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def door_counts(out: Path, hand: Path) -> str:
    hand_rows = {r["source"]: r for r in _read_csv(hand / "door_counts.csv")}
    lines = ["### Door counts vs hand count", "",
             "| Source | hand IN | sys IN | IN err | hand OUT | sys OUT | OUT err |",
             "|---|---|---|---|---|---|---|"]
    for src, hr in hand_rows.items():
        rows = _read_csv(out / f"{src}_minutes.csv")
        sin = sum(int(_num(r["in"])) for r in rows)
        sout = sum(int(_num(r["out"])) for r in rows)
        hin, hout = _num(hr.get("hand_in")), _num(hr.get("hand_out"))
        lines.append(f"| {src} | {hin:g} | {sin} | {sin - hin:+g} | {hout:g} | {sout} | {sout - hout:+g} |")
    return "\n".join(lines)


def queue_mae(out: Path, hand: Path) -> str:
    labels = _read_csv(hand / "queue_labels.csv")
    by_src: dict[str, list] = {}
    for r in labels:
        if r.get("hand_queue", "").strip() == "":
            continue
        by_src.setdefault(r["source"], []).append((_num(r["t_seconds"]), _num(r["hand_queue"])))
    lines = ["### Queue count - mean absolute error", "",
             "| Source | labelled points | MAE (people) |", "|---|---|---|"]
    for src, pts in by_src.items():
        occ = [(_num(r["t"]), _num(r["queue"])) for r in _read_csv(out / f"{src}_occupancy.csv")
               if r.get("queue", "").strip() != ""]
        if not occ:
            lines.append(f"| {src} | {len(pts)} | no system occupancy log |")
            continue
        errs = []
        for t, hv in pts:
            sv = min(occ, key=lambda o: abs(o[0] - t))[1]   # nearest system sample
            errs.append(abs(sv - hv))
        mae = sum(errs) / len(errs) if errs else 0.0
        lines.append(f"| {src} | {len(pts)} | {mae:.2f} |")
    return "\n".join(lines)


def _overlap(a0, a1, b0, b1, tol):
    return a0 - tol <= b1 and b0 - tol <= a1


def alerts(out: Path, hand: Path, tol: float = 5.0) -> str:
    expected = _read_csv(hand / "expected_alerts.csv")
    exp_by_src: dict[str, list] = {}
    for r in expected:
        exp_by_src.setdefault(r["source"], []).append(
            (r["type"], _num(r.get("start_seconds")), _num(r.get("end_seconds"))))
    lines = ["### Alerts - expected vs system", "",
             "| Source | type | expected | found | missed | wrong (extra) |",
             "|---|---|---|---|---|---|"]
    srcs = set(exp_by_src)
    for src in sorted(srcs):
        sys_alerts = [json.loads(ln) for ln in
                      (out / f"{src}_alerts.jsonl").read_text(encoding="utf-8").splitlines()
                      if ln.strip()] if (out / f"{src}_alerts.jsonl").exists() else []
        for atype in ("queue", "empty_counter"):
            exp = [e for e in exp_by_src.get(src, []) if e[0] == atype]
            sysa = [s for s in sys_alerts if s["type"] == atype]
            matched_sys = set()
            found = 0
            for _, e0, e1 in exp:
                hit = next((i for i, s in enumerate(sysa)
                            if i not in matched_sys and _overlap(e0, e1, s["start"], s["end"], tol)), None)
                if hit is not None:
                    matched_sys.add(hit)
                    found += 1
            missed = len(exp) - found
            wrong = len(sysa) - len(matched_sys)
            if exp or sysa:
                lines.append(f"| {src} | {atype} | {len(exp)} | {found} | {missed} | {wrong} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="output")
    ap.add_argument("--hand", default="measurement/hand")
    ap.add_argument("--write", default="measurement/RESULTS.md")
    args = ap.parse_args()
    out, hand = Path(args.output), Path(args.hand)
    parts = [door_counts(out, hand), "", queue_mae(out, hand), "", alerts(out, hand)]
    text = "\n".join(parts) + "\n"
    print(text)
    Path(args.write).write_text(text, encoding="utf-8")
    print(f"(written to {args.write})")


if __name__ == "__main__":
    main()
