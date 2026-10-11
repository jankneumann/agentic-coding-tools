"""Helpers shared by the golden/broken outcome modules."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(workdir: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(workdir), capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def sh(workdir: Path, script: str) -> None:
    subprocess.run(["sh", "-c", script], cwd=str(workdir), capture_output=True, check=True)
