"""Detector tests for context-impact inference (ri-08).

The library layer never shells out to git, so everything here runs on literal
file lists with no repository present.
"""

from __future__ import annotations

import pytest
from wp_fixtures import SURFACES, minimal_package

import context_impact
from context_impact import (
    ContextImpactRulesError,
    declared_surfaces,
    index_scopes,
    infer_surfaces,
    load_rules,
)

# One representative path per surface. If a rule table edit stops classifying
# any of these, that surface has silently lost its detector.
REPRESENTATIVE = {
    "capabilities": "openspec/specs/skill-workflow/spec.md",
    "apis": "openspec/contracts/phase-record/schemas/record.schema.json",
    "architecture": "docs/architecture-analysis/architecture.json",
    "decisions": "docs/decisions/2026-07-25-some-decision.md",
    "documentation": "docs/guides/workflow.md",
    "semantic_code": "agent-coordinator/src/service.py",
}


@pytest.fixture(scope="module")
def rules():
    return load_rules()


class TestRuleTableIntegrity:
    def test_every_surface_has_at_least_one_rule(self, rules):
        missing = [s for s in SURFACES if not rules.globs_for(s)]
        assert not missing, f"surfaces with no detector rule: {missing}"

    def test_no_rule_names_an_unknown_surface(self, rules):
        assert set(rules.surfaces()) <= set(SURFACES)

    def test_surfaces_constant_matches_the_schema_enum(self):
        assert tuple(context_impact.SURFACES) == SURFACES

    def test_an_unknown_surface_in_the_table_fails_loading(self, tmp_path):
        bad = tmp_path / "rules.yaml"
        bad.write_text(
            "schema_version: 1\nrules:\n  - surface: telemetry\n    globs: ['**/*.py']\n"
        )
        with pytest.raises(ContextImpactRulesError, match="telemetry"):
            load_rules(bad)

    def test_a_missing_rule_file_raises_rather_than_yielding_no_rules(self, tmp_path):
        with pytest.raises(ContextImpactRulesError, match="not found"):
            load_rules(tmp_path / "absent.yaml")

    def test_a_rule_without_globs_fails_loading(self, tmp_path):
        bad = tmp_path / "rules.yaml"
        bad.write_text("schema_version: 1\nrules:\n  - surface: apis\n    globs: []\n")
        with pytest.raises(ContextImpactRulesError, match="apis"):
            load_rules(bad)


class TestInference:
    @pytest.mark.parametrize("surface,path", sorted(REPRESENTATIVE.items()))
    def test_each_surface_is_inferred_from_a_representative_path(
        self, rules, surface, path
    ):
        package = minimal_package(
            scope={"write_allow": ["**"], "read_allow": ["**"]}
        )
        implied = infer_surfaces(package, [path], rules)
        assert surface in implied, f"{path} should imply {surface}, got {sorted(implied)}"
        assert path in implied[surface]

    def test_changed_files_outside_write_allow_are_ignored(self, rules):
        package = minimal_package(
            scope={"write_allow": ["agent-coordinator/**"], "read_allow": ["**"]}
        )
        implied = infer_surfaces(package, ["docs/guides/workflow.md"], rules)
        assert "documentation" not in implied

    def test_changed_files_inside_write_allow_are_counted(self, rules):
        package = minimal_package(
            scope={"write_allow": ["docs/**"], "read_allow": ["**"]}
        )
        implied = infer_surfaces(package, ["docs/guides/workflow.md"], rules)
        assert "documentation" in implied

    def test_denied_paths_are_excluded_even_when_write_allowed(self, rules):
        package = minimal_package(
            scope={
                "write_allow": ["docs/**"],
                "read_allow": ["**"],
                "deny": ["docs/decisions/**"],
            }
        )
        implied = infer_surfaces(
            package, ["docs/decisions/2026-07-25-some-decision.md"], rules
        )
        assert "decisions" not in implied

    def test_a_contract_file_implies_apis(self, rules):
        package = minimal_package(
            scope={"write_allow": ["contracts/**"], "read_allow": ["**"]}
        )
        implied = infer_surfaces(
            package,
            ["contracts/openapi/v1.yaml"],
            rules,
            contract_files=["contracts/openapi/v1.yaml"],
        )
        assert "apis" in implied

    def test_a_contract_file_outside_write_allow_does_not_imply_apis(self, rules):
        package = minimal_package(
            scope={"write_allow": ["docs/**"], "read_allow": ["**"]}
        )
        implied = infer_surfaces(
            package,
            ["contracts/openapi/v1.yaml"],
            rules,
            contract_files=["contracts/openapi/v1.yaml"],
        )
        assert "apis" not in implied

    def test_no_changed_files_implies_nothing(self, rules):
        package = minimal_package(scope={"write_allow": ["**"], "read_allow": ["**"]})
        assert infer_surfaces(package, [], rules) == {}

    def test_one_file_may_imply_several_surfaces(self, rules):
        package = minimal_package(scope={"write_allow": ["**"], "read_allow": ["**"]})
        implied = infer_surfaces(package, ["docs/decisions/2026-07-25-x.md"], rules)
        assert {"decisions", "documentation"} <= set(implied)


class TestDeclaredSurfaces:
    def test_a_package_without_the_block_declares_nothing(self):
        assert declared_surfaces(minimal_package()) is None

    def test_an_empty_list_is_a_declaration_not_an_absence(self):
        package = minimal_package(context_impact={"surfaces": []})
        assert declared_surfaces(package) == frozenset()

    def test_declared_surfaces_are_returned(self):
        package = minimal_package(context_impact={"surfaces": ["apis", "documentation"]})
        assert declared_surfaces(package) == frozenset({"apis", "documentation"})


class TestIndexScopes:
    def test_read_allow_and_deny_are_returned(self):
        package = minimal_package(
            scope={
                "write_allow": ["src/**"],
                "read_allow": ["src/**", "contracts/**"],
                "deny": ["src/secrets/**"],
            }
        )
        scopes = index_scopes(package)
        assert scopes.read_allow == ("src/**", "contracts/**")
        assert scopes.deny == ("src/secrets/**",)

    def test_a_path_matching_both_resolves_denied(self):
        package = minimal_package(
            scope={
                "write_allow": ["src/**"],
                "read_allow": ["src/**"],
                "deny": ["src/secrets/**"],
            }
        )
        scopes = index_scopes(package)
        assert scopes.allows("src/app.py")
        assert not scopes.allows("src/secrets/key.py")

    def test_a_path_outside_read_allow_is_not_allowed(self):
        package = minimal_package(
            scope={"write_allow": ["src/**"], "read_allow": ["src/**"]}
        )
        assert not index_scopes(package).allows("docs/guide.md")

    def test_missing_deny_defaults_to_empty(self):
        package = minimal_package(
            scope={"write_allow": ["src/**"], "read_allow": ["src/**"]}
        )
        assert index_scopes(package).deny == ()
