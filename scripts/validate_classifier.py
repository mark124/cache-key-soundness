"""Check the classifier against hand labels (Table 5).

Two labelling rounds, both kept:
  round 1  data/validation/labels_round1.csv  seed 20260926. The labeller was
           given shortened instructions that left out several built-environment
           cases, so this round mostly measures the instructions. Reported as a
           pilot: results/table5_round1_*.
  round 2  data/validation/labels.csv         seed 20260927, drawn from the
           steps NOT in round 1, labelled with the full rubric shown on every
           card. This is Table 5: results/table5_*.

  python scripts/validate_classifier.py draw   -> data/validation/labels.csv (round 2)
  python scripts/validate_classifier.py        -> score both rounds (offline)
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
from collections import Counter

ROOT = os.path.join(os.path.dirname(__file__), "..")
RES = os.path.join(ROOT, "results")
VAL = os.path.join(ROOT, "data", "validation")
SEED_ROUND2 = 20260927
KEY_COLS = ["repo", "file", "job", "step_index"]


def _steps():
    with open(os.path.join(RES, "cache_steps.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def draw():
    steps = _steps()
    with open(os.path.join(VAL, "labels_round1.csv"), encoding="utf-8") as f:
        seen = {tuple(r[k] for k in KEY_COLS) for r in csv.DictReader(f)}
    pool = [s for s in steps if tuple(s[k] for k in KEY_COLS) not in seen]
    rng = random.Random(SEED_ROUND2)
    order = lambda s: [s[k] for k in KEY_COLS]
    built = sorted((s for s in pool if s["path_kind"] == "built_env"), key=order)
    rest = sorted((s for s in pool if s["path_kind"] != "built_env"), key=order)
    pick = rng.sample(built, min(60, len(built))) + rng.sample(rest, min(40, len(rest)))
    rng.shuffle(pick)
    with open(os.path.join(VAL, "labels.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(KEY_COLS + ["paths", "key", "restore_keys", "label_path_kind", "label_verdict", "label_note"])
        for s in pick:
            w.writerow([s[k] for k in KEY_COLS] + [s["paths"], s["key"].split("  #computed-by:")[0],
                                                    s["restore_keys"], "", "", ""])
    print(f"drew {len(pick)} steps (excluding {len(seen)} from round 1) -> data/validation/labels.csv")


def score(labels_file, prefix):
    path = os.path.join(VAL, labels_file)
    if not os.path.exists(path):
        return
    steps = {tuple(s[k] for k in KEY_COLS): s for s in _steps()}
    with open(path, encoding="utf-8") as f:
        done = [l for l in csv.DictReader(f) if l["label_path_kind"].strip()]
    if not done:
        print(f"{labels_file}: no labels yet")
        return
    rows, summary = [], {}
    for field, lab in (("path_kind", "label_path_kind"), ("verdict", "label_verdict")):
        pairs = [(l[lab].strip(), steps[tuple(l[k] for k in KEY_COLS)][field]) for l in done if l[lab].strip()]
        agree = sum(a == b for a, b in pairs)
        confusion = Counter(f"label {a} / tool {b}" for a, b in pairs if a != b)
        pct = round(100 * agree / len(pairs), 1) if pairs else None
        rows.append({"field": field, "labelled": len(pairs), "agree": agree, "agreement_pct": pct,
                     "disagreements": json.dumps(dict(confusion), sort_keys=True)})
        summary.update({f"{field}_labelled": len(pairs), f"{field}_agree": agree, f"{field}_agreement_pct": pct})
    # verdict agreement restricted to steps both sides call a built environment
    both = [(l["label_verdict"].strip(), steps[tuple(l[k] for k in KEY_COLS)]["verdict"]) for l in done
            if l["label_path_kind"].strip() == "built_env"
            and steps[tuple(l[k] for k in KEY_COLS)]["path_kind"] == "built_env"]
    summary["verdict_both_built_env_n"] = len(both)
    summary["verdict_both_built_env_agree"] = sum(a == b for a, b in both)
    summary["verdict_both_built_env_pct"] = (round(100 * summary["verdict_both_built_env_agree"] / len(both), 1)
                                             if both else None)
    with open(os.path.join(RES, f"{prefix}_validation.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(RES, f"{prefix}_summary.json"), "w", newline="\n") as f:
        json.dump(summary, f, indent=2)
    print(prefix, json.dumps(summary))


if __name__ == "__main__":
    if sys.argv[1:] == ["draw"]:
        draw()
    else:
        score("labels_round1.csv", "table5_round1")
        score("labels.csv", "table5")
