#!/usr/bin/env python3
"""Run the skill test suites that cannot share a pytest process.

Why this exists
---------------
Many skills ship their own ``scripts/models.py``, ``scripts/render_report.py``
and friends, and their tests do::

    sys.path.insert(0, <skill>/scripts)
    from models import Finding

Two such suites in a single pytest process race for the ``models`` entry in
``sys.modules``: whichever imports first wins, and every later suite silently
imports the *other* skill's module. That surfaces as
``ImportError: cannot import name 'Finding' from 'models'`` pointing at a
completely unrelated skill.

``--import-mode=importlib`` (set in pyproject) fixes collisions between
*test module* names. It does nothing for the ``sys.path`` imports of the code
under test, so the isolation has to happen at the process level.

That is the whole reason ``testpaths`` in ``skills/pyproject.toml`` is a
hand-maintained list rather than plain discovery: it is the subset of suites
that happen not to collide. Everything outside it was simply never run —
47 directories at the time this script was written. This script runs that
complement, one pytest process per directory, so no suite is excluded merely
because it shares a module name with another.

Coverage is computed as a complement, not a second hand-maintained list: any
new test directory is picked up automatically by whichever side it falls on.
The only way to opt out is to add it to ``EXCLUDED`` below with a written
justification.

Usage::

    python tests/run_isolated_suites.py            # all isolated suites
    python tests/run_isolated_suites.py --list     # print what would run
    python tests/run_isolated_suites.py --jobs 4   # cap parallelism
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent.parent

# Directory names never worth walking into.
_PRUNE = {".venv", "__pycache__", ".git", "node_modules", ".pytest_cache", ".ruff_cache"}

# `install_assets/` holds verbatim copies of skill payloads that `install.sh`
# ships to consumers. Their tests are the same files as the first-party ones,
# so running them would double every count and re-import the same module names
# under different paths. `install.sh --check` is what validates that payload.
_PRUNE_PAYLOAD = {"install_assets"}

# Directories that look like suites to the discovery walk but are not. Every
# entry needs a written justification, same rule as PIP_AUDIT_IGNORED_VULNS in
# .github/workflows/security.yml — when the reason expires, delete the entry
# rather than carrying it forward.
EXCLUDED: dict[str, str] = {
    # `test_linker.py` here is a production module — the linker that resolves
    # test files for the architecture graph — not a pytest suite. It matches
    # test_*.py by coincidence of naming and collects zero tests.
    "refresh-architecture/scripts/insights": (
        "test_linker.py is a production module, not a suite (collects 0 tests)"
    ),
}

# Suites that run in the post-merge tier instead of blocking a PR, because they
# are currently red for reasons unrelated to the change under review. These were
# invisible until this runner started executing them; quarantining is what makes
# turning them on affordable without spiking the pre-merge failure rate.
#
# This list is a debt ledger, not a parking lot: every entry names what is
# broken, and an entry whose suite goes green must be deleted (the post-merge
# job fails on an unexpected pass, so it cannot rot silently).
QUARANTINED: dict[str, str] = {
    "tests/docs": (
        "asserts CLAUDE.md inlines /prototype-feature and "
        "--prototype-context; CLAUDE.md was refactored into docs/guides/* "
        "link stubs, so the assertions target content that moved"
    ),
    "tests/agent-coordinator": "2 failures, untriaged",
    "tests/autopilot": "8 failures, untriaged",
    "tests/phase-record-compaction": "5 failures, untriaged",
    "tests/playwright-validator": "6 failures, untriaged",
}


def _covered_by_testpaths() -> list[str]:
    """Return the testpaths entries from skills/pyproject.toml."""
    cfg = tomllib.loads((SKILLS_ROOT / "pyproject.toml").read_text())
    return cfg["tool"]["pytest"]["ini_options"]["testpaths"]


def discover_all_test_dirs() -> set[str]:
    """Every directory under skills/ holding at least one test_*.py file."""
    found: set[str] = set()
    for root, dirs, files in os.walk(SKILLS_ROOT):
        dirs[:] = [d for d in dirs if d not in _PRUNE and d not in _PRUNE_PAYLOAD]
        if any(f.startswith("test_") and f.endswith(".py") for f in files):
            found.add(os.path.relpath(root, SKILLS_ROOT))
    return found


def isolated_suites(tier: str = "pre-merge") -> list[str]:
    """Test dirs that the in-process pytest run does not already cover.

    ``pre-merge`` returns the blocking set (quarantined suites removed),
    ``post-merge`` returns only the quarantined ones, ``all`` returns both.
    """
    testpaths = _covered_by_testpaths()
    out = []
    for d in discover_all_test_dirs():
        if any(d == t or d.startswith(t + os.sep) for t in testpaths):
            continue
        if d in EXCLUDED:
            continue
        if tier == "pre-merge" and d in QUARANTINED:
            continue
        if tier == "post-merge" and d not in QUARANTINED:
            continue
        out.append(d)
    return sorted(out)


def _suite_pythonpath(suite: str) -> list[str]:
    """Directories a suite needs on sys.path to import the code it tests.

    Skill tests import their subject as a top-level module (``from models
    import Finding``) after inserting the skill's ``scripts/`` dir. Suites that
    live beside that code get it implicitly; ones invoked from the repo root do
    not, so reconstruct it here rather than editing 47 conftest files.
    """
    parts = Path(suite).parts
    paths = [str(SKILLS_ROOT / "tests" / "_shared")]

    # `<skill>/scripts/tests` and `<skill>/scripts` -> `<skill>/scripts`
    if "scripts" in parts:
        idx = parts.index("scripts")
        paths.append(str(SKILLS_ROOT.joinpath(*parts[: idx + 1])))
    # `<skill>/tests` -> `<skill>/scripts` when the skill keeps one
    elif len(parts) >= 2 and parts[0] != "tests":
        candidate = SKILLS_ROOT / parts[0] / "scripts"
        if candidate.is_dir():
            paths.append(str(candidate))
    # `tests/<skill>` -> `<skill>/scripts` when a matching skill exists
    elif len(parts) >= 2 and parts[0] == "tests":
        candidate = SKILLS_ROOT / parts[1] / "scripts"
        if candidate.is_dir():
            paths.append(str(candidate))

    return paths


def run_suite(suite: str) -> tuple[str, int, float, str]:
    """Run one suite in its own pytest process. Returns (suite, rc, secs, tail)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [*_suite_pythonpath(suite), env.get("PYTHONPATH", "")])
    )

    start = time.monotonic()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            suite,
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        cwd=SKILLS_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - start
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    return suite, proc.returncode, elapsed, tail[-1] if tail else "(no output)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print the suites and exit")
    ap.add_argument(
        "--tier",
        choices=("pre-merge", "post-merge", "all"),
        default="pre-merge",
        help="pre-merge blocks PRs; post-merge runs the quarantined suites",
    )
    ap.add_argument(
        "--jobs",
        type=int,
        default=min(8, (os.cpu_count() or 2)),
        help="parallel pytest processes (default: min(8, cpu count))",
    )
    args = ap.parse_args()

    suites = isolated_suites(args.tier)
    if args.list:
        for s in suites:
            print(s)
        return 0

    if not suites:
        print("No isolated suites discovered.")
        return 0

    print(
        f"Running {len(suites)} isolated skill suites "
        f"({args.tier} tier) across {args.jobs} processes\n"
    )
    failures: list[tuple[str, str]] = []
    unexpected_passes: list[str] = []
    total = 0.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for suite, rc, secs, tail in pool.map(run_suite, suites):
            total += secs
            quarantined = suite in QUARANTINED
            if rc == 0:
                mark = "ok  "
                # A quarantined suite that passes has been fixed; the ledger
                # entry is now a lie and must be deleted. Failing here is what
                # stops QUARANTINED from silently accumulating dead entries.
                if quarantined:
                    mark = "PASS"
                    unexpected_passes.append(suite)
            else:
                mark = "known" if quarantined else "FAIL"
                if not quarantined:
                    failures.append((suite, tail))
            print(f"  {mark} {suite:<48} {secs:5.1f}s  {tail}")

    print(f"\n{len(suites)} suites, {total:.1f}s of process time")

    if unexpected_passes:
        print(f"\n{len(unexpected_passes)} quarantined suite(s) now pass:")
        for suite in unexpected_passes:
            print(f"  {suite}")
        print(
            "\nRemove them from QUARANTINED in tests/run_isolated_suites.py "
            "so they block PRs again."
        )
    if failures:
        print(f"\n{len(failures)} suite(s) failed:")
        for suite, tail in failures:
            print(f"  {suite}: {tail}")
        print(
            "\nReproduce a single suite with:\n"
            "  cd skills && .venv/bin/python -m pytest <suite> -q"
        )

    if failures or unexpected_passes:
        return 1

    print("All isolated suites passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
