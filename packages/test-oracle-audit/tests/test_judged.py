"""Judged-stage tests (wp-judged-explain, task 5.1).

Spec: specs/test-oracle-audit/spec.md -- "Judged Oracle Assessment in Shadow Mode".
Design: D7 (batched, blind, shadow-only), D1 "Shared cut-points".
Contract: contracts/schemas/stage-record.schema.json (JudgedPayload).

Public API assumed (the implementation is written afterwards against these tests):

    judged.build_state(entry: TestEntry, *, repo_root: Path) -> dict
    judged.run_judged(entries, *, repo_root, dry_run=False, event_sink=None,
                      extra_context=None) -> list[StageRecord]

``decide`` is stubbed on the ``system_one_decisions`` module object, so the code
under test must call ``system_one_decisions.decide(...)`` through the module.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import system_one_decisions
from system_one_decisions.testing import stub_decide

from test_oracle_audit.records import StageRecord, TestEntry, TestId, content_hash_of_file
from test_oracle_audit.vocabulary import ORACLE_SOURCES

SITE = "test-oracle-audit.judge"
BOUNDARIES = ("pure_function", "module_api", "service_api", "ui", "mixed")
KEY_RE = re.compile(r"^t(\d+)\.(oracle_source|survives_refactor|boundary)$")
FIXTURE_PROJECT = Path(__file__).resolve().parent / "fixtures" / "judged" / "proj"
TOKEN_BUDGET = 32_000  # decide()'s documented 32K-token budget (~4 chars/token)


def _judged():
    """Import lazily so every test fails (RED) with ImportError until judged.py exists."""
    from test_oracle_audit import judged as module

    return module


# --------------------------------------------------------------------------- helpers


def _entry(root: Path, rel: str, func: str, *, fixtures=(), covered=("src/calc.py",)) -> TestEntry:
    tree = ast.parse((root / rel).read_text("utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func)
    return TestEntry(
        test_id=TestId(node_id=f"{rel}::{func}", content_hash=content_hash_of_file(root / rel, func)),
        path=rel,
        line_start=node.lineno,
        line_end=node.end_lineno or node.lineno,
        function_name=func,
        fixtures=tuple(fixtures),
        covered_modules=tuple(covered),
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE_PROJECT, dest)
    return dest


@pytest.fixture
def entries(repo: Path) -> list[TestEntry]:
    return [
        _entry(repo, "tests/test_calc.py", "test_add_matches_spec", fixtures=("sample_pair",)),
        _entry(repo, "tests/test_calc.py", "test_scale_snapshot"),
    ]


def _choice(dist: dict[str, float]) -> SimpleNamespace:
    top = max(dist, key=lambda k: dist[k])
    return SimpleNamespace(type="choice", choice=top, confidence=dist[top], probabilities=dict(dist))


def _noul(p: float) -> SimpleNamespace:
    return SimpleNamespace(type="noul", noul=p)


def _dist(top: str, p: float, labels: tuple[str, ...]) -> dict[str, float]:
    rest = (1.0 - p) / (len(labels) - 1)
    return {label: (p if label == top else rest) for label in labels}


class FakeDecide:
    """Records every call; answers every question key it receives.

    The i-th distinct ``t<i>`` index (sorted numerically) gets ``ORACLE[i]``-style answers,
    so a test can check which answer reached which record without knowing 0/1-based keys.
    """

    def __init__(self, *, oracle=None, boundary=None, survives=None, returns_none_if: Callable | None = None):
        self.calls: list[dict[str, Any]] = []
        self.oracle = oracle or [_dist("spec", 0.8, ORACLE_SOURCES), _dist("current_impl_output", 0.7, ORACLE_SOURCES)]
        self.boundary = boundary or [_dist("pure_function", 0.6, BOUNDARIES), _dist("service_api", 0.5, BOUNDARIES)]
        self.survives = survives or [0.9, 0.25]
        self.returns_none_if = returns_none_if

    def __call__(self, state, questions, *, site, event_sink=None, dry_run=False):
        self.calls.append({"state": state, "questions": questions, "site": site, "dry_run": dry_run})
        if self.returns_none_if is not None and self.returns_none_if(state, questions):
            return None
        indexes = sorted({int(KEY_RE.match(k).group(1)) for k in questions})
        rank = {idx: i for i, idx in enumerate(indexes)}
        answers: dict[str, Any] = {}
        for key in questions:
            idx, q = KEY_RE.match(key).groups()
            i = rank[int(idx)] % 2
            if q == "oracle_source":
                answers[key] = _choice(self.oracle[i])
            elif q == "boundary":
                answers[key] = _choice(self.boundary[i])
            else:
                answers[key] = _noul(self.survives[i])
        return answers


def _install(monkeypatch: pytest.MonkeyPatch, fake: FakeDecide) -> FakeDecide:
    monkeypatch.setattr(system_one_decisions, "decide", fake)
    return fake


def _state_text(state: Any) -> str:
    return json.dumps(state, default=str, sort_keys=True)


# --------------------------------------------------------------------------- .19


def test_answers_are_recorded_as_judgment_with_full_distributions(
    monkeypatch, repo, entries, schema_validator
) -> None:
    """test-oracle-audit.19: judged records hold full distributions, evidence_class judgment."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    fake = _install(monkeypatch, FakeDecide())

    records = _judged().run_judged(entries, repo_root=repo)

    assert [r.test_id for r in records] == [e.test_id for e in entries]
    for r in records:
        assert isinstance(r, StageRecord)
        assert r.stage == "judged"
        assert r.status == "ok"
        assert r.evidence_class == "judgment"
        schema_validator(r.to_json())
    first, second = records
    # Full distributions are stored verbatim (not just the argmax), for both tests in the batch.
    assert first.payload["oracle_source"] == fake.oracle[0]
    assert second.payload["oracle_source"] == fake.oracle[1]
    assert set(first.payload["oracle_source"]) == set(ORACLE_SOURCES)
    assert first.payload["boundary"] == fake.boundary[0]
    assert second.payload["boundary"] == fake.boundary[1]
    assert first.payload["survives_refactor"] == pytest.approx(0.9)
    assert second.payload["survives_refactor"] == pytest.approx(0.25)
    assert first.payload["truncated"] is False


def test_decide_is_called_through_the_module_with_the_judge_site_and_three_questions(
    monkeypatch, repo, entries
) -> None:
    """test-oracle-audit.19 (D7): site, questions keyed t<i>.<q>, vocabulary options offered."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    fake = _install(monkeypatch, FakeDecide())

    _judged().run_judged(entries, repo_root=repo, dry_run=False)

    assert fake.calls, "decide() was never reached through system_one_decisions.decide"
    for call in fake.calls:
        assert call["site"] == SITE
        assert call["dry_run"] is False
        assert call["questions"], "no questions were asked"
        assert all(KEY_RE.match(k) for k in call["questions"]), sorted(call["questions"])
    questions = fake.calls[0]["questions"]
    kinds = {KEY_RE.match(k).group(2) for k in questions}
    assert kinds == {"oracle_source", "survives_refactor", "boundary"}
    oracle_q = next(v for k, v in questions.items() if k.endswith(".oracle_source"))
    boundary_q = next(v for k, v in questions.items() if k.endswith(".boundary"))
    assert all(label in _state_text(oracle_q) for label in ORACLE_SOURCES)
    assert all(label in _state_text(boundary_q) for label in BOUNDARIES)


def test_event_sink_is_forwarded_to_decide(monkeypatch, repo, entries) -> None:
    """test-oracle-audit.19 (D7): the caller's event_sink reaches decide()."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    seen: dict[str, Any] = {}

    def spy(state, questions, *, site, event_sink=None, dry_run=False):
        seen["sink"] = event_sink
        return FakeDecide()(state, questions, site=site)

    monkeypatch.setattr(system_one_decisions, "decide", spy)
    sink = lambda event: None

    _judged().run_judged(entries, repo_root=repo, event_sink=sink)

    assert seen["sink"] is sink


def test_each_test_file_is_one_decide_call_when_state_fits_the_budget(monkeypatch, repo, entries) -> None:
    """test-oracle-audit.19 (D7 "Batching"): one decide() call per test file under budget."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    fake = _install(monkeypatch, FakeDecide())

    _judged().run_judged(entries, repo_root=repo)

    assert len(fake.calls) == 1
    indexes = {KEY_RE.match(k).group(1) for k in fake.calls[0]["questions"]}
    assert len(indexes) == len(entries)


# --------------------------------------------------------------------------- .20


def test_missing_key_degrades_every_record_without_raising(monkeypatch, repo, entries, schema_validator) -> None:
    """test-oracle-audit.20: TYPESAFE_API_KEY unset -> every record degraded with a reason."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    stub_decide(monkeypatch)  # decide() returns None, the unavailable signal

    records = _judged().run_judged(entries, repo_root=repo)

    assert len(records) == len(entries)
    for r in records:
        assert r.stage == "judged"
        assert r.status == "degraded"
        assert r.reason == "no_key"
        assert r.evidence_class == "judgment"
        schema_validator(r.to_json())


def test_dry_run_degrades_every_record_and_is_forwarded_to_decide(monkeypatch, repo, entries) -> None:
    """test-oracle-audit.20: --dry-run -> every record degraded (reason dry_run)."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")  # a key must not rescue a dry run
    calls: list[bool] = []

    def spy(state, questions, *, site, event_sink=None, dry_run=False):
        calls.append(dry_run)

    monkeypatch.setattr(system_one_decisions, "decide", spy)

    records = _judged().run_judged(entries, repo_root=repo, dry_run=True)

    assert [r.status for r in records] == ["degraded"] * len(entries)
    assert {r.reason for r in records} == {"dry_run"}
    assert all(c is True for c in calls)  # dry_run=True threaded through, or no call made at all


def test_degraded_judged_records_validate_against_the_stage_schema(monkeypatch, repo, entries, schema_validator) -> None:
    """test-oracle-audit.20: degraded records carry a reason and stay schema-valid."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    stub_decide(monkeypatch)
    for r in _judged().run_judged(entries, repo_root=repo, dry_run=True):
        data = r.to_json()
        assert data["status"] == "degraded" and data["reason"]
        schema_validator(data)


def test_run_judged_never_raises_when_decide_fails(monkeypatch, repo, entries) -> None:
    """test-oracle-audit.20, .23: a judged failure is recorded, never raised (never affects exit)."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")

    def boom(*_a, **_kw):
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(system_one_decisions, "decide", boom)

    records = _judged().run_judged(entries, repo_root=repo)

    assert len(records) == len(entries)
    assert all(r.status in {"degraded", "error"} and r.reason for r in records)


# --------------------------------------------------------------------------- .21


def test_state_handed_to_decide_excludes_other_approaches_and_labels(monkeypatch, repo, entries) -> None:
    """test-oracle-audit.21: static flags, mutation, rename, history and human label never reach decide()."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    fake = _install(monkeypatch, FakeDecide())
    sentinels = {
        "static": {"rules": ["SENTINEL_STATIC_FLAG_91c"]},
        "mutation": {"kill_rate": 0.123456789, "backend": "SENTINEL_MUTATION_BACKEND_4d2"},
        "rename": {"survives": False, "renamed_symbols": 7351},
        "history": {"co_change_ratio": 0.987654321, "tag": "SENTINEL_HISTORY_8aa"},
        "label": {"label": "SENTINEL_HUMAN_LABEL_b0e", "note": "SENTINEL_LABEL_NOTE_17f"},
    }
    context = {e.test_id.node_id: sentinels for e in entries}

    _judged().run_judged(entries, repo_root=repo, extra_context=context)

    assert fake.calls
    for call in fake.calls:
        text = _state_text(call["state"])
        for needle in ("SENTINEL_STATIC_FLAG_91c", "SENTINEL_MUTATION_BACKEND_4d2", "0.123456789",
                       "7351", "SENTINEL_HISTORY_8aa", "0.987654321", "SENTINEL_HUMAN_LABEL_b0e",
                       "SENTINEL_LABEL_NOTE_17f"):
            assert needle not in text, f"{needle!r} leaked into the judged state"
        # The questions are not the place to smuggle them either.
        assert "SENTINEL" not in _state_text(call["questions"])


def test_extra_context_in_flat_form_is_also_excluded(monkeypatch, repo, entries) -> None:
    """test-oracle-audit.21: blindness holds whatever shape extra_context takes."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    fake = _install(monkeypatch, FakeDecide())

    _judged().run_judged(entries, repo_root=repo, extra_context={"static_flags": ["SENTINEL_FLAT_5c3"], "mutation_kill_rate": 0.4242})

    for call in fake.calls:
        text = _state_text(call["state"])
        assert "SENTINEL_FLAT_5c3" not in text and "0.4242" not in text


def test_build_state_has_test_fixture_covered_source_and_cited_spec(repo, entries) -> None:
    """test-oracle-audit.21 (D7 "State"): the blind state is source + fixtures + covered bodies + cited spec."""
    state = _judged().build_state(entries[0], repo_root=repo)

    assert isinstance(state, dict)
    text = _state_text(state)
    assert "def test_add_matches_spec" in text  # the test itself
    assert "assert add(a, b) == 5" in text
    assert "def sample_pair" in text and "return (2, 3)" in text  # the fixture it uses
    assert "def add(a, b)" in text and "_normalise(a) + _normalise(b)" in text  # covered source body
    assert "ADD_SCENARIO_MARKER_7f3" in text  # the cited spec scenario text
    assert "Calculator tests." in text  # test module docstring


def test_build_state_for_an_uncited_test_omits_spec_text_and_unused_fixtures(repo, entries) -> None:
    """test-oracle-audit.21 (D7 "State"): only the cited spec and the fixtures the test uses are included."""
    state = _judged().build_state(entries[1], repo_root=repo)

    text = _state_text(state)
    assert "def test_scale_snapshot" in text
    assert "def scale" in text
    assert "def sample_pair" not in text
    # test_scale_snapshot cites no spec itself, so the scenario body of another test is not included
    assert "ADD_SCENARIO_MARKER_7f3" not in text


def test_build_state_has_no_other_approach_keys(repo, entries) -> None:
    """test-oracle-audit.21: no key of the state names another approach's output or a label."""
    state = _judged().build_state(entries[0], repo_root=repo)

    banned = ("static", "mutation", "kill", "rename", "history", "co_change", "label", "flag", "rule")
    keys: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                keys.append(str(k).lower())
                walk(v)
        elif isinstance(node, list | tuple):
            for v in node:
                walk(v)

    walk(state)
    offenders = [k for k in keys if any(b in k for b in banned)]
    assert not offenders, offenders


def test_build_state_is_pure_and_deterministic(repo, entries) -> None:
    """test-oracle-audit.21 (D7): building a state reads the repo only; same input, same state."""
    before = sorted(p.name for p in repo.rglob("*"))
    a = _judged().build_state(entries[0], repo_root=repo)
    b = _judged().build_state(entries[0], repo_root=repo)
    assert a == b
    assert sorted(p.name for p in repo.rglob("*")) == before


def test_covered_source_bodies_are_truncated_and_flagged(monkeypatch, repo, entries) -> None:
    """test-oracle-audit.19, .22 (D7 "State"): huge covered bodies are truncated; payload.truncated is True."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    lines = "\n".join(f"    value_{i} = {i}" for i in range(6000))
    (repo / "src" / "calc.py").write_text(
        'def add(a, b):\n    """Return the sum."""\n' + lines + "\n    return a + b  # TAIL_MARKER_zz9\n"
    )
    fake = _install(monkeypatch, FakeDecide())

    state = _judged().build_state(entries[0], repo_root=repo)
    records = _judged().run_judged(entries, repo_root=repo)

    text = _state_text(state)
    assert "def add" in text  # the head of the body is kept
    assert "TAIL_MARKER_zz9" not in text  # the tail is cut
    assert len(text) < len(lines)
    assert all(r.status == "ok" and r.payload["truncated"] is True for r in records)
    assert fake.calls


# --------------------------------------------------------------------------- .22


def _over_budget(state, questions) -> bool:
    return len(_state_text(state)) + len(_state_text(questions)) > TOKEN_BUDGET * 4


def test_over_budget_state_is_degraded_not_silently_truncated(monkeypatch, repo, entries, schema_validator) -> None:
    """test-oracle-audit.22: an over-budget state gives status degraded, reason over_budget."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    huge = "# " + ("pad " * 200_000)  # ~800K chars, far beyond 32K tokens, in the test itself
    path = repo / "tests" / "test_big.py"
    path.write_text(
        'def test_big():\n    blob = """' + huge + '"""\n    assert blob\n'
    )
    big = _entry(repo, "tests/test_big.py", "test_big", covered=())
    fake = _install(monkeypatch, FakeDecide(returns_none_if=_over_budget))

    records = _judged().run_judged([big], repo_root=repo)

    assert len(records) == 1
    assert records[0].status == "degraded"
    assert records[0].reason == "over_budget"
    assert records[0].evidence_class == "judgment"
    schema_validator(records[0].to_json())
    assert fake.calls


def test_one_over_budget_test_does_not_degrade_the_rest_of_its_file(monkeypatch, repo, schema_validator) -> None:
    """test-oracle-audit.22 (D7 "Batching"): over budget -> one call per test; neighbours stay ok."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    huge = "pad " * 200_000
    (repo / "tests" / "test_mixed.py").write_text(
        "def test_small():\n    assert 1 + 1 == 2\n\n\n"
        'def test_huge():\n    blob = """' + huge + '"""\n    assert blob\n'
    )
    small = _entry(repo, "tests/test_mixed.py", "test_small", covered=())
    big = _entry(repo, "tests/test_mixed.py", "test_huge", covered=())
    _install(monkeypatch, FakeDecide(returns_none_if=_over_budget))

    records = _judged().run_judged([small, big], repo_root=repo)

    by_name = {r.test_id.node_id.split("::")[-1]: r for r in records}
    assert by_name["test_small"].status == "ok"
    assert by_name["test_small"].reason is None
    assert by_name["test_huge"].status == "degraded"
    assert by_name["test_huge"].reason == "over_budget"
    schema_validator(by_name["test_small"].to_json())


def test_reasons_are_distinguished_between_no_key_dry_run_and_over_budget(monkeypatch, repo, entries) -> None:
    """test-oracle-audit.20, .22: the three degraded reasons are distinct and never swapped."""
    stub_decide(monkeypatch)

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    no_key = {r.reason for r in _judged().run_judged(entries, repo_root=repo)}
    dry = {r.reason for r in _judged().run_judged(entries, repo_root=repo, dry_run=True)}
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    keyed_none = {r.reason for r in _judged().run_judged(entries, repo_root=repo)}

    assert no_key == {"no_key"}
    assert dry == {"dry_run"}
    # A key is present but decide() still returned None: the budget is the remaining cause.
    assert keyed_none == {"over_budget"}


# --------------------------------------------------------------------------- .23


def test_confident_current_impl_output_is_recorded_but_changes_nothing(monkeypatch, repo, entries) -> None:
    """test-oracle-audit.23: p > 0.9 on current_impl_output is shadow data; run_judged returns, never raises/exits."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    confident = _dist("current_impl_output", 0.97, ORACLE_SOURCES)
    _install(monkeypatch, FakeDecide(oracle=[confident, confident], survives=[0.01, 0.01]))

    # Any SystemExit / exception here would be a gate; the stage must simply return records.
    try:
        records = _judged().run_judged(entries, repo_root=repo)
    except BaseException as exc:  # noqa: BLE001 - the point of the test
        pytest.fail(f"judged findings must never raise or exit: {exc!r}")

    assert [r.status for r in records] == ["ok", "ok"]
    assert all(r.payload["oracle_source"]["current_impl_output"] > 0.9 for r in records)
    assert all(r.evidence_class == "judgment" for r in records)


def test_judged_module_has_no_exit_path_and_no_direct_sdk_import() -> None:
    """test-oracle-audit.23, D7: judged.py never exits non-zero and never imports the SDK directly."""
    source = Path(_judged().__file__).read_text("utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(a.name.split(".")[0] == "typesafe_sdk" for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "typesafe_sdk"
            # D7 / stub_decide caveat: import the module, never pre-bind the function.
            if node.module == "system_one_decisions":
                assert "decide" not in {a.name for a in node.names}
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            assert name not in {"exit", "_exit"}, "judged.py must not exit"
