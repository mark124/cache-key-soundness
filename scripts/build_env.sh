#!/usr/bin/env bash
# Build fixture/.venv with the given tool, the way a typical workflow's
# "install dependencies" step does.
#   usage: build_env.sh TOOL PYTHON_PATH [plain]
# "plain" leaves out every command that names the interpreter (no
# `poetry env use`, no `uv --python`), as many real workflows do; gitman's
# `make install` is `poetry config virtualenvs.in-project true` + `poetry install`.
set -euxo pipefail
tool="$1"; py="$2"; mode="${3:-}"
cd fixture
case "$tool" in
  pip)
    "$py" -m venv .venv
    .venv/bin/pip install -r requirements.txt ;;
  poetry)
    poetry config virtualenvs.in-project true
    [ "$mode" = plain ] || poetry env use "$py"
    poetry install --no-root ;;
  uv)
    if [ "$mode" = plain ]; then uv sync; else uv sync --python "$py"; fi ;;
  *) echo "unknown tool $tool"; exit 2 ;;
esac
