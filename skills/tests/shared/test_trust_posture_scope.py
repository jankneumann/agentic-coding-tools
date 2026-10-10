"""Trust-posture scenarios for dispatch-contract (Roadmap-Approval-Scoped Auto
Dispositions; design D5 posture digest and D8 scoped auto).

Every scenario of ``specs/trust-posture/spec.md`` has a test here. The gate is
the real :class:`~shared.approval_gate.ApprovalGate` reading a real posture
file; only the coordinator transport, the audit sink and the marker seam are
substituted.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills"))

from shared import trust_posture as tp  # noqa: E402
from shared.approval_gate import (  # noqa: E402
    ApprovalGate,
    Outcome,
    Resolution,
)
from shared.trust_posture import Gate  # noqa: E402

_REF = "gate-decision:11111111-2222-4333-8444-555555555555"


def _write(root: Path, gates: dict[str, Any], body: str = "# Posture\n") -> Path:
    doc = {"schema_version": 1, "gates": gates}
    path = root / tp.DEFAULT_CONTRACT_FILENAME
    path.write_text(
        "---\n" + yaml.safe_dump(doc, sort_keys=False) + "---\n\n" + body,
        encoding="utf-8",
    )
    return path


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, record: dict[str, Any]) -> bool:
        self.records.append(record)
        return True


class _Coordinator:
    """Files approvals and never resolves them, so notify windows time out."""

    def __init__(self) -> None:
        self.filed: list[dict[str, Any]] = []

    def request_approval(self, **kwargs: Any) -> str:
        self.filed.append(kwargs)
        return "approval-1"

    def push_notification(self, **_kwargs: Any) -> bool:
        return True

    def check_approval(self, _approval_id: str) -> str:
        return "pending"


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _gate(
    root: Path, marker: Optional[dict[str, Any]], coordinator: Any = None
) -> ApprovalGate:
    clock = _Clock()
    return ApprovalGate(
        coordinator=coordinator or _Coordinator(),
        audit=_Audit(),
        repo_root=str(root),
        clock=clock,
        sleep=clock.sleep,
        poll_interval_seconds=60,
        marker_reader=lambda _ctx: marker,
    )


# --------------------------------------------------------------------------- #
# Scoped auto (D8)
# --------------------------------------------------------------------------- #


def test_dispatched_run_with_a_valid_approval_reference_proceeds(tmp_path: Path) -> None:
    _write(tmp_path, {"proposal_approval": {"disposition": "auto"}})
    decision = _gate(tmp_path, {"roadmap_approval_ref": _REF}).evaluate(
        Gate.PROPOSAL_APPROVAL, {"change_id": "demo"}
    )
    assert decision.outcome is Outcome.PROCEED
    assert decision.resolution is Resolution.AUTO
    assert decision.scope == "roadmap_approval"
    assert decision.to_audit_record()["scope"] == "roadmap_approval"


def test_standalone_run_falls_back_to_the_unscoped_disposition(tmp_path: Path) -> None:
    _write(tmp_path, {"proposal_approval": {"disposition": "auto"}})
    decision = _gate(tmp_path, None).evaluate(Gate.PROPOSAL_APPROVAL, {"change_id": "demo"})
    assert decision.outcome is Outcome.BLOCKED
    assert decision.resolution is Resolution.POSTURE_BLOCK
    assert decision.scope == "unscoped"
    assert "unscoped fallback" in decision.reason


def test_declared_notify_fallback_is_used(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "replan_required": {
                "disposition": "auto",
                "unscoped": {
                    "disposition": "notify_with_timeout",
                    "timeout_seconds": 600,
                    "default_action": "block",
                },
            }
        },
    )
    coordinator = _Coordinator()
    decision = _gate(tmp_path, None, coordinator).evaluate(
        Gate.REPLAN_REQUIRED, {"change_id": "demo"}
    )
    assert len(coordinator.filed) == 1, "the unscoped notify fallback files an approval"
    assert coordinator.filed[0]["timeout_seconds"] == 600
    assert decision.outcome is Outcome.BLOCKED
    assert decision.resolution is Resolution.TIMEOUT_BLOCK
    assert decision.scope == "unscoped"


def test_a_reference_not_from_the_launch_marker_is_ignored(tmp_path: Path) -> None:
    _write(tmp_path, {"proposal_approval": {"disposition": "auto"}})
    decision = _gate(tmp_path, None).evaluate(
        Gate.PROPOSAL_APPROVAL,
        {"change_id": "demo", "roadmap_approval_ref": "gate-decision:Z"},
    )
    assert decision.outcome is Outcome.BLOCKED
    assert decision.to_audit_record()["scope"] == "unscoped"


def test_non_scoped_auto_gates_are_unaffected(tmp_path: Path) -> None:
    _write(tmp_path, {"pr_creation": {"disposition": "auto"}})
    decision = _gate(tmp_path, None).evaluate(Gate.PR_CREATION, {"change_id": "demo"})
    assert decision.outcome is Outcome.PROCEED
    assert decision.scope is None


@pytest.mark.parametrize(
    "gates, needle",
    [
        (
            {"proposal_approval": {"disposition": "auto", "unscoped": {"disposition": "auto"}}},
            "proposal_approval",
        ),
        ({"merge": {"disposition": "auto", "unscoped": {"disposition": "block"}}}, "merge"),
    ],
)
def test_invalid_unscoped_config_is_rejected(
    tmp_path: Path, gates: dict[str, Any], needle: str
) -> None:
    errors = tp.validate_posture_file(_write(tmp_path, gates))
    assert errors, "invalid unscoped config must fail validation"
    assert any(needle in error and "unscoped" in error for error in errors), errors


def test_unscoped_notify_requires_its_timeout_fields(tmp_path: Path) -> None:
    errors = tp.validate_posture_file(
        _write(
            tmp_path,
            {
                "proposal_approval": {
                    "disposition": "auto",
                    "unscoped": {"disposition": "notify_with_timeout"},
                }
            },
        )
    )
    assert any("timeout_seconds" in error for error in errors)


def test_absent_unscoped_defaults_to_block(tmp_path: Path) -> None:
    _write(tmp_path, {"proposal_approval": {"disposition": "auto"}})
    posture = tp.load_posture(tmp_path)
    assert posture.unscoped_for(Gate.PROPOSAL_APPROVAL) == tp.BLOCK


# --------------------------------------------------------------------------- #
# Posture digest (D5)
# --------------------------------------------------------------------------- #


def test_digest_ignores_prose_and_key_order(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    _write(
        first,
        {"merge": {"disposition": "block"}, "pr_creation": {"disposition": "auto"}},
        body="# One body\n",
    )
    _write(
        second,
        {"pr_creation": {"disposition": "auto"}, "merge": {"disposition": "block"}},
        body="# A completely different body\n\nMore prose.\n",
    )
    assert tp.posture_digest(tp.load_posture(first)) == tp.posture_digest(
        tp.load_posture(second)
    )


def test_digest_changes_when_a_disposition_or_parameter_changes(tmp_path: Path) -> None:
    _write(tmp_path, {"merge": {"disposition": "block"}})
    before = tp.posture_digest(tp.load_posture(tmp_path))
    _write(
        tmp_path,
        {"merge": {"disposition": "notify_with_timeout", "timeout_seconds": 60, "default_action": "block"}},
    )
    notify_60 = tp.posture_digest(tp.load_posture(tmp_path))
    _write(
        tmp_path,
        {"merge": {"disposition": "notify_with_timeout", "timeout_seconds": 90, "default_action": "block"}},
    )
    notify_90 = tp.posture_digest(tp.load_posture(tmp_path))
    assert len({before, notify_60, notify_90}) == 3


def test_absent_posture_has_the_fixed_all_block_digest(tmp_path: Path) -> None:
    absent = tp.load_posture(tmp_path)
    assert absent.present is False
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    _write(explicit, {gate.value: {"disposition": "block"} for gate in Gate})
    digest = tp.posture_digest(absent)
    assert digest == tp.posture_digest(None)
    assert digest == tp.posture_digest(tp.load_posture(explicit))
    assert len(digest) == 64 and int(digest, 16) >= 0
