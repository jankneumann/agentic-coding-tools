"""Explain stage: advisory prose for flagged tests only (spec: Explanations for Flagged Tests Only; design D8).

A test is *flagged* when at least one measured approach points at it:

- ``static``: any static rule fired,
- ``judged``: P(intent-derived) is below the ``judged_impl_derived_p`` display threshold,
- ``mutation``: kill rate is in the bottom tercile of the suite's cut-points (``insufficient`` never flags),
- ``rename``: the rename broke the test,
- ``history``: ``co_change_ratio`` is above the ``co_change_high`` display threshold.

Only ok records count as evidence. Unflagged tests are never sent to the backend. The explainer sees all
the evidence (that is its job) but it is not a measured approach: its action is advisory and nothing in
the analysis reads it. Thresholds come from ``load_thresholds()``; the kill-rate cut-points are passed in
(computed per suite by :func:`test_oracle_audit.thresholds.tercile_cutpoints`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from test_oracle_audit.records import StageRecord, TestEntry
from test_oracle_audit.thresholds import load_thresholds, tercile_of
from test_oracle_audit.vocabulary import INTENT_DERIVED

STAGE = "explain"

ACTIONS: tuple[str, ...] = (
    "keep",
    "strengthen_assertions",
    "rewrite_from_spec",
    "declare_characterization",
    "delete_candidate",
)
MAX_PROSE_CHARS = 600
MEASURED_STAGES: tuple[str, ...] = ("static", "judged", "mutation", "rename", "history")

SYSTEM_PROMPT = (
    "You review one automated test that a quality audit flagged. Explain, in plain prose, why the "
    "evidence suggests the test may not guard intent, then recommend exactly one advisory action. "
    f"Reply with only a JSON object: {{\"action\": <one of {', '.join(ACTIONS)}>, \"prose\": <string of at "
    f"most {MAX_PROSE_CHARS} characters>}}. The action is advisory; it is not a verdict."
)

_FENCE_RE = re.compile(r"^```[\w-]*\s*|\s*```$")


@runtime_checkable
class ExplainBackend(Protocol):
    """The shape of ``gen_eval``'s backend: one prompt (and optional system prompt) in, text out."""

    def run(self, prompt: str, system: str | None = None) -> str: ...


# --------------------------------------------------------------------------- flagging


def _ok(stages: Mapping[str, StageRecord], stage: str) -> dict[str, Any] | None:
    record = stages.get(stage)
    return record.payload if record is not None and record.status == "ok" else None


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def intent_probability(oracle_source: Mapping[str, Any]) -> float:
    """P(intent-derived): the mass the judged ``oracle_source`` distribution puts on intent-derived labels."""
    return float(sum(p for label, p in oracle_source.items() if label in INTENT_DERIVED and _number(p)))


def flagged_by(
    stages: Mapping[str, StageRecord],
    *,
    thresholds: Mapping[str, Any],
    kill_rate_cuts: tuple[float, float] | None,
) -> list[str]:
    """Which measured approaches flag one test, in :data:`MEASURED_STAGES` order."""
    flags: list[str] = []

    static = _ok(stages, "static")
    if static is not None and static.get("rules"):
        flags.append("static")

    judged = _ok(stages, "judged")
    if (
        judged is not None
        and isinstance(judged.get("oracle_source"), Mapping)
        and intent_probability(judged["oracle_source"]) < thresholds["judged_impl_derived_p"]
    ):
        flags.append("judged")

    mutation = _ok(stages, "mutation")
    if (
        mutation is not None
        and kill_rate_cuts is not None
        and _number(mutation.get("kill_rate"))
        and tercile_of(float(mutation["kill_rate"]), kill_rate_cuts) == "bottom"
    ):
        flags.append("mutation")

    rename = _ok(stages, "rename")
    if rename is not None and rename.get("survives") is False:
        flags.append("rename")

    history = _ok(stages, "history")
    if (
        history is not None
        and _number(history.get("co_change_ratio"))
        and history["co_change_ratio"] > thresholds["co_change_high"]
    ):
        flags.append("history")

    return flags


def select_flagged(
    joined: Mapping[str, Mapping[str, StageRecord]],
    *,
    thresholds: Mapping[str, Any] | None = None,
    kill_rate_cuts: tuple[float, float] | None = None,
) -> list[str]:
    """Node ids flagged by at least one approach, in ``joined`` order."""
    cfg = load_thresholds() if thresholds is None else thresholds
    return [
        node_id
        for node_id, stages in joined.items()
        if flagged_by(stages, thresholds=cfg, kill_rate_cuts=kill_rate_cuts)
    ]


# --------------------------------------------------------------------------- request / reply


def _test_source(entry: TestEntry, repo_root: Path | None) -> str | None:
    if repo_root is None:
        return None
    try:
        lines = (Path(repo_root) / entry.path).read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    return "\n".join(lines[entry.line_start - 1 : entry.line_end])


def _prompt(
    entry: TestEntry,
    stages: Mapping[str, StageRecord],
    flags: Sequence[str],
    repo_root: Path | None,
) -> str:
    evidence = {
        name: {"status": rec.status, "reason": rec.reason, "payload": rec.payload}
        for name, rec in sorted(stages.items())
        if name in MEASURED_STAGES
    }
    parts = [
        f"Test: {entry.test_id.node_id}",
        f"Flagged by: {', '.join(flags)}",
        "Evidence (JSON):",
        json.dumps(evidence, indent=2, sort_keys=True, default=str),
    ]
    source = _test_source(entry, repo_root)
    if source:
        parts += ["Test source:", source]
    parts.append(f"Allowed actions: {', '.join(ACTIONS)}")
    return "\n".join(parts)


def _parse_reply(reply: str) -> tuple[dict[str, str] | None, str]:
    """``({"action", "prose"}, "")`` or ``(None, reason)``. Over-long prose is capped, not rejected."""
    text = _FENCE_RE.sub("", reply.strip())
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        try:
            data = json.loads(text[start : end + 1]) if 0 <= start < end else None
        except ValueError:
            data = None
    if not isinstance(data, dict):
        return None, "unparseable_reply"
    action, prose = data.get("action"), data.get("prose")
    if action not in ACTIONS:
        return None, "invalid_action"
    if not isinstance(prose, str):
        return None, "invalid_prose"
    return {"action": action, "prose": prose.strip()[:MAX_PROSE_CHARS]}, ""


def _record(entry: TestEntry, status: str, flags: Sequence[str], *, reason: str | None = None, **extra: str) -> StageRecord:
    return StageRecord(
        test_id=entry.test_id,
        stage=STAGE,
        status=status,
        payload={**extra, "flagged_by": list(flags)},
        reason=reason,
    )


def run_explain(
    entries: Sequence[TestEntry],
    joined: Mapping[str, Mapping[str, StageRecord]],
    *,
    backend: ExplainBackend | None,
    thresholds: Mapping[str, Any] | None = None,
    kill_rate_cuts: tuple[float, float] | None = None,
    repo_root: Path | None = None,
) -> list[StageRecord]:
    """One explain record per flagged entry, in entry order; unflagged tests produce nothing.

    ``backend=None`` degrades each flagged test (``no_backend``). A failing or malformed backend reply
    is recorded against that test and never raised. ``repo_root`` (optional) adds the test source to
    the request.
    """
    cfg = load_thresholds() if thresholds is None else thresholds
    records: list[StageRecord] = []
    for entry in entries:
        stages = joined.get(entry.test_id.node_id, {})
        flags = flagged_by(stages, thresholds=cfg, kill_rate_cuts=kill_rate_cuts)
        if not flags:
            continue
        if backend is None:
            records.append(_record(entry, "degraded", flags, reason="no_backend"))
            continue
        try:
            reply = backend.run(_prompt(entry, stages, flags, repo_root), SYSTEM_PROMPT)
        except Exception as exc:  # noqa: BLE001 - advisory stage: backend trouble is data, never an exit
            records.append(_record(entry, "error", flags, reason=f"backend_error: {type(exc).__name__}"))
            continue
        parsed, reason = _parse_reply(reply if isinstance(reply, str) else "")
        if parsed is None:
            records.append(_record(entry, "degraded", flags, reason=reason))
        else:
            records.append(_record(entry, "ok", flags, **parsed))
    return records
