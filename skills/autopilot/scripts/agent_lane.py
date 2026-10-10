"""Drive ``convergence_loop.converge()`` with the running agent as a review lane.

In a cloud container the only dispatchable review vendor is often the agent
that is driving the loop. ``converge()`` still needs an orchestrator and a
fix callback, so this module serves both through a file handshake in a
protocol directory the agent watches:

- review round N: writes ``awaiting-review-N`` (the packet path), then waits
  for the agent to write ``findings-round-N.json`` (review-findings schema);
- fix round N: writes ``fix-request-round-N.json`` (the scoped payloads),
  then waits for the agent to apply and commit the edits and touch
  ``fix-done-round-N``.

Every step is appended to ``events.jsonl`` and the outcome to ``result.json``.
On a converged VAL_REVIEW the ``## Validation Review`` section of
``validation-report.md`` is written with a ``**Status**`` line, which the goal
gate requires when VAL_REVIEW is enabled.

This is a committed replacement for per-session driver scripts::

    python3 skills/autopilot/scripts/agent_lane.py converge \\
        --change-id <id> --phase VAL_REVIEW --proto-dir <dir> \\
        --base-ref origin/<pr-base> --model <model id>
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_SCRIPTS = Path(__file__).resolve().parent
_PARALLEL_INFRA = _SCRIPTS.parent.parent / "parallel-infrastructure" / "scripts"
for _path in (_SCRIPTS, _PARALLEL_INFRA):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

LANE = "claude_code"
DEFAULT_TIMEOUT_SECONDS = 5400.0
POLL_SECONDS = 2.0

#: review phase -> (converge review_type, fix sub-step name)
PHASES: dict[str, tuple[str, str]] = {
    "PLAN_REVIEW": ("plan", "PLAN_FIX"),
    "IMPL_REVIEW": ("implementation", "IMPL_FIX"),
    "VAL_REVIEW": ("implementation", "VAL_FIX"),
}

VAL_REVIEW_HEADING = "Validation Review"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Handshake:
    """The protocol directory shared with the agent serving the lane."""

    def __init__(
        self,
        proto_dir: Path,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        poll_seconds: float = POLL_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.dir = Path(proto_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self._sleep = sleep
        self._clock = clock

    def event(self, kind: str, **data: Any) -> None:
        with (self.dir / "events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": _now(), "event": kind, **data}, default=str) + "\n")

    def wait_for(self, name: str) -> Path:
        target = self.dir / name
        deadline = self._clock() + self.timeout_seconds
        while not target.exists():
            if self._clock() > deadline:
                raise TimeoutError(f"timed out waiting for {target}")
            self._sleep(self.poll_seconds)
        return target

    def read_json(self, name: str) -> Any:
        """Wait for ``name`` and return it parsed, re-reading while it is still
        being written (present but not yet valid JSON)."""
        target = self.wait_for(name)
        deadline = self._clock() + self.timeout_seconds
        while True:
            try:
                return json.loads(target.read_text(encoding="utf-8"))
            except ValueError:
                if self._clock() > deadline:
                    raise
                self._sleep(self.poll_seconds)


class AgentLaneOrchestrator:
    """A single review lane served by the running agent through ``Handshake``.

    Implements the part of ``ReviewOrchestrator`` that ``converge()`` calls.
    """

    def __init__(self, handshake: Handshake, *, model: str) -> None:
        self.handshake = handshake
        self.model = model
        self.round = 0
        self.adapters: dict[str, Any] = {}

    def dispatch_and_wait(
        self,
        review_type: str,
        dispatch_mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: float | None = None,
        packet_path: Path | None = None,
        result_callback: Callable[[Any, int], None] | None = None,
    ) -> list[Any]:
        from review_dispatcher import ReviewResult

        self.round += 1
        n = self.round
        hs = self.handshake
        hs.event("review_requested", round=n, packet_path=str(packet_path or ""))
        (hs.dir / f"awaiting-review-{n}").write_text(str(packet_path or ""), encoding="utf-8")
        start = time.monotonic()
        findings = hs.read_json(f"findings-round-{n}.json")
        result = ReviewResult(
            vendor=LANE,
            success=True,
            findings=findings,
            model_used=self.model,
            models_attempted=[self.model],
            elapsed_seconds=time.monotonic() - start,
            agent_id=LANE,
        )
        if result_callback is not None:
            result_callback(result, 1)
        hs.event("review_received", round=n, findings=len(findings.get("findings", [])))
        return [result]


def make_fix_callback(
    handshake: Handshake, orchestrator: AgentLaneOrchestrator, *, fix_phase: str
) -> Callable[[list[dict[str, Any]], Path], None]:
    def fix_callback(payloads: list[dict[str, Any]], worktree_path: Path) -> None:
        n = orchestrator.round
        handshake.event(
            "phase_history_substep", phase=fix_phase, status="started", round=n,
            item_ids=[p.get("id") for p in payloads],
        )
        (handshake.dir / f"fix-request-round-{n}.json").write_text(
            json.dumps(payloads, indent=2, default=str), encoding="utf-8"
        )
        handshake.wait_for(f"fix-done-round-{n}")
        handshake.event("phase_history_substep", phase=fix_phase, status="completed", round=n)

    return fix_callback


def write_validation_review_section(report_path: Path, *, status: str, body: str) -> None:
    """Replace (or append) the report's ``## Validation Review`` section."""
    text = report_path.read_text(encoding="utf-8") if report_path.exists() else "# Validation Report\n"
    section = f"## {VAL_REVIEW_HEADING}\n\n**Status**: {status}\n\n{body.strip()}\n"
    pattern = re.compile(rf"^## {re.escape(VAL_REVIEW_HEADING)}\s*\n.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(lambda _m: section + "\n", text, count=1).rstrip() + "\n"
    else:
        text = text.rstrip() + "\n\n" + section
    report_path.write_text(text, encoding="utf-8")


def _review_body(result: dict[str, Any], *, min_quorum: int, policy: dict[str, Any]) -> str:
    lines = [
        f"- Result: converged in {result['rounds']} round(s) via `agent_lane.py converge`.",
        f"- Lanes: `{LANE}` only (min_quorum={min_quorum}).",
    ]
    if policy.get("policy_id"):
        lines.append(
            f"- Degradation: `single_vendor_review` under quorum policy `{policy['policy_id']}`."
        )
    if result.get("summary"):
        lines.append(f"- Summary: {result['summary']}")
    return "\n".join(lines)


def run_converge(
    *,
    change_id: str,
    phase: str,
    worktree: Path,
    proto_dir: Path,
    base_ref: str | None,
    model: str,
    environment: str = "cloud_container",
    max_rounds: int = 3,
    fix_mode: str = "targeted",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: float = POLL_SECONDS,
    converge_fn: Callable[..., Any] | None = None,
    policy_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError(f"phase must be one of {sorted(PHASES)}")
    review_type, fix_phase = PHASES[phase]
    if converge_fn is None:
        import convergence_loop

        converge_fn = convergence_loop.converge
    if policy_fn is None:
        from review_dispatcher import resolve_quorum_policy

        policy_fn = resolve_quorum_policy

    worktree = Path(worktree).resolve()
    change_dir = worktree / "openspec" / "changes" / change_id
    handshake = Handshake(proto_dir, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)
    logging.basicConfig(
        filename=str(handshake.dir / "converge.log"), level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    policy = policy_fn(environment=environment, verified_review_lanes=1)
    min_quorum = int(policy["min_quorum"][phase])
    orchestrator = AgentLaneOrchestrator(handshake, model=model)
    handshake.event("converge_started", phase=phase, min_quorum=min_quorum, policy=policy)
    try:
        res = converge_fn(
            change_id=change_id,
            review_type=review_type,
            artifacts_dir=change_dir,
            worktree_path=worktree,
            max_rounds=max_rounds,
            min_quorum=min_quorum,
            fix_mode=fix_mode,
            verified_lanes=[LANE],
            counting_lanes=[LANE],
            base_ref=base_ref,
            fix_callback=make_fix_callback(handshake, orchestrator, fix_phase=fix_phase),
            memory_callback=lambda text: handshake.event("memory", text=text),
            orchestrator=orchestrator,
            escalation_callback=lambda summary: handshake.event("escalation", summary=summary),
        )
        out: dict[str, Any] = {
            "phase": phase,
            "policy": policy,
            "min_quorum": min_quorum,
            "converged": bool(res.converged),
            "rounds": res.rounds,
            "reason": res.reason,
            "escalate_findings": res.escalate_findings,
            "validation_errors": res.validation_errors,
            "checkpoint_dir": str(res.checkpoint_dir) if res.checkpoint_dir else None,
            "summary": (res.consensus or {}).get("summary"),
        }
    except Exception as exc:  # noqa: BLE001 - recorded for the agent, not swallowed silently
        out = {"phase": phase, "converged": False, "error": f"{type(exc).__name__}: {exc}"}

    if phase == "VAL_REVIEW" and out.get("converged"):
        write_validation_review_section(
            change_dir / "validation-report.md",
            status="pass",
            body=_review_body(out, min_quorum=min_quorum, policy=policy),
        )
        out["report_section_written"] = VAL_REVIEW_HEADING
    (handshake.dir / "result.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    handshake.event(
        "converge_finished", **{k: out.get(k) for k in ("converged", "rounds", "reason", "error")}
    )
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cv = sub.add_parser("converge", help="Run converge() with the agent as the review lane.")
    cv.add_argument("--change-id", required=True)
    cv.add_argument("--phase", required=True, choices=sorted(PHASES))
    cv.add_argument("--proto-dir", required=True, type=Path)
    cv.add_argument("--worktree", type=Path, default=Path.cwd())
    cv.add_argument("--base-ref", default=None, help="Ref the review packet diffs against (the PR base).")
    cv.add_argument("--model", required=True, help="Model id serving the lane, recorded on each review.")
    cv.add_argument("--environment", default="cloud_container", choices=["cloud_container", "host"])
    cv.add_argument("--max-rounds", type=int, default=3)
    cv.add_argument("--fix-mode", default="targeted", choices=["inline", "targeted"])
    cv.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    out = run_converge(
        change_id=args.change_id,
        phase=args.phase,
        worktree=args.worktree,
        proto_dir=args.proto_dir,
        base_ref=args.base_ref,
        model=args.model,
        environment=args.environment,
        max_rounds=args.max_rounds,
        fix_mode=args.fix_mode,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps({k: out.get(k) for k in ("phase", "converged", "rounds", "reason", "error")}))
    return 0 if out.get("converged") else 1


if __name__ == "__main__":
    raise SystemExit(main())
