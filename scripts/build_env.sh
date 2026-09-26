#!/usr/bin/env bash
# Build fixture/.venv with the given tool, the way a typical workflow's
# "install dependencies" step does.  usage: build_env.sh TOOL PYTHON_PATH
set -euxo pipefail
tool="$1"; py="$2"
cd fixture
case "$tool" in
  pip)
    "$py" -m venv .venv
    .venv/bin/pip install -r requirements.txt ;;
  poetry)
    poetry config virtualenvs.in-project true
    poetry env use "$py"
    poetry install --no-root ;;
  uv)
    uv sync --python "$py" ;;
  *) echo "unknown tool $tool"; exit 2 ;;
esac
