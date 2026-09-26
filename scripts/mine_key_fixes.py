"""History of cache keys for built Python environments.

For every workflow file in the sample that caches a built environment, walk
its commit history and find commits that change a cache `key:` line. Classify
each key change:

  adds_interpreter  the new key carries a Python-version signal the old one
                    lacked, or a stronger one (none -> minor -> full)
  manual_bust       the keys differ only in a number (v1 -> v2, cache-3 ->
                    cache-4): the CI equivalent of `make clean`, forcing a
                    rebuild without saying why the old entry went bad
  other             anything else (renames, lockfile changes, restructuring)

  python scripts/mine_key_fixes.py fetch    (network; GitHub REST)
     -> data/raw/key_changes.jsonl
  python scripts/mine_key_fixes.py table    (offline)
     -> results/table4_key_changes.csv, results/table4_summary.json
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from cachekeys.analyze import interp_signal  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(ROOT, "data", "raw")
RES = os.path.join(ROOT, "results")
MAX_COMMITS = 40
RANK = {"none": 0, "version_file": 1, "minor": 1, "full": 2}
KEY_LINE = re.compile(r"^\s*key:\s*(.+?)\s*$")


def _signal(key):
    return interp_signal(key, set(), [], {})[0]


def classify_change(old: str, new: str) -> str:
    if RANK[_signal(new)] > RANK[_signal(old)]:
        return "adds_interpreter"
    if re.sub(r"\d+", "#", old) == re.sub(r"\d+", "#", new) and old != new:
        return "manual_bust"
    return "other"


def key_pairs(patch: str):
    """Pair removed and added `key:` lines inside each hunk, in order."""
    pairs = []
    for hunk in re.split(r"^@@.*@@.*$", patch or "", flags=re.M):
        minus, plus = [], []
        for ln in hunk.splitlines():
            if ln.startswith("-") and KEY_LINE.match(ln[1:]):
                minus.append(KEY_LINE.match(ln[1:]).group(1))
            elif ln.startswith("+") and KEY_LINE.match(ln[1:]):
                plus.append(KEY_LINE.match(ln[1:]).group(1))
        pairs += list(zip(minus, plus))
    return pairs


def fetch():
    from fetch_sample import _req  # noqa: E402
    steps = list(csv.DictReader(open(os.path.join(RES, "cache_steps.csv"), encoding="utf-8")))
    targets = sorted({(s["repo"], s["file"]) for s in steps if s["path_kind"] == "built_env"})
    out = os.path.join(RAW, "key_changes.jsonl")
    done = set()
    if os.path.exists(out):
        done = {(json.loads(l)["repo"], json.loads(l)["file"]) for l in open(out)}
    with open(out, "a", newline="\n") as f:
        for n, (repo, wf) in enumerate(targets):
            if (repo, wf) in done:
                continue
            path = f".github/workflows/{wf}"
            commits, _ = _req(f"https://api.github.com/repos/{repo}/commits?path={path}&per_page={MAX_COMMITS}")
            changes = []
            for c in commits if isinstance(commits, list) else []:
                full, _ = _req(f"https://api.github.com/repos/{repo}/commits/{c['sha']}")
                for fl in full.get("files", []):
                    if fl.get("filename") != path:
                        continue
                    for old, new in key_pairs(fl.get("patch", "")):
                        if old != new:
                            changes.append({"sha": c["sha"], "date": c["commit"]["committer"]["date"],
                                            "message": c["commit"]["message"].splitlines()[0][:200],
                                            "url": c["html_url"], "old": old, "new": new})
            f.write(json.dumps({"repo": repo, "file": wf, "commits_scanned": len(commits)
                                if isinstance(commits, list) else 0, "changes": changes}) + "\n")
            f.flush()
            print(f"{n + 1}/{len(targets)} {repo} {wf}: {len(changes)} key changes", file=sys.stderr)


def table():
    rows = []
    files = 0
    for line in open(os.path.join(RAW, "key_changes.jsonl")):
        r = json.loads(line)
        files += 1
        for c in r["changes"]:
            rows.append({"repo": r["repo"], "file": r["file"], "sha": c["sha"], "date": c["date"][:10],
                         "kind": classify_change(c["old"], c["new"]),
                         "old_signal": _signal(c["old"]), "new_signal": _signal(c["new"]),
                         "old_key": c["old"], "new_key": c["new"], "message": c["message"],
                         "url": c["url"]})
    with open(os.path.join(RES, "table4_key_changes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["repo", "file", "sha", "date", "kind", "old_signal", "new_signal",
                                          "old_key", "new_key", "message", "url"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    kinds = Counter(r["kind"] for r in rows)
    summary = {"workflow_files_scanned": files, "key_changes": len(rows),
               "files_with_any_key_change": len({(r["repo"], r["file"]) for r in rows}),
               **{f"kind_{k}": kinds.get(k, 0) for k in ("adds_interpreter", "manual_bust", "other")},
               "repos_with_adds_interpreter": len({r["repo"] for r in rows if r["kind"] == "adds_interpreter"}),
               "repos_with_manual_bust": len({r["repo"] for r in rows if r["kind"] == "manual_bust"})}
    assert sum(kinds.values()) == len(rows)
    with open(os.path.join(RES, "table4_summary.json"), "w", newline="\n") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    {"fetch": fetch, "table": table}[sys.argv[1]]()
