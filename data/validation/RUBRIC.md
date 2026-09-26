# Labelling rubric

Fill `label_path_kind` and `label_verdict` in `labels.csv` for each row,
reading only `paths`, `key` and `restore_keys`. Open the workflow at
`https://github.com/<repo>/blob/<sha>/.github/workflows/<file>` when the key
refers to a value set elsewhere (the sha is in `results/cache_steps.csv`).

## label_path_kind

| value | when |
|---|---|
| `built_env` | at least one path is a Python environment that an installer *built*: a virtualenv (`.venv`, `venv*`, poetry's `virtualenvs`, the whole `~/.cache/pypoetry`), `.tox`, `.nox`, `site-packages`, `~/.local` (pip `--user`), or the interpreter's own install directory (`pythonLocation`) |
| `download_store` | every path is a package-manager download cache (`~/.cache/pip`, `pip cache dir`, `~/.cache/uv`, poetry `cache`/`artifacts`) |
| `other` | anything else (`node_modules`, build outputs, pre-commit, mypy cache, tool installs) |

## label_verdict (only when `built_env`; otherwise write `not_applicable`)

| value | when |
|---|---|
| `sound` | the key (or the path) pins the exact interpreter: setup-python's `python-version` **output**, `pythonLocation`, a full `3.X.Y` literal or matrix of them, or a value computed from `python --version` / `sys.version` |
| `minor_only` | the key carries a Python version only to minor precision (`3.12`, `py312`, `matrix.python-version` whose values are minors) |
| `no_interpreter` | the key carries no Python version at all |
| `version_file` | the key hashes `.python-version` / `.tool-versions` / `runtime.txt` and nothing stronger |

`label_note`: anything the rubric did not anticipate.
