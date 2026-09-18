"""Tests for the judged implementation-strategy classification (D1-D4).

Covers: design.md section matching, the config-held confidence floor,
_classify_package's degradation contract, and select_strategies()'s
judged-override wiring (including that vendor scarcity stays reachable
via the unmodified weighted-sum fallback -- see design.md D1).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import yaml

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[2] / "autopilot" / "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import implementation_strategy_selector as iss


def _write_packages(tmp_path: Path, packages: list[dict]) -> Path:
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(yaml.dump({"packages": packages}))
    return wp_path


class TestDesignSectionForPackage:
    def test_matches_heading_containing_package_id(self) -> None:
        design = (
            "# Design\n\n"
            "## wp-backend\n\n"
            "Backend notes here.\n\n"
            "## wp-frontend\n\n"
            "Frontend notes here.\n"
        )
        section = iss._design_section_for_package(design, "wp-backend")
        assert section == "Backend notes here."

    def test_no_match_returns_none(self) -> None:
        design = "# Design\n\n## wp-frontend\n\nFrontend notes.\n"
        assert iss._design_section_for_package(design, "wp-backend") is None

    def test_last_heading_captures_to_end_of_document(self) -> None:
        design = "## wp-only\n\nOnly section, no trailing heading.\n"
        section = iss._design_section_for_package(design, "wp-only")
        assert section == "Only section, no trailing heading."


class TestLoadStrategyConfidenceFloor:
    def test_missing_config_returns_default(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.json"
        assert (
            iss.load_strategy_confidence_floor(missing)
            == iss.DEFAULT_STRATEGY_CONFIDENCE_FLOOR
        )

    def test_malformed_config_returns_default(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert (
            iss.load_strategy_confidence_floor(bad)
            == iss.DEFAULT_STRATEGY_CONFIDENCE_FLOOR
        )

    def test_valid_config_overrides_default(self, tmp_path: Path) -> None:
        config = tmp_path / "implementation-strategy-judgment.json"
        config.write_text('{"confidence_floor": 0.8}')
        assert iss.load_strategy_confidence_floor(config) == 0.8


class TestClassifyPackage:
    def test_no_module_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(iss, "system_one_decisions", None)
        result = iss._classify_package("wp-1", {}, None, ["claude", "gpt4", "grok"])
        assert result is None

    def test_decide_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(iss, "system_one_decisions", fake_module)
        result = iss._classify_package("wp-1", {}, None, ["claude", "gpt4", "grok"])
        assert result is None

    def test_confident_answer_is_used(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "strategy": {"choice": "alternatives", "confidence": 0.9},
        }
        monkeypatch.setattr(iss, "system_one_decisions", fake_module)
        result = iss._classify_package("wp-1", {}, None, ["claude", "gpt4", "grok"])
        assert result == "alternatives"

    def test_low_confidence_answer_is_dropped(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "strategy": {"choice": "alternatives", "confidence": 0.2},
        }
        monkeypatch.setattr(iss, "system_one_decisions", fake_module)
        result = iss._classify_package("wp-1", {}, None, ["claude", "gpt4", "grok"])
        assert result is None

    def test_unknown_choice_is_dropped(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "strategy": {"choice": "rewrite_from_scratch", "confidence": 0.9},
        }
        monkeypatch.setattr(iss, "system_one_decisions", fake_module)
        result = iss._classify_package("wp-1", {}, None, ["claude", "gpt4", "grok"])
        assert result is None

    def test_vendor_count_is_passed_as_state_context(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(iss, "system_one_decisions", fake_module)
        iss._classify_package("wp-1", {"loc_estimate": 50}, None, ["claude", "gpt4"])
        state, _questions = fake_module.decide.call_args[0]
        assert state["available_vendor_count"] == 2


class TestSelectStrategiesJudgedOverride:
    def test_judged_answer_overrides_the_weighted_sum(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        """metadata scores below threshold, but a confident judgment wins."""
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-judged",
                "metadata": {
                    "loc_estimate": 400,
                    "alternatives_count": 0,
                    "package_kind": "crud",
                },
            },
        ])
        monkeypatch.setattr(
            iss, "_classify_package",
            lambda pkg_id, metadata, design_section, available_vendors: "alternatives",
        )
        result = iss.select_strategies(wp, available_vendors=["claude", "gpt4", "grok"])
        assert result["wp-judged"] == "alternatives"

    def test_unavailable_judgment_falls_back_to_weighted_sum(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-fallback",
                "metadata": {
                    "loc_estimate": 400,
                    "alternatives_count": 0,
                    "package_kind": "crud",
                },
            },
        ])
        monkeypatch.setattr(
            iss, "_classify_package",
            lambda pkg_id, metadata, design_section, available_vendors: None,
        )
        result = iss.select_strategies(wp, available_vendors=["claude", "gpt4", "grok"])
        assert result["wp-fallback"] == "lead_review"

    def test_vendor_scarcity_stays_reachable_via_unmodified_fallback(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        """design.md D1: no hard vendor gate -- the existing weighted-sum
        rule still reaches "alternatives" with only 2 vendors when the
        judgment is unavailable, exactly as it did before this item."""
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-scarce",
                "metadata": {
                    "loc_estimate": 150,
                    "alternatives_count": 2,
                    "package_kind": "crud",
                },
            },
        ])
        monkeypatch.setattr(
            iss, "_classify_package",
            lambda pkg_id, metadata, design_section, available_vendors: None,
        )
        result = iss.select_strategies(wp, available_vendors=["claude", "gpt4"])
        assert result["wp-scarce"] == "alternatives"

    def test_design_path_section_reaches_the_judgment(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-designed",
                "metadata": {"loc_estimate": 50},
            },
        ])
        design_path = tmp_path / "design.md"
        design_path.write_text("## wp-designed\n\nUse a state machine.\n")

        captured: dict = {}

        def _fake_classify(pkg_id, metadata, design_section, available_vendors):
            captured["design_section"] = design_section
            return None

        monkeypatch.setattr(iss, "_classify_package", _fake_classify)
        iss.select_strategies(
            wp, design_path=design_path,
            available_vendors=["claude", "gpt4", "grok"],
        )
        assert captured["design_section"] == "Use a state machine."

    def test_missing_design_path_passes_none_section(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        wp = _write_packages(tmp_path, [
            {"package_id": "wp-no-design", "metadata": {"loc_estimate": 50}},
        ])
        captured: dict = {}

        def _fake_classify(pkg_id, metadata, design_section, available_vendors):
            captured["design_section"] = design_section
            return None

        monkeypatch.setattr(iss, "_classify_package", _fake_classify)
        iss.select_strategies(wp, available_vendors=["claude", "gpt4", "grok"])
        assert captured["design_section"] is None
