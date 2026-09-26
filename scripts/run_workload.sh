#!/usr/bin/env bash
# Run the test suite the way a typical workflow's "test" step does.
# usage: run_workload.sh TOOL
set -x
tool="$1"
cd fixture
case "$tool" in
  pip)    source .venv/bin/activate && pytest -q ;;
  poetry) poetry run pytest -q ;;
  uv)     uv run pytest -q ;;
  *) echo "unknown tool $tool"; exit 2 ;;
esac
