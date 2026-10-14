"""Agreement and predictive analysis (spec: Agreement and Predictive Analysis; design D10, D11).

Standard library only. Every statistic is a few lines and every metric carries ``n`` and a seeded
bootstrap 95% interval, written so a small ``n`` cannot overclaim: a cell with ``n < 20`` is
``insufficient`` and has no point estimate.

Explanation records are not a measured approach and are never opened here: only the stages in
:data:`APPROACHES` are read from the joined records.
"""

from __future__ import annotations

import itertools
import math
import random
import zlib
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .disagreement import (
    CLASSES,
    Joined,
    classify_disagreements,
    is_number,
    judged_top_label,
    numeric_kill_rate,
    ok_record,
    p_intent_derived,
)
from .ledger import LabelEntry
from .records import SCHEMA_VERSION, validate
from .thresholds import load_thresholds, tercile_cutpoints
from .vocabulary import INTENT_DERIVED

# Spec "Agreement and Predictive Analysis" / design D10: a metric with n below this is `insufficient`.
MIN_N = 20
# Spec / design D10 (ri-08 floor): a judged question whose binary kappa is below this is excluded.
KAPPA_BINARY_FLOOR = 0.7
# Design D10: seeded bootstrap with 2,000 resamples gives the 95% interval.
N_RESAMPLES = 2000
CI_LEVEL = 0.95

# The five measured approaches (design D10 approach-coverage table). `explain` is deliberately absent.
APPROACHES: tuple[str, ...] = ("static", "judged", "mutation", "rename", "history")

INSUFFICIENT = "insufficient"

# --------------------------------------------------------------------------- statistic primitives


def cohen_kappa(a: Sequence[Any], b: Sequence[Any]) -> float:
    """Cohen's kappa between two equal-length label sequences.

    When chance agreement is total (both raters used one single class) kappa is undefined; perfect
    agreement then scores 1.0 and anything else 0.0.
    """
    if len(a) != len(b):
        raise ValueError("cohen_kappa needs two sequences of equal length")
    n = len(a)
    if n == 0:
        raise ValueError("cohen_kappa needs at least one pair")
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[label] * cb.get(label, 0) for label in ca) / (n * n)
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else 0.0
    return (observed - expected) / (1.0 - expected)


def brier(probs: Sequence[float], outcomes: Sequence[float | bool]) -> float:
    """Mean squared error of probability forecasts against 0/1 outcomes."""
    if len(probs) != len(outcomes) or not probs:
        raise ValueError("brier needs equal-length, non-empty sequences")
    return sum((p - float(o)) ** 2 for p, o in zip(probs, outcomes, strict=True)) / len(probs)


def cliffs_delta(xs: Sequence[float], ys: Sequence[float]) -> float:
    """``(#x>y - #x<y) / (len(xs) * len(ys))``; ties count as neither."""
    if not xs or not ys:
        raise ValueError("cliffs_delta needs two non-empty groups")
    ordered = sorted(ys)
    greater = smaller = 0
    for x in xs:
        greater += bisect_left(ordered, x)  # ys strictly below x
        smaller += len(ordered) - bisect_right(ordered, x)  # ys strictly above x
    return (greater - smaller) / (len(xs) * len(ys))


def auc(scores: Sequence[float], labels: Sequence[float | bool]) -> float:
    """Probability a positive outscores a negative; ties count 0.5."""
    positives = [s for s, y in zip(scores, labels, strict=True) if y]
    negatives = [s for s, y in zip(scores, labels, strict=True) if not y]
    if not positives or not negatives:
        raise ValueError("auc needs at least one positive and one negative")
    return (cliffs_delta(positives, negatives) + 1.0) / 2.0


def youden_threshold(scores: Sequence[float], labels: Sequence[float | bool]) -> float:
    """The cut maximising Youden's J (TPR - FPR), predicting positive when ``score > cut``.

    Candidates are midpoints between adjacent distinct scores; the lowest best cut wins ties.
    """
    distinct = sorted(set(scores))
    if len(distinct) == 1:
        return float(distinct[0])
    positives = [s for s, y in zip(scores, labels, strict=True) if y]
    negatives = [s for s, y in zip(scores, labels, strict=True) if not y]
    best_cut, best_j = (distinct[0] + distinct[1]) / 2.0, -math.inf
    for lo, hi in itertools.pairwise(distinct):
        cut = (lo + hi) / 2.0
        tpr = sum(s > cut for s in positives) / len(positives)
        fpr = sum(s > cut for s in negatives) / len(negatives)
        if tpr - fpr > best_j + 1e-12:
            best_cut, best_j = cut, tpr - fpr
    return float(best_cut)


def _quantile(ordered: Sequence[float], q: float) -> float:
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def bootstrap_ci[T](
    fn: Callable[[list[T]], float],
    data: Sequence[T],
    *,
    seed: int,
    n_resamples: int = N_RESAMPLES,
) -> tuple[float, float]:
    """95% percentile interval of ``fn`` over seeded resamples (with replacement) of ``data``.

    Resamples on which ``fn`` is undefined (NaN) are skipped; ``(nan, nan)`` comes back if every
    resample is undefined.
    """
    rng = random.Random(seed)
    items = list(data)
    stats: list[float] = []
    for _ in range(n_resamples):
        value = float(fn(rng.choices(items, k=len(items))))
        if not math.isnan(value):
            stats.append(value)
    if not stats:
        return math.nan, math.nan
    stats.sort()
    tail = (1.0 - CI_LEVEL) / 2.0
    return _quantile(stats, tail), _quantile(stats, 1.0 - tail)


# --------------------------------------------------------------------------- metric builders


def _derive_seed(seed: int, *parts: str) -> int:
    """A stable per-metric seed so adding a metric never shifts another metric's interval."""
    return zlib.crc32("|".join([str(seed), *parts]).encode("utf-8"))


def _insufficient(subject: str, comparison: str, metric: str, n: int) -> dict[str, Any]:
    return {"subject": subject, "comparison": comparison, "metric": metric, "n": n, "status": INSUFFICIENT}


def _estimate(
    subject: str,
    comparison: str,
    metric: str,
    data: Sequence[Any],
    fn: Callable[[list[Any]], float],
    seed: int,
) -> dict[str, Any]:
    """One metric cell: point estimate plus bootstrap interval, or `insufficient`."""
    n = len(data)
    if n < MIN_N:
        return _insufficient(subject, comparison, metric, n)
    value = float(fn(list(data)))
    if math.isnan(value):
        return _insufficient(subject, comparison, metric, n)
    lo, hi = bootstrap_ci(fn, data, seed=_derive_seed(seed, subject, comparison, metric))
    if math.isnan(lo) or math.isnan(hi):
        return _insufficient(subject, comparison, metric, n)
    return {
        "subject": subject,
        "comparison": comparison,
        "metric": metric,
        "n": n,
        "status": "ok",
        "value": value,
        "ci95": [lo, hi],
    }


def _nan_if_empty(fn: Callable[..., float]) -> Callable[..., float]:
    def wrapped(*args: Any) -> float:
        try:
            return fn(*args)
        except (ValueError, ZeroDivisionError):
            return math.nan

    return wrapped


# --------------------------------------------------------------------------- joined-record views


def _human_pairs(joined: Joined, labels: Mapping[str, LabelEntry]) -> list[tuple[str, str]]:
    """(judged top label, human label) for tests having both a current label and an ok judged answer."""
    pairs = []
    for node_id in sorted(joined):
        human = labels.get(node_id)
        judged = ok_record(joined[node_id], "judged")
        top = judged_top_label(judged) if judged is not None else None
        if human is not None and top is not None:
            pairs.append((top, human.label))
    return pairs


def _survival_pairs(joined: Joined) -> list[tuple[float, bool]]:
    """(forecast P(survives), observed survival); low-confidence renames are excluded (D5, D10)."""
    pairs = []
    for node_id in sorted(joined):
        judged = ok_record(joined[node_id], "judged")
        rename = ok_record(joined[node_id], "rename")
        if judged is None or rename is None or rename.payload.get("low_confidence"):
            continue
        p, survives = judged.payload.get("survives_refactor"), rename.payload.get("survives")
        if is_number(p) and isinstance(survives, bool):
            pairs.append((float(p), survives))
    return pairs


def _rules_seen(joined: Joined) -> list[str]:
    rules: set[str] = set()
    for stages in joined.values():
        static = ok_record(stages, "static")
        if static is not None:
            rules.update(static.payload.get("rules", ()))
    return sorted(rules)


def _is_insufficient_record(stage: str, payload: Mapping[str, Any]) -> bool:
    if stage == "mutation":
        return payload.get("kill_rate") == INSUFFICIENT
    if stage == "history":
        return payload.get("co_change_ratio") == INSUFFICIENT
    if stage == "rename":
        return bool(payload.get("low_confidence"))
    return False


def _approach_coverage(joined: Joined) -> dict[str, dict[str, Any]]:
    counts = {stage: {"ok": 0, "degraded": 0, "insufficient": 0} for stage in APPROACHES}
    for stages in joined.values():
        for stage in APPROACHES:
            record = stages.get(stage)
            if record is None:
                continue
            if record.status != "ok":
                counts[stage]["degraded"] += 1  # degraded, skipped and error: the stage gave no usable value
            elif _is_insufficient_record(stage, record.payload):
                counts[stage]["insufficient"] += 1
            else:
                counts[stage]["ok"] += 1
    return {stage: {**c, "not_run": c["ok"] + c["insufficient"] == 0} for stage, c in counts.items()}


# --------------------------------------------------------------------------- the analysis


def _judged_question_metrics(
    joined: Joined, labels: Mapping[str, LabelEntry], seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    metrics: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    # oracle_source vs the human label: seven-class and binary (D2 split) kappa.
    pairs = _human_pairs(joined, labels)

    def kappa7(sample: list[tuple[str, str]]) -> float:
        return cohen_kappa([j for j, _ in sample], [h for _, h in sample])

    def kappa_binary(sample: list[tuple[str, str]]) -> float:
        return cohen_kappa([j in INTENT_DERIVED for j, _ in sample], [h in INTENT_DERIVED for _, h in sample])

    m7 = _estimate("oracle_source", "human_label", "kappa_7", pairs, kappa7, seed)
    mb = _estimate("oracle_source", "human_label", "kappa_binary", pairs, kappa_binary, seed)
    metrics += [m7, mb]
    if mb["status"] == "ok":
        if mb["value"] < KAPPA_BINARY_FLOOR:
            excluded.append(
                {
                    "subject": "oracle_source",
                    "kind": "judged_question",
                    "reason": f"kappa_binary {mb['value']:.2f} < {KAPPA_BINARY_FLOOR} floor",
                }
            )
        else:
            candidates.append(
                {
                    "subject": "oracle_source",
                    "kind": "judged_question",
                    "reason": f"kappa_binary {mb['value']:.2f} >= {KAPPA_BINARY_FLOOR} floor",
                }
            )

    # survives_refactor vs observed rename survival: Brier against the base-rate Brier.
    survival = _survival_pairs(joined)

    def brier_of(sample: list[tuple[float, bool]]) -> float:
        return brier([p for p, _ in sample], [o for _, o in sample])

    def base_rate_brier(sample: list[tuple[float, bool]]) -> float:
        rate = sum(o for _, o in sample) / len(sample)
        return brier([rate] * len(sample), [o for _, o in sample])

    b = _estimate("survives_refactor", "rename_survival", "brier", survival, brier_of, seed)
    base = _estimate(
        "survives_refactor", "rename_survival", "brier_base_rate", survival, base_rate_brier, seed
    )
    metrics += [b, base]
    if b["status"] == "ok" and base["status"] == "ok":
        better = b["value"] < base["value"] and not math.isclose(b["value"], base["value"], rel_tol=1e-9)
        if better:
            candidates.append(
                {
                    "subject": "survives_refactor",
                    "kind": "judged_question",
                    "reason": f"brier {b['value']:.3f} better than base rate {base['value']:.3f}",
                }
            )
        else:
            excluded.append(
                {
                    "subject": "survives_refactor",
                    "kind": "judged_question",
                    "reason": f"brier {b['value']:.3f} not better than base rate {base['value']:.3f}",
                }
            )
    return metrics, candidates, excluded


def _static_rule_metrics(
    joined: Joined, labels: Mapping[str, LabelEntry], seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    metrics: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    @_nan_if_empty
    def delta(sample: list[tuple[bool, float]]) -> float:
        return cliffs_delta([r for f, r in sample if f], [r for f, r in sample if not f])

    @_nan_if_empty
    def precision(sample: list[tuple[bool, bool]]) -> float:
        flagged = [pos for f, pos in sample if f]
        return sum(flagged) / len(flagged)

    @_nan_if_empty
    def recall(sample: list[tuple[bool, bool]]) -> float:
        positives = [f for f, pos in sample if pos]
        return sum(positives) / len(positives)

    for rule in _rules_seen(joined):
        kill_data: list[tuple[bool, float]] = []
        label_data: list[tuple[bool, bool]] = []
        for node_id in sorted(joined):
            stages = joined[node_id]
            static = ok_record(stages, "static")
            if static is None:
                continue
            flagged = rule in static.payload.get("rules", ())
            rate = numeric_kill_rate(stages)
            if rate is not None:
                kill_data.append((flagged, rate))
            human = labels.get(node_id)
            if human is not None:
                label_data.append((flagged, human.label not in INTENT_DERIVED))

        d = _estimate(rule, "kill_rate", "cliffs_delta", kill_data, delta, seed)
        metrics.append(d)
        metrics.append(_estimate(rule, "human_label", "precision", label_data, precision, seed))
        metrics.append(_estimate(rule, "human_label", "recall", label_data, recall, seed))
        if d["status"] == "ok":
            lo, hi = d["ci95"]
            if lo <= 0.0 <= hi:
                excluded.append(
                    {
                        "subject": rule,
                        "kind": "static_rule",
                        "reason": f"cliffs_delta {d['value']:.2f} CI [{lo:.2f}, {hi:.2f}] spans 0 (not_predictive)",
                    }
                )
            else:
                candidates.append(
                    {
                        "subject": rule,
                        "kind": "static_rule",
                        "reason": f"cliffs_delta {d['value']:.2f} CI [{lo:.2f}, {hi:.2f}] excludes 0",
                    }
                )
    return metrics, candidates, excluded


def _auc_metric(subject: str, data: list[tuple[float, bool]], seed: int) -> dict[str, Any]:
    @_nan_if_empty
    def fn(sample: list[tuple[float, bool]]) -> float:
        return auc([s for s, _ in sample], [y for _, y in sample])

    metric = _estimate(subject, "human_label", "auc", data, fn, seed)
    if metric["status"] == "ok":
        metric["threshold"] = youden_threshold([s for s, _ in data], [y for _, y in data])
        metric["provisional"] = True
    return metric


def _auc_metrics(joined: Joined, labels: Mapping[str, LabelEntry], seed: int) -> list[dict[str, Any]]:
    co_change: list[tuple[float, bool]] = []  # positive: human label NOT intent-derived
    p_intent: list[tuple[float, bool]] = []  # positive: human label intent-derived
    for node_id in sorted(joined):
        human = labels.get(node_id)
        if human is None:
            continue
        intent = human.label in INTENT_DERIVED
        history = ok_record(joined[node_id], "history")
        ratio = history.payload.get("co_change_ratio") if history is not None else None
        if is_number(ratio):
            co_change.append((float(ratio), not intent))
        judged = ok_record(joined[node_id], "judged")
        mass = p_intent_derived(judged) if judged is not None else None
        if mass is not None:
            p_intent.append((mass, intent))
    return [_auc_metric("co_change_ratio", co_change, seed), _auc_metric("p_intent_derived", p_intent, seed)]


def _group_by_suite(
    joined: Joined, suites: Sequence[str], suite_of: Mapping[str, str] | None
) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Joined records per suite. Without a mapping all tests are pooled (keyed by the sole suite, if one)."""
    if suite_of is None:
        return {suites[0] if len(suites) == 1 else "*": dict(joined)}
    groups: dict[str, dict[str, Mapping[str, Any]]] = {s: {} for s in suites}
    for node_id, stages in joined.items():
        groups.setdefault(suite_of.get(node_id, suites[0]), {})[node_id] = stages
    return groups


def _numeric_rates(group: Mapping[str, Mapping[str, Any]]) -> list[float]:
    rates = (numeric_kill_rate(stages) for stages in group.values())
    return [r for r in rates if r is not None]


def open_decisions(
    disagreements: Mapping[str, Sequence[str]], candidates: int, excluded: int
) -> list[dict[str, Any]]:
    """The fixed D13 open decisions, each with the pilot's evidence."""
    weak = len(disagreements.get("weak_assertions", ()))
    return [
        {
            "id": "coverage_ratchet",
            "question": "What should happen to the line-coverage ratchet?",
            "options": [
                "keep the line-coverage ratchet",
                "allow a coverage drop with a deletion manifest citing audit evidence",
                "replace it with a mutation-score ratchet",
            ],
            "evidence": (
                f"{weak} intent-derived test(s) sit in the bottom kill-rate tercile (weak_assertions); "
                f"{candidates} linter candidate(s) and {excluded} excluded signal(s) in this run. "
                "The audit changes no ratchet baseline."
            ),
        },
        {
            "id": "in_file_markers",
            "question": "Should oracle-source labels become in-file pytest markers?",
            "options": [
                "keep the sidecar label ledger",
                "adopt in-file markers (note: no suite in the repo uses --strict-markers today)",
            ],
            "evidence": "no suite in the repo uses --strict-markers today, so an unregistered marker is not an error.",
        },
    ]


def analyze(
    joined: Joined,
    labels: Mapping[str, LabelEntry],
    *,
    seed: int = 0,
    suites: Sequence[str],
    suite_of: Mapping[str, str] | None = None,
    source_revision: str | None = None,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The analysis document (``analysis-report.schema.json``).

    ``joined`` maps node id to ``{stage: StageRecord}``; ``labels`` maps node id to the current human
    label. ``suite_of`` optionally maps node id to its suite so tercile cut-points and the D11
    classes are computed per suite; without it all tests are pooled.
    """
    thresholds = dict(thresholds) if thresholds is not None else load_thresholds()
    suites = list(suites)

    metrics: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for part_metrics, part_candidates, part_excluded in (
        _judged_question_metrics(joined, labels, seed),
        _static_rule_metrics(joined, labels, seed),
    ):
        metrics += part_metrics
        candidates += part_candidates
        excluded += part_excluded
    metrics += _auc_metrics(joined, labels, seed)

    cutpoints: dict[str, list[float]] = {}
    disagreements: dict[str, list[str]] = {name: [] for name in CLASSES}
    for group_name, group in _group_by_suite(joined, suites, suite_of).items():
        rates = _numeric_rates(group)
        cuts = tercile_cutpoints(rates) if rates else None
        if cuts is not None:
            for suite in suites if group_name == "*" else [group_name]:
                cutpoints[suite] = [cuts[0], cuts[1]]
        found = classify_disagreements(group, labels, kill_rate_cuts=cuts, thresholds=thresholds)
        for name in CLASSES:
            disagreements[name] += found[name]
    disagreements = {name: sorted(ids) for name, ids in disagreements.items()}

    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "advisory": True,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "suites": suites,
        "seed": seed,
        "approach_coverage": _approach_coverage(joined),
        "metrics": metrics,
        "linter_candidates": candidates,
        "excluded": excluded,
        "disagreements": disagreements,
        "open_decisions": open_decisions(disagreements, len(candidates), len(excluded)),
        "tercile_cutpoints": cutpoints,
    }
    if source_revision is not None:
        doc["source_revision"] = source_revision
    validate(doc, "analysis-report")
    return doc


__all__ = [
    "APPROACHES",
    "KAPPA_BINARY_FLOOR",
    "MIN_N",
    "analyze",
    "auc",
    "bootstrap_ci",
    "brier",
    "cliffs_delta",
    "cohen_kappa",
    "open_decisions",
    "youden_threshold",
]
