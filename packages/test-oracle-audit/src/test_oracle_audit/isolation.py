"""Isolated execution of audited suites (design D3, D1 "Suite environment").

Mutation and rename-survival change source code, so they only ever run inside an
:func:`isolated_copy`: a ``git worktree add --detach`` of ``HEAD`` into a scratch
directory (``shutil.copytree`` when the tree is not a git checkout). The copy and
its scratch directories are removed on exit, also when the body raises, and the
``git worktree`` registration is removed and pruned.

Besides the copy this module owns what both execution stages share:

* the redirected environment (``HOME``, ``TMPDIR``, ``XDG_*``, ``--basetemp``) so
  audited tests cannot write outside the scratch directory;
* :func:`run_suite`, which runs the audited tests in the copy and returns per-test
  outcomes and (optionally) the source functions each test called. A tiny pytest
  plugin, written into the scratch directory at run time, records both; it needs
  nothing beyond the interpreter the suite already runs under (no pytest-cov).
"""

from __future__ import annotations

import contextlib
import functools
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from test_oracle_audit.records import SuiteSpec

_IGNORED_ON_COPY = shutil.ignore_patterns(
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
)
_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")

BASELINE_TIMEOUT_SECONDS = 1800.0


@dataclass(frozen=True)
class IsolatedCopy:
    """A throwaway copy of the audited repository plus the environment to run it in."""

    root: Path
    env: dict[str, str]
    basetemp: Path
    scratch: Path | None = None  # the per-copy scratch directory that holds root, home, tmp, ...


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_VARS}
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=600
    )


def _git_toplevel(repo_root: Path) -> Path | None:
    try:
        proc = _git(repo_root, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return Path(proc.stdout.strip()).resolve()


def _add_worktree(repo_root: Path, destination: Path) -> tuple[Path, Path] | None:
    """``(copy_root, worktree_path)`` for a detached HEAD worktree, or ``None`` when unavailable."""
    top = _git_toplevel(repo_root)
    if top is None:
        return None
    try:
        proc = _git(top, "worktree", "add", "--detach", "--quiet", str(destination), "HEAD")
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        shutil.rmtree(destination, ignore_errors=True)
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _git(top, "worktree", "prune")
        return None
    relative = repo_root.resolve().relative_to(top)
    return destination / relative, destination


def _git_quiet(repo_root: Path, *args: str) -> None:
    top = _git_toplevel(repo_root)
    if top is not None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _git(top, *args)


@contextlib.contextmanager
def isolated_copy(repo_root: Path, *, scratch_root: Path | None = None) -> Iterator[IsolatedCopy]:
    """Yield an :class:`IsolatedCopy` of ``repo_root``; everything is removed on exit.

    Layout under a fresh directory made in ``scratch_root`` (the system temp
    directory by default)::

        <scratch>/repo/        the copy (a worktree of HEAD, or a copytree)
        <scratch>/home|tmp|xdg-*/   redirected HOME, TMPDIR, XDG dirs (beside the copy)
        <scratch>/basetemp     pytest --basetemp (created by pytest)
    """
    repo_root = Path(repo_root).resolve()
    scratch_parent = Path(scratch_root) if scratch_root is not None else None
    if scratch_parent is not None:
        scratch_parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="test-oracle-audit-", dir=scratch_parent)).resolve()
    worktree: Path | None = None
    try:
        added = _add_worktree(repo_root, scratch / "repo")
        if added is not None:
            root, worktree = added
        else:
            root = scratch / "repo"
            shutil.copytree(repo_root, root, ignore=_IGNORED_ON_COPY, symlinks=True)
        dirs = {
            "HOME": scratch / "home",
            "TMPDIR": scratch / "tmp",
            "XDG_CACHE_HOME": scratch / "xdg-cache",
            "XDG_CONFIG_HOME": scratch / "xdg-config",
            "XDG_DATA_HOME": scratch / "xdg-data",
            "XDG_STATE_HOME": scratch / "xdg-state",
        }
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        yield IsolatedCopy(
            root=root,
            env={key: str(path) for key, path in dirs.items()},
            basetemp=scratch / "basetemp",
            scratch=scratch,
        )
    finally:
        try:
            if worktree is not None:
                _git_quiet(repo_root, "worktree", "remove", "--force", str(worktree))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
            if worktree is not None:  # drops the registration of a tree `remove` could not handle
                _git_quiet(repo_root, "worktree", "prune")


# --- source tree helpers -----------------------------------------------------


def source_files(root: Path, suite: SuiteSpec) -> list[Path]:
    """Python files under the suite's source roots (resolved inside ``root``), sorted."""
    found: set[Path] = set()
    for source_root in suite.source_roots:
        path = root / source_root
        if path.is_file() and path.suffix == ".py":
            found.add(path)
        elif path.is_dir():
            found.update(
                p
                for p in path.rglob("*.py")
                if "__pycache__" not in p.parts and not p.name.startswith("test_") and p.name != "conftest.py"
            )
    return sorted(found)


def dotted_module(path: Path, root: Path) -> str:
    """Dotted module name of a source file: climb while the directory is a package.

    ``src/mini/calc.py`` (``mini/__init__.py`` present) is ``mini.calc``; a script
    in a directory without ``__init__.py`` is just its stem; ``pkg/__init__.py`` is ``pkg``.
    """
    root = root.resolve()
    parts = [] if path.stem == "__init__" else [path.stem]
    directory = path.resolve().parent
    while directory != root and (directory / "__init__.py").is_file():
        parts.insert(0, directory.name)
        directory = directory.parent
    return ".".join(parts) if parts else path.resolve().parent.name


# --- running pytest inside the copy -------------------------------------------

PLUGIN_MODULE = "oracle_audit_plugin"

# Written into the scratch directory and loaded with ``-p`` + PYTHONPATH, so the audited
# suite's interpreter needs nothing installed. It records, per test, the outcome and
# (with ORACLE_AUDIT_TRACE=1) the source functions the test called, through
# ``sys.monitoring`` (3.12+; both pilot suites require it). Node ids are repo-relative.
PLUGIN_SOURCE = '''\
"""pytest plugin injected by test-oracle-audit (outcomes, selection, function-level calls)."""
import json
import os
import sys

import pytest

_ROOT = os.path.realpath(os.environ["ORACLE_AUDIT_ROOT"])
_OUT = os.environ["ORACLE_AUDIT_OUT"]
_SELECT = os.environ.get("ORACLE_AUDIT_SELECT")
_TRACE = os.environ.get("ORACLE_AUDIT_TRACE") == "1"
_SOURCES = [os.path.realpath(p) for p in json.loads(os.environ.get("ORACLE_AUDIT_SOURCES", "[]"))]

_ids = {}
_collect_errors = set()
_outcomes = {}
_calls = {}
_state = {"current": None, "tracer": "off"}
_RANK = {"passed": 0, "skipped": 1, "failed": 2}


def _node_id(item):
    rel = os.path.relpath(os.path.realpath(str(item.path)), _ROOT).replace(os.sep, "/")
    return rel + item.nodeid.partition("::")[1] + item.nodeid.partition("::")[2]


def pytest_itemcollected(item):
    _ids[item.nodeid] = _node_id(item)


def pytest_collectreport(report):
    if report.failed and report.nodeid:
        full = os.path.join(_state["rootpath"], report.nodeid.partition("::")[0])
        _collect_errors.add(os.path.relpath(os.path.realpath(full), _ROOT).replace(os.sep, "/"))


def pytest_configure(config):
    _state["rootpath"] = str(config.rootpath)


def pytest_collection_modifyitems(config, items):
    if not _SELECT:
        return
    with open(_SELECT, encoding="utf-8") as fh:
        wanted = set(json.load(fh))
    keep = [it for it in items if _ids.get(it.nodeid, _node_id(it)) in wanted]
    dropped = [it for it in items if it not in keep]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = keep


def pytest_runtest_logreport(report):
    nid = _ids.get(report.nodeid, report.nodeid)
    outcome = report.outcome
    if outcome not in _RANK:
        outcome = "failed"
    previous = _outcomes.get(nid)
    if previous is None or _RANK[outcome] > _RANK[previous]:
        _outcomes[nid] = outcome


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    _state["current"] = set()
    try:
        yield
    finally:
        _calls[_ids.get(item.nodeid, item.nodeid)] = sorted(_state["current"])
        _state["current"] = None


def _start_tracer():
    mon = getattr(sys, "monitoring", None)
    if mon is None:
        return
    tool = mon.PROFILER_ID
    try:
        mon.use_tool_id(tool, "oracle_audit")
    except ValueError:
        _state["tracer"] = "tool_busy"
        return
    cache = {}

    def on_start(code, offset):
        name = code.co_filename
        rel = cache.get(name, False)
        if rel is False:
            real = os.path.realpath(name)
            rel = None
            if any(real == s or real.startswith(s + os.sep) for s in _SOURCES):
                rel = os.path.relpath(real, _ROOT).replace(os.sep, "/")
            cache[name] = rel
        if rel is None:
            return mon.DISABLE
        current = _state["current"]
        if current is not None:
            current.add((rel, code.co_qualname))
        return None

    mon.register_callback(tool, mon.events.PY_START, on_start)
    mon.set_events(tool, mon.events.PY_START)
    _state["tracer"] = "monitoring"
    _state["tool"] = tool


def pytest_sessionstart(session):
    if _TRACE:
        _start_tracer()


def pytest_sessionfinish(session, exitstatus):
    mon = getattr(sys, "monitoring", None)
    if _state.get("tool") is not None and mon is not None:
        mon.set_events(_state["tool"], 0)
        mon.free_tool_id(_state["tool"])
    payload = {
        "outcomes": _outcomes,
        "coverage": {k: [list(pair) for pair in v] for k, v in _calls.items()},
        "tracer": _state["tracer"],
        "collect_errors": sorted(_collect_errors),
    }
    with open(_OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
'''


@dataclass
class SuiteRun:
    """Result of one pytest invocation inside an isolated copy."""

    returncode: int | None  # None: timed out
    outcomes: dict[str, str] = field(default_factory=dict)  # node id -> passed | failed | skipped
    coverage: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # node id -> (file, qualname)
    collect_errors: set[str] = field(default_factory=set)  # repo-relative files that failed to collect
    results_found: bool = False
    tracer: str = "off"
    output: str = ""
    seconds: float = 0.0

    @property
    def timed_out(self) -> bool:
        return self.returncode is None


@functools.cache
def _real_uv_dirs() -> dict[str, str]:
    """uv's cache and managed-Python directories under the *real* home, so the redirected
    HOME does not force every run to re-download wheels and interpreters."""
    out: dict[str, str] = {}
    for var, args in (("UV_CACHE_DIR", ("cache", "dir")), ("UV_PYTHON_INSTALL_DIR", ("python", "dir"))):
        if os.environ.get(var):
            continue
        try:
            proc = subprocess.run(["uv", *args], capture_output=True, text=True, check=False, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            out[var] = proc.stdout.strip().splitlines()[-1]
    return out


def pytest_launcher(
    copy: IsolatedCopy,
    suite: SuiteSpec,
    *,
    python: str | None,
    overlay: Sequence[str] = (),
) -> list[str]:
    """``[python, -m, pytest]``, or ``uv run --project <copy project> ... pytest`` (design D1).

    ``overlay`` lists ``--with`` requirements added on top of the suite's own environment.
    """
    if python is not None:
        return [python, "-m", "pytest"]
    project = copy.root / suite.project_root
    extras = [arg for extra in suite.uv_extras for arg in ("--extra", extra)]
    withs = [arg for spec in overlay for arg in ("--with", spec)]
    return ["uv", "run", "--project", str(project), *extras, *withs, "pytest"]


def run_environment(copy: IsolatedCopy, *, python: str | None) -> dict[str, str]:
    env = {**os.environ, **copy.env, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    if python is None:
        env.update(_real_uv_dirs())
    return env


def _plugin_dir(copy: IsolatedCopy) -> Path:
    scratch = copy.scratch or copy.basetemp.parent
    directory = scratch / "audit-plugin"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{PLUGIN_MODULE}.py"
    if not path.exists():
        path.write_text(PLUGIN_SOURCE, encoding="utf-8")
    return directory


def _communicate(proc: subprocess.Popen[str], timeout: float | None) -> tuple[str, bool]:
    try:
        out, _ = proc.communicate(timeout=timeout)
        return out or "", False
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return out or "", True


def run_command(
    argv: Sequence[str], *, cwd: Path, env: dict[str, str], timeout: float | None
) -> tuple[int | None, str]:
    """Run ``argv`` in its own process group; ``(None, output)`` when it timed out.

    Raises ``OSError`` when the program cannot be started.
    """
    proc = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    out, timed_out = _communicate(proc, timeout)
    return (None if timed_out else proc.returncode), out


def run_suite(
    copy: IsolatedCopy,
    suite: SuiteSpec,
    *,
    python: str | None = None,
    node_ids: Sequence[str] | None = None,
    trace: bool = False,
    timeout: float | None = BASELINE_TIMEOUT_SECONDS,
    overlay: Sequence[str] = (),
) -> SuiteRun:
    """Run the audited tests inside ``copy`` and read per-test results from the plugin.

    ``node_ids`` (repo-relative) restricts the run to those tests; otherwise the suite's
    ``test_paths`` run whole. With ``trace`` the run also records the source functions each
    test called. Raises ``OSError`` when the interpreter cannot be started.
    """
    project = (copy.root / suite.project_root).resolve()
    scratch = copy.scratch or copy.basetemp.parent
    plugin_dir = _plugin_dir(copy)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=scratch))
    out_file = work / "results.json"
    env = run_environment(copy, python=python)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(plugin_dir), env.get("PYTHONPATH", "")]))
    env["ORACLE_AUDIT_ROOT"] = str(copy.root.resolve())
    env["ORACLE_AUDIT_OUT"] = str(out_file)
    env["ORACLE_AUDIT_SOURCES"] = json.dumps([str((copy.root / s).resolve()) for s in suite.source_roots])
    env["ORACLE_AUDIT_TRACE"] = "1" if trace else "0"
    if node_ids is not None:
        select = work / "select.json"
        select.write_text(json.dumps(sorted(set(node_ids))), encoding="utf-8")
        env["ORACLE_AUDIT_SELECT"] = str(select)
        targets = sorted({nid.split("::", 1)[0] for nid in node_ids})
        paths = [os.path.relpath((copy.root / t).resolve(), project) for t in targets]
    else:
        paths = [os.path.relpath((copy.root / p).resolve(), project) for p in suite.test_paths]
    argv = [
        *pytest_launcher(copy, suite, python=python, overlay=overlay),
        "-p",
        PLUGIN_MODULE,
        "-p",
        "no:cacheprovider",
        f"--basetemp={copy.basetemp}",
        "--continue-on-collection-errors",
        "-q",
        *suite.pytest_args,
        *paths,
    ]
    started = time.monotonic()
    try:
        code, output = run_command(argv, cwd=project, env=env, timeout=timeout)
    finally:
        seconds = time.monotonic() - started
    run = SuiteRun(returncode=code, output=output[-2000:], seconds=seconds)
    if out_file.is_file():
        try:
            data = json.loads(out_file.read_text("utf-8"))
        except (OSError, ValueError):
            data = None
        if data is not None:
            run.results_found = True
            run.outcomes = dict(data.get("outcomes", {}))
            run.coverage = {k: [(f, q) for f, q in v] for k, v in data.get("coverage", {}).items()}
            run.tracer = data.get("tracer", "off")
            run.collect_errors = set(data.get("collect_errors", ()))
    shutil.rmtree(work, ignore_errors=True)
    return run


def can_collect(copy: IsolatedCopy, suite: SuiteSpec, *, python: str | None = None) -> bool:
    """True when pytest starts in the copy and collects at least one test (exit 0, 1 or 5 with items)."""
    project = (copy.root / suite.project_root).resolve()
    argv = [
        *pytest_launcher(copy, suite, python=python),
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        f"--basetemp={copy.basetemp}",
        "--continue-on-collection-errors",
        *suite.pytest_args,
        *(os.path.relpath((copy.root / p).resolve(), project) for p in suite.test_paths),
    ]
    try:
        code, output = run_command(
            argv, cwd=project, env=run_environment(copy, python=python), timeout=BASELINE_TIMEOUT_SECONDS
        )
    except OSError:
        return False
    return code in (0, 1) and "::" in output
