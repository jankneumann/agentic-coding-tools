"""CLI + boundary tests for the refresh orchestrator (ri-07 tasks 4.1-4.3)."""

from __future__ import annotations

import json
import subprocess

import pytest

import cli
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


def test_refresh_check_reports_summary_with_owner_and_exit_code(tmp_path, capsys):
    register(_FreshProducer("documentation.inventory", owner="doc-owner"))
    code = cli.main(
        ["--repo", str(tmp_path), "--revision", FULL_SHA, "refresh-check", "--producer", "documentation.inventory"]
    )
    out = json.loads(capsys.readouterr().out)
    assert out["outcome"] == "succeeded"
    assert code == 0
    entry = out["producer_results"][0]
    assert entry["producer_id"] == "documentation.inventory"
    # Owner is preserved via the registry join (ri-06 ProducerResult has no owner field).
    assert entry["owner"] == "doc-owner"


def test_scoped_refresh_reports_producer_without_manifest(tmp_path, capsys, monkeypatch):
    register(_FreshProducer("documentation.inventory", owner="doc-owner"))
    register(_FreshProducer("api.contracts"))
    # Skip the checkout guard so the mutating path runs in the test sandbox.
    monkeypatch.setattr(cli, "_require_mutation", lambda repo: None)
    code = cli.main(
        ["--repo", str(tmp_path), "--revision", FULL_SHA, "refresh", "--producer", "documentation.inventory"]
    )
    out = json.loads(capsys.readouterr().out)
    assert [p["producer_id"] for p in out["producer_results"]] == ["documentation.inventory"]
    assert out["producer_results"][0]["owner"] == "doc-owner"
    # A scoped run emits no aggregate manifest and no durable operation.
    assert out["manifest_path"] is None
    assert out["operation_id"] is None
    assert code == 0


def test_refresh_refuses_real_shared_checkout(tmp_path):
    # Exercise the REAL checkout-policy guard (no monkeypatch): a plain checkout
    # that is not a managed worktree must be refused, so the gate is not decoration.
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    register(_FreshProducer("documentation.inventory"))
    with pytest.raises(ProducerError, match="managed worktree"):
        cli.main(["--repo", str(tmp_path), "--revision", FULL_SHA, "refresh"])


def test_refresh_uses_the_configured_semantic_indexer(tmp_path, capsys, monkeypatch):
    # Regression: the production refresh path called orchestrator.generate()
    # without ``semantic_indexer``, so it always took the None default. The index
    # was then reported not-configured even when the service was reachable,
    # pinning every `make refresh-project-context` run to degraded. Only tests
    # ever injected a working indexer.
    from semantic_adapter import SemanticIndexOutcome

    # A full (unscoped) refresh drives the durable store, which resolves its base
    # directory from --git-common-dir, so the fixture must be a real repository.
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    register(_FreshProducer("documentation.inventory"))
    monkeypatch.setattr(cli, "_require_mutation", lambda repo: None)

    def fake_indexer(repo, rev):
        return SemanticIndexOutcome(
            operation_id="op-1", registry_record_id="rec-1", indexed_revision=rev
        )

    monkeypatch.setattr(cli, "default_semantic_indexer", lambda: fake_indexer)
    cli.main(["--repo", str(tmp_path), "--revision", FULL_SHA, "refresh"])
    out = json.loads(capsys.readouterr().out)

    assert out["semantic_index"]["status"] == "succeeded"
    assert out["semantic_index"]["indexed_revision"] == FULL_SHA


def test_refresh_degrades_when_indexing_is_unconfigured(tmp_path, capsys, monkeypatch):
    # The other half of the contract: with no indexing stack the factory returns
    # None and the refresh degrades cleanly instead of failing.
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    register(_FreshProducer("documentation.inventory"))
    monkeypatch.setattr(cli, "_require_mutation", lambda repo: None)
    monkeypatch.setattr(cli, "default_semantic_indexer", lambda: None)

    code = cli.main(["--repo", str(tmp_path), "--revision", FULL_SHA, "refresh"])
    out = json.loads(capsys.readouterr().out)

    assert out["semantic_index"]["status"] == "not-configured"
    assert out["semantic_index"]["fallback"]["kind"] == "exact-search"
    assert code == 2  # degraded, not failed


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
