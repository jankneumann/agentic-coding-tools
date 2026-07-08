"""Core data models for agent trajectory scenarios.

Where gen-eval validates a deployed *service* via fixed transport-level step
sequences, this package validates the *agents themselves*: given a task prompt
and a fixture repo state, run a skill headless (per vendor) and score whether
the agent achieved the goal — files/branch/commit/PR/artifacts produced, and
prohibited side effects avoided.

The goal-gate vocabulary deliberately **reuses gen-eval's** ``ExpectBlock``
(assertion primitives) and mirrors ``SideEffectsBlock``'s ``verify`` /
``prohibit`` split. We import the real gen-eval shapes so the two frameworks
share one assertion contract rather than re-inventing it.
"""

from __future__ import annotations

from typing import Literal

# Reuse gen-eval's assertion vocabulary. ExpectBlock powers ``command`` goal
# gates (exit_code / error_contains / not_empty); SideEffectStep/SideEffectsBlock
# establish the verify-vs-prohibit split we mirror below for workspace state.
from gen_eval.models import ExpectBlock  # noqa: F401  (re-exported)
from pydantic import BaseModel, Field, model_validator

GoalGateCheck = Literal["file", "branch", "commit", "pr", "artifact", "command"]
GateStatus = Literal["pass", "fail", "error", "skip"]
GateMode = Literal["verify", "prohibit"]


class GoalGate(BaseModel):
    """A single expected (or prohibited) outcome of an agent run.

    Mirrors the shape of gen-eval's ``SideEffectStep`` (``id`` + ``mode`` +
    transport-specific fields + optional ``expect``), but the "transport" here
    is *post-run workspace state* — the filesystem and git history the agent
    left behind — rather than a live HTTP/MCP/DB call.

    ``mode``:
      * ``verify``   — the gate passes when the condition holds (outcome present).
      * ``prohibit`` — the gate passes when the condition does NOT hold (side
        effect absent). This is how we score "the agent must not have committed
        secrets / deleted main / pushed to a protected branch".
    """

    id: str
    check: GoalGateCheck
    mode: GateMode = "verify"
    description: str = ""

    # check == "file" / "artifact": path is relative to the workspace root.
    path: str | None = None
    # check == "file" / "artifact": regex that must be found in the file body.
    contains: str | None = None

    # check == "branch": the branch name that must exist.
    branch: str | None = None

    # check == "commit": a commit whose message matches this regex must exist.
    message_contains: str | None = None
    # check == "commit": minimum number of new commits on the working branch.
    min_count: int | None = None

    # check == "pr": if set, the created PR's head branch must match.
    pr_head: str | None = None

    # check == "artifact": key in WorkspaceState.artifacts (alternative to path).
    artifact_key: str | None = None

    # check == "command": argv run in the workspace root; scored via ``expect``.
    command: list[str] | None = None
    # Reused gen-eval ExpectBlock: exit_code / error_contains / not_empty / ...
    expect: ExpectBlock | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> GoalGate:
        if self.check == "command" and not self.command:
            raise ValueError(f"goal gate '{self.id}': check 'command' requires 'command'")
        if self.check == "branch" and not self.branch:
            raise ValueError(f"goal gate '{self.id}': check 'branch' requires 'branch'")
        if self.check in ("file", "artifact") and not (self.path or self.artifact_key):
            raise ValueError(
                f"goal gate '{self.id}': check '{self.check}' requires 'path' or 'artifact_key'"
            )
        return self


class GoalGatesBlock(BaseModel):
    """Verify/prohibit split for a scenario's goal gates.

    Mirrors gen-eval's ``SideEffectsBlock`` exactly: ``verify`` gates must
    hold, ``prohibit`` gates must not. Gates may also carry ``mode`` inline;
    the block lists are a convenience so scenario authors can group outcomes.
    """

    verify: list[GoalGate] = Field(default_factory=list)
    prohibit: list[GoalGate] = Field(default_factory=list)

    def all_gates(self) -> list[GoalGate]:
        """Return every gate with its effective ``mode`` resolved by list.

        A gate placed in ``prohibit`` is forced to ``mode="prohibit"`` even if
        it declared ``verify`` inline, so the list placement is authoritative.
        """
        resolved: list[GoalGate] = []
        for gate in self.verify:
            resolved.append(gate.model_copy(update={"mode": "verify"}))
        for gate in self.prohibit:
            resolved.append(gate.model_copy(update={"mode": "prohibit"}))
        return resolved


class FixtureSpec(BaseModel):
    """Declarative starting repo state for a scenario.

    The runner materializes this into a throwaway workspace before invoking the
    agent. ``files`` seeds file contents; ``git_init`` makes the workspace a git
    repo (with an initial commit) so branch/commit/PR gates are meaningful;
    ``commands`` are optional setup shell steps (e.g. ``npm install`` on GX10).
    """

    files: dict[str, str] = Field(default_factory=dict)
    git_init: bool = True
    base_branch: str = "main"
    commands: list[list[str]] = Field(default_factory=list)


class AgentScenario(BaseModel):
    """A complete agent trajectory scenario.

    The unit of test: a task prompt + fixture repo state + the skill under test
    + the vendors to run it across + the goal gates that define success.
    """

    id: str
    name: str
    description: str = ""
    task_prompt: str
    fixture: FixtureSpec = Field(default_factory=FixtureSpec)
    skill_under_test: str
    vendors: list[str] = Field(default_factory=list)
    goal_gates: GoalGatesBlock = Field(default_factory=GoalGatesBlock)
    # Optional trajectory-judge criteria (additive LLM review). Absent => the
    # judge still runs with default criteria but only when a backend is injected.
    judge_criteria: str = ""
    tags: list[str] = Field(default_factory=list)
    # Provenance: point findings back at the scenario source file when known.
    source_path: str | None = None

    @model_validator(mode="after")
    def _require_vendors_and_gates(self) -> AgentScenario:
        if not self.vendors:
            raise ValueError(f"scenario '{self.id}': at least one vendor is required")
        if not self.goal_gates.all_gates():
            raise ValueError(f"scenario '{self.id}': at least one goal gate is required")
        return self


# ---------------------------------------------------------------------------
# Run-time state and results
# ---------------------------------------------------------------------------


class PRRef(BaseModel):
    """A pull request the agent claims to have created.

    In-container there is no live GitHub, so PR gates are scored against what
    the executor *reports* (the CLI adapter parses the PR URL from stdout; the
    fake executor emits it from its script). On the GX10 the CLI adapter
    resolves this from ``gh pr view``.
    """

    number: int | None = None
    head: str | None = None
    url: str | None = None
    title: str | None = None


class WorkspaceState(BaseModel):
    """Post-run state the deterministic scorer inspects.

    ``root`` is the on-disk workspace (a git repo when the fixture initialized
    one). ``created_pr`` and ``artifacts`` capture out-of-tree effects the
    executor observed.
    """

    root: str
    working_branch: str | None = None
    created_pr: PRRef | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)


class RunResult(BaseModel):
    """The output of running one scenario against one vendor.

    ``transcript_events`` is a list of normalized ``collect-transcripts`` events
    (the LLM-judge input shape). ``transcript_path`` points at the JSONL on disk
    when the executor persisted it.
    """

    scenario_id: str
    vendor: str
    workspace: WorkspaceState
    transcript_events: list[dict] = Field(default_factory=list)
    transcript_path: str | None = None
    exit_code: int = 0
    error: str | None = None


class GateVerdict(BaseModel):
    """Result of scoring one goal gate deterministically (no LLM)."""

    gate_id: str
    check: GoalGateCheck
    mode: GateMode
    status: GateStatus
    detail: str = ""


class TrajectoryFinding(BaseModel):
    """A single trajectory-quality observation from the LLM judge."""

    kind: Literal["inefficiency", "unnecessary_action", "wrong_but_passed", "other"]
    description: str
    severity: Literal["low", "medium", "high"] = "medium"


class TrajectoryVerdict(BaseModel):
    """Result of the injectable LLM-judge trajectory review.

    Additive to the deterministic score (like gen-eval's SemanticVerdict):
    ``skip`` when no backend is injected; never overrides the goal-gate verdict.
    """

    status: Literal["pass", "fail", "skip"]
    confidence: float = 0.0
    reasoning: str = ""
    findings: list[TrajectoryFinding] = Field(default_factory=list)
    error_message: str | None = None


class VendorRunVerdict(BaseModel):
    """Aggregate verdict for one scenario against one vendor."""

    scenario_id: str
    vendor: str
    gate_verdicts: list[GateVerdict]
    trajectory: TrajectoryVerdict
    # Deterministic status: pass only when every goal gate passed.
    deterministic_status: Literal["pass", "fail", "error"]
    error: str | None = None

    @property
    def failed_gates(self) -> list[GateVerdict]:
        return [g for g in self.gate_verdicts if g.status in ("fail", "error")]


class ParityMatrix(BaseModel):
    """Per-vendor results for one scenario — the cross-vendor parity view."""

    scenario_id: str
    scenario_name: str
    results: list[VendorRunVerdict]

    @property
    def all_vendors_pass(self) -> bool:
        return all(r.deterministic_status == "pass" for r in self.results)
