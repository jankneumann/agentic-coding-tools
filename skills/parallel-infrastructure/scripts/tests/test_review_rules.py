"""Tests for path-glob rule resolution (review_rules.py)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import review_rules as rr  # noqa: E402


class TestLoadConfigNoProjectFile:
    def test_falls_back_to_embedded_default(self, tmp_path: Path) -> None:
        config = rr.load_config(tmp_path)
        assert config.default_rules  # the real embedded sidecar has entries
        assert config.project_rules == []

    def test_no_repo_root_still_loads_default(self) -> None:
        config = rr.load_config(None)
        assert config.default_rules


class TestLoadConfigWithProjectFile:
    def test_project_rules_and_default_rules_both_present(self, tmp_path: Path) -> None:
        (tmp_path / ".review-rules.json").write_text(
            json.dumps({
                "schema_version": 1,
                "rules": [{"path": "special/**", "rule": "Special handling."}],
            })
        )
        config = rr.load_config(tmp_path)
        assert config.project_rules == [("special/**", "Special handling.")]
        assert config.default_rules  # still loaded, not replaced

    def test_project_include_overrides_default_include(self, tmp_path: Path) -> None:
        (tmp_path / ".review-rules.json").write_text(
            json.dumps({"schema_version": 1, "include": ["custom/**"], "rules": []})
        )
        config = rr.load_config(tmp_path)
        assert config.include == ["custom/**"]

    def test_project_omitting_a_key_inherits_the_default(self, tmp_path: Path) -> None:
        (tmp_path / ".review-rules.json").write_text(
            json.dumps({"schema_version": 1, "rules": []})
        )
        default_config = rr.load_config(None)
        project_config = rr.load_config(tmp_path)
        assert project_config.generated_paths == default_config.generated_paths

    def test_malformed_project_file_falls_back_to_default_only(self, tmp_path: Path) -> None:
        (tmp_path / ".review-rules.json").write_text("{not valid json")
        config = rr.load_config(tmp_path)
        assert config.project_rules == []
        assert config.default_rules


class TestResolveRule:
    def test_project_rule_outranks_default_for_the_same_pattern(self, tmp_path: Path) -> None:
        config = rr.RuleConfig(
            project_rules=[("**/*.py", "Project-specific Python rule.")],
            default_rules=[("**/*.py", "Default Python rule.")],
        )
        match = rr.resolve_rule("src/foo.py", config)
        assert match.source == "project"
        assert match.text == "Project-specific Python rule."

    def test_falls_through_to_default_when_project_has_no_match(self) -> None:
        config = rr.RuleConfig(
            project_rules=[("**/*.md", "Markdown rule.")],
            default_rules=[("**/*.py", "Default Python rule.")],
        )
        match = rr.resolve_rule("src/foo.py", config)
        assert match.source == "default"
        assert match.text == "Default Python rule."

    def test_declaration_order_first_match_wins(self) -> None:
        config = rr.RuleConfig(
            default_rules=[
                ("**/*.py", "General Python rule."),
                ("skills/**/*.py", "Skills-specific Python rule."),
            ]
        )
        match = rr.resolve_rule("skills/foo/bar.py", config)
        assert match.text == "General Python rule."
        assert match.pattern == "**/*.py"

    def test_no_match_falls_back_to_default_text(self) -> None:
        config = rr.RuleConfig(default_rules=[("**/*.py", "Python rule.")])
        match = rr.resolve_rule("README.md", config)
        assert match.source == "default"
        assert match.pattern == "(default)"
        assert match.text == rr.DEFAULT_RULE_TEXT

    def test_case_insensitive_matching(self) -> None:
        config = rr.RuleConfig(default_rules=[("**/*.py", "Python rule.")])
        match = rr.resolve_rule("SRC/FOO.PY", config)
        assert match.text == "Python rule."


class TestGroupFilesByRule:
    def test_files_sharing_a_rule_are_grouped(self) -> None:
        config = rr.RuleConfig(default_rules=[("**/*.py", "Python rule.")])
        groups = rr.group_files_by_rule(["a.py", "b.py", "c.py"], config)
        assert len(groups) == 1
        assert groups[0].files == ["a.py", "b.py", "c.py"]
        assert groups[0].text == "Python rule."

    def test_files_with_different_rules_get_separate_groups(self) -> None:
        config = rr.RuleConfig(
            default_rules=[
                ("**/*.py", "Python rule."),
                ("**/*.md", "Markdown rule."),
            ]
        )
        groups = rr.group_files_by_rule(["a.py", "readme.md"], config)
        assert len(groups) == 2
        assert groups[0].pattern == "**/*.py"
        assert groups[1].pattern == "**/*.md"

    def test_group_ids_are_sequential(self) -> None:
        config = rr.RuleConfig(
            default_rules=[
                ("**/*.py", "Python rule."),
                ("**/*.md", "Markdown rule."),
            ]
        )
        groups = rr.group_files_by_rule(["a.py", "readme.md"], config)
        assert [g.group_id for g in groups] == [1, 2]

    def test_to_dict_shape(self) -> None:
        config = rr.RuleConfig(default_rules=[("**/*.py", "Python rule.")])
        groups = rr.group_files_by_rule(["a.py"], config)
        d = groups[0].to_dict()
        assert set(d.keys()) == {"group_id", "source", "pattern", "files"}
        assert "text" not in d  # rendered separately, not part of the metadata contract

    def test_no_project_file_uses_only_default_groups(self, tmp_path: Path) -> None:
        config = rr.load_config(tmp_path)
        groups = rr.group_files_by_rule(["agent-coordinator/agents.yaml"], config)
        assert len(groups) == 1
        assert groups[0].source == "default"


class TestEmbeddedDefaultSidecar:
    def test_sidecar_file_is_valid_json_with_rules(self) -> None:
        doc = json.loads(rr.DEFAULT_RULES_PATH.read_text())
        assert doc["schema_version"] == 1
        assert len(doc["rules"]) > 0

    def test_sidecar_matches_its_install_assets_mirror(self) -> None:
        mirror = (
            SCRIPTS_DIR.parent
            / "install_assets" / "openspec" / "schemas" / "review-rules.json"
        )
        assert rr.DEFAULT_RULES_PATH.read_text() == mirror.read_text()

    def test_skill_md_rule_resolves(self) -> None:
        config = rr.load_config(None)
        match = rr.resolve_rule("skills/parallel-infrastructure/SKILL.md", config)
        assert match.source == "default"
        assert match.pattern != "(default)"
