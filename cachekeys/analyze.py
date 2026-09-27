"""Find actions/cache steps in a GitHub Actions workflow and judge whether the
cache key covers what the cached Python environment depends on.

A cached virtual environment (or any directory that pip/poetry/uv *built*)
depends on the exact interpreter it was created with: its `python` is a
symlink into that interpreter's install directory, and compiled extensions
are built against its ABI. A cache of *downloads* (the pip, poetry or uv
package store) does not: those files are content-addressed and re-checked
on install. So only built-environment caches need the interpreter in the key.

Everything here is a pure function of the workflow text, so results are
reproducible from the committed workflow files alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

import yaml

CACHE_USES = re.compile(r"^actions/cache(/restore|/save)?@", re.I)
SETUP_PY_USES = re.compile(r"^actions/setup-python@", re.I)
EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)

# --- what the cached path is -------------------------------------------------
# Directories that hold a *built* Python environment.
BUILT_ENV = re.compile(
    r"""(^|[/\\\s'"])(
        [\w.-]*venv[^/\\\s]*    # .venv, venv, venv311, .venv-docs, ha-venv
      | virtualenvs?             # poetry's ~/.cache/pypoetry/virtualenvs
      | \.tox | \.nox
      | site-packages
      | \.local                  # pip install --user lands in ~/.local
      | pypoetry                 # the whole poetry cache dir holds virtualenvs/
    )([/\\\s'"]|$)""",
    re.X | re.I,
)
# Tool-version managers and other ecosystems that happen to live under
# ~/.local: not a Python environment.
# Under ~/.local only lib/, bin/ and the Python tool folders hold a Python
# environment; anything else there (mise, a window manager's files, ...) does not.
NOT_PY_ENV = re.compile(
    r"\.local/(?!lib\b|bin\b|pypoetry\b|pipx\b|share/(pypoetry|pipx|virtualenvs)\b|[\w.-]*venv)[^/\s]", re.I)
# Package-manager download stores: content-addressed, safe without the
# interpreter in the key.
DOWNLOAD_STORE = re.compile(
    r"""(\.cache/pip | pip-cache | /pip/cache | \\pip\\cache | Caches/pip | pip\\Cache
      | \.cache/pypoetry/(cache|artifacts)
      | \.cache/uv | uv-cache | UV_CACHE_DIR
      | pip\ cache\ dir | steps\.[\w-]+\.outputs\.(pip-)?(cache-)?dir )""",
    re.X | re.I,
)
# A path that itself encodes the interpreter location. actions/cache folds
# the path list into the cache version, so such a cache cannot be restored
# for a different interpreter even when the key omits it.
PATH_PINS_INTERPRETER = re.compile(r"pythonLocation|python-path|hostedtoolcache", re.I)

# --- what the key says about the interpreter --------------------------------
FULL_VERSION_EXPR = re.compile(
    r"steps\.[\w-]+\.outputs\.python-version|env\.pythonLocation|steps\.[\w-]+\.outputs\.python-path",
    re.I,
)
FULL_VERSION_LITERAL = re.compile(r"(?<![\d.])3\.\d{1,2}\.\d{1,2}(?![\d.])")
MINOR_VERSION_LITERAL = re.compile(
    r"(?<![\w.])3\.\d{1,2}(?![\d.])|(?:py|python|cp)-?3\.?\d{1,2}(?!\d)", re.I)
VERSION_FILE = re.compile(r"hashFiles\([^)]*(\.python-version|\.tool-versions|runtime\.txt)", re.I)
# interpreter version computed inside a run step that builds the key
FULL_VERSION_COMPUTED = re.compile(
    r"python_version\(\)|sys\.version|python3?\s+(-V|--version)|\$pythonLocation|\$\{?pythonLocation", re.I)
MATRIX_VERSION = re.compile(r"matrix\.[\w-]*py[\w-]*", re.I)
HASHFILES = re.compile(r"hashFiles\s*\(", re.I)
OS_SIGNAL = re.compile(r"runner\.os|matrix\.[\w-]*os\b|matrix\.[\w-]*platform|runner\.arch|ubuntu|windows|macos|linux", re.I)
# a run step that computes the interpreter version and exports it
VERSION_EXPORT = re.compile(
    r"(\w+)=\$\((?:[^)]*)(python3?\s+(-V|--version|-c[^)]*version)|sys\.version|python_version)",
    re.I,
)


@dataclass
class CacheStep:
    file: str
    job: str
    step_index: int
    step_id: str | None
    uses: str
    paths: list[str]
    key: str
    restore_keys: list[str]
    skip_on_hit: bool
    # derived
    path_kind: str = ""            # built_env | download_store | other
    path_pins_interpreter: bool = False
    interp_signal: str = ""        # full | minor | none
    interp_signal_detail: str = ""
    deps_hashed: bool = False
    os_signal: bool = False
    restore_key_drops_interp: bool = False
    verdict: str = ""              # see judge()
    notes: list[str] = field(default_factory=list)

    def row(self) -> dict:
        d = asdict(self)
        d["paths"] = " | ".join(self.paths)
        d["restore_keys"] = " | ".join(self.restore_keys)
        d["notes"] = "; ".join(self.notes)
        return d


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [ln.strip() for ln in str(v).splitlines() if ln.strip()]


def _resolve_env(text: str, env: dict) -> str:
    """Substitute ${{ env.X }} with its literal workflow/job value, when known,
    so that `env.PYTHON_VERSION: "3.12"` is judged by its value."""
    def sub(m):
        inner = m.group(1).strip()
        mm = re.fullmatch(r"env\.([\w-]+)", inner)
        if mm and mm.group(1) in env:
            return str(env[mm.group(1)])
        return m.group(0)
    return EXPR.sub(sub, text)


def _setup_python_inputs(steps) -> list[str]:
    out = []
    for s in steps:
        if isinstance(s, dict) and SETUP_PY_USES.match(str(s.get("uses", ""))):
            w = s.get("with") or {}
            out.append(str(w.get("python-version", "")) + " " + str(w.get("python-version-file", "")))
    return out


def _matrix_values(matrix: dict, name: str) -> list[str]:
    vals = []
    v = matrix.get(name)
    if isinstance(v, list):
        vals += [str(x) for x in v]
    for inc in matrix.get("include") or []:
        if isinstance(inc, dict) and name in inc:
            vals.append(str(inc[name]))
    return vals


def classify_path(paths: list[str]) -> tuple[str, bool]:
    joined = "\n".join(paths)
    pins = bool(PATH_PINS_INTERPRETER.search(joined))
    built = any(BUILT_ENV.search(p) and not NOT_PY_ENV.search(p) for p in paths)
    if built:
        return "built_env", pins
    if pins:
        # caching the interpreter's own install directory (site-packages
        # lives under pythonLocation)
        return "built_env", pins
    if all(DOWNLOAD_STORE.search(p) for p in paths) and paths:
        return "download_store", pins
    return "other", pins


def interp_signal(key: str, exported_vars: set[str], setup_inputs: list[str],
                  matrix: dict) -> tuple[str, str]:
    if FULL_VERSION_EXPR.search(key):
        return "full", FULL_VERSION_EXPR.search(key).group(0)
    for var in sorted(exported_vars):
        if re.search(r"\b" + re.escape(var) + r"\b", key):
            return "full", f"exported:{var}"
    if FULL_VERSION_COMPUTED.search(key):
        return "full", "computed:" + FULL_VERSION_COMPUTED.search(key).group(0)
    if FULL_VERSION_LITERAL.search(key):
        return "full", "literal:" + FULL_VERSION_LITERAL.search(key).group(0)
    if VERSION_FILE.search(key):
        return "version_file", VERSION_FILE.search(key).group(1)
    for m in re.finditer(r"matrix\.([\w-]+)", key):
        name = m.group(1)
        vals = _matrix_values(matrix, name)
        looks_py = bool(MATRIX_VERSION.fullmatch(m.group(0))) or (
            vals and all(re.fullmatch(r"(pypy-?)?3(\.\d+){1,2}", v) or MINOR_VERSION_LITERAL.search(v)
                         for v in vals))
        if not looks_py:
            continue
        # a matrix whose values are all exact patch versions is as good as full
        if vals and all(FULL_VERSION_LITERAL.fullmatch(v) for v in vals):
            return "full", f"{m.group(0)} (all patch-pinned)"
        return "minor", m.group(0)
    m = MINOR_VERSION_LITERAL.search(re.sub(r"@v\d+", "", key))
    if m:
        # a minor literal is exact if setup-python was pinned to that patch
        return "minor", "literal:" + m.group(0)
    return "none", ""


def judge(c: CacheStep) -> str:
    """Verdict for one cache step.

    not_applicable   the cached path is not a built Python environment
    sound            built env; key carries the exact interpreter (or the path
                     pins it) and a dependency hash
    minor_only       key carries only the minor version (e.g. 3.12)
    no_interpreter   key carries no interpreter version at all
    version_file     key hashes a version file (.python-version etc.); sound
                     only if that file pins a patch version, which the
                     workflow text alone cannot show
    """
    if c.path_kind != "built_env":
        return "not_applicable"
    if c.path_pins_interpreter or c.interp_signal == "full":
        return "sound"
    if c.interp_signal == "version_file":
        return "version_file"
    return "minor_only" if c.interp_signal == "minor" else "no_interpreter"


def analyze_workflow(text: str, filename: str = "") -> list[CacheStep]:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if not isinstance(doc, dict):
        return []
    wf_env = doc.get("env") if isinstance(doc.get("env"), dict) else {}
    results: list[CacheStep] = []
    jobs = doc.get("jobs") if isinstance(doc.get("jobs"), dict) else {}
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") if isinstance(job.get("steps"), list) else []
        env = dict(wf_env)
        if isinstance(job.get("env"), dict):
            env.update(job["env"])
        strategy = job.get("strategy") if isinstance(job.get("strategy"), dict) else {}
        matrix = strategy.get("matrix") if isinstance(strategy.get("matrix"), dict) else {}
        exported: set[str] = set()
        for s in steps:
            if isinstance(s, dict) and s.get("run"):
                for m in VERSION_EXPORT.finditer(str(s["run"])):
                    exported.add(m.group(1))
        setup_inputs = _setup_python_inputs(steps)
        run_by_id = {str(s["id"]): str(s.get("run", "")) for s in steps
                     if isinstance(s, dict) and s.get("id") and s.get("run")}
        for i, s in enumerate(steps):
            if not isinstance(s, dict):
                continue
            uses = str(s.get("uses", ""))
            if not CACHE_USES.match(uses) or uses.lower().startswith("actions/cache/save"):
                continue
            w = s.get("with") if isinstance(s.get("with"), dict) else {}
            step_env = dict(env)
            if isinstance(s.get("env"), dict):
                step_env.update(s["env"])
            key = _resolve_env(str(w.get("key", "")), step_env)
            # a key computed by an earlier run step: judge the text that
            # computes it, not the opaque reference
            for m in re.finditer(r"steps\.([\w-]+)\.outputs\.[\w-]+", key):
                if m.group(1) in run_by_id and not FULL_VERSION_EXPR.fullmatch(m.group(0)):
                    key += "  #computed-by: " + _resolve_env(run_by_id[m.group(1)], step_env)
            rkeys = [_resolve_env(k, step_env) for k in _as_list(w.get("restore-keys"))]
            paths = [_resolve_env(p, step_env) for p in _as_list(w.get("path"))]
            sid = s.get("id")
            skip = False
            if sid:
                pat = re.compile(r"steps\.%s\.outputs\.cache-hit" % re.escape(str(sid)))
                for later in steps[i + 1:]:
                    if isinstance(later, dict) and pat.search(str(later.get("if", ""))):
                        skip = True
                        break
            c = CacheStep(filename, str(job_name), i, sid, uses, paths, key, rkeys, skip)
            c.path_kind, c.path_pins_interpreter = classify_path(paths)
            c.interp_signal, c.interp_signal_detail = interp_signal(key, exported, setup_inputs, matrix)
            # setup-python pinned to one exact patch makes a literal minor exact
            if c.interp_signal == "minor" and setup_inputs and all(
                    FULL_VERSION_LITERAL.search(x) for x in setup_inputs):
                c.notes.append("setup-python pinned to exact patch")
                c.interp_signal = "full"
            c.deps_hashed = bool(HASHFILES.search(key))
            c.os_signal = bool(OS_SIGNAL.search(key))
            if rkeys and c.interp_signal == "full":
                c.restore_key_drops_interp = any(
                    interp_signal(rk, exported, setup_inputs, matrix)[0] != "full" for rk in rkeys)
            c.verdict = judge(c)
            results.append(c)
    return results
