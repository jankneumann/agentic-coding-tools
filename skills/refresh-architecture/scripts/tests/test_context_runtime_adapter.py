"""Tests for the architecture → project-context-runtime adapter (ri-04 wp-adapter).

Covers spec scenarios:
- architecture-refresh.10  records exactly one canonical architecture ProducerResult
- architecture-refresh.11  a separate process observes the persisted result
- architecture-refresh.12  a duplicate trigger reuses the canonical operation
- architecture-refresh.13  the adapter never finalizes the whole operation
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import context_runtime_adapter as adapter  # noqa: E402
from arch_utils import provenance as prov  # noqa: E402

_RUNTIME = SCRIPTS_DIR.parent / "project-context-runtime" / "scripts"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from models import OperationState, ProducerStatus  # noqa: E402
from store import OperationStore  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _run(repo: Path, *args: str) -> None:
    subprocess.run(args, cwd=str(repo), check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "proj"
    (r / "src").mkdir(parents=True)
    (r / "src" / "app.py").write_text("print('x')\n")
    arch = r / prov.ARCH_DIR_DEFAULT
    arch.mkdir(parents=True)
    (arch / "architecture.graph.json").write_text('{"nodes": [], "edges": []}\n')
    (arch / "architecture.summary.json").write_text('{"summary": "ok"}\n')
    _run(r, "git", "init", "-q")
    _run(r, "git", "config", "user.email", "t@e.com")
    _run(r, "git", "config", "user.name", "T")
    _run(r, "git", "config", "commit.gpgsign", "false")
    _run(r, "git", "add", "-A")
    _run(r, "git", "commit", "-q", "-m", "init")
    return r


def _store(repo: Path, tmp_path: Path) -> OperationStore:
    # Isolate the ledger under tmp so tests never touch a real Git common dir.
    return OperationStore(repo, base_dir=tmp_path / "ledger")


def _fresh_result(repo: Path):
    doc = prov.build_provenance(repo, mode="full", roots=["src"])
    prov.write_provenance(repo, doc)
    return adapter.architecture_result_fresh(doc)


# --------------------------------------------------------------------------- #
# Scenario .10 — one canonical producer result
# --------------------------------------------------------------------------- #
def test_records_one_canonical_architecture_result(repo: Path, tmp_path: Path) -> None:
    store = _store(repo, tmp_path)
    ad = adapter.ArchitectureAdapter(repo, store=store)
    op = ad.record_architecture(_fresh_result(repo))
    arch_results = [r for r in op.producer_results if r.producer_id == "architecture"]
    assert len(arch_results) == 1
    assert arch_results[0].status is ProducerStatus.FRESH
    assert arch_results[0].artifacts  # carries owned artifacts
    assert op.state is OperationState.RUNNING


def test_adapter_rejects_non_architecture_result(repo: Path, tmp_path: Path) -> None:
    from models import ProducerResult

    store = _store(repo, tmp_path)
    ad = adapter.ArchitectureAdapter(repo, store=store)
    other = ProducerResult(
        producer_id="documentation", producer_version="1", status=ProducerStatus.FRESH
    )
    with pytest.raises(Exception):
        ad.record_architecture(other)


# --------------------------------------------------------------------------- #
# Scenario .11 — separate process / fresh store observes the result
# --------------------------------------------------------------------------- #
def test_separate_reader_observes_persisted_result(repo: Path, tmp_path: Path) -> None:
    ledger = tmp_path / "ledger"
    writer = adapter.ArchitectureAdapter(repo, store=OperationStore(repo, base_dir=ledger))
    writer.record_architecture(_fresh_result(repo))

    # A brand-new adapter + store instance (no in-memory handle) reads it back.
    reader = adapter.ArchitectureAdapter(repo, store=OperationStore(repo, base_dir=ledger))
    result = reader.read_architecture_result()
    assert result is not None
    assert result.producer_id == "architecture"
    assert result.status is ProducerStatus.FRESH


def test_project_status_completed_for_fresh(repo: Path, tmp_path: Path) -> None:
    store = _store(repo, tmp_path)
    ad = adapter.ArchitectureAdapter(repo, store=store)
    ad.record_architecture(_fresh_result(repo))
    status = ad.project_status().to_dict()
    assert status["status"] == "COMPLETED"
    assert status["operation_id"] == status["refresh_id"]
    assert status["source_revision"] == prov.analyzed_revision(repo)
    assert status["producer_version"] == prov.PRODUCER_VERSION


def test_project_status_unknown_without_operation(repo: Path, tmp_path: Path) -> None:
    ad = adapter.ArchitectureAdapter(repo, store=_store(repo, tmp_path))
    assert ad.project_status().to_dict()["status"] == "UNKNOWN"


def test_project_status_failed_carries_remediation(repo: Path, tmp_path: Path) -> None:
    ad = adapter.ArchitectureAdapter(repo, store=_store(repo, tmp_path))
    ad.record_architecture(adapter.architecture_result_failed("analyzer crashed"))
    status = ad.project_status().to_dict()
    assert status["status"] == "FAILED"
    assert status["error_message"] == "analyzer crashed"
    assert status["remediation"], "failed status must surface remediation"


# --------------------------------------------------------------------------- #
# Scenario .12 — duplicate trigger reuses the canonical operation
# --------------------------------------------------------------------------- #
def test_duplicate_record_is_idempotent(repo: Path, tmp_path: Path) -> None:
    store = _store(repo, tmp_path)
    ad = adapter.ArchitectureAdapter(repo, store=store)
    result = _fresh_result(repo)
    op1 = ad.record_architecture(result)
    op2 = ad.record_architecture(result)  # duplicate trigger
    assert op1.operation_id == op2.operation_id
    arch_results = [r for r in op2.producer_results if r.producer_id == "architecture"]
    assert len(arch_results) == 1  # no duplicate producer appended
    # record_revision does not advance on the idempotent second call.
    assert op2.record_revision == op1.record_revision


# --------------------------------------------------------------------------- #
# Scenario .13 — adapter never finalizes the whole operation
# --------------------------------------------------------------------------- #
def test_adapter_never_finalizes_operation(repo: Path, tmp_path: Path) -> None:
    for build in (
        lambda: _fresh_result(repo),
        lambda: adapter.architecture_result_failed("x"),
        lambda: adapter.architecture_result_not_configured("no analyzers"),
    ):
        # Fresh operation each time via a distinct ledger so state is isolated.
        local = adapter.ArchitectureAdapter(
            repo, store=OperationStore(repo, base_dir=tmp_path / f"ledger-{id(build)}")
        )
        op = local.record_architecture(build())
        # The operation is never driven to a terminal state by the adapter.
        assert op.state not in (
            OperationState.SUCCEEDED,
            OperationState.DEGRADED,
            OperationState.FAILED,
        )
        assert op.state is OperationState.RUNNING
