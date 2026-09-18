"""Tests for the judged multi-vendor review eligibility check (ri-11).

Covers: the config-held threshold sidecar, _classify_pr_risk's degradation
contract, and check_review_eligibility's judged-override wiring -- including
that the deterministic draft/origin skips still short-circuit before any
decide() call, and that an existing approval still short-circuits a PR the
judgment marked eligible (see design.md D2).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import vendor_review as vr


def _pr_size(**overrides) -> dict:
    base = {
        "additions": 10,
        "deletions": 5,
        "changed_lines": 15,
        "changed_files": 1,
        "files": ["skills/example/scripts/example.py"],
        "title": "example change",
        "body": "",
    }
    base.update(overrides)
    return base


class TestLoadVendorReviewThresholds:
    def test_missing_config_returns_defaults(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.json"
        assert vr.load_vendor_review_thresholds(missing) == {
            "max_changed_lines": vr.SMALL_PR_MAX_CHANGED_LINES,
            "max_files": vr.SMALL_PR_MAX_FILES,
            "confidence_floor": vr.DEFAULT_VENDOR_REVIEW_CONFIDENCE_FLOOR,
        }

    def test_malformed_config_returns_defaults(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert vr.load_vendor_review_thresholds(bad)["confidence_floor"] == (
            vr.DEFAULT_VENDOR_REVIEW_CONFIDENCE_FLOOR
        )

    def test_valid_config_overrides_defaults(self, tmp_path: Path) -> None:
        config = tmp_path / "vendor-review-judgment.json"
        config.write_text(
            '{"max_changed_lines": 20, "max_files": 1, "confidence_floor": 0.8}'
        )
        assert vr.load_vendor_review_thresholds(config) == {
            "max_changed_lines": 20,
            "max_files": 1,
            "confidence_floor": 0.8,
        }


class TestClassifyPrRisk:
    def test_no_module_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(vr, "system_one_decisions", None)
        assert vr._classify_pr_risk(1, "openspec", _pr_size()) is None

    def test_decide_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        assert vr._classify_pr_risk(1, "openspec", _pr_size()) is None

    def test_confident_high_risk_answer_is_eligible(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "warrants_review": {"noul": 0.9},
            "risk": {"score": 3.2, "confidence": 0.7},
        }
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        result = vr._classify_pr_risk(1, "openspec", _pr_size())
        assert result == {"eligible": True, "risk_score": 3.2, "risk_probability": 0.7}

    def test_confident_low_risk_answer_is_ineligible_but_classified(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "warrants_review": {"noul": 0.1},
            "risk": {"score": 0.4, "confidence": 0.9},
        }
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        result = vr._classify_pr_risk(1, "openspec", _pr_size())
        assert result == {"eligible": False, "risk_score": 0.4, "risk_probability": 0.9}

    def test_malformed_noul_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {"warrants_review": {"noul": "high"}}
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        assert vr._classify_pr_risk(1, "openspec", _pr_size()) is None

    def test_missing_warrants_review_key_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {"risk": {"score": 1.0, "confidence": 0.5}}
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        assert vr._classify_pr_risk(1, "openspec", _pr_size()) is None

    def test_state_excludes_diff_and_includes_metadata(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        vr._classify_pr_risk(
            42, "openspec",
            _pr_size(title="fix guardrails", body="x" * 5000, files=["a.py", "b.py"]),
        )
        state, questions = fake_module.decide.call_args[0]
        assert state["title"] == "fix guardrails"
        assert len(state["body"]) <= 2000
        assert state["files"] == ["a.py", "b.py"]
        assert "diff" not in state
        assert questions["risk"]["criteria"] == list(vr._RISK_LEVELS)

    def test_dry_run_default_is_threaded_into_decide(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        vr._classify_pr_risk(1, "openspec", _pr_size())
        assert fake_module.decide.call_args.kwargs["dry_run"] is False

    def test_dry_run_true_is_threaded_into_decide(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        vr._classify_pr_risk(1, "openspec", _pr_size(), dry_run=True)
        assert fake_module.decide.call_args.kwargs["dry_run"] is True


class TestCheckReviewEligibilityJudgedOverride:
    def test_draft_pr_never_calls_decide(self, monkeypatch) -> None:
        fake_module = MagicMock()
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        result = vr.check_review_eligibility(
            1, "openspec", _pr_size(), is_draft=True,
        )
        assert result["eligible"] is False
        assert result["reason"] == "draft_pr"
        fake_module.decide.assert_not_called()

    def test_skip_origin_never_calls_decide(self, monkeypatch) -> None:
        fake_module = MagicMock()
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        result = vr.check_review_eligibility(1, "dependabot", _pr_size())
        assert result["eligible"] is False
        assert result["reason"] == "skip_origin"
        fake_module.decide.assert_not_called()

    def test_small_risky_pr_is_eligible_via_judgment(self, monkeypatch) -> None:
        """design.md D1: a 40-line guardrails.py change is 'small' under the
        size rule but the judgment routes it to review anyway."""
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "warrants_review": {"noul": 0.85},
            "risk": {"score": 3.0, "confidence": 0.8},
        }
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        pr_size = _pr_size(
            changed_lines=40, changed_files=1,
            files=["skills/guardrails/scripts/guardrails.py"],
        )
        result = vr.check_review_eligibility(1, "openspec", pr_size)
        assert result["eligible"] is True
        assert result["details"]["evidence_class"] == "judgment"
        assert result["details"]["risk_score"] == 3.0
        assert result["details"]["risk_probability"] == 0.8

    def test_large_docs_only_pr_is_not_eligible_via_judgment(self, monkeypatch) -> None:
        """design.md D1: a 320-line docs move is 'large' under the size rule
        but the judgment routes it away from review anyway."""
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "warrants_review": {"noul": 0.05},
            "risk": {"score": 0.2, "confidence": 0.9},
        }
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        pr_size = _pr_size(
            changed_lines=320, changed_files=2, files=["docs/a.md", "docs/b.md"],
        )
        result = vr.check_review_eligibility(1, "openspec", pr_size)
        assert result["eligible"] is False
        assert result["reason"] == "low_risk_judged"
        assert result["details"]["evidence_class"] == "judgment"

    def test_dry_run_reaches_the_judgment_call(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        vr.check_review_eligibility(1, "openspec", _pr_size(), dry_run=True)
        assert fake_module.decide.call_args.kwargs["dry_run"] is True

    def test_unavailable_judgment_falls_back_to_small_pr_rule(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        result = vr.check_review_eligibility(1, "openspec", _pr_size(changed_lines=10, changed_files=1))
        assert result["eligible"] is False
        assert result["reason"] == "small_pr"

    def test_unavailable_judgment_falls_back_to_large_pr_eligible(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        pr_size = _pr_size(changed_lines=500, changed_files=10)
        result = vr.check_review_eligibility(1, "openspec", pr_size)
        assert result["eligible"] is True
        assert "evidence_class" not in result["details"]

    def test_existing_approval_still_short_circuits_a_judged_eligible_pr(self, monkeypatch) -> None:
        """A judgment saying 'warrants review' must not bypass the existing
        has_approval skip -- the two checks are independent."""
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "warrants_review": {"noul": 0.95},
            "risk": {"score": 3.5, "confidence": 0.9},
        }
        monkeypatch.setattr(vr, "system_one_decisions", fake_module)
        pr_size = _pr_size(changed_lines=200, changed_files=5)
        result = vr.check_review_eligibility(
            1, "openspec", pr_size,
            existing_reviews=[{"state": "APPROVED", "reviewer": "someone"}],
        )
        assert result["eligible"] is False
        assert result["reason"] == "has_approval"
