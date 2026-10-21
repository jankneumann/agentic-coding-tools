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
import threading
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

    #: The per-run handshake files. A new run starts with none of them, so a
    #: reused protocol directory cannot answer this run's rounds with a previous
    #: run's findings or fix acknowledgements.
    ROUND_FILES = ("awaiting-review-*", "findings-round-*", "fix-request-round-*", "fix-done-round-*", "result.json")

    def clear_rounds(self) -> list[str]:
        removed = sorted(
            path.name for pattern in self.ROUND_FILES for path in self.dir.glob(pattern) if path.is_file()
        )
        for name in removed:
            (self.dir / name).unlink()
        return removed

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


class CompositeOrchestrator:
    """The handshake lane plus the dispatcher's other verified lanes (design D7).

    Each round runs ``ReviewOrchestrator.dispatch_and_wait(include_lanes=...)``
    in a thread while the handshake lane is served in this one, then returns
    both result lists. The checkpoint callback is forwarded with the round's
    full expected count. The review orchestrator is built on the first round
    that has a lane for it, so a run ``converge()`` refuses below quorum
    never builds one.
    """

    def __init__(
        self,
        agent_lane: AgentLaneOrchestrator,
        *,
        include_lanes: list[str] | tuple[str, ...] = (),
        review_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.agent_lane = agent_lane
        self.include_lanes = list(include_lanes)
        self._review_factory = review_factory
        self._review: Any = None
        self.results_by_round: list[list[Any]] = []

    @property
    def round(self) -> int:
        return self.agent_lane.round

    @property
    def adapters(self) -> dict[str, Any]:
        return getattr(self._review, "adapters", None) or {}

    def _review_orchestrator(self) -> Any:
        if self._review is None and self.include_lanes:
            if self._review_factory is None:
                raise RuntimeError(f"no review orchestrator for lanes {self.include_lanes}")
            self._review = self._review_factory()
        return self._review

    def dispatch_and_wait(
        self,
        review_type: str,
        dispatch_mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: float | None = None,
        packet_path: Path | None = None,
        result_callback: Callable[[Any, int], None] | None = None,
        *,
        toolless_packet_path: Path | None = None,
        spend_context: Any = None,
    ) -> list[Any]:
        review = self._review_orchestrator()
        expected = 1 + (len(self.include_lanes) if review is not None else 0)

        def forward(result: Any, _count: int) -> None:
            if result_callback is not None:
                result_callback(result, expected)

        review_results: list[Any] = []
        review_errors: list[BaseException] = []

        def run_review() -> None:
            try:
                review_results.extend(review.dispatch_and_wait(
                    review_type, dispatch_mode, prompt, cwd,
                    timeout_seconds=timeout_seconds,
                    packet_path=packet_path,
                    result_callback=forward,
                    include_lanes=self.include_lanes,
                    toolless_packet_path=toolless_packet_path,
                    spend_context=spend_context,
                ))
            except BaseException as exc:  # noqa: BLE001 - re-raised in the caller's thread
                review_errors.append(exc)

        thread = None
        if review is not None:
            thread = threading.Thread(target=run_review, name="composite-review", daemon=True)
            thread.start()
        try:
            agent_results = self.agent_lane.dispatch_and_wait(
                review_type, dispatch_mode, prompt, cwd,
                timeout_seconds=timeout_seconds, packet_path=packet_path, result_callback=forward,
            )
        finally:
            if thread is not None:
                thread.join()
        if review_errors:
            raise review_errors[0]
        results = [*agent_results, *review_results]
        self.results_by_round.append(results)
        return results


def make_fix_callback(
    handshake: Handshake, orchestrator: Any, *, fix_phase: str
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
    lanes = result.get("lanes") or [LANE]
    listed = ", ".join(f"`{lane}`" for lane in lanes)
    lines = [
        f"- Result: converged in {result['rounds']} round(s) via `agent_lane.py converge`.",
        f"- Lanes: {listed}{' only' if len(lanes) == 1 else ''} (min_quorum={min_quorum}).",
    ]
    if len(lanes) == 1 and policy.get("policy_id"):
        lines.append(
            f"- Degradation: `single_vendor_review` under quorum policy `{policy['policy_id']}`."
        )
    if result.get("summary"):
        lines.append(f"- Summary: {result['summary']}")
    return "\n".join(lines)


#: review phase -> the per-phase consensus file under ``<change>/reviews/``
CONSENSUS_FILES: dict[str, str] = {
    "PLAN_REVIEW": "consensus-plan.json",
    "IMPL_REVIEW": "consensus-impl-review.json",
    "VAL_REVIEW": "consensus-val-review.json",
}


def _resolve_lanes(
    verified_lanes: list[str] | None, counting_lanes: list[str] | None
) -> tuple[list[str], list[str]]:
    """``claude_code`` first (the running agent serves it), then the rest, deduplicated."""
    verified = list(dict.fromkeys([LANE, *(verified_lanes or [])]))
    counting = list(dict.fromkeys(counting_lanes)) if counting_lanes else list(verified)
    return verified, counting


def _lane_of(result: Any, verified: list[str]) -> str:
    for lane in verified:
        if lane in (getattr(result, "vendor", None), getattr(result, "agent_id", None)):
            return lane
    return str(getattr(result, "vendor", None) or getattr(result, "agent_id", None))


def _lane_report(
    results_by_round: list[list[Any]], verified: list[str], *, phase: str
) -> dict[str, Any]:
    """The ``lanes`` / ``lane_results`` / ``degradations`` fields of ``result.json``.

    ``lane_results`` holds each lane's most recent result. A metered result
    whose spend the dispatcher could not record (``spend_recorded is False``)
    becomes one ``metered_spend_unrecorded`` degradation per lane and round.
    """
    succeeded: set[str] = set()
    lane_results: dict[str, dict[str, Any]] = {}
    degradations: list[dict[str, Any]] = []
    for n, results in enumerate(results_by_round, start=1):
        for result in results:
            lane = _lane_of(result, verified)
            if getattr(result, "success", False):
                succeeded.add(lane)
            lane_results[lane] = {
                "success": bool(getattr(result, "success", False)),
                "model_used": getattr(result, "model_used", None),
                "generation_id": getattr(result, "generation_id", None),
                "cost_usd": getattr(result, "cost_usd", None),
                "cost_source": getattr(result, "cost_source", None),
            }
            if getattr(result, "spend_recorded", None) is False:
                degradations.append({
                    "code": "metered_spend_unrecorded",
                    "phase": phase,
                    "detail": f"{lane} round {n} spend not recorded",
                })
    ordered = [lane for lane in verified if lane in succeeded]
    ordered += sorted(succeeded - set(ordered))
    return {"lanes": ordered, "lane_results": lane_results, "degradations": degradations}


def _quorum_received(consensus: dict[str, Any] | None, results_by_round: list[list[Any]]) -> int:
    if consensus and consensus.get("quorum_received") is not None:
        return int(consensus["quorum_received"])
    last = results_by_round[-1] if results_by_round else []
    return sum(1 for result in last if getattr(result, "success", False))


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
    verified_lanes: list[str] | None = None,
    counting_lanes: list[str] | None = None,
    review_orchestrator_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run one review phase through ``converge()`` and record ``result.json``.

    ``verified_lanes`` are the review lanes the launch marker (or a
    ``--check-vendors --json`` probe) verified; ``claude_code`` is always one.
    The others are dispatched by a ``ReviewOrchestrator`` alongside the
    handshake lane. ``counting_lanes`` default to the verified lanes.
    """
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
    stale = handshake.clear_rounds()
    if stale:
        handshake.event("stale_round_files_removed", files=stale)
    logging.basicConfig(
        filename=str(handshake.dir / "converge.log"), level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    verified, counting = _resolve_lanes(verified_lanes, counting_lanes)
    others = [lane for lane in verified if lane != LANE]
    if review_orchestrator_factory is None:
        def review_orchestrator_factory() -> Any:
            from review_dispatcher import _orchestrator_for_dispatch

            return _orchestrator_for_dispatch(None, worktree)

    policy = policy_fn(environment=environment, verified_review_lanes=len(verified))
    min_quorum = int(policy["min_quorum"][phase])
    orchestrator = CompositeOrchestrator(
        AgentLaneOrchestrator(handshake, model=model),
        include_lanes=others,
        review_factory=review_orchestrator_factory,
    )
    handshake.event(
        "converge_started", phase=phase, min_quorum=min_quorum, policy=policy,
        verified_lanes=verified, counting_lanes=counting,
    )
    try:
        res = converge_fn(
            change_id=change_id,
            review_type=review_type,
            artifacts_dir=change_dir,
            worktree_path=worktree,
            max_rounds=max_rounds,
            min_quorum=min_quorum,
            fix_mode=fix_mode,
            verified_lanes=verified,
            counting_lanes=counting,
            base_ref=base_ref,
            phase=phase,
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
            "missing_lanes": getattr(res, "missing_lanes", None),
            "quorum_received": _quorum_received(res.consensus, orchestrator.results_by_round),
            **_lane_report(orchestrator.results_by_round, verified, phase=phase),
        }
        if res.consensus is not None:
            consensus_path = change_dir / "reviews" / CONSENSUS_FILES[phase]
            consensus_path.parent.mkdir(parents=True, exist_ok=True)
            consensus_path.write_text(json.dumps(res.consensus, indent=2, default=str), encoding="utf-8")
            out["consensus_path"] = str(consensus_path)
    except Exception as exc:  # noqa: BLE001 - recorded for the agent, not swallowed silently
        out = {"phase": phase, "converged": False, "error": f"{type(exc).__name__}: {exc}"}
        # Spend already sent but not recorded is still reported on a failed run.
        degradations = _lane_report(orchestrator.results_by_round, verified, phase=phase)["degradations"]
        if degradations:
            out["degradations"] = degradations

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
    cv.add_argument(
        "--verified-lanes", action="append", default=None, metavar="LANE",
        help="A verified review lane (repeatable): the launch marker's execution_profile.lanes.review, "
        "or the --check-vendors --json verified list. claude_code is always included.",
    )
    cv.add_argument(
        "--counting-lanes", action="append", default=None, metavar="LANE",
        help="A lane that counts toward quorum (repeatable): the launch marker's "
        "review_requirements.counting_lanes. Defaults to the verified lanes.",
    )
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
        verified_lanes=args.verified_lanes,
        counting_lanes=args.counting_lanes,
    )
    print(json.dumps(
        {k: out.get(k) for k in ("phase", "converged", "rounds", "reason", "missing_lanes", "error")}
    ))
    return 0 if out.get("converged") else 1


if __name__ == "__main__":
    raise SystemExit(main())
