"""Scenario runner — loops over vendors and builds the parity matrix.

The runner is the composition point: for each vendor in ``scenario.vendors`` it
asks the injected :class:`ScenarioExecutor` to run the agent, scores the goal
gates deterministically, then (additively) runs the injectable trajectory judge.
Because both the executor and the judge are injected, the cross-vendor parity
matrix is *structural* — the same loop drives a fake executor in tests and real
per-vendor CLIs on the GX10.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .executor import ScenarioExecutor
from .judge import TrajectoryJudgeBackend, review_trajectory
from .models import (
    AgentScenario,
    ParityMatrix,
    TrajectoryVerdict,
    VendorRunVerdict,
)
from .scorer import deterministic_status, score_gates


def run_scenario(
    scenario: AgentScenario,
    executor: ScenarioExecutor,
    *,
    judge_backend: TrajectoryJudgeBackend | None = None,
    workspaces_root: str | Path | None = None,
) -> ParityMatrix:
    """Run one scenario across every vendor it declares.

    Args:
        scenario: the loaded scenario.
        executor: injected per-vendor executor (fake or real CLI adapter).
        judge_backend: optional LLM-judge backend; ``None`` => judge skips.
        workspaces_root: parent dir for per-vendor workspaces; a temp dir when
            omitted.

    Returns:
        A :class:`ParityMatrix` with one :class:`VendorRunVerdict` per vendor.
    """
    base = Path(workspaces_root) if workspaces_root else Path(tempfile.mkdtemp(prefix="agent-scn-"))
    base.mkdir(parents=True, exist_ok=True)

    results: list[VendorRunVerdict] = []
    for vendor in scenario.vendors:
        workdir = base / f"{scenario.id}--{vendor}"
        results.append(_run_one_vendor(scenario, vendor, workdir, executor, judge_backend))

    return ParityMatrix(
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        results=results,
    )


def _run_one_vendor(
    scenario: AgentScenario,
    vendor: str,
    workdir: Path,
    executor: ScenarioExecutor,
    judge_backend: TrajectoryJudgeBackend | None,
) -> VendorRunVerdict:
    try:
        run_result = executor.run(scenario, vendor, workdir)
    except Exception as exc:
        return VendorRunVerdict(
            scenario_id=scenario.id,
            vendor=vendor,
            gate_verdicts=[],
            trajectory=TrajectoryVerdict(status="skip", reasoning="executor raised"),
            deterministic_status="error",
            error=f"executor error: {exc}",
        )

    gate_verdicts = score_gates(scenario.goal_gates, run_result.workspace)
    det_status = deterministic_status(gate_verdicts)
    # An executor-level failure (non-zero exit with no gates) still surfaces.
    if not gate_verdicts and run_result.error:
        det_status = "error"

    trajectory = review_trajectory(
        judge_backend,
        task_prompt=scenario.task_prompt,
        criteria=scenario.judge_criteria,
        transcript_events=run_result.transcript_events,
        deterministic_status=det_status,
    )

    return VendorRunVerdict(
        scenario_id=scenario.id,
        vendor=vendor,
        gate_verdicts=gate_verdicts,
        trajectory=trajectory,
        deterministic_status=det_status,  # type: ignore[arg-type]
        error=run_result.error if det_status == "error" else None,
    )


def run_scenarios(
    scenarios: list[AgentScenario],
    executor: ScenarioExecutor,
    *,
    judge_backend: TrajectoryJudgeBackend | None = None,
    workspaces_root: str | Path | None = None,
) -> list[ParityMatrix]:
    """Run a suite of scenarios, returning one parity matrix each."""
    return [
        run_scenario(
            s, executor, judge_backend=judge_backend, workspaces_root=workspaces_root
        )
        for s in scenarios
    ]
