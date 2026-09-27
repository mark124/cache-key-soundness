"""python -m cachekeys lint [PATH ...]    check workflow files (default .github/workflows)
python -m cachekeys reproduce           regenerate every file under results/ offline
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys

from .analyze import analyze_workflow

ADVICE = {
    "minor_only": "the key carries only the minor Python version; a patch release changes the "
                  "interpreter the cached environment links to. Put ${{ env.pythonLocation }} in the "
                  "key (exact version and CPU architecture).",
    "no_interpreter": "the key carries no Python version; the cached environment can be restored "
                      "under a different interpreter. Put ${{ env.pythonLocation }} in the key "
                      "(exact version and CPU architecture).",
}


def lint(paths: list[str]) -> int:
    files = []
    for p in paths or [".github/workflows"]:
        files += sorted(glob.glob(os.path.join(p, "*.y*ml"))) if os.path.isdir(p) else [p]
    problems = 0
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for c in analyze_workflow(fh.read(), f):
                where = f"{f}: job '{c.job}', step {c.step_index + 1}"
                if c.verdict in ADVICE:
                    problems += 1
                    sev = "error" if c.skip_on_hit else "warning"
                    print(f"{where}: {sev}: cached environment {c.paths} — {ADVICE[c.verdict]}"
                          + (" Installation is skipped on a cache hit, so the stale environment "
                             "is used as-is." if c.skip_on_hit else ""))
                if c.restore_key_drops_interp:
                    problems += 1
                    print(f"{where}: warning: a restore-keys prefix omits the Python version, so a "
                          f"miss can restore an environment built for another interpreter.")
    print(f"{len(files)} file(s), {problems} finding(s)")
    return 1 if problems else 0


def reproduce() -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for script in ["scripts/analyze_sample.py", "scripts/collect_harm.py table", "scripts/collect_bench.py table",
                   "scripts/adjudicate_round2.py", "scripts/validate_classifier.py", "scripts/mine_key_fixes.py table"]:
        parts = script.split()
        path = os.path.join(here, parts[0])
        if not os.path.exists(path):
            print(f"skip {parts[0]} (not present)")
            continue
        print(f"== {script}")
        subprocess.run([sys.executable, path] + parts[1:], check=True, cwd=here)
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("lint", "reproduce"):
        print(__doc__)
        return 2
    return lint(argv[1:]) if argv[0] == "lint" else reproduce()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
