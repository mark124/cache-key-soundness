"""Timing experiment (bench.yml) -> Table 4.

  python scripts/collect_bench.py fetch RUN_ID     (needs gh + network)
  python scripts/collect_bench.py table            (offline)

fetch writes data/bench/run-<id>/bench-<tool>-<mode>-<rep>.json and run.json.
table writes
  results/table4_bench.csv       one row per tool x mode: median, min, max seconds
  results/table4_bench_raw.csv   every timed job
  results/table4_summary.json    numbers quoted in the text
"""
from __future__ import annotations

import csv
import glob
import shutil
import json
import os
import statistics
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
BENCH = os.path.join(ROOT, "data", "bench")
RES = os.path.join(ROOT, "results")
REPO = os.environ.get("CKS_REPO", "mark124/cache-key-soundness")
TOOLS = ["pip", "poetry", "uv"]
MODES = ["none", "download", "venv"]


def fetch(rid):
    d = os.path.join(BENCH, f"run-{rid}")
    os.makedirs(d, exist_ok=True)
    subprocess.run(["gh", "run", "download", rid, "-R", REPO, "-p", "bench-*", "-D", d], check=True)
    for p in glob.glob(os.path.join(d, "bench-*", "*.json")):
        os.replace(p, os.path.join(d, os.path.basename(p)))
        shutil.rmtree(os.path.dirname(p), ignore_errors=True)
    meta = subprocess.run(["gh", "run", "view", rid, "-R", REPO, "--json",
                           "databaseId,url,headSha,createdAt,conclusion"],
                          capture_output=True, text=True, check=True).stdout
    with open(os.path.join(d, "run.json"), "w", newline="\n") as f:
        f.write(meta)


def table():
    recs = []
    for p in sorted(glob.glob(os.path.join(BENCH, "run-*", "bench-*.json"))):
        with open(p) as f:
            recs.append(json.load(f))
    os.makedirs(RES, exist_ok=True)
    with open(os.path.join(RES, "table4_bench_raw.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tool", "mode", "rep", "seconds", "cache_hit", "run_id", "image_version"],
                           lineterminator="\n")
        w.writeheader()
        for r in sorted(recs, key=lambda r: (r["tool"], MODES.index(r["mode"]), r["rep"])):
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    rows, summary = [], {"timed_jobs": len(recs)}
    for t in TOOLS:
        for m in MODES:
            xs = [r["seconds"] for r in recs if r["tool"] == t and r["mode"] == m]
            if not xs:
                continue
            med = round(statistics.median(xs), 1)
            rows.append({"tool": t, "mode": m, "n": len(xs), "median_s": med,
                         "min_s": round(min(xs), 1), "max_s": round(max(xs), 1)})
            summary[f"{t}_{m}_median_s"] = med
        if f"{t}_venv_median_s" in summary and f"{t}_download_median_s" in summary:
            summary[f"{t}_download_minus_venv_s"] = round(summary[f"{t}_download_median_s"]
                                                         - summary[f"{t}_venv_median_s"], 1)
    with open(os.path.join(RES, "table4_bench.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tool", "mode", "n", "median_s", "min_s", "max_s"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(RES, "table4_summary.json"), "w", newline="\n") as f:
        json.dump(summary, f, indent=2)
    for r in rows:
        print(r)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(sys.argv[2])
    table()
