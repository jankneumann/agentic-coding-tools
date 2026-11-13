"""Disagreement classes (spec: Disagreement Report; design D11).

Lists, by named class, the tests where measured approaches disagree. "Intent-derived" is *judged or
human*: the human label when the test has one, otherwise the judged top label. Only ``ok`` records
count as evidence, and explanation records are never read (they are not a measured approach).

The kill-rate tercile cut-points are passed in (computed once per suite by
:func:`test_oracle_audit.thresholds.tercile_cutpoints`) and the co-change threshold comes from the
``thresholds`` mapping (``load_thresholds()``); this module holds no threshold literal.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .ledger import LabelEntry
from .records import StageRecord
from .thresholds import tercile_of
from .vocabulary import INTENT_DERIVED, ORACLE_SOURCES

CLASSES: tuple[str, ...] = (
    "weak_assertions",
    "static_blind_spot",
    "coupled_spec_test",
    "judge_vs_human",
    "rubber_stamp",
)

Joined = Mapping[str, Mapping[str, StageRecord]]


def is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def ok_record(stages: Mapping[str, StageRecord], stage: str) -> StageRecord | None:
    """The stage's record when present and ``ok``, else ``None``."""
    record = stages.get(stage)
    return record if record is not None and record.status == "ok" else None


def judged_top_label(record: StageRecord) -> str | None:
    """Argmax of a judged ``oracle_source`` distribution (ties go to vocabulary order)."""
    dist = record.payload.get("oracle_source")
    if not isinstance(dist, Mapping) or not dist:
        return None
    ranked = [(float(dist[label]), -i, label) for i, label in enumerate(ORACLE_SOURCES) if label in dist]
    return max(ranked)[2] if ranked else None


def p_intent_derived(record: StageRecord) -> float | None:
    """Judged probability mass on the intent-derived labels."""
    dist = record.payload.get("oracle_source")
    if not isinstance(dist, Mapping) or not dist:
        return None
    return float(sum(p for label, p in dist.items() if label in INTENT_DERIVED))


def numeric_kill_rate(stages: Mapping[str, StageRecord]) -> float | None:
    record = ok_record(stages, "mutation")
    if record is None:
        return None
    rate = record.payload.get("kill_rate")
    return float(rate) if is_number(rate) else None


def _oracle_label(stages: Mapping[str, StageRecord], human: LabelEntry | None) -> str | None:
    """Judged-or-human label: the human one when present, else the judged top label."""
    if human is not None:
        return human.label
    judged = ok_record(stages, "judged")
    return judged_top_label(judged) if judged is not None else None


def classify_disagreements(
    joined: Joined,
    labels: Mapping[str, LabelEntry],
    *,
    kill_rate_cuts: tuple[float, float] | None,
    thresholds: Mapping[str, Any],
) -> dict[str, list[str]]:
    """The five D11 classes, each a sorted list of node ids.

    ``kill_rate_cuts`` may be ``None`` when no test has a numeric kill rate; then no test is in the
    bottom tercile.
    """
    co_change_high = float(thresholds["co_change_high"])
    out: dict[str, list[str]] = {name: [] for name in CLASSES}

    for node_id in sorted(joined):
        stages = joined[node_id]
        human = labels.get(node_id)
        label = _oracle_label(stages, human)
        intent = label in INTENT_DERIVED if label is not None else False

        rate = numeric_kill_rate(stages)
        band = tercile_of(rate, kill_rate_cuts) if rate is not None and kill_rate_cuts is not None else None

        # weak_assertions: right oracle, assertions too loose.
        if intent and band == "bottom":
            out["weak_assertions"].append(node_id)

        # static_blind_spot: no static rule fired, yet the oracle is current_impl_output.
        static = ok_record(stages, "static")
        if static is not None and not static.payload.get("rules") and label == "current_impl_output":
            out["static_blind_spot"].append(node_id)

        # coupled_spec_test: intent-derived but the rename broke it (low-confidence renames excluded, D10).
        rename = ok_record(stages, "rename")
        if (
            intent
            and rename is not None
            and not rename.payload.get("low_confidence")
            and rename.payload.get("survives") is False
        ):
            out["coupled_spec_test"].append(node_id)

        # judge_vs_human: binary classes differ (needs both a human label and an ok judged answer).
        judged = ok_record(stages, "judged")
        judged_label = judged_top_label(judged) if judged is not None else None
        if (
            human is not None
            and judged_label is not None
            and (judged_label in INTENT_DERIVED) != (human.label in INTENT_DERIVED)
        ):
            out["judge_vs_human"].append(node_id)

        # rubber_stamp: co-change above threshold while the kill rate is known and not bottom tercile.
        history = ok_record(stages, "history")
        ratio = history.payload.get("co_change_ratio") if history is not None else None
        if is_number(ratio) and float(ratio) > co_change_high and band is not None and band != "bottom":
            out["rubber_stamp"].append(node_id)

    return out


__all__ = ["CLASSES", "classify_disagreements", "judged_top_label", "p_intent_derived"]
