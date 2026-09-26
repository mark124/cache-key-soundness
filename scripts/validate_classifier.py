"""Check the classifier against hand labels.

  python scripts/validate_classifier.py draw   -> data/validation/labels.csv
      Seeded random sample of 100 cache steps (60 classified as built
      environments, 40 not), with blank label columns. A person fills in
      `label_path_kind` and `label_verdict` using RUBRIC.md, reading only the
      path, key and workflow text, never the tool's columns (they are hidden
      in the file on purpose).
  python scripts/validate_classifier.py        -> results/table4_validation.csv
      (offline) agreement between labels and classifier, per field.
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
SEED = 20260926
KEY_COLS = ["repo", "file", "job", "step_index"]


def draw():
    steps = list(csv.DictReader(open(os.path.join(RES, "cache_steps.csv"), encoding="utf-8")))
    rng = random.Random(SEED)
    built = sorted((s for s in steps if s["path_kind"] == "built_env"), key=lambda s: [s[k] for k in KEY_COLS])
    rest = sorted((s for s in steps if s["path_kind"] != "built_env"), key=lambda s: [s[k] for k in KEY_COLS])
    pick = rng.sample(built, min(60, len(built))) + rng.sample(rest, min(40, len(rest)))
    rng.shuffle(pick)
    os.makedirs(VAL, exist_ok=True)
    with open(os.path.join(VAL, "labels.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(KEY_COLS + ["paths", "key", "restore_keys", "label_path_kind", "label_verdict", "label_note"])
        for s in pick:
            w.writerow([s[k] for k in KEY_COLS] + [s["paths"], s["key"].split("  #computed-by:")[0],
                                                    s["restore_keys"], "", "", ""])
    print(f"drew {len(pick)} steps -> data/validation/labels.csv")


def score():
    steps = {tuple(s[k] for k in KEY_COLS): s
             for s in csv.DictReader(open(os.path.join(RES, "cache_steps.csv"), encoding="utf-8"))}
    labels = list(csv.DictReader(open(os.path.join(VAL, "labels.csv"), encoding="utf-8")))
    done = [l for l in labels if l["label_path_kind"].strip()]
    if not done:
        print("no labels yet: fill data/validation/labels.csv (see data/validation/RUBRIC.md)")
        return
    rows = []
    for field, lab in (("path_kind", "label_path_kind"), ("verdict", "label_verdict")):
        pairs = [(l[lab].strip(), steps[tuple(l[k] for k in KEY_COLS)][field]) for l in done
                 if l[lab].strip()]
        agree = sum(a == b for a, b in pairs)
        confusion = Counter(f"{a}->{b}" for a, b in pairs if a != b)
        rows.append({"field": field, "labelled": len(pairs), "agree": agree,
                     "agreement_pct": round(100 * agree / len(pairs), 1) if pairs else None,
                     "disagreements": json.dumps(dict(confusion), sort_keys=True)})
    with open(os.path.join(RES, "table4_validation.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    summary = {}
    for r in rows:
        summary[f'{r["field"]}_labelled'] = r["labelled"]
        summary[f'{r["field"]}_agree'] = r["agree"]
        summary[f'{r["field"]}_agreement_pct'] = r["agreement_pct"]
        print(r)
    with open(os.path.join(RES, "table4_summary.json"), "w", newline="\n") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    draw() if sys.argv[1:] == ["draw"] else score()
