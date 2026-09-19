"""Tests for the judged candidate-work rubric scorer (ri-17).

Covers: score_batch's batched-question shape, the Score-to-schema score
mapping (design D6), the all-or-nothing degradation contract (design D3,
deliberately different from the per-item fallback used elsewhere in this
roadmap), and compute_agreement's report-function correctness against an
explicitly synthetic fixture pair (design D8).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "supervise" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rubric_score as rs  # noqa: E402

_FINGERPRINT = "a" * 64
_AS_OF = "2026-09-19T00:00:00Z"


def _score_answer(score: float) -> dict:
    return {"score": score}


def _manifest(stub_keys: list[str]) -> dict:
    return {
        "schema_version": 1,
        "fingerprint": _FINGERPRINT,
        "as_of": _AS_OF,
        "requested_keys": list(stub_keys),
        "candidates": [
            {
                "stub_key": key,
                "stub": {"title": f"Stub {key}"},
                "signals": {"staleness_days": 1},
                "evidence": [],
            }
            for key in stub_keys
        ],
        "ready_set": [],
    }


def _answers_for(stub_keys: list[str], score: float) -> dict:
    answers: dict = {}
    for key in stub_keys:
        for factor in rs._FACTORS:
            answers[f"{key}__{factor}"] = _score_answer(score)
    return answers


class TestScoreBatch:
    def test_no_module_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(rs, "system_one_decisions", None)
        result = rs.score_batch(REPO_ROOT, _manifest(["change:add-foo"]))
        assert result is None

    def test_no_requested_keys_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        result = rs.score_batch(REPO_ROOT, _manifest([]))
        assert result is None
        fake_module.decide.assert_not_called()

    def test_batches_one_question_per_stub_per_factor(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        keys = ["change:add-foo", "change:add-bar"]
        rs.score_batch(REPO_ROOT, _manifest(keys))
        assert fake_module.decide.call_count == 1
        state, questions = fake_module.decide.call_args[0]
        assert len(questions) == len(keys) * len(rs._FACTORS)
        for key in keys:
            for factor in rs._FACTORS:
                assert questions[f"{key}__{factor}"]["type"] == "score"
                assert len(questions[f"{key}__{factor}"]["criteria"]) == 5
        assert set(state["candidates"]) == set(keys)

    def test_twenty_stubs_five_factors_is_one_hundred_questions(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        keys = [f"change:add-stub-{i:02d}" for i in range(20)]
        rs.score_batch(REPO_ROOT, _manifest(keys))
        _state, questions = fake_module.decide.call_args[0]
        assert len(questions) == 100

    @pytest.mark.parametrize(
        ("raw_score", "expected_schema_score"),
        [(0.0, 1), (1.0, 2), (2.4, 3), (2.6, 4), (4.0, 5), (-1.0, 1), (10.0, 5)],
    )
    def test_score_mapping_from_zero_indexed_position(
        self, monkeypatch, raw_score: float, expected_schema_score: int,
    ) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = _answers_for(["change:add-foo"], raw_score)
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        result = rs.score_batch(REPO_ROOT, _manifest(["change:add-foo"]))
        assert result is not None
        assert result["scores"][0]["relevance"]["score"] == expected_schema_score

    def test_successful_batch_validates_against_the_schema(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = _answers_for(["change:add-foo"], 3.0)
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        result = rs.score_batch(REPO_ROOT, _manifest(["change:add-foo"]))
        assert result is not None
        assert result["fingerprint"] == _FINGERPRINT
        assert result["scored_at"] == _AS_OF
        assert result["scores"][0]["stub_key"] == "change:add-foo"
        # Live judgment never populates justification -- rank_candidates
        # substitutes a legend label for it (see test_digest.py coverage).
        assert "justification" not in result["scores"][0]["relevance"]

    def test_decide_returns_none_yields_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        result = rs.score_batch(REPO_ROOT, _manifest(["change:add-foo"]))
        assert result is None

    def test_one_missing_factor_discards_the_whole_batch(self, monkeypatch) -> None:
        """Design D3: unlike ri-15/16/12/13's per-item fallback, a single
        missing factor here invalidates the WHOLE batch, not just its stub --
        rank_candidates' _validate_score_join already rejects a partial
        scores document outright, so a partial result here would be rejected
        downstream anyway."""
        fake_module = MagicMock()
        answers = _answers_for(["change:add-foo", "change:add-bar"], 3.0)
        del answers["change:add-bar__risk"]  # one factor missing for one stub
        fake_module.decide.return_value = answers
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        result = rs.score_batch(REPO_ROOT, _manifest(["change:add-foo", "change:add-bar"]))
        assert result is None

    def test_malformed_score_field_discards_the_whole_batch(self, monkeypatch) -> None:
        fake_module = MagicMock()
        answers = _answers_for(["change:add-foo"], 3.0)
        answers["change:add-foo__risk"] = {"score": "not-a-number"}
        fake_module.decide.return_value = answers
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        result = rs.score_batch(REPO_ROOT, _manifest(["change:add-foo"]))
        assert result is None

    def test_dry_run_is_threaded_into_decide(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        rs.score_batch(REPO_ROOT, _manifest(["change:add-foo"]), dry_run=True)
        assert fake_module.decide.call_args.kwargs["dry_run"] is True

    def test_candidate_manifest_mismatch_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        manifest = _manifest(["change:add-foo"])
        manifest["candidates"] = []  # requested_keys no longer covered
        result = rs.score_batch(REPO_ROOT, manifest)
        assert result is None
        fake_module.decide.assert_not_called()


class TestComputeAgreement:
    def test_identical_documents_agree_completely(self) -> None:
        doc = {
            "scores": [
                {"stub_key": "change:add-foo", **_all_score_row(3)},
            ],
        }
        result = rs.compute_agreement(doc, doc)
        assert result["agreement_rate"] == 1.0
        assert result["shared_stub_count"] == 1
        assert result["total_comparisons"] == len(rs._FACTORS)

    def test_partial_disagreement_is_reflected_per_factor(self) -> None:
        a = {"scores": [{"stub_key": "change:add-foo", **_all_score_row(3)}]}
        b_row = _all_score_row(3)
        b_row["risk"] = {"score": 1}
        b = {"scores": [{"stub_key": "change:add-foo", **b_row}]}
        result = rs.compute_agreement(a, b)
        assert result["per_factor"]["risk"]["agreements"] == 0
        assert result["per_factor"]["relevance"]["agreements"] == 1
        assert 0.0 < result["agreement_rate"] < 1.0

    def test_no_shared_stubs_yields_zero_rate_without_dividing_by_zero(self) -> None:
        a = {"scores": [{"stub_key": "change:add-foo", **_all_score_row(3)}]}
        b = {"scores": [{"stub_key": "change:add-bar", **_all_score_row(3)}]}
        result = rs.compute_agreement(a, b)
        assert result["shared_stub_count"] == 0
        assert result["agreement_rate"] == 0.0


def _all_score_row(score: int) -> dict:
    return {factor: {"score": score} for factor in rs._FACTORS}


class TestCli:
    def test_score_batch_command_exits_nonzero_when_unavailable(
        self, monkeypatch, tmp_path: Path, capsys,
    ) -> None:
        monkeypatch.setattr(rs, "system_one_decisions", None)
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(_manifest(["change:add-foo"])))
        exit_code = rs._cli_main(
            ["--repo-root", str(REPO_ROOT), "score-batch", "--manifest", str(manifest_path)],
        )
        assert exit_code == 1
        assert capsys.readouterr().out == ""

    def test_score_batch_command_prints_scores_on_success(
        self, monkeypatch, tmp_path: Path, capsys,
    ) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = _answers_for(["change:add-foo"], 3.0)
        monkeypatch.setattr(rs, "system_one_decisions", fake_module)
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(_manifest(["change:add-foo"])))
        exit_code = rs._cli_main(
            ["--repo-root", str(REPO_ROOT), "score-batch", "--manifest", str(manifest_path)],
        )
        assert exit_code == 0
        printed = json.loads(capsys.readouterr().out)
        assert printed["scores"][0]["stub_key"] == "change:add-foo"
