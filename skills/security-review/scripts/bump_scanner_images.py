#!/usr/bin/env python3
"""Re-resolve each pinned scanner image tag to its current digest.

A pin that nobody can bump becomes a pin nobody trusts, and the usual next step
is someone quietly reverting to a floating tag. This makes the bump one command
whose output is a reviewable diff naming exactly which scanner moved.

    python3 bump_scanner_images.py            # rewrite scanner-images.env
    python3 bump_scanner_images.py --check     # report drift, change nothing

`--check` exits 1 when a pin is behind its tag, so a scheduled job can open a
bump PR rather than letting the pin rot silently — the failure mode pinning is
supposed to replace, not introduce.

Resolution uses `skopeo inspect --raw`, whose output is the manifest *list*, so
the digest is the multi-arch one and resolves identically on arm64 and amd64.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / "scanner-images.env"
_ASSIGN = re.compile(r'^(?P<name>[A-Z_]+)_IMAGE_(?P<kind>TAG|DIGEST)="(?P<value>[^"]*)"$')


def resolve_digest(reference: str) -> str:
    """The manifest-list digest for `reference`, as `sha256:...`."""
    proc = subprocess.run(
        ["skopeo", "inspect", "--raw", f"docker://{reference}"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"could not resolve {reference}: {proc.stderr.decode(errors='replace').strip()}"
        )
    # Hash the raw manifest bytes rather than parsing a field out of it: that is
    # what a registry digest *is*, and it stays correct across manifest schema
    # versions that move or rename the field.
    return "sha256:" + hashlib.sha256(proc.stdout).hexdigest()


def read_pins(text: str) -> dict[str, dict[str, str]]:
    pins: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        m = _ASSIGN.match(line.strip())
        if m:
            pins.setdefault(m["name"], {})[m["kind"].lower()] = m["value"]
    return pins


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="Report drift and exit 1 if any pin is behind its tag; write nothing.",
    )
    parser.add_argument("--env-file", type=Path, default=ENV_FILE)
    args = parser.parse_args(argv)

    text = args.env_file.read_text(encoding="utf-8")
    pins = read_pins(text)
    if not pins:
        print(f"no pins found in {args.env_file}", file=sys.stderr)
        return 2

    drifted: list[str] = []
    for name, fields in sorted(pins.items()):
        tag = fields.get("tag", "")
        if not tag:
            continue
        try:
            current = resolve_digest(tag)
        except RuntimeError as exc:
            print(f"WARN: {exc}", file=sys.stderr)
            continue
        pinned = fields.get("digest", "")
        if current == pinned:
            print(f"{name}: up to date ({tag})")
            continue
        drifted.append(name)
        print(f"{name}: {tag}\n  pinned  {pinned or '(none)'}\n  current {current}")
        if not args.check:
            text = re.sub(
                rf'^{name}_IMAGE_DIGEST="[^"]*"$',
                f'{name}_IMAGE_DIGEST="{current}"',
                text,
                flags=re.M,
            )

    if args.check:
        if drifted:
            print(
                f"\n{len(drifted)} pin(s) behind their tag: {', '.join(drifted)}. "
                "Run `make security-bump-scanner-images` and review the upstream "
                "changelog — a new rule set can change findings on unchanged code.",
                file=sys.stderr,
            )
            return 1
        return 0

    if drifted:
        text = re.sub(r"^# Resolved .*$", f"# Resolved {_today()}", text, count=1, flags=re.M)
        args.env_file.write_text(text, encoding="utf-8")
        print(f"\nrewrote {args.env_file} ({len(drifted)} pin(s) bumped)")
    return 0


def _today() -> str:
    from datetime import date

    return date.today().isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
