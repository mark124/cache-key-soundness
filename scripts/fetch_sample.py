"""Collect the study sample from the GitHub API. Needs a token (GITHUB_TOKEN,
or `gh auth token`). Everything downstream runs offline from what this
writes, so reviewers never need to run it.

  1. frame    GitHub repository search: Python repositories, not forks, not
              archived, pushed in the 12 months before the snapshot date,
              four star strata x one query per creation year.
              -> data/raw/frame.jsonl
  2. sample   seeded random sample of up to N repositories per stratum.
              -> data/raw/sample.jsonl
  3. fetch    for each sampled repository, the default-branch HEAD commit and
              every .github/workflows/*.yml|yaml blob at that commit (GraphQL).
              -> data/raw/manifest.jsonl       one line per repo: sha + files
              -> data/raw/cache_workflows.jsonl.gz  text of every workflow
                 file that mentions actions/cache (the only ones analysed)

usage: python scripts/fetch_sample.py [frame|sample|fetch|all]
"""
from __future__ import annotations

import gzip
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SNAPSHOT = "2026-09-26"
PUSHED_SINCE = "2025-09-26"
STRATA = [("s1", "10..99"), ("s2", "100..999"), ("s3", "1000..9999"), ("s4", ">=10000")]
YEARS = range(2008, 2027)
PAGES_PER_QUERY = 3          # 300 results per (stratum, year) query
PER_STRATUM = 1000
SEED = 20260926
RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def token() -> str:
    t = os.environ.get("GITHUB_TOKEN")
    if not t:
        t = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
    return t


def _req(url, data=None):
    headers = {"Authorization": "bearer " + token(), "Accept": "application/vnd.github+json",
               "User-Agent": "cache-key-soundness"}
    body = json.dumps(data).encode() if data is not None else None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=60) as r:
                return json.load(r), r.headers
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 502, 503):
                reset = e.headers.get("x-ratelimit-reset")
                wait = max(5, int(reset) - int(time.time()) + 2) if reset and e.headers.get(
                    "x-ratelimit-remaining") == "0" else 20 * (attempt + 1)
                print(f"  {e.code}; waiting {wait}s", file=sys.stderr)
                time.sleep(min(wait, 900))
                continue
            raise
        except urllib.error.URLError:
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("giving up on " + url)


def frame():
    out = os.path.join(RAW, "frame.jsonl")
    seen = {}
    for sname, stars in STRATA:
        for y in YEARS:
            q = (f"language:Python stars:{stars} created:{y}-01-01..{y}-12-31 "
                 f"pushed:>={PUSHED_SINCE} fork:false archived:false")
            for page in range(1, PAGES_PER_QUERY + 1):
                url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
                    {"q": q, "sort": "updated", "order": "desc", "per_page": 100, "page": page})
                res, _ = _req(url)
                items = res.get("items", [])
                for it in items:
                    seen.setdefault(it["full_name"], {
                        "repo": it["full_name"], "stratum": sname, "stars": it["stargazers_count"],
                        "created": it["created_at"][:10], "default_branch": it["default_branch"],
                        "query": q})
                print(f"{sname} {y} p{page}: {len(items)} (total_count {res.get('total_count')}) frame={len(seen)}",
                      file=sys.stderr)
                time.sleep(2.2)      # search API: 30 requests/minute
                if len(items) < 100:
                    break
    with open(out, "w", newline="\n") as f:
        for r in sorted(seen.values(), key=lambda r: r["repo"]):
            f.write(json.dumps(r) + "\n")
    print(f"frame: {len(seen)} repositories -> {out}")


def sample():
    rows = [json.loads(l) for l in open(os.path.join(RAW, "frame.jsonl"))]
    rng = random.Random(SEED)
    chosen = []
    for sname, _ in STRATA:
        pool = sorted((r for r in rows if r["stratum"] == sname), key=lambda r: r["repo"])
        chosen += rng.sample(pool, min(PER_STRATUM, len(pool)))
    out = os.path.join(RAW, "sample.jsonl")
    with open(out, "w", newline="\n") as f:
        for r in sorted(chosen, key=lambda r: r["repo"]):
            f.write(json.dumps(r) + "\n")
    print(f"sample: {len(chosen)} repositories -> {out}")


GQL_REPO = """
  r%d: repository(owner: %s, name: %s) {
    nameWithOwner isArchived
    defaultBranchRef { target { oid } }
    object(expression: "HEAD:.github/workflows") {
      ... on Tree { entries { name type object { ... on Blob { oid byteSize isBinary text } } } }
    }
  }"""


def fetch():
    rows = [json.loads(l) for l in open(os.path.join(RAW, "sample.jsonl"))]
    man_path = os.path.join(RAW, "manifest.jsonl")
    wf_path = os.path.join(RAW, "cache_workflows.jsonl.gz")
    done = set()
    if os.path.exists(man_path):
        done = {json.loads(l)["repo"] for l in open(man_path)}
    todo = [r for r in rows if r["repo"] not in done]
    man = open(man_path, "a", newline="\n")
    wf = gzip.open(wf_path, "at", newline="\n")
    B = 20
    for i in range(0, len(todo), B):
        batch = todo[i:i + B]
        parts = []
        for j, r in enumerate(batch):
            o, n = r["repo"].split("/", 1)
            parts.append(GQL_REPO % (j, json.dumps(o), json.dumps(n)))
        res, _ = _req("https://api.github.com/graphql", {"query": "query {" + "".join(parts) + "}"})
        data = res.get("data") or {}
        for j, r in enumerate(batch):
            node = data.get(f"r{j}")
            rec = {"repo": r["repo"], "stratum": r["stratum"], "stars": r["stars"]}
            if not node:
                rec["error"] = "unavailable"
                man.write(json.dumps(rec) + "\n")
                continue
            rec["sha"] = ((node.get("defaultBranchRef") or {}).get("target") or {}).get("oid")
            files = []
            for e in ((node.get("object") or {}).get("entries") or []):
                if e["type"] != "blob" or not e["name"].lower().endswith((".yml", ".yaml")):
                    continue
                ob = e.get("object") or {}
                text = ob.get("text")
                files.append({"name": e["name"], "blob": ob.get("oid"), "bytes": ob.get("byteSize"),
                              "has_cache": bool(text and "actions/cache" in text)})
                if text and "actions/cache" in text:
                    wf.write(json.dumps({"repo": r["repo"], "sha": rec["sha"], "file": e["name"],
                                         "blob": ob.get("oid"), "text": text}) + "\n")
            rec["workflows"] = files
            man.write(json.dumps(rec) + "\n")
        man.flush(); wf.flush()
        print(f"fetched {min(i + B, len(todo))}/{len(todo)}", file=sys.stderr)
    man.close(); wf.close()


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    os.makedirs(RAW, exist_ok=True)
    if step in ("frame", "all"):
        frame()
    if step in ("sample", "all"):
        sample()
    if step in ("fetch", "all"):
        fetch()
