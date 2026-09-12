"""Tests for review_ledger.py: stable ids, fingerprint merge, compact, blocking."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
SCRIPTS = REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from jsonschema import Draft202012Validator

from review_ledger import (  # noqa: E402
    ScopeViolation,
    allowed_paths,
    blocking_items,
    check_fix_scope,
    compact,
    fingerprint,
    is_blocking_item,
    load_or_create,
    merge_findings,
    parked_path,
    reject_out_of_scope_fix,
    save,
)

CONTRACTS = change_dir(REPO_ROOT, "ledger-driven-review-convergence") / "contracts"
LEDGER_SCHEMA = json.loads((CONTRACTS / "review-ledger.schema.json").read_text())


def _cf(**overrides: object) -> dict:
    finding = {
        "id": 1,
        "status": "confirmed",
        "agreed_type": "bug",
        "agreed_axis": "correctness",
        "agreed_criticality": "high",
        "evidence_class": "deterministic",
        "file_path": "src/api.py",
        "description": "Missing null check in parse_line helper",
        "vendor_hits": ["codex", "grok"],
    }
    finding.update(overrides)
    return finding


def test_load_or_create_creates_ledger(tmp_path: Path) -> None:
    artifacts = tmp_path / "change"
    artifacts.mkdir()
    ledger = load_or_create(artifacts, "demo")
    path = artifacts / ".review-ledger" / "ledger.json"
    assert path.exists()
    assert ledger["change_id"] == "demo"
    assert ledger["items"] == []
    Draft202012Validator(LEDGER_SCHEMA).validate(
        json.loads(path.read_text())
    )


def test_same_defect_keeps_id_across_rounds(tmp_path: Path) -> None:
    artifacts = tmp_path / "change"
    artifacts.mkdir()
    ledger = load_or_create(artifacts, "demo")
    first = merge_findings(ledger, [_cf()], round_num=1)
    assert first[0]["id"] == 1
    second = merge_findings(
        ledger,
        [_cf(id=99, description="Missing null check in parse_line helper")],
        round_num=2,
    )
    assert second[0]["id"] == 1
    assert second[0]["last_seen_round"] == 2
    assert second[0]["first_seen_round"] == 1
    save(ledger, artifacts)
    Draft202012Validator(LEDGER_SCHEMA).validate(
        json.loads((artifacts / ".review-ledger" / "ledger.json").read_text())
    )


def test_fingerprint_match_merges_without_synthesizer_id() -> None:
    a = fingerprint("correctness", "src/api.py", "Missing null check in parse_line")
    b = fingerprint("correctness", "src/api.py", "Missing null check in parse_line")
    assert a == b
    c = fingerprint("security", "src/api.py", "Missing null check in parse_line")
    assert a != c


def test_new_defect_gets_new_id(tmp_path: Path) -> None:
    artifacts = tmp_path / "change"
    artifacts.mkdir()
    ledger = load_or_create(artifacts, "demo")
    merge_findings(ledger, [_cf()], round_num=1)
    merge_findings(
        ledger,
        [_cf(id=2, description="Unbounded retry loop in worker", file_path="src/worker.py")],
        round_num=1,
    )
    ids = [item["id"] for item in ledger["items"]]
    assert ids == [1, 2]


def test_compact_retires_when_tokens_gone(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    target = src / "api.py"
    target.write_text("Missing null check in parse_line helper still present\n")
    artifacts = tmp_path / "change"
    artifacts.mkdir()
    ledger = load_or_create(artifacts, "demo")
    merge_findings(
        ledger,
        [_cf(description="Missing null check in parse_line helper", file_path="src/api.py")],
        round_num=1,
    )
    # Rewrite so none of the description tokens remain.
    target.write_text("def ok():\n    return 1\n")
    compact(ledger, tmp_path)
    assert ledger["items"][0]["status"] == "retired"


def test_compact_retires_missing_file(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    artifacts = tmp_path / "change"
    artifacts.mkdir()
    ledger = load_or_create(artifacts, "demo")
    merge_findings(
        ledger,
        [_cf(file_path="src/gone.py", description="Dead helper still imported")],
        round_num=1,
    )
    compact(ledger, tmp_path)
    assert ledger["items"][0]["status"] == "retired"


def test_compact_reopens_addressed_if_tokens_remain(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    target = src / "api.py"
    target.write_text("Missing null check in parse_line helper still here\n")
    artifacts = tmp_path / "change"
    artifacts.mkdir()
    ledger = load_or_create(artifacts, "demo")
    merge_findings(
        ledger,
        [_cf(description="Missing null check in parse_line helper", file_path="src/api.py")],
        round_num=1,
    )
    ledger["items"][0]["status"] = "addressed"
    compact(ledger, tmp_path)
    assert ledger["items"][0]["status"] == "open"


def test_unconfirmed_medium_judgment_does_not_block() -> None:
    item = {
        "status": "open",
        "consensus_status": "unconfirmed",
        "criticality": "medium",
        "evidence_class": "judgment",
    }
    assert is_blocking_item(item) is False
    assert blocking_items({"items": [item]}) == []


def test_confirmed_high_judgment_blocks() -> None:
    item = {
        "status": "open",
        "consensus_status": "confirmed",
        "criticality": "high",
        "evidence_class": "judgment",
    }
    assert is_blocking_item(item) is True


def test_deterministic_unconfirmed_medium_blocks() -> None:
    item = {
        "status": "open",
        "consensus_status": "unconfirmed",
        "criticality": "medium",
        "evidence_class": "deterministic",
    }
    assert is_blocking_item(item) is True


def test_parked_and_retired_never_block() -> None:
    parked = {
        "status": "parked",
        "consensus_status": "disagreement",
        "criticality": "critical",
        "evidence_class": "deterministic",
    }
    retired = {
        "status": "retired",
        "consensus_status": "confirmed",
        "criticality": "critical",
        "evidence_class": "deterministic",
    }
    assert is_blocking_item(parked) is False
    assert is_blocking_item(retired) is False


def test_retired_match_does_not_reopen(tmp_path: Path) -> None:
    artifacts = tmp_path / "change"
    artifacts.mkdir()
    ledger = load_or_create(artifacts, "demo")
    merge_findings(ledger, [_cf()], round_num=1)
    ledger["items"][0]["status"] = "retired"
    merge_findings(ledger, [_cf(id=7)], round_num=2)
    assert len(ledger["items"]) == 1
    assert ledger["items"][0]["status"] == "retired"


def test_allowed_paths_are_cited_file_only() -> None:
    item = {"file_path": "src/api.py", "type": "bug"}
    assert allowed_paths(item) == ["src/api.py"]


def test_spec_gap_includes_spec_file() -> None:
    item = {
        "file_path": "src/api.py",
        "type": "spec_gap",
        "spec_file": "openspec/changes/demo/specs/api/spec.md",
    }
    paths = allowed_paths(item)
    assert "src/api.py" in paths
    assert "openspec/changes/demo/specs/api/spec.md" in paths


def test_out_of_scope_fix_is_rejected() -> None:
    result = check_fix_scope(
        files_modified=["src/frontend/app.tsx"],
        allowed=["src/api.py"],
    )
    assert result["compliant"] is False
    with pytest.raises(ScopeViolation):
        reject_out_of_scope_fix(["src/frontend/app.tsx"], ["src/api.py"])


def test_in_scope_fix_passes() -> None:
    result = check_fix_scope(
        files_modified=["src/api.py"],
        allowed=["src/api.py"],
    )
    assert result["compliant"] is True


def test_parked_path_location(tmp_path: Path) -> None:
    assert parked_path(tmp_path / "change") == (
        tmp_path / "change" / "reviews" / "parked-disagreements.json"
    )
