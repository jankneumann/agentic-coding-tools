"""AI-DORA scorecard skeleton.

Aggregates events from the coordinator, the worktree registry, and the repo
into a DORA-adapted scorecard bucketed by Vibe-Coding loop (Inner / Middle /
Outer). See docs/mental-models.md, Part 4 for the framework.

Source adapters below are intentional stubs marked TODO(source: ...). Wire
each one to your real data store; the metric computation and output layers
already work.

Usage:
    python scripts/ai_dora_snapshot.py                       # 30d window, markdown
    python scripts/ai_dora_snapshot.py --window 7d
    python scripts/ai_dora_snapshot.py --output json
    python scripts/ai_dora_snapshot.py --source coordinator  # only one source

Design rules (from the doc):
- No silent zeros. A metric whose source is unavailable reports
  Status.UNAVAILABLE with a reason — never 0.
- Output groups metrics by loop, never mixed.
- Output and outcome metrics are reported as a pair when applicable
  (e.g., merged_prs is meaningless without revert_rate beside it).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Protocol


REPO_ROOT = Path(__file__).resolve().parent.parent


class Loop(str, Enum):
    INNER = "inner"
    MIDDLE = "middle"
    OUTER = "outer"


class Status(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


@dataclass
class Metric:
    name: str
    loop: Loop
    value: float | int | str | None
    status: Status
    unit: str = ""
    reason: str = ""
    source: str = ""
    paired_with: str = ""


@dataclass
class Window:
    start: datetime
    end: datetime

    @property
    def days(self) -> int:
        return max(1, (self.end - self.start).days)


def parse_window(spec: str) -> Window:
    match = re.fullmatch(r"(\d+)([dhw])", spec)
    if not match:
        raise ValueError(f"window must look like 30d, 7d, 24h, 2w — got {spec!r}")
    n, unit = int(match.group(1)), match.group(2)
    delta = {"h": timedelta(hours=n), "d": timedelta(days=n), "w": timedelta(weeks=n)}[unit]
    end = datetime.now(timezone.utc)
    return Window(start=end - delta, end=end)


class Source(Protocol):
    name: str

    def available(self) -> tuple[bool, str]: ...

    def fetch(self, window: Window) -> dict: ...


@dataclass
class CoordinatorSource:
    """Pulls claims, heartbeats, phase events, token usage from the coordinator."""

    name: str = "coordinator"
    api_url: str = field(default_factory=lambda: os.environ.get("COORD_API_URL", ""))
    api_key: str = field(default_factory=lambda: os.environ.get("COORD_API_KEY", ""))

    def available(self) -> tuple[bool, str]:
        if not self.api_url:
            return False, "COORD_API_URL not set"
        if not self.api_key:
            return False, "COORD_API_KEY not set"
        return True, ""

    def fetch(self, window: Window) -> dict:
        # TODO(source: coordinator): replace with HTTP calls to coord API.
        # Endpoints expected (verify against agent-coordinator/):
        #   GET /events?since=...&until=...   → phase transitions, validation results
        #   GET /claims?since=...             → work-package claims and outcomes
        #   GET /tokens?since=...             → phase_token_pre/post audit-trail entries
        # Returned shape consumed by metric computers below; document it here
        # once the adapter is wired so future readers can reason about it.
        raise NotImplementedError("CoordinatorSource.fetch is a stub")


@dataclass
class RegistrySource:
    """Reads .git-worktrees/.registry.json plus learning-log files locally."""

    name: str = "registry"
    registry_path: Path = field(default_factory=lambda: REPO_ROOT / ".git-worktrees" / ".registry.json")
    learning_log_dir: Path = field(default_factory=lambda: REPO_ROOT / ".roadmap-runtime")

    def available(self) -> tuple[bool, str]:
        if not self.registry_path.exists():
            return False, f"missing {self.registry_path.relative_to(REPO_ROOT)}"
        return True, ""

    def fetch(self, window: Window) -> dict:
        # TODO(source: registry): parse .git-worktrees/.registry.json for active
        # agents, heartbeats, stale entries; walk learning-log dir for roadmap
        # checkpoints in window. Return:
        #   {"active_agents": int, "stale_agents": int,
        #    "tier_choices": [{"change_id": ..., "tier": ..., "outcome": ...}],
        #    "checkpoints": [...]}
        registry = json.loads(self.registry_path.read_text()) if self.registry_path.exists() else {}
        return {"raw_registry": registry, "checkpoints": []}


@dataclass
class RepoSource:
    """Reads git history and validation artifacts from the working tree."""

    name: str = "repo"
    repo_root: Path = REPO_ROOT

    def available(self) -> tuple[bool, str]:
        if not (self.repo_root / ".git").exists():
            return False, "not a git repository"
        return True, ""

    def fetch(self, window: Window) -> dict:
        # TODO(source: repo): use `git log --since=... --first-parent main` to
        # collect merge commits, then look for rework-report.json under
        # openspec/changes/archive/<id>/ for validation history. Return:
        #   {"merges": [{"sha": ..., "ts": ..., "change_id": ...,
        #                 "reverted_within": "24h" | None,
        #                 "iterations": int}],
        #    "rework_actions": {"iterate": int, "block-cleanup": int, ...},
        #    "validation_phases": {"smoke": {"pass": int, "fail": int}, ...}}
        return {"merges": [], "rework_actions": {}, "validation_phases": {}}


# ---------------------------------------------------------------------------
# Metric computers — one function per metric. Each takes the merged source
# bundle and returns a Metric. Use the unavailable() helper when the required
# source is missing.
# ---------------------------------------------------------------------------


def unavailable(name: str, loop: Loop, reason: str, source: str) -> Metric:
    return Metric(name=name, loop=loop, value=None, status=Status.UNAVAILABLE,
                  reason=reason, source=source)


def m_turns_per_accepted_patch(bundle: dict) -> Metric:
    coord = bundle.get("coordinator")
    if coord is None:
        return unavailable("turns_per_accepted_patch", Loop.INNER,
                           "coordinator source unavailable", "coordinator")
    # TODO(metric): count agent turns vs accepted edits within turn-level events.
    return Metric(name="turns_per_accepted_patch", loop=Loop.INNER, value=None,
                  status=Status.UNAVAILABLE, reason="not yet implemented",
                  source="coordinator", unit="ratio")


def m_tool_retry_rate(bundle: dict) -> Metric:
    coord = bundle.get("coordinator")
    if coord is None:
        return unavailable("tool_retry_rate", Loop.INNER,
                           "coordinator source unavailable", "coordinator")
    return Metric(name="tool_retry_rate", loop=Loop.INNER, value=None,
                  status=Status.UNAVAILABLE, reason="not yet implemented",
                  source="coordinator", unit="ratio")


def m_validation_phase_pass_rate(bundle: dict) -> Metric:
    repo = bundle.get("repo") or {}
    phases = repo.get("validation_phases") or {}
    if not phases:
        return unavailable("validation_phase_pass_rate", Loop.MIDDLE,
                           "no validation_phases in repo source", "repo")
    total_pass = sum(p.get("pass", 0) for p in phases.values())
    total = sum(p.get("pass", 0) + p.get("fail", 0) for p in phases.values())
    rate = total_pass / total if total else 0.0
    return Metric(name="validation_phase_pass_rate", loop=Loop.MIDDLE,
                  value=round(rate, 3), status=Status.OK, unit="ratio",
                  source="repo")


def m_review_iterations_to_merge(bundle: dict) -> Metric:
    repo = bundle.get("repo") or {}
    merges = repo.get("merges") or []
    if not merges:
        return unavailable("review_iterations_to_merge", Loop.MIDDLE,
                           "no merges in window", "repo")
    avg = sum(m.get("iterations", 0) for m in merges) / len(merges)
    return Metric(name="review_iterations_to_merge", loop=Loop.MIDDLE,
                  value=round(avg, 2), status=Status.OK, unit="iterations",
                  source="repo")


def m_rework_action_distribution(bundle: dict) -> Metric:
    repo = bundle.get("repo") or {}
    actions = repo.get("rework_actions") or {}
    if not actions:
        return unavailable("rework_action_distribution", Loop.MIDDLE,
                           "no rework actions in window", "repo")
    return Metric(name="rework_action_distribution", loop=Loop.MIDDLE,
                  value=json.dumps(actions, sort_keys=True),
                  status=Status.OK, unit="counts", source="repo")


def m_vendor_review_divergence(bundle: dict) -> Metric:
    coord = bundle.get("coordinator")
    if coord is None:
        return unavailable("vendor_review_divergence", Loop.MIDDLE,
                           "coordinator source unavailable", "coordinator")
    return Metric(name="vendor_review_divergence", loop=Loop.MIDDLE, value=None,
                  status=Status.UNAVAILABLE, reason="not yet implemented",
                  source="coordinator", unit="ratio")


def m_deploy_frequency(bundle: dict, window: Window) -> Metric:
    repo = bundle.get("repo") or {}
    merges = repo.get("merges") or []
    per_day = len(merges) / window.days
    if not merges:
        return unavailable("deploy_frequency", Loop.OUTER,
                           "no merges in window", "repo")
    return Metric(name="deploy_frequency", loop=Loop.OUTER, value=round(per_day, 2),
                  status=Status.OK, unit="per_day", source="repo",
                  paired_with="change_failure_rate")


def m_change_failure_rate(bundle: dict) -> Metric:
    repo = bundle.get("repo") or {}
    merges = repo.get("merges") or []
    if not merges:
        return unavailable("change_failure_rate", Loop.OUTER,
                           "no merges in window", "repo")
    failures = sum(1 for m in merges if m.get("reverted_within"))
    rate = failures / len(merges)
    return Metric(name="change_failure_rate", loop=Loop.OUTER, value=round(rate, 3),
                  status=Status.OK, unit="ratio", source="repo",
                  paired_with="deploy_frequency")


def m_lead_time_for_changes(bundle: dict) -> Metric:
    coord = bundle.get("coordinator")
    if coord is None:
        return unavailable("lead_time_for_changes", Loop.OUTER,
                           "coordinator source unavailable", "coordinator")
    return Metric(name="lead_time_for_changes", loop=Loop.OUTER, value=None,
                  status=Status.UNAVAILABLE, reason="not yet implemented",
                  source="coordinator", unit="hours")


def m_tier_selection_accuracy(bundle: dict) -> Metric:
    reg = bundle.get("registry") or {}
    choices = reg.get("tier_choices") or []
    if not choices:
        return unavailable("tier_selection_accuracy", Loop.OUTER,
                           "no tier_choices in window", "registry")
    correct = sum(1 for c in choices if c.get("outcome") == "matched")
    rate = correct / len(choices)
    return Metric(name="tier_selection_accuracy", loop=Loop.OUTER,
                  value=round(rate, 3), status=Status.OK, unit="ratio",
                  source="registry")


def m_cost_per_merged_feature(bundle: dict) -> Metric:
    coord = bundle.get("coordinator")
    if coord is None:
        return unavailable("cost_per_merged_feature", Loop.OUTER,
                           "coordinator source unavailable", "coordinator")
    return Metric(name="cost_per_merged_feature", loop=Loop.OUTER, value=None,
                  status=Status.UNAVAILABLE, reason="not yet implemented",
                  source="coordinator", unit="tokens")


METRIC_FNS: list[Callable[[dict], Metric] | Callable[[dict, Window], Metric]] = [
    m_turns_per_accepted_patch,
    m_tool_retry_rate,
    m_validation_phase_pass_rate,
    m_review_iterations_to_merge,
    m_rework_action_distribution,
    m_vendor_review_divergence,
    m_deploy_frequency,
    m_change_failure_rate,
    m_lead_time_for_changes,
    m_tier_selection_accuracy,
    m_cost_per_merged_feature,
]


def collect(bundle: dict, window: Window) -> list[Metric]:
    results: list[Metric] = []
    for fn in METRIC_FNS:
        results.append(fn(bundle, window) if fn is m_deploy_frequency else fn(bundle))
    return results


# ---------------------------------------------------------------------------
# Output renderers
# ---------------------------------------------------------------------------


def render_markdown(metrics: list[Metric], window: Window, sources: dict[str, str]) -> str:
    lines = [
        f"# AI-DORA snapshot — {window.start.date()} to {window.end.date()}",
        "",
        "Sources:",
    ]
    for name, status in sorted(sources.items()):
        lines.append(f"- `{name}`: {status}")
    lines.append("")
    for loop in Loop:
        in_loop = [m for m in metrics if m.loop == loop]
        if not in_loop:
            continue
        lines.append(f"## {loop.value.title()} loop")
        lines.append("")
        lines.append("| Metric | Value | Unit | Status | Source | Notes |")
        lines.append("|---|---|---|---|---|---|")
        for m in in_loop:
            value = "—" if m.value is None else m.value
            note = m.reason if m.status == Status.UNAVAILABLE else (
                f"paired with `{m.paired_with}`" if m.paired_with else ""
            )
            lines.append(f"| `{m.name}` | {value} | {m.unit or '—'} | {m.status.value} | `{m.source}` | {note} |")
        lines.append("")
    return "\n".join(lines)


def render_json(metrics: list[Metric], window: Window, sources: dict[str, str]) -> str:
    payload = {
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "sources": sources,
        "metrics": [
            {
                "name": m.name,
                "loop": m.loop.value,
                "value": m.value,
                "unit": m.unit,
                "status": m.status.value,
                "reason": m.reason,
                "source": m.source,
                "paired_with": m.paired_with or None,
            }
            for m in metrics
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AI-DORA scorecard snapshot")
    p.add_argument("--window", default="30d", help="lookback window: 24h, 7d, 30d, 2w (default 30d)")
    p.add_argument("--output", choices=("md", "json"), default="md")
    p.add_argument("--source", action="append", choices=("coordinator", "registry", "repo"),
                   help="restrict to a single source (repeatable)")
    args = p.parse_args(argv)

    window = parse_window(args.window)
    all_sources: list[Source] = [CoordinatorSource(), RegistrySource(), RepoSource()]
    if args.source:
        all_sources = [s for s in all_sources if s.name in set(args.source)]

    bundle: dict = {}
    source_status: dict[str, str] = {}
    for src in all_sources:
        ok, reason = src.available()
        if not ok:
            source_status[src.name] = f"unavailable ({reason})"
            continue
        try:
            bundle[src.name] = src.fetch(window)
            source_status[src.name] = "ok"
        except NotImplementedError as exc:
            source_status[src.name] = f"stub ({exc})"
        except Exception as exc:
            source_status[src.name] = f"error ({exc.__class__.__name__}: {exc})"

    metrics = collect(bundle, window)
    if args.output == "md":
        sys.stdout.write(render_markdown(metrics, window, source_status))
    else:
        sys.stdout.write(render_json(metrics, window, source_status))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
