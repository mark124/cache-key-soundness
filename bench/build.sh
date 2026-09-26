#!/usr/bin/env bash
# Build bench/.venv with TOOL using the interpreter at PY.  usage: build.sh TOOL PY
set -euxo pipefail
tool="$1"; py="$2"
cd bench
case "$tool" in
  pip)    "$py" -m venv .venv && .venv/bin/pip install -q -r requirements.txt ;;
  poetry) poetry config virtualenvs.in-project true && poetry env use "$py" && poetry install --no-root -q ;;
  uv)     uv venv --python "$py" .venv && uv pip install --python .venv/bin/python -r requirements.txt ;;
esac
