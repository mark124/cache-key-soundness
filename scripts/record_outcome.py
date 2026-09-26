"""Write one experiment outcome as JSON. Runs under the runner's system
python (/usr/bin/python3) so it does not depend on the environment under test.

usage: record_outcome.py OUT RC LOGFILE
Reads the rest of its inputs from environment variables set by harm.yml.
"""
import json
import os
import sys

out, rc, logfile = sys.argv[1], int(sys.argv[2]), sys.argv[3]
env = os.environ

probe = None
if os.path.exists(env["PROBE_OUT"]):
    with open(env["PROBE_OUT"]) as f:
        probe = json.load(f)

seed = None
seed_path = os.path.join("fixture", ".venv", ".seedinfo.json")
if os.path.exists(seed_path):
    with open(seed_path) as f:
        seed = json.load(f)

with open(logfile, errors="replace") as f:
    log = f.read()

toolcache = sorted(os.listdir("/opt/hostedtoolcache/Python")) if os.path.isdir(
    "/opt/hostedtoolcache/Python") else []

record = {
    "condition": env["CONDITION"],
    "tool": env["TOOL"],
    "key": env["CACHE_KEY"],
    "cache_hit": env["CACHE_HIT"] == "true",
    "cache_matched_key": env.get("CACHE_MATCHED_KEY", ""),
    "leg_requested": env["LEG_REQUESTED"],
    "leg_actual": env["LEG_ACTUAL"],
    "seed": seed,
    "rc": rc,
    "probe": probe,
    "toolcache_python": toolcache,
    "image_os": env.get("ImageOS"),
    "image_version": env.get("ImageVersion"),
    "run_id": env.get("GITHUB_RUN_ID"),
    "run_attempt": env.get("GITHUB_RUN_ATTEMPT"),
    "log_tail": log[-4000:],
}
with open(out, "w") as f:
    json.dump(record, f, indent=2)
print(json.dumps({k: record[k] for k in ("condition", "tool", "cache_hit", "rc")}))
