"""Tests for the judged fix-tier classification (ri-13).

Covers: _judge_fix_tier_gates's batched-question shape, call-count for
non-judgeable sources, and degradation contract (whole-batch and
per-finding); classify_finding's judged_hint override; and classify()'s
wiring of the batch, including the acceptance outcome's terse-actionable
vs verbose-unactionable marker case.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import classify as cl  # noqa: E402
from fix_models import Finding  # noqa: E402


def _make_finding(
    *,
    id: str = "test-001",
    source: str = "ruff",
    severity: str = "medium",
    category: str = "lint",
    title: str = "Test finding",
    detail: str = "",
) -> Finding:
    return Finding(
        id=id, source=source, severity=severity, category=category,
        title=title, detail=detail, file_path="src/app.py", line=1,
    )


def _noul_answer(noul: float) -> dict:
    return {"noul": noul}


class TestJudgeFixTierGates:
    def test_no_module_returns_empty(self, monkeypatch) -> None:
        monkeypatch.setattr(cl, "system_one_decisions", None)
        result = cl._judge_fix_tier_gates(
            [_make_finding(source="markers", detail=": fix")],
        )
        assert result == {}

    def test_no_judgeable_findings_skips_decide_entirely(self, monkeypatch) -> None:
        fake_module = MagicMock()
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        findings = [
            _make_finding(id="a", source="ruff"),
            _make_finding(id="b", source="mypy"),
            _make_finding(id="c", source="architecture"),
            _make_finding(id="d", source="security"),
        ]
        result = cl._judge_fix_tier_gates(findings)
        assert result == {}
        fake_module.decide.assert_not_called()

    def test_batches_markers_and_deferred_in_one_call(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        findings = [
            _make_finding(id="a", source="ruff"),
            _make_finding(id="b", source="markers", detail=": fix"),
            _make_finding(id="c", source="deferred:openspec", detail="slow query"),
        ]
        cl._judge_fix_tier_gates(findings)
        assert fake_module.decide.call_count == 1
        state, questions = fake_module.decide.call_args[0]
        assert set(questions) == {"finding_1", "finding_2"}
        assert set(state["findings"]) == {"finding_1", "finding_2"}
        assert questions["finding_1"]["type"] == "noul"
        assert questions["finding_2"]["type"] == "noul"

    def test_payload_includes_title_for_open_tasks_findings(self, monkeypatch) -> None:
        """Codex P1 (PR #601): collect_deferred.py's open-tasks collector puts
        the actual checkbox text in `title` and a generic "Open task in
        change <id>" placeholder in `detail`. A payload with `detail` alone
        leaves the judge blind to what the finding actually is."""
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        finding = _make_finding(
            source="deferred:open-tasks",
            title="Wire the retry budget into the vendor dispatcher",
            detail="Open task in change add-retry-budget",
        )
        cl._judge_fix_tier_gates([finding])
        state, _questions = fake_module.decide.call_args[0]
        assert (
            state["findings"]["finding_0"]["title"]
            == "Wire the retry budget into the vendor dispatcher"
        )

    def test_confident_true_answer_maps_above_threshold(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {"finding_0": _noul_answer(0.9)}
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        result = cl._judge_fix_tier_gates(
            [_make_finding(source="markers", detail=": fix")],
        )
        assert result[0] is True

    def test_confident_false_answer_maps_below_threshold(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {"finding_0": _noul_answer(0.1)}
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        result = cl._judge_fix_tier_gates(
            [_make_finding(source="markers", detail=": fix")],
        )
        assert result[0] is False

    def test_malformed_answer_is_absent_from_result(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {"finding_0": {"noul": "not-a-number"}}
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        result = cl._judge_fix_tier_gates(
            [_make_finding(source="markers", detail=": fix")],
        )
        assert 0 not in result

    def test_one_missing_answer_does_not_discard_the_rest_of_the_batch(
        self, monkeypatch,
    ) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {"finding_0": _noul_answer(0.9)}
        # finding_1 missing entirely -- a partial response.
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        findings = [
            _make_finding(id="a", source="markers", detail=": fix"),
            _make_finding(id="b", source="markers", detail=": also fix"),
        ]
        result = cl._judge_fix_tier_gates(findings)
        assert 0 in result
        assert 1 not in result

    def test_decide_returns_none_yields_empty(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        result = cl._judge_fix_tier_gates(
            [_make_finding(source="markers", detail=": fix")],
        )
        assert result == {}

    def test_dry_run_is_threaded_into_decide(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        cl._judge_fix_tier_gates(
            [_make_finding(source="markers", detail=": fix")], dry_run=True,
        )
        assert fake_module.decide.call_args.kwargs["dry_run"] is True


class TestClassifyFindingJudgedHint:
    def test_hint_true_overrides_heuristic_for_markers(self) -> None:
        # Detail is too short for the heuristic to grant agent tier on its own.
        finding = _make_finding(source="markers", detail=": no")
        result = cl.classify_finding(finding, judged_hint=True)
        assert result.tier == "agent"

    def test_hint_false_overrides_heuristic_for_markers(self) -> None:
        # Detail is long enough for the heuristic to grant agent tier alone.
        finding = _make_finding(
            source="markers", detail=": this has plenty of context to act on",
        )
        result = cl.classify_finding(finding, judged_hint=False)
        assert result.tier == "manual"

    def test_hint_true_overrides_heuristic_for_deferred(self) -> None:
        finding = _make_finding(
            source="deferred:openspec", detail="no fix keywords here at all",
        )
        result = cl.classify_finding(finding, judged_hint=True)
        assert result.tier == "agent"

    def test_hint_none_falls_back_to_heuristic(self) -> None:
        finding = _make_finding(source="markers", detail=": fix")
        result = cl.classify_finding(finding, judged_hint=None)
        assert result.tier == "manual"  # ": fix" is < 10 chars


class TestClassifyWiring:
    def test_no_decide_call_for_ruff_only_findings(self, monkeypatch) -> None:
        fake_module = MagicMock()
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        findings = [
            _make_finding(id="a", source="ruff", severity="high"),
            _make_finding(id="b", source="mypy", severity="high"),
        ]
        cl.classify(findings, severity_filter="medium")
        fake_module.decide.assert_not_called()

    def test_verbose_unactionable_marker_lands_manual_terse_actionable_lands_agent(
        self, monkeypatch,
    ) -> None:
        """The roadmap item's own acceptance outcome: a ten-word TODO with no
        actionable content is judged to the manual tier, and a terse but
        actionable one is judged to the agent tier -- inverting what the old
        character-count heuristic alone would have done."""
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "finding_0": _noul_answer(0.05),  # verbose but empty -> not actionable
            "finding_1": _noul_answer(0.95),  # terse but concrete -> actionable
        }
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        findings = [
            _make_finding(
                id="verbose",
                source="markers",
                severity="low",
                detail=(
                    ": this really needs to be looked at again at some point "
                    "by someone who understands the whole picture here"
                ),
            ),
            _make_finding(
                id="terse", source="markers", severity="low", detail=": fix typo",
            ),
        ]
        result = cl.classify(findings, severity_filter="low")
        by_id = {cf.finding.id: cf for cf in result}
        assert by_id["verbose"].tier == "manual"
        assert by_id["terse"].tier == "agent"

    def test_unavailable_judgment_falls_back_to_heuristics_unchanged(
        self, monkeypatch,
    ) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        findings = [
            _make_finding(
                source="markers", severity="low",
                detail=": refactor this function to use async pattern",
            ),
        ]
        result = cl.classify(findings, severity_filter="low")
        assert result[0].tier == "agent"

    def test_dry_run_reaches_the_judgment(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(cl, "system_one_decisions", fake_module)
        cl.classify(
            [_make_finding(source="markers", severity="low", detail=": fix")],
            severity_filter="low", dry_run=True,
        )
        assert fake_module.decide.call_args.kwargs["dry_run"] is True
