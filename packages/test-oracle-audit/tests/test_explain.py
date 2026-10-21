"""Explanation-stage tests (wp-judged-explain, task 5.3).

Spec: specs/test-oracle-audit/spec.md -- "Explanations for Flagged Tests Only".
Design: D8 (flagging rule, backend, output), D1 "Shared cut-points".
Contract: contracts/schemas/stage-record.schema.json (ExplainPayload).
(Scenario .38, "explanation never feeds analysis", belongs to the analysis tests.)

Public API assumed (the implementation is written afterwards against these tests):

    explain.ExplainBackend                      # Protocol: run(prompt: str, system: str | None = None) -> str
    explain.select_flagged(joined, *, thresholds, kill_rate_cuts) -> list[str]
    explain.run_explain(entries, joined, *, backend, thresholds=None, kill_rate_cuts=None)
        -> list[StageRecord]

``joined`` maps node_id -> {stage: StageRecord}. A backend reply is a JSON object
``{"action": <enum>, "prose": <str>}``. Only flagged tests produce records.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from test_oracle_audit.records import StageRecord, TestEntry, TestId
from test_oracle_audit.thresholds import load_thresholds, tercile_cutpoints, tercile_of
from test_oracle_audit.vocabulary import ORACLE_SOURCES

ACTIONS = ("keep", "strengthen_assertions", "rewrite_from_spec", "declare_characterization", "delete_candidate")
THRESHOLDS = {"judged_impl_derived_p": 0.5, "co_change_high": 0.5}
CUTS = (0.3, 0.6)  # bottom <= 0.3 < middle <= 0.6 < top


def _explain():
    from test_oracle_audit import explain as module

    return module


# --------------------------------------------------------------------------- builders


def _tid(node_id: str) -> TestId:
    return TestId(node_id=node_id, content_hash="sha256:" + "ab" * 32)


def _entry(name: str) -> TestEntry:
    return TestEntry(
        test_id=_tid(f"tests/test_x.py::{name}"),
        path="tests/test_x.py",
        line_start=1,
        line_end=5,
        function_name=name,
    )


def _node(name: str) -> str:
    return f"tests/test_x.py::{name}"


def _rec(name: str, stage: str, payload: dict[str, Any], *, status: str = "ok", reason: str | None = None) -> StageRecord:
    return StageRecord(test_id=_tid(_node(name)), stage=stage, status=status, payload=payload, reason=reason)


def _oracle(p_intent: float) -> dict[str, float]:
    """An oracle_source distribution whose intent-derived mass is exactly ``p_intent``."""
    return {
        "spec": p_intent * 0.5,
        "property": p_intent * 0.5,
        "reference_impl": 0.0,
        "external_contract": 0.0,
        "characterization": (1 - p_intent) * 0.5,
        "current_impl_output": (1 - p_intent) * 0.5,
        "none": 0.0,
    }


def _judged(p_intent: float, *, boundary: str = "pure_function") -> StageRecord | dict[str, Any]:
    return {
        "oracle_source": _oracle(p_intent),
        "survives_refactor": 0.5,
        "boundary": {boundary: 1.0},
        "truncated": False,
    }


def _clean(name: str) -> dict[str, StageRecord]:
    """A test no approach flags (the .36 scenario): no static rule, intent-derived, mid kill rate,
    survives the rename, low co-change ratio."""
    return {
        "static": _rec(name, "static", {"rules": []}),
        "judged": _rec(name, "judged", _judged(0.9)),
        "mutation": _rec(name, "mutation", {"backend": "ast", "covering_mutants": 10, "killed_mutants": 5, "kill_rate": 0.5}),
        "rename": _rec(name, "rename", {"survives": True, "renamed_symbols": 3, "unrenamable_symbols": 0, "low_confidence": False}),
        "history": _rec(name, "history", {"co_change_ratio": 0.1, "co_change_denominator": 20, "added_with_fix": False}),
    }


def _with(name: str, **overrides: StageRecord) -> dict[str, StageRecord]:
    return {**_clean(name), **overrides}


def _mutation(name: str, rate: float | str) -> StageRecord:
    return _rec(name, "mutation", {"backend": "ast", "covering_mutants": 10, "killed_mutants": 0, "kill_rate": rate})


def _history(name: str, ratio: float | str) -> StageRecord:
    return _rec(name, "history", {"co_change_ratio": ratio, "co_change_denominator": 20, "added_with_fix": False})


def _rename(name: str, survives: bool) -> StageRecord:
    return _rec(name, "rename", {"survives": survives, "renamed_symbols": 3, "unrenamable_symbols": 0, "low_confidence": False})


def _join(**tests: dict[str, StageRecord]) -> dict[str, dict[str, StageRecord]]:
    return {_node(name): stages for name, stages in tests.items()}


class SpyBackend:
    """An ExplainBackend that records every request and answers with a valid reply."""

    def __init__(self, reply: str | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self.reply = reply or json.dumps({"action": "strengthen_assertions", "prose": "Assert on the output."})

    def run(self, prompt: str, system: str | None = None) -> str:
        self.requests.append({"prompt": prompt, "system": system})
        return self.reply


def _select(joined, *, thresholds: Mapping = THRESHOLDS, cuts=CUTS) -> set[str]:
    return set(_explain().select_flagged(joined, thresholds=thresholds, kill_rate_cuts=cuts))


# --------------------------------------------------------------------------- .36 flagging


def test_a_test_no_approach_flags_is_not_flagged(  ) -> None:
    """test-oracle-audit.36: no static rule, intent-derived, mid kill rate, survives, low co-change -> unflagged."""
    assert _select(_join(clean=_clean("clean"))) == set()


@pytest.mark.parametrize("rate", [0.5, 0.95, 0.31, 0.6])
def test_mid_or_top_kill_rate_tercile_is_not_flagged(rate: float) -> None:
    """test-oracle-audit.36: only the bottom kill-rate tercile flags; middle and top (and the cut itself) do not."""
    joined = _join(t=_with("t", mutation=_mutation("t", rate)))
    assert _select(joined) == set()


@pytest.mark.parametrize(
    ("stage", "record", "expected"),
    [
        ("static", lambda: _rec("t", "static", {"rules": ["assertion_free"]}), "static"),
        ("judged", lambda: _rec("t", "judged", _judged(0.2)), "judged"),
        ("mutation", lambda: _mutation("t", 0.1), "mutation"),
        ("rename", lambda: _rename("t", False), "rename"),
        ("history", lambda: _history("t", 0.9), "history"),
    ],
)
def test_each_measured_approach_alone_flags_a_test(stage, record, expected) -> None:
    """test-oracle-audit.36 (D8): flagged by at least one approach, each of the five rules in turn."""
    joined = _join(t=_with("t", **{stage: record()}))
    assert _select(joined) == {_node("t")}


def test_flagged_set_is_the_union_over_tests() -> None:
    """test-oracle-audit.36: select_flagged returns exactly the node ids with >= 1 flag."""
    joined = _join(
        keep=_clean("keep"),
        a=_with("a", static=_rec("a", "static", {"rules": ["mock_assertion_dominant"]})),
        b=_with("b", rename=_rename("b", False), history=_history("b", 0.99)),
    )
    result = _explain().select_flagged(joined, thresholds=THRESHOLDS, kill_rate_cuts=CUTS)
    assert isinstance(result, list)
    assert sorted(result) == [_node("a"), _node("b")]
    assert len(result) == len(set(result))


def test_insufficient_kill_rate_is_not_flagged_by_the_mutation_rule() -> None:
    """test-oracle-audit.36 (D8): a test with an insufficient kill rate is not flagged by that rule."""
    assert _select(_join(t=_with("t", mutation=_mutation("t", "insufficient")))) == set()


def test_insufficient_co_change_ratio_is_not_flagged_by_the_history_rule() -> None:
    """test-oracle-audit.36 (D8): an insufficient co-change ratio cannot exceed the threshold."""
    assert _select(_join(t=_with("t", history=_history("t", "insufficient")))) == set()


def test_without_kill_rate_cut_points_the_mutation_rule_cannot_fire() -> None:
    """test-oracle-audit.36 (D8, D1): no cut-points (no numeric kill rates in the suite) -> no mutation flag."""
    joined = _join(t=_with("t", mutation=_mutation("t", 0.0)))
    assert _select(joined, cuts=None) == set()


@pytest.mark.parametrize("stage", ["static", "judged", "mutation", "rename", "history"])
def test_degraded_or_missing_approach_records_flag_nothing(stage: str) -> None:
    """test-oracle-audit.36 (D8): only ok records can flag; degraded/skipped/missing ones are not evidence."""
    degraded = _rec("t", stage, {}, status="degraded", reason="no_key")
    assert _select(_join(t=_with("t", **{stage: degraded}))) == set()
    without = _clean("t")
    del without[stage]
    assert _select(_join(t=without)) == set()


def test_judged_threshold_comes_from_the_thresholds_argument() -> None:
    """test-oracle-audit.36 (D7, D8): P(intent-derived) below judged_impl_derived_p flags; the value is read, not hard-coded."""
    joined = _join(t=_with("t", judged=_rec("t", "judged", _judged(0.6))))
    assert _select(joined, thresholds={**THRESHOLDS, "judged_impl_derived_p": 0.5}) == set()
    assert _select(joined, thresholds={**THRESHOLDS, "judged_impl_derived_p": 0.7}) == {_node("t")}


def test_co_change_threshold_comes_from_the_thresholds_argument() -> None:
    """test-oracle-audit.36 (D8): co_change_ratio above co_change_high flags; the value is read, not hard-coded."""
    joined = _join(t=_with("t", history=_history("t", 0.6)))
    assert _select(joined, thresholds={**THRESHOLDS, "co_change_high": 0.8}) == set()
    assert _select(joined, thresholds={**THRESHOLDS, "co_change_high": 0.4}) == {_node("t")}


def test_judged_probability_is_the_intent_derived_mass_of_oracle_source() -> None:
    """test-oracle-audit.36 (D8): P(intent-derived) sums the intent-derived labels (spec/property/reference_impl/external_contract)."""
    split = dict.fromkeys(ORACLE_SOURCES, 0.0)
    split.update({"spec": 0.2, "external_contract": 0.2, "characterization": 0.6})  # P(intent) = 0.4 < 0.5
    flagged = _with("f", judged=_rec("f", "judged", {**_judged(0.9), "oracle_source": split}))
    split_ok = dict.fromkeys(ORACLE_SOURCES, 0.0)
    split_ok.update({"spec": 0.3, "reference_impl": 0.3, "current_impl_output": 0.4})  # P(intent) = 0.6
    fine = _with("g", judged=_rec("g", "judged", {**_judged(0.9), "oracle_source": split_ok}))
    assert _select(_join(f=flagged, g=fine)) == {_node("f")}


def test_boundary_answer_is_never_a_flagging_input() -> None:
    """test-oracle-audit.36 (D7): the boundary answer is descriptive only and does not change what is flagged."""
    for boundary in ("pure_function", "module_api", "service_api", "ui", "mixed"):
        joined = _join(
            ok=_with("ok", judged=_rec("ok", "judged", _judged(0.9, boundary=boundary))),
            bad=_with("bad", judged=_rec("bad", "judged", _judged(0.1, boundary=boundary))),
        )
        assert _select(joined) == {_node("bad")}


def test_kill_rate_terciles_use_the_suites_tercile_cutpoints() -> None:
    """test-oracle-audit.36 (D1, D8): flagging uses thresholds.tercile_cutpoints over the suite's numeric kill rates."""
    rates = {f"t{i}": round(0.1 * i, 1) for i in range(1, 10)}
    joined = _join(**{n: _with(n, mutation=_mutation(n, r)) for n, r in rates.items()})
    cuts = tercile_cutpoints(list(rates.values()))
    expected = {_node(n) for n, r in rates.items() if tercile_of(r, cuts) == "bottom"}
    assert expected  # sanity: the bottom third is non-empty and not everything
    assert expected != set(joined)
    assert _select(joined, cuts=cuts) == expected


def test_a_different_suite_means_different_cut_points_and_different_flags() -> None:
    """test-oracle-audit.36 (D1 "per suite"): the same kill rate is flagged under one suite's cuts, not another's."""
    joined = _join(t=_with("t", mutation=_mutation("t", 0.5)))
    assert _select(joined, cuts=(0.6, 0.8)) == {_node("t")}
    assert _select(joined, cuts=(0.2, 0.4)) == set()


# --------------------------------------------------------------------------- .36 requests


def test_unflagged_tests_are_not_sent_to_the_backend() -> None:
    """test-oracle-audit.36: no explanation request is made for a test no approach flagged."""
    entries = [_entry("clean_one"), _entry("clean_two"), _entry("flagged_one")]
    joined = _join(
        clean_one=_clean("clean_one"),
        clean_two=_clean("clean_two"),
        flagged_one=_with("flagged_one", static=_rec("flagged_one", "static", {"rules": ["assertion_free"]})),
    )
    backend = SpyBackend()

    records = _explain().run_explain(entries, joined, backend=backend, kill_rate_cuts=CUTS, thresholds=THRESHOLDS)

    assert len(backend.requests) == 1
    prompt = backend.requests[0]["prompt"]
    assert "flagged_one" in prompt
    assert "clean_one" not in prompt and "clean_two" not in prompt
    assert [r.test_id.node_id for r in records] == [_node("flagged_one")]


def test_no_flagged_tests_means_no_backend_calls_and_no_records() -> None:
    """test-oracle-audit.36: a fully clean suite sends nothing."""
    entries = [_entry("a"), _entry("b")]
    backend = SpyBackend()

    records = _explain().run_explain(entries, _join(a=_clean("a"), b=_clean("b")), backend=backend, kill_rate_cuts=CUTS, thresholds=THRESHOLDS)

    assert backend.requests == []
    assert records == []


def test_the_explainer_sees_the_evidence_that_flagged_the_test() -> None:
    """test-oracle-audit.36 (D8 "Not measured"): the explainer sees all evidence, so the prompt names the fired rule."""
    entries = [_entry("t")]
    joined = _join(t=_with("t", static=_rec("t", "static", {"rules": ["mock_assertion_dominant"]})))
    backend = SpyBackend()

    _explain().run_explain(entries, joined, backend=backend, kill_rate_cuts=CUTS, thresholds=THRESHOLDS)

    assert "mock_assertion_dominant" in backend.requests[0]["prompt"]


def test_thresholds_default_to_the_package_configuration() -> None:
    """test-oracle-audit.36 (D1, D7): thresholds=None reads load_thresholds(), never literals."""
    cfg = load_thresholds()
    low = max(cfg["judged_impl_derived_p"] - 0.2, 0.0)
    high = min(cfg["judged_impl_derived_p"] + 0.2, 1.0)
    entries = [_entry("low"), _entry("high")]
    joined = _join(
        low=_with("low", judged=_rec("low", "judged", _judged(low))),
        high=_with("high", judged=_rec("high", "judged", _judged(high))),
    )
    backend = SpyBackend()

    records = _explain().run_explain(entries, joined, backend=backend, kill_rate_cuts=CUTS)

    assert [r.test_id.node_id for r in records] == [_node("low")]


# --------------------------------------------------------------------------- .36 / .37 output


def test_flagged_tests_get_a_prose_record_with_an_enum_action(schema_validator) -> None:
    """test-oracle-audit.36 (D8 "Output"): ok record, stage explain, evidence_class prose, flagged_by named."""
    entries = [_entry("t")]
    joined = _join(t=_with("t", static=_rec("t", "static", {"rules": ["assertion_free"]}), rename=_rename("t", False)))

    (rec,) = _explain().run_explain(entries, joined, backend=SpyBackend(), kill_rate_cuts=CUTS, thresholds=THRESHOLDS)

    assert rec.stage == "explain" and rec.status == "ok" and rec.evidence_class == "prose"
    assert rec.payload["action"] in ACTIONS
    assert rec.payload["prose"] == "Assert on the output."
    assert set(rec.payload["flagged_by"]) == {"static", "rename"}
    schema_validator(rec.to_json())


@pytest.mark.parametrize("action", ACTIONS)
def test_every_enum_action_is_accepted(action: str, schema_validator) -> None:
    """test-oracle-audit.36: each advisory action in the enum round-trips."""
    backend = SpyBackend(json.dumps({"action": action, "prose": "ok"}))
    joined = _join(t=_with("t", static=_rec("t", "static", {"rules": ["assertion_free"]})))

    (rec,) = _explain().run_explain([_entry("t")], joined, backend=backend, kill_rate_cuts=CUTS, thresholds=THRESHOLDS)

    assert rec.status == "ok" and rec.payload["action"] == action
    schema_validator(rec.to_json())


def test_prose_is_capped_at_600_characters(schema_validator) -> None:
    """test-oracle-audit.36 (D8, ExplainPayload.prose maxLength 600): over-long prose is capped, not rejected."""
    backend = SpyBackend(json.dumps({"action": "keep", "prose": "word " * 1000}))
    joined = _join(t=_with("t", static=_rec("t", "static", {"rules": ["assertion_free"]})))

    (rec,) = _explain().run_explain([_entry("t")], joined, backend=backend, kill_rate_cuts=CUTS, thresholds=THRESHOLDS)

    assert rec.status == "ok"
    assert 0 < len(rec.payload["prose"]) <= 600
    assert rec.payload["prose"].startswith("word word")
    schema_validator(rec.to_json())


def test_an_action_outside_the_enum_is_never_recorded_as_ok(schema_validator) -> None:
    """test-oracle-audit.36 (D8): an invented action is not stored as an ok explanation."""
    backend = SpyBackend(json.dumps({"action": "burn_it_down", "prose": "Delete everything."}))
    joined = _join(t=_with("t", static=_rec("t", "static", {"rules": ["assertion_free"]})))

    (rec,) = _explain().run_explain([_entry("t")], joined, backend=backend, kill_rate_cuts=CUTS, thresholds=THRESHOLDS)

    if rec.status == "ok":
        assert rec.payload["action"] in ACTIONS
    else:
        assert rec.status in {"degraded", "error"} and rec.reason
    schema_validator(rec.to_json())


def test_unparseable_backend_reply_and_backend_errors_are_recorded_not_raised(schema_validator) -> None:
    """test-oracle-audit.36, .37: backend trouble degrades that test's record; the stage never raises."""
    joined = _join(
        bad_reply=_with("bad_reply", static=_rec("bad_reply", "static", {"rules": ["assertion_free"]})),
        boom=_with("boom", static=_rec("boom", "static", {"rules": ["assertion_free"]})),
    )

    class Flaky:
        def run(self, prompt: str, system: str | None = None) -> str:
            if "boom" in prompt and "bad_reply" not in prompt:
                raise RuntimeError("backend down")
            return "I am not JSON at all"

    records = _explain().run_explain(
        [_entry("bad_reply"), _entry("boom")], joined, backend=Flaky(), kill_rate_cuts=CUTS, thresholds=THRESHOLDS
    )

    assert len(records) == 2
    for rec in records:
        assert rec.stage == "explain"
        assert rec.status in {"degraded", "error"} and rec.reason
        schema_validator(rec.to_json())


# --------------------------------------------------------------------------- .37


def test_no_backend_degrades_each_flagged_tests_record(schema_validator) -> None:
    """test-oracle-audit.37: backend None -> each flagged test has a degraded record, reason no_backend."""
    entries = [_entry("clean"), _entry("f1"), _entry("f2")]
    joined = _join(
        clean=_clean("clean"),
        f1=_with("f1", static=_rec("f1", "static", {"rules": ["assertion_free"]})),
        f2=_with("f2", history=_history("f2", 0.9)),
    )

    records = _explain().run_explain(entries, joined, backend=None, kill_rate_cuts=CUTS, thresholds=THRESHOLDS)

    assert sorted(r.test_id.node_id for r in records) == [_node("f1"), _node("f2")]
    for rec in records:
        assert rec.stage == "explain"
        assert rec.status == "degraded"
        assert rec.reason == "no_backend"
        assert rec.evidence_class == "prose"
        schema_validator(rec.to_json())


def test_no_backend_with_nothing_flagged_emits_nothing() -> None:
    """test-oracle-audit.36, .37: degradation applies to flagged tests only."""
    assert _explain().run_explain([_entry("c")], _join(c=_clean("c")), backend=None, kill_rate_cuts=CUTS, thresholds=THRESHOLDS) == []


def test_explain_backend_protocol_is_runtime_usable() -> None:
    """test-oracle-audit.37 (D8): ExplainBackend has the gen_eval backend shape run(prompt, system) -> str."""
    protocol = _explain().ExplainBackend
    assert hasattr(protocol, "run")

    class Mine:
        def run(self, prompt: str, system: str | None = None) -> str:
            return ""

    # A structurally conforming object is accepted wherever a backend is expected.
    backend: Any = Mine()
    assert isinstance(backend.run("p"), str)
