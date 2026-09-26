# cache-key-soundness

Artifact for the paper *Tests Passed on the Wrong Python: Incomplete Cache
Keys in GitHub Actions* (Mark C. Johnson).

A GitHub Actions workflow that caches a **built** Python environment (a
virtualenv, `.tox`, a Poetry environment) and skips installation on a cache
hit is running an incremental build. The cache key is the only record of what
that environment depends on. This repository measures how often those keys
omit the interpreter, tests what happens when they match, and ships a linter.

## Reproduce every number (offline, about 10 seconds)

```bash
git clone https://github.com/mark124/cache-key-soundness && cd cache-key-soundness
pip install -r requirements.txt
python -m cachekeys reproduce      # or: make all
python -m pytest -q tests          # classifier unit tests
```

Needs Python 3.10+ and nothing else: no token, no network. All inputs are
committed under `data/`.

## Paper to file map

| Paper | Produced by | Data |
|---|---|---|
| Table 1 (sample, prevalence) | `make table1` → `scripts/analyze_sample.py` | `results/table1_sample.csv` |
| Table 2 (key verdicts) | `make table2` → `scripts/analyze_sample.py` | `results/table2_key_composition.csv`, `results/table2_repo_level.csv` |
| Numbers in abstract and §5.1 | `make table2` | `results/headline.json` |
| Per-step classification | `make table2` | `results/cache_steps.csv` |
| Table 3 (controlled experiment) | `make table3` → `scripts/collect_harm.py table` | `results/table3_matrix.csv`, `results/table3_harm.csv`, `results/table3_summary.json` |
| Table 4 (timing of cache strategies) | `make table4` → `scripts/collect_bench.py table` | `results/table4_bench.csv`, `results/table4_bench_raw.csv`, `results/table4_summary.json` |
| Table 5 (classifier validation) | `make table5` → `scripts/validate_classifier.py` | `results/table5_validation.csv`, `results/table5_summary.json` |
| §5.3 (key history, no table) | `make rq3` → `scripts/mine_key_fixes.py table` | `results/rq3_key_changes.csv`, `results/rq3_summary.json` |
| Every `\ck{...}` number in the PDF | `python scripts/make_numbers.py v1.0` | `paper/numbers.tex` |

Every number in the PDF is a hyperlink to the line of the results file it
comes from, at tag `v1.0`.

## What is in `data/`

| Path | Contents |
|---|---|
| `data/raw/frame.jsonl` | sampling frame: every repository returned by the search queries (query string recorded per row) |
| `data/raw/sample.jsonl` | the seeded random sample (seed `20260926`) |
| `data/raw/manifest.jsonl` | per sampled repository: HEAD commit SHA and every workflow file (name, blob SHA) |
| `data/raw/cache_workflows.jsonl.gz` | full text of each workflow file that mentions `actions/cache`, at that SHA |
| `data/raw/key_changes.jsonl` | commits that changed a cache `key:` line in those files |
| `data/harm/run-*/` | outcome records downloaded from the public `harm` workflow runs, with run URLs |
| `data/bench/run-*/` | timing records from the public `bench` workflow run (Table 4), with the run URL |
| `data/validation/labels.csv` | hand labels for the classifier check; rubric in `RUBRIC.md` |

## Re-collecting from scratch (network, not needed to reproduce)

```bash
python scripts/fetch_sample.py all            # ~30 min, GitHub token via GITHUB_TOKEN or gh
python scripts/mine_key_fixes.py fetch        # ~1 h (REST rate limit)
gh workflow run harm.yml                      # then:
python scripts/collect_harm.py fetch <run-id>
```

A re-collection will differ from the committed snapshot (repositories change);
the paper's numbers are the committed snapshot's.

## The linter

```bash
python -m cachekeys lint .github/workflows
```

It flags a cache step that stores a built Python environment under a key
without the exact interpreter version, as an `error` when the workflow also
skips installation on a hit. The fix is to put
`${{ steps.<setup-python id>.outputs.python-version }}` in the key.

## The controlled experiment

`.github/workflows/harm.yml`: four conditions x three tools (pip, Poetry, uv) on
`ubuntu-24.04`. Every action is pinned by commit SHA; Poetry, uv and the fixture's
dependencies are pinned by version. See the header comment in the workflow.

## Licence

MIT, see `LICENSE`. Workflow files under `data/raw/` are excerpts of public
repositories, redistributed for research; each record names its repository
and commit.
