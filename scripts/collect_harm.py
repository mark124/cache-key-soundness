"""Download the outcome artifacts of harm.yml runs and build Table 3.

  python scripts/collect_harm.py fetch RUN_ID [RUN_ID ...]   (needs gh + network)
  python scripts/collect_harm.py table                        (offline)

fetch writes data/harm/run-<id>/outcome-<condition>-<tool>.json, plus
data/harm/run-<id>/run.json (run metadata and URL) so each outcome links to
its public log. table reads only those committed files.

Outcome classes, per (condition, tool, run):
  correct_hit       exact key hit, environment reused as built, tests ran on
                    the requested interpreter        (the cache working)
  correct_miss      exact key missed, environment rebuilt, tests ran on the
                    requested interpreter                    (the fix working)
  self_healed       cache hit, but the tool noticed and rebuilt the
                    environment; tests ran on the requested interpreter
  loud_failure      the test step exited non-zero
  silent_wrong      the test step passed, on a DIFFERENT interpreter than the
                    job asked for
"""
from __future__ import annotations

import csv
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
HARM = os.path.join(ROOT, "data", "harm")
RES = os.path.join(ROOT, "results")
REPO = os.environ.get("CKS_REPO", "mark124/cache-key-soundness")


def fetch(run_ids):
    for rid in run_ids:
        d = os.path.join(HARM, f"run-{rid}")
        os.makedirs(d, exist_ok=True)
        subprocess.run(["gh", "run", "download", rid, "-R", REPO, "-D", d], check=True)
        # gh puts each artifact in its own folder; flatten
        for p in glob.glob(os.path.join(d, "outcome-*", "*.json")):
            os.replace(p, os.path.join(d, os.path.basename(p)))
            os.rmdir(os.path.dirname(p))
        meta = subprocess.run(["gh", "run", "view", rid, "-R", REPO, "--json",
                               "databaseId,url,headSha,createdAt,conclusion,attempt"],
                              capture_output=True, text=True, check=True).stdout
        with open(os.path.join(d, "run.json"), "w", newline="\n") as f:
            f.write(meta)
        print(f"run {rid}: {len(glob.glob(os.path.join(d, 'outcome-*.json')))} outcomes")


LABEL = {"correct_miss": "correct (miss)", "correct_hit": "correct (hit)", "self_healed": "self-healed",
         "loud_failure": "loud failure", "silent_wrong": "silent wrong"}


def classify(o: dict) -> str:
    if o["rc"] != 0:
        return "loud_failure"
    ran = (o.get("probe") or {}).get("version", "")
    if ran and ran != o["leg_actual"]:
        return "silent_wrong"
    if not o["cache_hit"]:
        return "correct_miss"
    # a hit that ran on the Python the environment was built with is a plain,
    # correct cache hit; a hit that ran on a different (requested) Python means
    # the tool noticed and rebuilt the environment itself
    seed = (o.get("seed") or {}).get("python_version", "")
    return "correct_hit" if ran == seed else "self_healed"


def table():
    rows = []
    for p in sorted(glob.glob(os.path.join(HARM, "run-*", "outcome-*.json"))):
        o = json.load(open(p))
        run = json.load(open(os.path.join(os.path.dirname(p), "run.json")))
        rows.append({
            "run_id": run["databaseId"], "run_url": run["url"],
            "condition": o["condition"], "tool": o["tool"],
            "seed_python": (o.get("seed") or {}).get("python_version", ""),
            "leg_requested": o["leg_requested"], "leg_actual": o["leg_actual"],
            "cache_hit": o["cache_hit"], "matched_key": o.get("cache_matched_key", ""),
            "rc": o["rc"], "tests_ran_on": (o.get("probe") or {}).get("version", ""),
            "outcome": classify(o), "image_version": o.get("image_version", ""),
            "file": os.path.relpath(p, ROOT).replace("\\", "/"),
        })
    rows.sort(key=lambda r: (r["condition"], r["tool"], r["run_id"]))
    os.makedirs(RES, exist_ok=True)
    with open(os.path.join(RES, "table3_harm.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    # condition x tool matrix (one cell per pair; runs must agree, else "mixed")
    from collections import Counter, defaultdict
    cell = defaultdict(set)
    for r in rows:
        cell[(r["condition"], r["tool"])].add(r["outcome"])
    conds = sorted({r["condition"] for r in rows})
    with open(os.path.join(RES, "table3_matrix.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["condition", "pip", "poetry", "uv"])
        for c in conds:
            w.writerow([c] + ["/".join(sorted(LABEL[o] for o in cell[(c, t)])) or "-" for t in ("pip", "poetry", "uv")])
    oc = Counter(r["outcome"] for r in rows)
    summary = {"runs": len({r["run_id"] for r in rows}), "outcomes": len(rows),
               **{f"n_{k}": oc.get(k, 0) for k in ("correct_miss", "correct_hit", "self_healed", "loud_failure", "silent_wrong")},
               "pairs_inconsistent_across_runs": sum(1 for v in cell.values() if len(v) > 1)}
    for r in rows:
        summary.setdefault(f'{r["condition"]}_{r["tool"]}_outcome', r["outcome"])
        summary.setdefault(f'{r["condition"]}_{r["tool"]}_ran_on', r["tests_ran_on"])
        summary.setdefault(f'{r["condition"]}_{r["tool"]}_asked', r["leg_actual"])
        summary.setdefault(f'{r["condition"]}_seed_python', r["seed_python"])
    with open(os.path.join(RES, "table3_summary.json"), "w", newline="\n") as f:
        json.dump(summary, f, indent=2)
    for r in rows:
        print(f'{r["condition"]} {r["tool"]:6} hit={r["cache_hit"]!s:5} rc={r["rc"]:<3} '
              f'asked={r["leg_actual"]:8} ran={r["tests_ran_on"]:8} -> {r["outcome"]}')


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(sys.argv[2:])
    table() if sys.argv[1] in ("table", "fetch") else None
