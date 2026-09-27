"""Are the shared-across-Python caches found in RQ1 live? Check public CI logs.

For each of the steps flagged `shared_across_python` in results/cache_steps.csv
we looked at a recent successful run of that workflow. This script keeps the
evidence, because GitHub deletes run logs after about 90 days.

  python scripts/check_wild.py fetch     (network: gh + public logs)
      -> data/wild/<owner>__<repo>__run-<id>.json   per job: Python set up,
         cache lines, Python the tests ran on, plus the raw matching lines
  python scripts/check_wild.py table     (offline)
      -> results/wild_summary.json, results/wild_cases.csv

Cases that cannot be settled from logs (the workflow changed, or the cache
path is never populated) are recorded with the reason, from data/wild/notes.json.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
WILD = os.path.join(ROOT, "data", "wild")
RES = os.path.join(ROOT, "results")

# repo, workflow file, job-name prefix, run id checked
RUNS = [
    ("jacebrowning/gitman", "main.yml", "build", "35938984458"),
    ("nextcord/nextcord", "lint.yml", "pyright", "35673493319"),
]
PATTERNS = {
    # setup-python v3+ prints "set up"; v2 printed "setup"
    "setup": re.compile(r"Successfully set ?up CPython \(([\d.]+)\)|^\s*Python (\d+\.\d+\.\d+)\s*$"),
    "cache_restored": re.compile(r"Cache restored from key: (.+)"),
    "cache_not_found": re.compile(r"Cache not found for input keys: (.+)"),
    "path_missing": re.compile(r"Path Validation Error"),
    "tests_on": re.compile(r"platform linux -- Python ([\d.]+)"),
    "installer": re.compile(r"No dependencies to install or update|Installing dependencies from lock file"),
}


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def fetch():
    os.makedirs(WILD, exist_ok=True)
    for repo, wf, prefix, rid in RUNS:
        meta = json.loads(gh("api", f"repos/{repo}/actions/runs/{rid}"))
        jobs = json.loads(gh("api", f"repos/{repo}/actions/runs/{rid}/jobs?per_page=100"))["jobs"]
        out = {"repo": repo, "workflow": wf, "run_id": rid, "run_url": meta["html_url"],
               "created_at": meta["created_at"], "head_sha": meta["head_sha"],
               "conclusion": meta["conclusion"], "jobs": []}
        for j in jobs:
            if not j["name"].startswith(prefix):
                continue
            log = gh("run", "view", "-R", repo, "--job", str(j["id"]), "--log")
            rec = {"name": j["name"], "conclusion": j["conclusion"], "lines": []}
            for line in log.splitlines():
                text = line.split("\t", 2)[-1]
                text = re.sub(r"^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ", "", text)
                for k, pat in PATTERNS.items():
                    m = pat.search(text)
                    if m:
                        rec["lines"].append({"kind": k, "text": text.strip()[:300]})
                        val = next((g for g in m.groups() if g), True) if m.groups() else True
                        rec.setdefault(k, val)
            out["jobs"].append(rec)
        name = f"{repo.replace('/', '__')}__run-{rid}.json"
        with open(os.path.join(WILD, name), "w", newline="\n", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(name, len(out["jobs"]), "jobs")


def table():
    rows = []
    for p in sorted(glob.glob(os.path.join(WILD, "*__run-*.json"))):
        with open(p, encoding="utf-8") as f:
            r = json.load(f)
        for j in r["jobs"]:
            asked, ran = j.get("setup", ""), j.get("tests_on", "")
            rows.append({"repo": r["repo"], "run_url": r["run_url"], "job": j["name"],
                         "job_conclusion": j["conclusion"], "python_set_up": asked,
                         "cache_restored": bool(j.get("cache_restored")),
                         "cache_path_missing": bool(j.get("path_missing")),
                         "tests_ran_on": ran,
                         "wrong_python": bool(asked and ran and asked != ran)})
    with open(os.path.join(RES, "wild_cases.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(WILD, "notes.json"), encoding="utf-8") as f:
        notes = json.load(f)
    live = {r["repo"] for r in rows if r["cache_restored"]}
    wrong = [r for r in rows if r["wrong_python"]]
    summary = {
        "shared_cases_checked": sum(1 for n in notes.values() if n["status"] in ("inert", "undetermined"))
                                + len({r["repo"] for r in rows}),
        "live_shared_caches": len(live),
        "inert_shared_caches": sum(1 for n in notes.values() if n["status"] == "inert")
                               + len({r["repo"] for r in rows if r["cache_path_missing"] and not r["cache_restored"]}),
        "undetermined_shared_caches": sum(1 for n in notes.values() if n["status"] == "undetermined"),
        "wild_jobs_in_live_run": sum(1 for r in rows if r["repo"] in live),
        "wild_jobs_wrong_python": len(wrong),
        "wild_jobs_wrong_python_passed": sum(1 for r in wrong if r["job_conclusion"] == "success"),
        "wild_tests_ran_on": ", ".join(sorted({r["tests_ran_on"] for r in wrong})),
    }
    with open(os.path.join(RES, "wild_summary.json"), "w", newline="\n") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    {"fetch": fetch, "table": table}[sys.argv[1]]()
