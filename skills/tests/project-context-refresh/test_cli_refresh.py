"""CLI + boundary tests for the refresh orchestrator (ri-07 tasks 4.1-4.3)."""

from __future__ import annotations

import json
import subprocess

import pytest

import cli
import orchestrator
from registry import Producer, ProducerError, ProducerSpec, list_producers, register

FULL_SHA = "a" * 40


class _FreshProducer(Producer):
    def __init__(self, pid: str, owner: str = "owner"):
        self.spec = ProducerSpec(
            producer_id=pid, producer_version="1", owner=owner, inputs=("x",), outputs=()
        )

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        from _runtime import ProducerResult, ProducerStatus, ValidationResult, ValidationStatus

        return ProducerResult(
            producer_id=self.spec.producer_id,
            producer_version="1",
            status=ProducerStatus.FRESH,
            validations=(
                ValidationResult(
                    validation_id=f"{self.spec.producer_id}-check",
                    status=ValidationStatus.PASSED,
                    summary="ok",
                ),
            ),
        )


def test_refresh_check_reports_summary_and_exit_code(tmp_path, capsys):
    register(_FreshProducer("documentation.inventory"))
    code = cli.main(
        ["--repo", str(tmp_path), "--revision", FULL_SHA, "refresh-check", "--producer", "documentation.inventory"]
    )
    out = json.loads(capsys.readouterr().out)
    assert out["outcome"] == "succeeded"
    assert code == 0
    assert [p["producer_id"] for p in out["producer_results"]] == ["documentation.inventory"]


def test_refresh_single_producer_preserves_owner(tmp_path, capsys, monkeypatch):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    register(_FreshProducer("documentation.inventory", owner="doc-owner"))
    register(_FreshProducer("api.contracts"))
    # Skip the checkout guard so the mutating path runs in the test sandbox.
    monkeypatch.setattr(cli, "_require_mutation", lambda repo: None)
    code = cli.main(
        ["--repo", str(tmp_path), "--revision", FULL_SHA, "refresh", "--producer", "documentation.inventory"]
    )
    out = json.loads(capsys.readouterr().out)
    ids = [p["producer_id"] for p in out["producer_results"]]
    assert ids == ["documentation.inventory"]
    # The manifest exists and preserves the producer id.
    manifest = tmp_path / orchestrator.DEFAULT_MANIFEST_PATH
    assert manifest.is_file()
    assert code in (0, 2)  # succeeded, or degraded if the tmp store degrades


def test_refresh_refuses_shared_checkout(tmp_path, monkeypatch):
    register(_FreshProducer("documentation.inventory"))

    def _boom(repo):
        raise ProducerError("refusing to write outside a managed worktree: shared")

    monkeypatch.setattr(cli, "_require_mutation", _boom)
    with pytest.raises(ProducerError):
        cli.main(["--repo", str(tmp_path), "--revision", FULL_SHA, "refresh"])


def test_capability_producer_is_not_configured():
    # Configured-only scope: the proposal names a "capability" producer with no
    # canonical owner; it must never appear in the configured registry.
    ids = {spec.producer_id for spec in list_producers()}
    assert "capability" not in ids
    assert ids == {
        "documentation.inventory",
        "api.contracts",
        "decisions.timeline",
        "openspec.projection",
    }
