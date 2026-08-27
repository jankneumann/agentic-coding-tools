#!/usr/bin/env python3
"""Run the architecture refresh pipeline against an arbitrary target directory.

Four modes:

* default — exec ``refresh_architecture.sh`` in place (legacy behavior).
* ``--check`` — read-only, mtime-independent freshness check via architecture
  provenance. Writes nothing; exits 0 only when ``fresh`` (ri-04 D4).
* ``--staged`` — deterministic stage → validate → promote → write provenance.
  A failed generation leaves the last known-good committed artifacts intact
  (spec scenarios architecture-refresh.8 and .9).
* ``--ensure`` — ``--check``, then ``--staged`` only if the check is not fresh.
  Purely a composition of the other two (D4): it owns no freshness logic, no
  digest routine and no promotion path, so there is exactly one implementation
  of each for the two to share.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence, TextIO

SCRIPTS_DIR = Path(__file__).resolve().parent
REFRESH_SCRIPT = SCRIPTS_DIR / "refresh_architecture.sh"

# Ensure ``arch_utils`` is importable under ``python -m`` invocation too.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

#: Required outputs a full/quick refresh must stage before promotion.
_REQUIRED_STAGED = ("architecture.graph.json", "architecture.summary.json")
_STAGING_DIRNAME = ".architecture-staging"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run architecture analysis using this repository's tooling against "
            "a target project directory."
        )
    )
    parser.add_argument(
        "--target-dir",
        default=".",
        help="Directory to analyze (used as working directory; default: current directory)",
    )
    parser.add_argument("--python-src-dir", help="Override PYTHON_SRC_DIR for analysis")
    parser.add_argument("--ts-src-dir", help="Override TS_SRC_DIR for analysis")
    parser.add_argument("--migrations-dir", help="Override MIGRATIONS_DIR for analysis")
    parser.add_argument("--arch-dir", help="Override ARCH_DIR output directory")
    parser.add_argument("--python", help="Python interpreter for the pipeline (maps to PYTHON)")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip Layer 3 report/view generation",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Read-only freshness check via architecture provenance. Writes "
            "nothing; prints a JSON drift report and exits 0 only when fresh."
        ),
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help=(
            "Deterministic stage/validate/promote refresh that writes "
            "architecture provenance and preserves last known-good on failure."
        ),
    )
    parser.add_argument(
        "--ensure",
        action="store_true",
        help=(
            "Check freshness and run the staged refresh only when the check is "
            "not fresh. Writes nothing on an already-fresh checkout."
        ),
    )
    return parser.parse_args(argv)


def build_env(args: argparse.Namespace) -> dict[str, str]:
    """Build child-process environment for refresh_architecture.sh."""
    env = dict(os.environ)
    env["SCRIPTS_DIR"] = str(SCRIPTS_DIR)

    overrides = {
        "PYTHON_SRC_DIR": args.python_src_dir,
        "TS_SRC_DIR": args.ts_src_dir,
        "MIGRATIONS_DIR": args.migrations_dir,
        "ARCH_DIR": args.arch_dir,
        "PYTHON": args.python,
    }
    for key, value in overrides.items():
        if value is not None:
            env[key] = value

    return env


# --------------------------------------------------------------------------- #
# Check mode (read-only)
# --------------------------------------------------------------------------- #
def run_check(target_dir: Path, *, mode: str, stream: TextIO | None = None) -> int:
    """Print a JSON freshness report; return 0 only when ``fresh``.

    *stream* defaults to stdout, which is what ``--check`` has always written
    to. Ensure mode overrides it so that the report it does not want on stdout
    (the "why I am about to refresh" one) does not have to be recomputed to be
    redirected.
    """
    from arch_utils.provenance import check_freshness

    result = check_freshness(target_dir, mode=mode)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True), file=stream or sys.stdout)
    return 0 if result.is_fresh else 1


# --------------------------------------------------------------------------- #
# Staged generation (stage → validate → promote → provenance)
# --------------------------------------------------------------------------- #
def _run_pipeline(target_dir: Path, env: dict[str, str], quick: bool) -> int:
    """Execute refresh_architecture.sh once. Split out for test injection."""
    cmd = ["bash", str(REFRESH_SCRIPT)]
    if quick:
        cmd.append("--quick")
    try:
        return subprocess.run(cmd, cwd=str(target_dir), env=env, check=False).returncode
    except OSError as exc:
        print(f"ERROR: failed to launch refresh script: {exc}", file=sys.stderr)
        return 1


def _required_outputs_present(staging: Path) -> bool:
    return all((staging / name).is_file() for name in _REQUIRED_STAGED)


def _promote(staging: Path, dest: Path) -> set[str]:
    """Copy every staged file into *dest*; return the promoted relative paths.

    Atomic per file, and a byte-identical write is skipped so an unchanged
    rebuild leaves no repository diff. Promotion is a one-way merge on purpose:
    a file in *dest* with no staged counterpart is left alone, because the
    optional stages skip soft (a partial refresh must not destroy the last good
    copy) and ``views/.gitkeep`` is committed but never staged.

    The returned set is what makes that survivable in the record — provenance
    needs to know which artifacts this run produced, and the output directory
    cannot tell it. A path is reported as promoted when it was staged, whether
    or not its bytes changed: an unchanged artifact was still regenerated from
    the current inputs, which is exactly what a deterministic producer means.
    """
    from arch_utils.provenance import _atomic_write_bytes  # canonical primitive

    promoted: set[str] = set()
    for src in sorted(staging.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(staging)
        _atomic_write_bytes(dest / rel, src.read_bytes())
        promoted.add(rel.as_posix())
    return promoted


def run_staged(target_dir: Path, args: argparse.Namespace) -> int:
    """Deterministic staged refresh; preserves committed artifacts on failure."""
    from arch_utils import provenance

    mode = "quick" if args.quick else "full"
    rev = provenance.analyzed_revision(target_dir)
    if rev is None:
        print(
            "ERROR: --staged requires a committed Git revision (HEAD)",
            file=sys.stderr,
        )
        return 2

    env = build_env(args)
    # Deterministic clock: every producer stamps the analyzed commit's epoch, so
    # identical inputs yield byte-identical staged artifacts.
    env["SOURCE_DATE_EPOCH"] = str(provenance.deterministic_epoch(target_dir, rev))

    staging = target_dir / _STAGING_DIRNAME
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    env["ARCH_DIR"] = str(staging.resolve())

    try:
        rc = _run_pipeline(target_dir, env, args.quick)
        if rc != 0 or not _required_outputs_present(staging):
            print(
                "refresh failed before promotion — committed architecture "
                "artifacts left untouched",
                file=sys.stderr,
            )
            return rc or 1

        dest = target_dir / provenance.ARCH_DIR_DEFAULT
        dest.mkdir(parents=True, exist_ok=True)
        promoted = _promote(staging, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # Record the roots the analyzers were actually pointed at. `env` carries the
    # --python-src-dir/--ts-src-dir/--migrations-dir overrides; os.environ does
    # not, so letting build_provenance fall back to the ambient environment
    # stamps roots that may not exist and yields an inert input fingerprint.
    # `promoted` is what this run actually produced. Without it the record is
    # built by scanning the output directory, which cannot distinguish a fresh
    # artifact from one a soft-skipped stage left behind at an older revision.
    doc = provenance.build_provenance(
        target_dir,
        mode=mode,
        roots=provenance.default_input_roots(env),
        generated=promoted,
    )
    changed, _sha = provenance.write_provenance(target_dir, doc)
    carried_over = [a["path"] for a in doc["artifacts"] if a.get("carried_over")]
    if carried_over:
        print(
            "NOTE: left in place from an earlier revision, not regenerated by "
            "this run:\n  " + "\n  ".join(carried_over),
            file=sys.stderr,
        )
    print(
        json.dumps(
            {
                "status": "generated",
                "source_revision": doc["source_revision"],
                "worktree_dirty": doc["worktree_dirty"],
                "input_fingerprint": doc["input_fingerprint"],
                "provenance_changed": changed,
                "provenance_path": (
                    f"{provenance.ARCH_DIR_DEFAULT}/{provenance.PROVENANCE_FILENAME}"
                ),
                "artifacts": [a["path"] for a in doc["artifacts"]],
                "carried_over": carried_over,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# Ensure mode (check, then staged refresh only if needed)
# --------------------------------------------------------------------------- #
def run_ensure(target_dir: Path, args: argparse.Namespace, *, mode: str) -> int:
    """Make the artifacts current, doing nothing if they already are (D4).

    Every byte of behaviour here comes from :func:`run_check` and
    :func:`run_staged`; the only thing this function decides is which of the two
    reports belongs on stdout. Fresh means the check report is the answer and no
    write happens at all. Not fresh means the check report is the *reason*, so it
    goes to stderr and the staged report — including its exit code — becomes the
    answer. Callers therefore parse exactly one JSON document either way.
    """
    buffered = io.StringIO()
    if run_check(target_dir, mode=mode, stream=buffered) == 0:
        sys.stdout.write(buffered.getvalue())
        return 0

    sys.stderr.write(buffered.getvalue())
    return run_staged(target_dir, args)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    target_dir = Path(args.target_dir).expanduser().resolve()

    if not target_dir.is_dir():
        print(f"ERROR: target directory not found: {target_dir}", file=sys.stderr)
        return 2

    mode = "quick" if args.quick else "full"

    if args.check:
        return run_check(target_dir, mode=mode)

    if not REFRESH_SCRIPT.is_file():
        print(f"ERROR: refresh script not found: {REFRESH_SCRIPT}", file=sys.stderr)
        return 2

    if args.ensure:
        return run_ensure(target_dir, args, mode=mode)

    if args.staged:
        return run_staged(target_dir, args)

    env = build_env(args)
    # Use bash explicitly so execution does not depend on executable bit state.
    cmd = ["bash", str(REFRESH_SCRIPT)]
    if args.quick:
        cmd.append("--quick")

    try:
        result = subprocess.run(cmd, cwd=target_dir, env=env, check=False)
    except OSError as exc:
        print(f"ERROR: failed to launch refresh script: {exc}", file=sys.stderr)
        return 1

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
