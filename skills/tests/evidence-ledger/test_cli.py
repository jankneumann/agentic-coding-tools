"""CLI contract (design D9): exit 0 valid, 1 violations, 2 usage/load error."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "skills" / "evidence-ledger" / "scripts" / "evidence_ledger.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_valid_ledger_exits_zero() -> None:
    result = _run("validate", FIXTURES / "valid" / "full_ledger.yaml")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_invalid_ledger_exits_one_with_tab_separated_lines() -> None:
    path = FIXTURES / "invalid" / "signal_role_mismatch__control_is_variable.json"
    result = _run("validate", path)
    assert result.returncode == 1
    code, where, message = result.stdout.strip().split("\t")
    assert (code, where) == ("signal_role_mismatch", "/signals/0/control_fact")
    assert message


def test_edited_fact_with_previous_exits_one() -> None:
    result = _run(
        "validate",
        FIXTURES / "revisions" / "edited_fact_in_place.json",
        "--previous",
        FIXTURES / "revisions" / "base.json",
        "--json",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert [v["code"] for v in payload["violations"]] == ["fact_mutated"]
    assert set(payload["violations"][0]) == {"code", "path", "message"}


def test_dispute_via_reverify_with_previous_exits_zero() -> None:
    result = _run(
        "validate",
        FIXTURES / "revisions" / "dispute_via_reverify.json",
        "--previous",
        FIXTURES / "revisions" / "base.json",
        "--json",
    )
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout) == {"valid": True, "violations": []}


def test_missing_file_exits_two(tmp_path: Path) -> None:
    result = _run("validate", tmp_path / "absent.yaml")
    assert result.returncode == 2
    assert "absent.yaml" in result.stderr


def test_unparseable_file_exits_two(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert _run("validate", broken).returncode == 2


def test_missing_subcommand_exits_two() -> None:
    assert _run().returncode == 2


def test_output_is_deterministic_across_runs() -> None:
    path = FIXTURES / "invalid" / "schema_violation__fact_missing_tool_version.json"
    first = _run("validate", path, "--json")
    second = _run("validate", path, "--json")
    assert first.returncode == second.returncode == 1
    assert first.stdout == second.stdout
