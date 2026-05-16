from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SMOKE = ROOT / "skills" / "autopilot" / "scripts" / "smoke_provider_dispatch.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SMOKE), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_codex_dry_run_smoke_succeeds() -> None:
    proc = _run("--provider", "codex", "--dry-run", "--json")

    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body["provider"] == "codex"
    assert body["result"]["outcome"] == "complete"
    assert body["payload"]["model"].startswith("gpt-")
    assert body["payload"]["model"] not in {"opus", "sonnet", "haiku"}


def test_gemini_dry_run_smoke_succeeds() -> None:
    proc = _run("--provider", "gemini", "--dry-run", "--json")

    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body["provider"] == "gemini"
    assert body["result"]["outcome"] == "complete"
    assert body["payload"]["model"].startswith("gemini-")
    assert body["payload"]["model"] not in {"opus", "sonnet", "haiku"}


def test_invalid_non_claude_alias_rejected() -> None:
    proc = _run(
        "--provider",
        "codex",
        "--dry-run",
        "--model",
        "opus",
        "--json",
    )

    assert proc.returncode != 0
    assert "Claude alias" in proc.stderr
