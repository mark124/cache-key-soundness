# cache-key-soundness

Work in progress. When a GitHub Actions workflow caches a built environment
(`.venv`, `node_modules`, `target/`), the cache key is the only record of what
that environment depends on. This repository measures how often those keys
leave inputs out, and what happens when a workflow then skips installation on
a cache hit.

- `.github/workflows/harm.yml` — controlled experiment (conditions C0, E1, E2)
- `fixture/` — the minimal project the experiment builds
- `scripts/` — build, workload and outcome-recording scripts

Full reproduction instructions will be added with the results.
