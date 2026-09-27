from cachekeys.analyze import analyze_workflow

HEAD = """
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - id: setup
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
"""


def one(body, head=HEAD):
    steps = analyze_workflow(head + body)
    assert len(steps) == 1, steps
    return steps[0]


def test_minor_only_with_skip():
    c = one("""
      - id: cache
        uses: actions/cache@v4
        with:
          path: .venv
          key: venv-${{ runner.os }}-${{ matrix.python-version }}-${{ hashFiles('poetry.lock') }}
      - if: steps.cache.outputs.cache-hit != 'true'
        run: poetry install
""")
    assert c.path_kind == "built_env"
    assert c.interp_signal == "minor"
    assert c.verdict == "minor_only"
    assert c.skip_on_hit and c.deps_hashed and c.os_signal


def test_full_version_output_is_sound():
    c = one("""
      - uses: actions/cache@v4
        with:
          path: .venv
          key: venv-${{ steps.setup.outputs.python-version }}-${{ hashFiles('requirements.txt') }}
""")
    assert c.verdict == "sound"
    assert not c.skip_on_hit


def test_no_interpreter():
    c = one("""
      - id: c
        uses: actions/cache@v4
        with:
          path: |
            .venv
          key: deps-${{ hashFiles('requirements*.txt') }}
      - if: steps.c.outputs.cache-hit != 'true'
        run: pip install -r requirements.txt
""")
    assert c.verdict == "no_interpreter" and c.skip_on_hit


def test_download_store_not_applicable():
    c = one("""
      - uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ hashFiles('requirements.txt') }}
""")
    assert c.path_kind == "download_store"
    assert c.verdict == "not_applicable"


def test_pythonlocation_path_pins_interpreter():
    c = one("""
      - uses: actions/cache@v4
        with:
          path: ${{ env.pythonLocation }}
          key: ${{ env.pythonLocation }}-${{ hashFiles('setup.py') }}
""")
    assert c.path_pins_interpreter and c.verdict == "sound"


def test_env_literal_minor_resolved():
    head = HEAD.replace("on: push\n", "on: push\nenv:\n  PY: '3.12'\n")
    c = one("""
      - uses: actions/cache@v4
        with:
          path: venv
          key: v-${{ env.PY }}-${{ hashFiles('x') }}
""", head)
    assert c.interp_signal == "minor"


def test_patch_pinned_matrix_is_full():
    head = HEAD.replace('["3.11", "3.12"]', '["3.11.9", "3.12.4"]')
    c = one("""
      - uses: actions/cache@v4
        with:
          path: .venv
          key: v-${{ matrix.python-version }}
""", head)
    assert c.verdict == "sound"


def test_exported_version_var():
    c = one("""
      - id: v
        run: echo "ver=$(python -V)" >> $GITHUB_OUTPUT
      - uses: actions/cache@v4
        with:
          path: .venv
          key: v-${{ steps.v.outputs.ver }}
""")
    assert c.verdict == "sound"


def test_restore_keys_drop_interpreter():
    c = one("""
      - uses: actions/cache@v4
        with:
          path: .venv
          key: v-${{ steps.setup.outputs.python-version }}-${{ hashFiles('a') }}
          restore-keys: |
            v-
""")
    assert c.verdict == "sound" and c.restore_key_drops_interp


def test_version_file():
    c = one("""
      - uses: actions/cache@v4
        with:
          path: .venv
          key: v-${{ hashFiles('.python-version', 'uv.lock') }}
""")
    assert c.verdict == "version_file"


def test_win32_is_not_a_python_version():
    c = one("""
      - uses: actions/cache@v4
        with:
          path: .venv
          key: win32-${{ hashFiles('a') }}
""")
    assert c.interp_signal == "none"


def test_poetry_cache_dir_is_built_env():
    c = one("""
      - uses: actions/cache@v4
        with:
          path: ~/.cache/pypoetry
          key: poetry-${{ hashFiles('poetry.lock') }}
""")
    assert c.path_kind == "built_env"


def test_save_only_step_ignored_and_bad_yaml():
    assert analyze_workflow(HEAD + """
      - uses: actions/cache/save@v4
        with: {path: .venv, key: k}
""") == []
    assert analyze_workflow("::: not yaml") == []


def test_mise_dir_is_not_python_env():
    c = one("""
      - uses: actions/cache@v4
        with:
          path: ~/.local/share/mise
          key: mise-${{ hashFiles('mise.toml') }}
""")
    assert c.path_kind == "other"


def test_key_computed_in_run_step_is_followed():
    c = one("""
      - id: k
        run: echo "key=venv-$(python -c 'import platform;print(platform.python_version())')" >> "$GITHUB_OUTPUT"
      - uses: actions/cache@v4
        with:
          path: .venv
          key: ${{ steps.k.outputs.key }}
""")
    assert c.interp_signal == "full"


def test_matrix_env_name_with_python_token():
    head = HEAD.replace('python-version: ["3.11", "3.12"]', 'env_name: ["py311", "py312-lint"]')
    c = one("""
      - uses: actions/cache@v4
        with:
          path: .venv
          key: venv-${{ matrix.env_name }}-${{ hashFiles('poetry.lock') }}
""", head)
    assert c.interp_signal == "minor"


def test_macos_pip_cache_is_download_store():
    c = one("""
      - uses: actions/cache@v4
        with:
          path: ~/Library/Caches/pip
          key: pip-${{ hashFiles('r.txt') }}
""")
    assert c.path_kind == "download_store"


def test_other_folders_under_local_are_not_python():
    for path, kind in [("~/.local/labwc", "other"), ("~/.local/share/mise", "other"),
                       ("~/.local", "built_env"), ("~/.local/lib/python3.12", "built_env"),
                       ("~/.local/share/pypoetry", "built_env")]:
        c = one(f"""
      - uses: actions/cache@v4
        with:
          path: {path}
          key: k-${{{{ hashFiles('a') }}}}
""")
        assert c.path_kind == kind, path


def test_python_tool_folders_under_local_and_prefixed_venvs():
    for path in ["~/.local/pypoetry", "~/.local/pipx", ".local/ha-venv", "ha-venv"]:
        c = one(f"""
      - uses: actions/cache@v4
        with:
          path: {path}
          key: k-${{{{ hashFiles('a') }}}}
""")
        assert c.path_kind == "built_env", path
