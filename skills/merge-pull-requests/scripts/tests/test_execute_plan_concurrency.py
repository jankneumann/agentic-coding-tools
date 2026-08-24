"""Deterministic executor interleaving tests for file-tier plan state."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from execute_plan import execute_node  # noqa: E402
from plan_storage import FilePlanStore  # noqa: E402
from test_execute_plan import dependencies, passing_status, persisted_plan  # noqa: E402
from test_merge_plan_contract import valid_plan  # noqa: E402


def test_gated_executor_cannot_overwrite_concurrent_approved_claim(
    tmp_path: Path,
) -> None:
    plan = valid_plan()
    node = plan["nodes"][1]
    node["definition"]["depends_on"] = []
    node["definition"]["gates"] = ["requires_human_approval"]
    node["auto_executable"] = False
    path = persisted_plan(tmp_path, plan)
    gate_started = threading.Event()
    claim_written = threading.Event()
    gate_finished = threading.Event()
    gated_results: list[dict] = []

    class DelayedGateStore(FilePlanStore):
        def _wait_after_gate_read(self, blocking_reason: str | None) -> None:
            if blocking_reason == "explicit operator approval required":
                gate_started.set()
                assert claim_written.wait(timeout=5)

        def save(self, pending: dict) -> None:
            reason = pending["nodes"][1]["state"].get("blocking_reason")
            self._wait_after_gate_read(reason)
            super().save(pending)

        def update_state(self, pr_number: int, **changes: object) -> dict:
            self._wait_after_gate_read(str(changes.get("blocking_reason") or ""))
            return super().update_state(pr_number, **changes)

    def run_gated() -> None:
        try:
            gated_results.append(
                execute_node(path, 11, store=DelayedGateStore(path), dependencies=dependencies())
            )
        finally:
            gate_finished.set()

    gated = threading.Thread(target=run_gated)
    gated.start()
    assert gate_started.wait(timeout=5)

    def check_after_claim(_pr: int, _origin: str) -> dict:
        claim_written.set()
        assert gate_finished.wait(timeout=5)
        state = FilePlanStore(path).load()["nodes"][1]["state"]
        assert state["outcome"] == "in_progress"
        assert state["claimed_by"] == "approved-run"
        return {"staleness": "fresh", "ci_merge_base_stale": False}

    approved = execute_node(
        path,
        11,
        approve_gate=True,
        claim_id="approved-run",
        dependencies=dependencies(
            get_live_status=lambda _pr: passing_status(),
            check_staleness=check_after_claim,
        ),
    )
    gated.join(timeout=5)

    assert not gated.is_alive()
    assert approved["action"] == "merged"
    assert gated_results[0]["action"] == "execution_in_progress"
    assert FilePlanStore(path).load()["nodes"][1]["state"]["outcome"] == "merged"
