"""Offline: classify every cache step in the committed sample and write the
tables the paper reports. Reads only committed files under data/raw/.

  results/cache_steps.csv                    one row per actions/cache step
  results/table1_sample.csv                  sample and prevalence, by stratum
  results/table2_key_composition.csv         verdicts for built-environment caches
  results/table2_repo_level.csv              the same, counted per repository
  results/headline.json                      every number quoted in the text
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cachekeys.analyze import analyze_workflow  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(ROOT, "data", "raw")
RES = os.path.join(ROOT, "results")
STRATA = ["s1", "s2", "s3", "s4"]
STRATUM_LABEL = {"s1": "10-99", "s2": "100-999", "s3": "1,000-9,999", "s4": "10,000+"}
VERDICTS = ["sound", "minor_only", "no_interpreter", "version_file"]


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    os.makedirs(RES, exist_ok=True)
    manifest = [json.loads(l) for l in open(os.path.join(RAW, "manifest.jsonl"))]
    by_repo = {m["repo"]: m for m in manifest}

    steps = []
    with gzip.open(os.path.join(RAW, "cache_workflows.jsonl.gz"), "rt", encoding="utf-8") as f:
        seen = set()
        for line in f:
            w = json.loads(line)
            ident = (w["repo"], w["file"])
            if ident in seen:          # a resumed fetch may repeat a line
                continue
            seen.add(ident)
            for c in analyze_workflow(w["text"], w["file"]):
                row = c.row()
                row["repo"] = w["repo"]
                row["sha"] = w["sha"]
                row["stratum"] = by_repo[w["repo"]]["stratum"]
                steps.append(row)

    fields = ["repo", "stratum", "sha", "file", "job", "step_index", "step_id", "uses", "paths",
              "key", "restore_keys", "skip_on_hit", "path_kind", "path_pins_interpreter",
              "interp_signal", "interp_signal_detail", "deps_hashed", "os_signal",
              "restore_key_drops_interp", "verdict", "notes"]
    steps.sort(key=lambda r: (r["repo"], r["file"], r["job"], r["step_index"]))
    write_csv(os.path.join(RES, "cache_steps.csv"), steps, fields)

    # ---- Table 1: sample and prevalence -----------------------------------
    t1 = []
    repos_cache = defaultdict(set)
    repos_built = defaultdict(set)
    for s in steps:
        repos_cache[s["stratum"]].add(s["repo"])
        if s["path_kind"] == "built_env":
            repos_built[s["stratum"]].add(s["repo"])
    tot = Counter()
    for st in STRATA + ["all"]:
        ms = [m for m in manifest if st == "all" or m["stratum"] == st]
        ok = [m for m in ms if "error" not in m]
        wf = [m for m in ok if m.get("workflows")]
        rc = set().union(*(repos_cache[x] for x in (STRATA if st == "all" else [st])))
        rb = set().union(*(repos_built[x] for x in (STRATA if st == "all" else [st])))
        t1.append({"stratum": st, "stars": STRATUM_LABEL.get(st, "all"),
                   "sampled": len(ms), "retrieved": len(ok), "with_workflows": len(wf),
                   "with_actions_cache": len(rc), "caching_built_python_env": len(rb),
                   "pct_of_workflow_repos_caching_built_env": pct(len(rb), len(wf))})
    write_csv(os.path.join(RES, "table1_sample.csv"), t1, list(t1[0].keys()))

    # ---- Table 2: key composition of built-environment caches -------------
    built = [s for s in steps if s["path_kind"] == "built_env"]
    t2 = []
    for v in VERDICTS:
        vs = [s for s in built if s["verdict"] == v]
        skip = [s for s in vs if s["skip_on_hit"]]
        t2.append({"verdict": v, "steps": len(vs), "pct_steps": pct(len(vs), len(built)),
                   "with_skip_on_hit": len(skip),
                   "with_deps_hash": sum(1 for s in vs if s["deps_hashed"]),
                   "with_os_signal": sum(1 for s in vs if s["os_signal"]),
                   "restore_keys_drop_interpreter": sum(1 for s in vs if s["restore_key_drops_interp"])})
    t2.append({"verdict": "total", "steps": len(built), "pct_steps": 100.0 if built else None,
               "with_skip_on_hit": sum(1 for s in built if s["skip_on_hit"]),
               "with_deps_hash": sum(1 for s in built if s["deps_hashed"]),
               "with_os_signal": sum(1 for s in built if s["os_signal"]),
               "restore_keys_drop_interpreter": sum(1 for s in built if s["restore_key_drops_interp"])})
    assert sum(r["steps"] for r in t2[:-1]) == t2[-1]["steps"], "verdicts must sum to total"
    write_csv(os.path.join(RES, "table2_key_composition.csv"), t2, list(t2[0].keys()))

    # repository level: a repo is exposed if any built-env cache it has is
    # unsound (minor_only / no_interpreter) AND skips install on a hit
    repo_rows = []
    for repo in sorted({s["repo"] for s in built}):
        rs = [s for s in built if s["repo"] == repo]
        repo_rows.append({
            "repo": repo, "stratum": rs[0]["stratum"], "built_env_steps": len(rs),
            "any_unsound": any(s["verdict"] in ("minor_only", "no_interpreter") for s in rs),
            "exposed": any(s["verdict"] in ("minor_only", "no_interpreter") and s["skip_on_hit"] for s in rs),
            "any_restore_key_fallback_hazard": any(s["restore_key_drops_interp"] for s in rs),
        })
    write_csv(os.path.join(RES, "table2_repo_level.csv"), repo_rows,
              ["repo", "stratum", "built_env_steps", "any_unsound", "exposed",
               "any_restore_key_fallback_hazard"])

    unsound = [s for s in built if s["verdict"] in ("minor_only", "no_interpreter")]
    headline = {
        "repos_sampled": t1[-1]["sampled"],
        "repos_with_workflows": t1[-1]["with_workflows"],
        "repos_with_actions_cache": t1[-1]["with_actions_cache"],
        "repos_caching_built_env": t1[-1]["caching_built_python_env"],
        "cache_steps_total": len(steps),
        "built_env_steps": len(built),
        "download_store_steps": sum(1 for s in steps if s["path_kind"] == "download_store"),
        "unsound_steps": len(unsound),
        "unsound_pct_of_built": pct(len(unsound), len(built)),
        "unsound_with_skip": sum(1 for s in unsound if s["skip_on_hit"]),
        "unsound_with_skip_pct_of_built": pct(sum(1 for s in unsound if s["skip_on_hit"]), len(built)),
        "repos_any_unsound": sum(1 for r in repo_rows if r["any_unsound"]),
        "repos_exposed": sum(1 for r in repo_rows if r["exposed"]),
        "repos_exposed_pct_of_built_env_repos": pct(sum(1 for r in repo_rows if r["exposed"]), len(repo_rows)),
        "minor_only_steps": sum(1 for s in built if s["verdict"] == "minor_only"),
        "no_interpreter_steps": sum(1 for s in built if s["verdict"] == "no_interpreter"),
        "sound_steps": sum(1 for s in built if s["verdict"] == "sound"),
        "version_file_steps": sum(1 for s in built if s["verdict"] == "version_file"),
        "unsound_with_restore_keys": sum(1 for s in unsound if s["restore_keys"]),
        "unsound_with_skip_or_restore_keys": sum(1 for s in unsound if s["skip_on_hit"] or s["restore_keys"]),
        "sound_with_skip": sum(1 for s in built if s["verdict"] == "sound" and s["skip_on_hit"]),
        "pct_workflow_repos_caching_built_env": t1[-1]["pct_of_workflow_repos_caching_built_env"],
        "frame_size": sum(1 for _ in open(os.path.join(RAW, "frame.jsonl"))),
        "repos_any_unsound_pct_of_built_env_repos": pct(sum(1 for r in repo_rows if r["any_unsound"]), len(repo_rows)),
        "sound_steps_with_restore_key_fallback_hazard": sum(
            1 for s in built if s["verdict"] == "sound" and s["restore_key_drops_interp"]),
    }
    with open(os.path.join(RES, "headline.json"), "w", newline="\n") as f:
        json.dump(headline, f, indent=2)
    print(json.dumps(headline, indent=2))


if __name__ == "__main__":
    main()
