"""End-to-end revision-aware architecture refresh (ri-04 wp-integration task 4.1).

Exercises the full flow with a stubbed analyzer pipeline:

    staged generate  →  architecture provenance
                     →  canonical architecture ProducerResult (ri-06 store)
                     →  cross-process projected RPC status
                     →  read-only check

Covers spec scenarios architecture-refresh.4, .8, .9, .11, .13.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import context_runtime_adapter as adapter  # noqa: E402
import run_architecture  # noqa: E402
from arch_utils import provenance as prov  # noqa: E402

_RUNTIME = SCRIPTS_DIR.parent / "project-context-runtime" / "scripts"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from models import OperationState, ProducerStatus  # noqa: E402
from store import OperationStore  # noqa: E402


def _run(repo: Path, *args: str) -> None:
    subprocess.run(args, cwd=str(repo), check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "proj"
    (r / "src").mkdir(parents=True)
    (r / "src" / "app.py").write_text("print('x')\n")
    _run(r, "git", "init", "-q")
    _run(r, "git", "config", "user.email", "t@e.com")
    _run(r, "git", "config", "user.name", "T")
    _run(r, "git", "config", "commit.gpgsign", "false")
    _run(r, "git", "add", "-A")
    _run(r, "git", "commit", "-q", "-m", "init")
    return r


def _fake_pipeline(target_dir: Path, env: dict, quick: bool) -> int:
    staging = Path(env["ARCH_DIR"])
    (staging / "views").mkdir(parents=True, exist_ok=True)
    (staging / "architecture.graph.json").write_text('{"nodes": [], "edges": []}\n')
    (staging / "architecture.summary.json").write_text('{"summary": "ok"}\n')
    (staging / "views" / "overview.md").write_text("# overview\n")
    return 0


def test_end_to_end_generate_record_read_check(repo: Path, tmp_path: Path) -> None:
    # 1. Staged generation writes deterministic artifacts + provenance.
    with patch.object(run_architecture, "_run_pipeline", _fake_pipeline):
        rc = run_architecture.main(["--target-dir", str(repo), "--staged"])
    assert rc == 0
    assert prov.provenance_path(repo).is_file()

    # 2. Record the architecture producer result through the canonical ri-06 store.
    ledger = tmp_path / "ledger"
    doc = prov.load_provenance(repo)
    writer = adapter.ArchitectureAdapter(repo, store=OperationStore(repo, base_dir=ledger))
    op = writer.record_architecture(adapter.architecture_result_fresh(doc))
    assert op.state is OperationState.RUNNING  # adapter never finalizes (.13)

    # 3. A separate reader (no in-memory handle) observes the persisted result (.11).
    reader = adapter.ArchitectureAdapter(repo, store=OperationStore(repo, base_dir=ledger))
    result = reader.read_architecture_result()
    assert result is not None and result.status is ProducerStatus.FRESH
    status = reader.project_status().to_dict()
    assert status["status"] == "COMPLETED"
    assert status["operation_id"] == op.operation_id

    # 4. Read-only check reports fresh and writes nothing (.9).
    before = prov.provenance_path(repo).read_bytes()
    check_rc = run_architecture.main(["--target-dir", str(repo), "--check"])
    assert check_rc == 0
    assert prov.provenance_path(repo).read_bytes() == before

    # 5. A relevant input change flips the check to stale (.4) and exits nonzero.
    (repo / "src" / "app.py").write_text("print('a real change')\n")
    assert run_architecture.main(["--target-dir", str(repo), "--check"]) == 1


def test_end_to_end_failure_preserves_committed_and_status(repo: Path, tmp_path: Path) -> None:
    # Establish a good committed set first.
    with patch.object(run_architecture, "_run_pipeline", _fake_pipeline):
        run_architecture.main(["--target-dir", str(repo), "--staged"])
    good = prov.provenance_path(repo).read_bytes()

    # A failing generation preserves the last known-good artifacts (.8).
    def _failing(target_dir: Path, env: dict, quick: bool) -> int:
        return 7

    with patch.object(run_architecture, "_run_pipeline", _failing):
        rc = run_architecture.main(["--target-dir", str(repo), "--staged"])
    assert rc == 7
    assert prov.provenance_path(repo).read_bytes() == good

    # The adapter can still record a FAILED producer result without finalizing (.13).
    ledger = tmp_path / "ledger"
    ad = adapter.ArchitectureAdapter(repo, store=OperationStore(repo, base_dir=ledger))
    op = ad.record_architecture(adapter.architecture_result_failed("analyzer crashed"))
    assert op.state is OperationState.RUNNING
    assert ad.project_status().to_dict()["status"] == "FAILED"
