"""Tests for the judged first-stage ground screen (ri-15).

Covers: the config-held confidence floor, _screen_findings's degradation
contract and batched-question shape, and run()'s wiring of the screen --
including that a confident Ground-A screen removes a finding without ever
reaching stage two, that a batch screening entirely below the Ground-B
floor makes zero stage-two calls, that protected-subject findings never
enter the screen, and that a stage-two failure still discards any
tentative stage-one work (D3: "removes nothing" is a whole-run guarantee).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

from openspec_paths import repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
SCRIPTS = REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fact_check  # noqa: E402

FIXTURES_DIR = (
    Path(__file__).parent / "fixtures" / "review-fixtures"
)


def _finding(**overrides) -> dict:
    doc = {
        "id": "f-1",
        "type": "correctness",
        "criticality": "high",
        "description": "Variable `used_variable` is declared but never used.",
        "disposition": "fix",
        "axis": "correctness",
        "severity": "critical",
        "file_path": "src/foo.py",
    }
    doc.update(overrides)
    return doc


def _noul_answer(vendor_module: MagicMock, answers: dict[str, float]) -> None:
    vendor_module.decide.return_value = {
        key: {"noul": p} for key, p in answers.items()
    }


class TestLoadGroundScreenConfidenceFloor:
    def test_missing_config_returns_default(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.json"
        assert (
            fact_check.load_ground_screen_confidence_floor(missing)
            == fact_check.DEFAULT_GROUND_SCREEN_CONFIDENCE_FLOOR
        )

    def test_malformed_config_returns_default(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert (
            fact_check.load_ground_screen_confidence_floor(bad)
            == fact_check.DEFAULT_GROUND_SCREEN_CONFIDENCE_FLOOR
        )

    def test_valid_config_overrides_default(self, tmp_path: Path) -> None:
        config = tmp_path / "fact-check-judgment.json"
        config.write_text('{"confidence_floor": 0.8}')
        assert fact_check.load_ground_screen_confidence_floor(config) == 0.8


class TestScreenFindings:
    def test_no_module_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(fact_check, "system_one_decisions", None)
        assert fact_check._screen_findings([_finding()], "diff") is None

    def test_no_findings_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)
        assert fact_check._screen_findings([], "diff") is None
        fake_module.decide.assert_not_called()

    def test_decide_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)
        assert fact_check._screen_findings([_finding()], "diff") is None

    def test_batches_two_questions_per_finding(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)
        findings = [_finding(id="f-1"), _finding(id="f-2")]
        fact_check._screen_findings(findings, "some diff")
        state, questions = fake_module.decide.call_args[0]
        assert set(questions) == {"ground_a_f-1", "ground_b_f-1", "ground_a_f-2", "ground_b_f-2"}
        assert state["packet_diff"] == "some diff"
        assert {f["id"] for f in state["findings"]} == {"f-1", "f-2"}

    def test_extracts_noul_per_finding_per_ground(self, monkeypatch) -> None:
        fake_module = MagicMock()
        _noul_answer(fake_module, {"ground_a_f-1": 0.9, "ground_b_f-1": 0.2})
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)
        screen = fact_check._screen_findings([_finding(id="f-1")], "diff")
        assert screen == {"f-1": {"ground_a": 0.9, "ground_b": 0.2}}

    def test_empty_answers_dict_is_unavailable(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {}
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)
        assert fact_check._screen_findings([_finding(id="f-1")], "diff") is None

    def test_missing_answer_for_one_finding_yields_empty_entry_for_it(self, monkeypatch) -> None:
        fake_module = MagicMock()
        _noul_answer(fake_module, {"ground_a_f-1": 0.9, "ground_b_f-1": 0.1})
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)
        screen = fact_check._screen_findings(
            [_finding(id="f-1"), _finding(id="f-2")], "diff",
        )
        assert screen == {"f-1": {"ground_a": 0.9, "ground_b": 0.1}, "f-2": {}}

    def test_dry_run_is_threaded_into_decide(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)
        fact_check._screen_findings([_finding()], "diff", dry_run=True)
        assert fake_module.decide.call_args.kwargs["dry_run"] is True


class TestRunWithGroundScreen:
    def test_confident_ground_a_removes_without_stage_two_call(self, monkeypatch) -> None:
        fake_module = MagicMock()
        _noul_answer(fake_module, {"ground_a_f-1": 0.95, "ground_b_f-1": 0.1})
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)

        calls = []

        def caller(_s: str, _u: str) -> str:
            calls.append(1)
            return json.dumps({"tool": "approve_all_comments"})

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=[_finding(id="f-1")],
            packet_diff="irrelevant", caller=caller,
        )
        assert calls == []
        assert outcome.status == "ran"
        assert outcome.removed_count == 1
        assert outcome.decisions[0].verdict == "removed"
        assert outcome.decisions[0].ground == fact_check.GROUND_A
        assert outcome.decisions[0].evidence_line is None

    def test_batch_below_floor_makes_zero_stage_two_calls(self, monkeypatch) -> None:
        fake_module = MagicMock()
        _noul_answer(fake_module, {"ground_a_f-1": 0.1, "ground_b_f-1": 0.2})
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)

        calls = []

        def caller(_s: str, _u: str) -> str:
            calls.append(1)
            return json.dumps({"tool": "approve_all_comments"})

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=[_finding(id="f-1")],
            packet_diff="irrelevant", caller=caller,
        )
        assert calls == [], "screened-out finding must never reach stage two"
        assert outcome.status == "ran"
        assert outcome.kept_findings == [_finding(id="f-1")]
        assert outcome.decisions[0].verdict == "kept"

    def test_confident_ground_b_still_requires_stage_two_evidence(self, monkeypatch) -> None:
        """A Ground-B screen only earns a finding a seat at stage two -- the
        existing evidence-line check still gates the actual removal."""
        fake_module = MagicMock()
        _noul_answer(fake_module, {"ground_a_f-1": 0.1, "ground_b_f-1": 0.9})
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)

        finding = _finding(id="f-1", file_path="src/foo.py")

        def caller_no_evidence(_s: str, _u: str) -> str:
            return json.dumps({
                "tool": "report_incorrect_comments",
                "items": [{"finding_id": "f-1", "ground": fact_check.GROUND_B, "evidence_line": "nonexistent line"}],
            })

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=[finding],
            packet_diff="+used_variable = compute()", caller=caller_no_evidence,
        )
        assert outcome.decisions[0].verdict == "kept", (
            "a fabricated evidence line must not remove the finding even "
            "after a confident Ground-B screen"
        )

        def caller_with_evidence(_s: str, _u: str) -> str:
            return json.dumps({
                "tool": "report_incorrect_comments",
                "items": [{"finding_id": "f-1", "ground": fact_check.GROUND_B, "evidence_line": "+used_variable = compute()"}],
            })

        outcome2 = fact_check.run(
            vendor="codex", round_num=1, findings=[finding],
            packet_diff="+used_variable = compute()", caller=caller_with_evidence,
        )
        assert outcome2.decisions[0].verdict == "removed"

    def test_protected_finding_never_enters_the_screen(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)

        protected = _finding(
            id="f-1", description="This introduces a data race on the shared counter.",
        )

        def caller(_s: str, _u: str) -> str:
            return json.dumps({"tool": "approve_all_comments"})

        fact_check.run(
            vendor="codex", round_num=1, findings=[protected],
            packet_diff="irrelevant", caller=caller,
        )
        fake_module.decide.assert_not_called()

    def test_unavailable_screen_falls_back_to_unmodified_stage_two(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)

        def caller(_s: str, _u: str) -> str:
            return json.dumps({
                "tool": "report_incorrect_comments",
                "items": [{"finding_id": "f-1", "ground": fact_check.GROUND_B, "evidence_line": "+used_variable = compute()"}],
            })

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=[_finding(id="f-1")],
            packet_diff="+used_variable = compute()", caller=caller,
        )
        assert outcome.decisions[0].verdict == "removed"

    def test_partial_per_finding_answer_falls_back_to_stage_two(self, monkeypatch) -> None:
        """A malformed/missing answer for ONE finding in an otherwise
        answered batch must not be silently treated as a confident
        below-floor screen -- it was never actually screened, so it falls
        back to stage two exactly like whole-screen unavailability."""
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            # f-1: only ground_a answered, ground_b missing entirely.
            "ground_a_f-1": {"noul": 0.1},
            # f-2: fully and confidently screened out.
            "ground_a_f-2": {"noul": 0.1},
            "ground_b_f-2": {"noul": 0.1},
        }
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)

        sent_finding_ids = []

        def caller(_s: str, _u: str) -> str:
            sent_finding_ids.append("called")
            return json.dumps({
                "tool": "report_incorrect_comments",
                "items": [{"finding_id": "f-1", "ground": fact_check.GROUND_B, "evidence_line": "+used_variable = compute()"}],
            })

        findings = [_finding(id="f-1"), _finding(id="f-2", file_path="src/bar.py")]
        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="+used_variable = compute()", caller=caller,
        )
        assert sent_finding_ids == ["called"], (
            "f-1's incomplete screen answer must still reach stage two"
        )
        decisions = {d.finding_id: d for d in outcome.decisions}
        assert decisions["f-1"].verdict == "removed"
        assert decisions["f-2"].verdict == "kept"

    def test_stage_two_failure_discards_stage_one_removal_too(self, monkeypatch) -> None:
        """D3: "removes nothing" on any call failure is a whole-run
        guarantee -- a stage-two failure must not let a tentative stage-one
        Ground-A removal for a DIFFERENT finding in the same batch survive."""
        fake_module = MagicMock()
        _noul_answer(fake_module, {
            "ground_a_f-1": 0.95, "ground_b_f-1": 0.1,
            "ground_a_f-2": 0.1, "ground_b_f-2": 0.9,
        })
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)

        def failing_caller(_s: str, _u: str) -> str:
            raise RuntimeError("vendor CLI timed out")

        findings = [_finding(id="f-1"), _finding(id="f-2", file_path="src/bar.py")]
        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="irrelevant", caller=failing_caller,
        )
        assert outcome.status == "skipped"
        assert outcome.kept_findings == findings
        assert outcome.removed_count == 0

    def test_dry_run_reaches_the_screen(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)

        def caller(_s: str, _u: str) -> str:
            return json.dumps({"tool": "approve_all_comments"})

        fact_check.run(
            vendor="codex", round_num=1, findings=[_finding(id="f-1")],
            packet_diff="irrelevant", caller=caller, dry_run=True,
        )
        assert fake_module.decide.call_args.kwargs["dry_run"] is True


class TestGroundAAgreementAgainstRecordedBatch:
    """D4: the [live] extra is not installed anywhere in this repo (per
    every prior judged item's own finding), so a live-model agreement
    figure is a separate validation-phase measurement, not something CI
    can produce. What CI *can* prove is that the screen's wiring, given a
    stage-one answer, reproduces the same Ground-A verdicts stage two's
    existing (already-labeled-correct, per test_fact_check_fixture.py)
    prompt recorded on this fixture set -- see design.md D4.
    """

    @staticmethod
    def _recorded_ground_a_ids(transcript_entry: str) -> set[str]:
        _tool, items = fact_check.parse_verdict(transcript_entry)
        return {
            str(item["finding_id"])
            for item in items
            if item.get("ground") == fact_check.GROUND_A
        }

    def test_stage_one_reproduces_the_recorded_ground_a_labels(self, monkeypatch) -> None:
        manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
        transcript = json.loads(
            (FIXTURES_DIR / "fact-check-transcript.json").read_text(encoding="utf-8")
        )["responses"]

        total_recorded_ground_a = 0
        agreements = 0

        for case in manifest["cases"]:
            recorded_ids = self._recorded_ground_a_ids(transcript[case["id"]])
            if not recorded_ids:
                continue
            findings = json.loads(
                (FIXTURES_DIR / case["findings_file"]).read_text(encoding="utf-8")
            )["findings"]

            # Simulate a stage-one screen that agrees with the recorded
            # Ground-A verdicts and has no signal on everything else --
            # this is the wiring under test, not a live-calibration claim.
            fake_module = MagicMock()
            answers = {}
            for f in findings:
                fid = str(f["id"])
                confident = fid in recorded_ids
                answers[f"ground_a_{fid}"] = {"noul": 0.95 if confident else 0.05}
                answers[f"ground_b_{fid}"] = {"noul": 0.05}
            fake_module.decide.return_value = answers
            monkeypatch.setattr(fact_check, "system_one_decisions", fake_module)

            def caller(_s: str, _u: str) -> str:
                return json.dumps({"tool": "approve_all_comments"})

            outcome = fact_check.run(
                vendor="fixture", round_num=1, findings=findings,
                packet_diff="(unused -- stage one resolves ground A directly)",
                caller=caller,
            )
            removed_by_ground_a = {
                d.finding_id for d in outcome.decisions
                if d.verdict == "removed" and d.ground == fact_check.GROUND_A
            }
            total_recorded_ground_a += len(recorded_ids)
            agreements += len(removed_by_ground_a & recorded_ids)

        assert total_recorded_ground_a >= 2, (
            "fixture set must carry at least two recorded Ground-A verdicts"
        )
        agreement_rate = agreements / total_recorded_ground_a
        print(  # recorded for visibility per the acceptance outcome
            f"stage-one/stage-two Ground-A agreement on the fixture batch: "
            f"{agreements}/{total_recorded_ground_a} ({agreement_rate:.0%})"
        )
        assert agreement_rate == 1.0
