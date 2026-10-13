"""Synthetic stage-record builders for the labelling, analysis, disagreement and report tests.

Plain in-memory data and standard library only. Test modules put this directory on
``sys.path`` and ``import analysis_builders``.

Assumed shape of the analysis input (the tests define it; see each test module header):

* ``joined``: ``dict[node_id, dict[stage, StageRecord]]`` (the D1 join on ``test_id``).
* ``labels``: ``dict[node_id, LabelEntry]`` as returned by ``LabelLedger.current_labels``.

Helper names deliberately avoid a ``test_`` prefix so pytest never collects them.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from test_oracle_audit.ledger import LabelEntry, LabelLedger
from test_oracle_audit.records import StageRecord, TestEntry, TestId
from test_oracle_audit.vocabulary import INTENT_DERIVED, ORACLE_SOURCES

SUITE = "test_evaluation"


def nid(i: int) -> str:
    return f"tests/test_synth.py::test_case_{i:03d}"


def tid(i: int) -> TestId:
    return TestId(node_id=nid(i), content_hash="sha256:" + hashlib.sha256(nid(i).encode()).hexdigest())


def entry(i: int) -> TestEntry:
    return TestEntry(
        test_id=tid(i),
        path="tests/test_synth.py",
        line_start=10 * i + 1,
        line_end=10 * i + 5,
        function_name=f"test_case_{i:03d}",
        covered_modules=("pkg.mod",),
    )


def distribution(top: str, p: float = 0.9) -> dict[str, float]:
    """A probability distribution over the oracle-source vocabulary with ``top`` as argmax."""
    rest = [label for label in ORACLE_SOURCES if label != top]
    dist = {label: (1.0 - p) / len(rest) for label in rest}
    dist[top] = p
    return dist


def p_intent(top: str, p: float = 0.9) -> float:
    return sum(v for k, v in distribution(top, p).items() if k in INTENT_DERIVED)


def static_rec(i: int, rules: Iterable[str] = (), *, status: str = "ok") -> StageRecord:
    if status != "ok":
        return StageRecord(tid(i), "static", status, {}, reason="parse_error")
    return StageRecord(tid(i), "static", "ok", {"rules": list(rules)})


def judged_rec(
    i: int,
    top: str = "spec",
    *,
    p: float = 0.9,
    survives: float = 0.5,
    boundary: str = "pure_function",
    status: str = "ok",
) -> StageRecord:
    if status != "ok":
        return StageRecord(tid(i), "judged", status, {}, reason="dry_run")
    boundaries = ("pure_function", "module_api", "service_api", "ui", "mixed")
    rest = [b for b in boundaries if b != boundary]
    bdist = {b: 0.1 / len(rest) for b in rest}
    bdist[boundary] = 0.9
    payload = {
        "oracle_source": distribution(top, p),
        "survives_refactor": survives,
        "boundary": bdist,
        "truncated": False,
    }
    return StageRecord(tid(i), "judged", "ok", payload)


def mutation_rec(i: int, kill_rate: float | str) -> StageRecord:
    covering = 3 if kill_rate == "insufficient" else 10
    killed = 0 if kill_rate == "insufficient" else round(float(kill_rate) * covering)
    payload = {"backend": "ast", "covering_mutants": covering, "killed_mutants": killed, "kill_rate": kill_rate}
    return StageRecord(tid(i), "mutation", "ok", payload)


def rename_rec(i: int, survives: bool, *, low_confidence: bool = False) -> StageRecord:
    payload = {
        "survives": survives,
        "renamed_symbols": 2,
        "unrenamable_symbols": 3 if low_confidence else 0,
        "low_confidence": low_confidence,
    }
    return StageRecord(tid(i), "rename", "ok", payload)


def history_rec(i: int, ratio: float | str) -> StageRecord:
    payload = {"co_change_ratio": ratio, "co_change_denominator": 8, "added_with_fix": False}
    return StageRecord(tid(i), "history", "ok", payload)


def explain_rec(i: int, action: str = "keep", payload: Mapping[str, Any] | None = None) -> StageRecord:
    body = dict(payload) if payload is not None else {"prose": "short", "action": action, "flagged_by": ["static"]}
    return StageRecord(tid(i), "explain", "ok", body)


def join(*record_groups: Iterable[StageRecord]) -> dict[str, dict[str, StageRecord]]:
    out: dict[str, dict[str, StageRecord]] = {}
    for group in record_groups:
        for rec in group:
            out.setdefault(rec.test_id.node_id, {})[rec.stage] = rec
    return out


def labels_for(mapping: Mapping[int, str]) -> dict[str, LabelEntry]:
    """Current human labels keyed by node id, built through the real ledger."""
    ledger = LabelLedger()
    for i, label in mapping.items():
        ledger.add(nid(i), tid(i).content_hash, label, "operator")
    return ledger.current_labels({nid(i): tid(i).content_hash for i in mapping})


def mixed_suite(n: int = 40) -> tuple[dict[str, dict[str, StageRecord]], dict[str, LabelEntry]]:
    """A deterministic suite with every approach present and partial judged/human disagreement."""
    recs: list[StageRecord] = []
    human: dict[int, str] = {}
    for i in range(n):
        intent = i % 2 == 0
        top = "spec" if intent else "current_impl_output"
        human[i] = top if i % 5 else ("current_impl_output" if intent else "spec")
        rules = ["private_import"] if i % 3 == 0 else []
        kill = round(0.05 + 0.9 * ((i * 7) % n) / n, 4)
        survives_p = 0.85 if i % 4 else 0.2
        recs += [
            static_rec(i, rules),
            judged_rec(i, top, survives=survives_p),
            mutation_rec(i, kill),
            rename_rec(i, survives=bool(i % 4)),
            history_rec(i, round(((i * 11) % n) / n, 4)),
        ]
    return join(recs), labels_for(human)


def fixed_open_decisions() -> list[dict[str, Any]]:
    return [
        {
            "id": "coverage_ratchet",
            "question": "What should happen to the line-coverage ratchet?",
            "options": [
                "keep the line-coverage ratchet",
                "allow a coverage drop with a deletion manifest citing audit evidence",
                "replace it with a mutation-score ratchet",
            ],
            "evidence": "pilot evidence per option",
        },
        {
            "id": "in_file_markers",
            "question": "Should oracle-source labels become in-file pytest markers?",
            "options": ["keep the sidecar ledger", "adopt in-file markers (note: no suite uses --strict-markers)"],
            "evidence": "no suite in the repo uses --strict-markers today",
        },
    ]


def make_analysis_doc(**overrides: Any) -> dict[str, Any]:
    """A hand-built, schema-valid analysis document for report rendering tests."""
    doc: dict[str, Any] = {
        "schema_version": 1,
        "advisory": True,
        "generated_at": "2026-10-13T00:00:00+00:00",
        "suites": [SUITE],
        "seed": 0,
        "approach_coverage": {
            "static": {"ok": 52, "degraded": 0, "insufficient": 0, "not_run": False},
            "judged": {"ok": 0, "degraded": 7, "insufficient": 0, "not_run": True},
            "mutation": {"ok": 31, "degraded": 0, "insufficient": 13, "not_run": False},
            "rename": {"ok": 44, "degraded": 0, "insufficient": 6, "not_run": False},
            "history": {"ok": 0, "degraded": 50, "insufficient": 0, "not_run": True},
        },
        "metrics": [
            {"subject": "oracle_source", "comparison": "human_label", "metric": "kappa_7", "n": 12,
             "status": "insufficient"},
            {"subject": "oracle_source", "comparison": "human_label", "metric": "kappa_binary", "n": 40,
             "status": "ok", "value": 0.55, "ci95": [0.31, 0.79]},
        ],
        "linter_candidates": [
            {"subject": "private_import", "kind": "static_rule", "reason": "cliffs_delta -0.8 CI excludes 0"}
        ],
        "excluded": [
            {"subject": "oracle_source", "kind": "judged_question", "reason": "kappa_binary 0.55 < 0.7 floor"}
        ],
        "disagreements": {
            "weak_assertions": [nid(1)],
            "static_blind_spot": [nid(2), nid(3)],
            "coupled_spec_test": [],
            "judge_vs_human": [nid(4)],
            "rubber_stamp": [],
        },
        "open_decisions": fixed_open_decisions(),
        "tercile_cutpoints": {SUITE: [0.25, 0.75]},
    }
    doc.update(overrides)
    return doc
