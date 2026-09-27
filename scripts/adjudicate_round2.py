"""Write data/validation/adjudication_round2.csv: every round-2 disagreement
between the hand label and the classifier, the line of RUBRIC.md it turns on,
and which side that line supports.

The resolution is a judgement, made by the tool's author against the written
rubric, so it is not independent. It is committed row by row so a reader can
check each call. The classifier was NOT changed after seeing these labels.

  python scripts/adjudicate_round2.py
"""
from __future__ import annotations

import csv
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
VAL = os.path.join(ROOT, "data", "validation")
RES = os.path.join(ROOT, "results")
KEY_COLS = ["repo", "file", "job", "step_index"]

# Calls that cannot be made by a pattern: (repo, file, job, step_index, field) -> (rule, resolution)
MANUAL = {
    "~/.local/bin/claude": ("built_env lists ~/.local/bin as pip --user output; this path is the "
                            "Claude Code CLI, not a Python environment. The rule is too broad.",
                            "classifier_error"),
}
UNDECIDABLE_MATRIX = ("verdict: the key uses a matrix value, but this job has no matrix in the "
                      "workflow file (it is set elsewhere), so its values cannot be read.",
                      "undecidable")


def path_rule(paths: str, label: str, tool: str):
    for needle, call in MANUAL.items():
        if needle in paths:
            return call
    parts = [p.strip() for p in paths.split("|")]
    if tool == "built_env" and len(parts) > 1:
        return ("path_kind: several folders listed and one is a built environment; "
                "'if any one is built_env, pick built_env'.", "tool_follows_rubric")
    if tool == "built_env" and "pythonLocation" in paths:
        return ("built_env lists pythonLocation (the interpreter's own install folder).", "tool_follows_rubric")
    if tool == "built_env":
        return ("built_env lists this folder.", "tool_follows_rubric")
    if tool == "download_store" and re.search(r"pip|uv", paths, re.I):
        return ("download_store lists pip and uv download caches.", "tool_follows_rubric")
    if tool == "other":
        return ("other: not a Python environment and not a pip/uv/poetry download cache "
                "(pre-commit, Hugging Face, Playwright, yarn, the whole ~/.cache, build output).",
                "tool_follows_rubric")
    return ("no rubric line decides this case.", "undecidable")


def verdict_rule(key: str, detail: str, has_matrix: bool, label: str, tool: str):
    if "matrix" in detail and not has_matrix:
        return UNDECIDABLE_MATRIX
    if "pythonLocation" in key or "pythonLocation" in detail:
        return ("sound lists pythonLocation.", "tool_follows_rubric")
    if "matrix" in detail:
        return ("minor_only: a matrix value whose list holds minor versions like 3.12.", "tool_follows_rubric")
    if detail.startswith("literal:"):
        return ("minor_only lists py313-style literals.", "tool_follows_rubric")
    return ("no rubric line decides this case.", "undecidable")


def main():
    import gzip
    import json
    import yaml
    steps = {tuple(s[k] for k in KEY_COLS): s
             for s in csv.DictReader(open(os.path.join(RES, "cache_steps.csv"), encoding="utf-8"))}
    texts = {}
    with gzip.open(os.path.join(ROOT, "data", "raw", "cache_workflows.jsonl.gz"), "rt", encoding="utf-8") as f:
        for line in f:
            w = json.loads(line)
            texts[(w["repo"], w["file"])] = w["text"]
    out = []
    for l in csv.DictReader(open(os.path.join(VAL, "labels.csv"), encoding="utf-8")):
        s = steps[tuple(l[k] for k in KEY_COLS)]
        base = {k: l[k] for k in KEY_COLS}
        if l["label_path_kind"] != s["path_kind"]:
            rule, res = path_rule(s["paths"], l["label_path_kind"], s["path_kind"])
            out.append({**base, "field": "path_kind", "label": l["label_path_kind"], "tool": s["path_kind"],
                        "paths": s["paths"], "key": s["key"].split("  #computed-by:")[0],
                        "rubric_line": rule, "resolution": res})
        elif s["path_kind"] == "built_env" and l["label_verdict"] != s["verdict"]:
            doc = yaml.safe_load(texts[(l["repo"], l["file"])])
            job = (doc.get("jobs") or {}).get(l["job"]) or {}
            has_matrix = bool((job.get("strategy") or {}).get("matrix"))
            rule, res = verdict_rule(s["key"], s["interp_signal_detail"], has_matrix, l["label_verdict"], s["verdict"])
            out.append({**base, "field": "verdict", "label": l["label_verdict"], "tool": s["verdict"],
                        "paths": s["paths"], "key": s["key"].split("  #computed-by:")[0],
                        "rubric_line": rule, "resolution": res})
    with open(os.path.join(VAL, "adjudication_round2.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    print(len(out), Counter(r["resolution"] for r in out))


if __name__ == "__main__":
    main()
