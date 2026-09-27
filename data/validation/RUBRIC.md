# Labelling rubric

Fill `label_path_kind` and `label_verdict` in `labels.csv` for each row,
reading only `paths`, `key` and `restore_keys`. Open the workflow at
`https://github.com/<repo>/blob/<sha>/.github/workflows/<file>` when the key
refers to a value set elsewhere (the sha is in `results/cache_steps.csv`).

## label_path_kind

| value | when |
|---|---|
| `built_env` | at least one path is a Python environment that an installer *built*: any folder with `venv` in its name (`.venv`, `venv`, `ha-venv`), poetry's `virtualenvs`, the whole `pypoetry` folder, `pipx`, `.tox`, `.nox`, `site-packages`, `~/.local` itself or its `lib`/`bin` (pip `--user`), or the interpreter's own install directory (`pythonLocation`) |
| `download_store` | every path is a package-manager download cache (`~/.cache/pip`, `pip cache dir`, `~/.cache/uv` or any uv cache folder, poetry `cache`/`artifacts`) |
| `other` | anything else (`node_modules`, build outputs, pre-commit, Hugging Face / spaCy / Playwright downloads, mypy cache, the whole `~/.cache`, other folders under `~/.local`) |

Round 1 (`labels_round1.csv`) was labelled from a shortened version of this
table given in chat, which left out `pythonLocation`, `site-packages`,
`~/.local`, the whole `pypoetry` folder and the "any one path" rule. Round 2
(`labels.csv`) was labelled with this full table shown on every card.

## label_verdict (only when `built_env`; otherwise write `not_applicable`)

| value | when |
|---|---|
| `sound` | the key (or the path) pins the exact interpreter: setup-python's `python-version` **output**, `pythonLocation`, a full `3.X.Y` literal or matrix of them, or a value computed from `python --version` / `sys.version` |
| `minor_only` | the key carries a Python version only to minor precision (`3.12`, `py312`, `matrix.python-version` whose values are minors) |
| `no_interpreter` | the key carries no Python version at all |
| `version_file` | the key hashes `.python-version` / `.tool-versions` / `runtime.txt` and nothing stronger |

`label_note`: anything the rubric did not anticipate.
