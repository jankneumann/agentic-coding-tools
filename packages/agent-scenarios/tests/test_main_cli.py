"""Subcommand dispatcher keeps the legacy form working (tasks 5.4/5.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_scenarios.__main__ import main
from tests.test_nightly_config import make_suite, write_config

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"


def test_legacy_form_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scenarios", str(SCENARIOS), "--validate-only"]) == 0
    cap = capsys.readouterr()
    assert len(json.loads(cap.out)["scenarios"]) >= 10
    assert "validated" in cap.err


def test_legacy_form_without_validate_only_prints_hint(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scenarios", str(SCENARIOS)]) == 0
    assert "no vendor CLIs configured" in capsys.readouterr().err


def test_legacy_empty_dir_exits_2(tmp_path: Path) -> None:
    assert main(["--scenarios", str(tmp_path)]) == 2


def test_validate_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "--scenarios", str(SCENARIOS)]) == 0
    assert "validated" in capsys.readouterr().err


def test_nightly_dry_run_routed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_suite(tmp_path)
    assert main(["nightly", "--config", str(write_config(tmp_path)), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["effective_vendors"] == ["claude", "codex"]


def test_nightly_invalid_config_exit_2(tmp_path: Path) -> None:
    assert main(["nightly", "--config", str(tmp_path / "nope.yaml")]) == 2


def test_results_routed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = tmp_path / "r.jsonl"
    assert main(["results", "query", "--store", str(store)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert main(["results", "trend", "--store", str(store)]) == 0
    assert main(["results", "latest", "--store", str(store)]) == 0


def test_gaps_flush_routed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["gaps", "flush", "--spool", str(tmp_path / "s.jsonl")]) == 0
    assert json.loads(capsys.readouterr().out) == {"delivered": 0, "remaining": 0}


def test_unknown_subcommand_args_fail() -> None:
    with pytest.raises(SystemExit):
        main(["results"])  # missing sub-subcommand
