#!/usr/bin/env python3
"""Install the pinned oasdiff for the contract breaking-change gate, verified.

Design D4 originally pinned a release tarball by sha256. Release-asset hosts are
not reachable from every environment this runs in, so the pin is instead a Go
module version installed with ``go install``, verified through Go's own module
authentication:

1. Refuse if checksum verification is disabled for the module: ``GOSUMDB=off``,
   ``GOFLAGS`` containing ``-insecure``, or ``GONOSUMDB`` / ``GONOSUMCHECK`` /
   ``GOINSECURE`` / ``GOPRIVATE`` patterns matching the module path. Both the
   process environment and ``go env`` (which includes ``go env -w`` settings)
   are checked.
2. ``go mod download -json MODULE@VERSION`` (verified against sum.golang.org by
   Go) must report a non-empty ``Sum`` and a ``GoModSum`` equal to the value
   recorded in ``oasdiff.sum`` next to this script.
3. ``go install MODULE@VERSION`` with ``GOBIN=--bin-dir``; the binary path is
   printed on stdout.

Any refusal exits non-zero before anything is installed, so the gate cannot run
a comparison with an unverified binary. Stdlib only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

MODULE = "github.com/oasdiff/oasdiff"
VERSION = "v1.33.0"
SUM_FILE = Path(__file__).resolve().parent / "oasdiff.sum"
PATTERN_VARS = ("GONOSUMDB", "GONOSUMCHECK", "GOINSECURE", "GOPRIVATE")
GO_ENV_VARS = ("GOSUMDB", "GOFLAGS", "GONOSUMDB", "GOINSECURE", "GOPRIVATE")


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str], dict[str, str]], Result]


class FetchError(Exception):
    pass


def subprocess_runner(cmd: list[str], env: dict[str, str]) -> Result:
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    return Result(proc.returncode, proc.stdout, proc.stderr)


def match_prefix_patterns(patterns: str, target: str) -> bool:
    """Go's module.MatchPrefixPatterns: comma-separated globs, path-prefix match."""
    target_parts = target.split("/")
    for pattern in patterns.split(","):
        pattern = pattern.strip().rstrip("/")
        if not pattern:
            continue
        glob_parts = pattern.split("/")
        if len(glob_parts) > len(target_parts):
            continue
        prefix = target_parts[: len(glob_parts)]
        if all(
            fnmatch.fnmatchcase(t, g) for t, g in zip(prefix, glob_parts, strict=True)
        ):
            return True
    return False


def verification_disabled(env: Mapping[str, str]) -> str | None:
    """Return why checksum verification is off for MODULE, or None if it is on."""
    if env.get("GOSUMDB", "").strip().lower() == "off":
        return "GOSUMDB=off"
    for flag in env.get("GOFLAGS", "").split():
        if flag.lstrip("-").split("=")[0] == "insecure":
            return f"GOFLAGS contains {flag}"
    for var in PATTERN_VARS:
        value = env.get(var, "")
        if match_prefix_patterns(value, MODULE):
            return f"{var}={value} matches {MODULE}"
    return None


def read_recorded_gomodsum(sum_file: Path) -> str:
    for line in sum_file.read_text().splitlines():
        fields = line.split()
        if (
            len(fields) == 3
            and fields[0] == MODULE
            and fields[1] == f"{VERSION}/go.mod"
        ):
            return fields[2]
    raise FetchError(f"{sum_file}: no '{MODULE} {VERSION}/go.mod h1:...' line")


def fetch(
    *, bin_dir: Path, sum_file: Path, env: Mapping[str, str], runner: Runner
) -> Path:
    env = dict(env)
    spec = f"{MODULE}@{VERSION}"

    reason = verification_disabled(env)
    if reason is None:
        res = runner(["go", "env", "-json", *GO_ENV_VARS], env)
        if res.returncode != 0:
            raise FetchError(f"go env failed: {res.stderr.strip()}")
        reason = verification_disabled(json.loads(res.stdout or "{}"))
    if reason:
        raise FetchError(
            f"refusing: module checksum verification is disabled ({reason})"
        )

    recorded = read_recorded_gomodsum(sum_file)

    res = runner(["go", "mod", "download", "-json", spec], env)
    try:
        info = json.loads(res.stdout) if res.stdout.strip() else {}
    except json.JSONDecodeError:
        info = {}
    if res.returncode != 0 or info.get("Error"):
        detail = info.get("Error") or res.stderr.strip()
        raise FetchError(f"refusing: go mod download {spec} failed: {detail}")
    if not info.get("Sum"):
        raise FetchError(f"refusing: go mod download reported no module Sum for {spec}")
    if info.get("GoModSum") != recorded:
        raise FetchError(
            f"refusing: GoModSum mismatch for {spec}: "
            f"recorded {recorded}, downloaded {info.get('GoModSum')!r}"
        )

    bin_dir.mkdir(parents=True, exist_ok=True)
    res = runner(["go", "install", spec], {**env, "GOBIN": str(bin_dir)})
    if res.returncode != 0:
        raise FetchError(f"go install {spec} failed: {res.stderr.strip()}")
    return bin_dir / "oasdiff"


def main(argv: list[str] | None = None, *, runner: Runner = subprocess_runner) -> int:
    parser = argparse.ArgumentParser(
        description="Install the pinned, verified oasdiff."
    )
    parser.add_argument("--bin-dir", required=True, type=Path)
    parser.add_argument("--sum-file", default=SUM_FILE, type=Path)
    args = parser.parse_args(argv)
    try:
        binary = fetch(
            bin_dir=args.bin_dir.resolve(),
            sum_file=args.sum_file,
            env=os.environ,
            runner=runner,
        )
    except FetchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(binary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
