"""Map loading, fail-closed validation and owner resolution (design D3, D4, D5, D6, D13)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from owners import (
    OwnershipConfigError,
    OwnershipContext,
    OwnerSet,
    load_ownership,
    pattern_matches,
)

MakeRepo = Callable[..., Path]

JAN = {"display_name": "Jan Neumann", "github": "jankneumann"}
KIM = {"display_name": "Kim Lee", "github": "kimlee"}
TWO = {"jan": JAN, "kim": KIM}


def ids(principals: tuple[Any, ...]) -> list[str]:
    return [p.id for p in principals]


def owners_doc(**assignments: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {"schema_version": 1, "default_owner": "jan"}
    if assignments:
        doc["assignments"] = assignments
    return doc


# --------------------------------------------------------------------------- loading


class TestLoading:
    def test_minimal_map_loads(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, owners=owners_doc())
        ctx = load_ownership(repo)
        assert isinstance(ctx, OwnershipContext)
        assert ctx.default_owner is not None and ctx.default_owner.id == "jan"
        assert ctx.has_map is True

    def test_missing_default_owner_rejected(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, owners={"schema_version": 1})
        with pytest.raises(OwnershipConfigError, match="default_owner"):
            load_ownership(repo)

    def test_unparseable_map_rejected(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, owners="default_owner: [unclosed\n")
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "invalid_map"

    def test_unknown_assignment_key_names_the_path(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            owners=owners_doc(capabilities={"x": {"owners": ["jan"], "reviewers": ["jan"]}}),
        )
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "invalid_map"
        assert "reviewers" in str(excinfo.value)
        assert "assignments" in str(excinfo.value)

    def test_unregistered_owner_fails_closed(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            owners=owners_doc(capabilities={"agent-identity": {"owners": ["nobody"]}}),
        )
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "unknown_owner"
        assert excinfo.value.subject == "nobody"
        assert "agent-identity" in str(excinfo.value)

    def test_unregistered_default_owner_fails_closed(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"kim": KIM}, owners=owners_doc())
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "unknown_owner"
        assert excinfo.value.subject == "jan"

    def test_agent_named_as_owner_rejected(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            agents=["claude-local"],
            owners=owners_doc(capabilities={"x": {"owners": ["claude-local"]}}),
        )
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "agent_as_owner"
        assert "human" in str(excinfo.value)

    def test_agent_as_default_owner_rejected(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            agents=["claude-local"],
            owners={"schema_version": 1, "default_owner": "claude-local"},
        )
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "agent_as_owner"

    def test_unsupported_glob_syntax_rejected(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN}, owners=owners_doc(paths={"!docs/**": {"owners": ["jan"]}})
        )
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "invalid_map"
        assert "`**`" in str(excinfo.value) or "pattern" in str(excinfo.value)

    def test_embedded_double_star_rejected(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            owners=owners_doc(paths={"openspec/spec**s/": {"owners": ["jan"]}}),
        )
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "invalid_map"
        assert "whole path segment" in str(excinfo.value)

    def test_registry_escape_rejected_by_schema(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            owners={**owners_doc(), "registry": "../other-repo/agents.yaml"},
        )
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code in {"invalid_map", "registry_outside_repo"}

    def test_registry_symlink_escape_rejected(self, make_repo: MakeRepo, tmp_path: Path) -> None:
        repo = make_repo(owners={**owners_doc(), "registry": "link.yaml"})
        outside = tmp_path / "outside.yaml"
        outside.write_text("humans: {jan: {display_name: Jan}}\n", encoding="utf-8")
        (repo / "link.yaml").symlink_to(outside)
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "registry_outside_repo"

    def test_registry_field_selects_registry(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            registry="config/people.yaml",
            owners={**owners_doc(), "registry": "config/people.yaml"},
        )
        assert load_ownership(repo).default_owner is not None

    def test_consumer_repository_registry_at_root(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, registry="agents.yaml")
        ctx = load_ownership(repo)
        owner_set = ctx.resolve_capability("anything")
        assert ids(owner_set.owners) == ["jan"]
        assert owner_set.source == "solo"

    def test_repo_root_defaults_to_git_toplevel(
        self, make_repo: MakeRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = make_repo(humans={"jan": JAN}, owners=owners_doc())
        nested = repo / "deep" / "dir"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        assert load_ownership().repo_root == repo.resolve()


# --------------------------------------------------------------------------- resolution


class TestCapabilityAndRoadmapResolution:
    def test_explicit_capability_with_distinct_acceptance(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=owners_doc(
                capabilities={"agent-identity": {"owners": ["jan"], "acceptance_rights": ["kim"]}}
            ),
        )
        result = load_ownership(repo).resolve_capability("agent-identity")
        assert isinstance(result, OwnerSet)
        assert ids(result.owners) == ["jan"]
        assert ids(result.decision_rights) == ["jan"]
        assert ids(result.acceptance_rights) == ["kim"]
        assert result.source == "explicit"
        assert result.matched_rule == "agent-identity"

    def test_unassigned_capability_falls_back_to_default(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=owners_doc())
        result = load_ownership(repo).resolve_capability("model-routing")
        assert ids(result.owners) == ["jan"]
        assert result.source == "default_owner"
        assert result.matched_rule is None

    def test_roadmap_item_explicit_and_fallback(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=owners_doc(
                roadmap_items={"multiplayer-collaboration/ri-02": {"owners": ["kim"]}}
            ),
        )
        ctx = load_ownership(repo)
        explicit = ctx.resolve_roadmap_item("multiplayer-collaboration", "ri-02")
        assert ids(explicit.owners) == ["kim"]
        assert explicit.source == "explicit"
        fallback = ctx.resolve_roadmap_item("multiplayer-collaboration", "ri-03")
        assert ids(fallback.owners) == ["jan"]
        assert fallback.source == "default_owner"

    def test_resolver_never_returns_an_empty_owner_set(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=owners_doc())
        ctx = load_ownership(repo)
        for result in (
            ctx.resolve_capability("x"),
            ctx.resolve_roadmap_item("r", "i"),
            ctx.resolve_path("a/b.txt"),
        ):
            assert result.owners and all(p.kind == "human" for p in result.owners)


class TestPathResolution:
    def test_default_fallback(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=owners_doc())
        result = load_ownership(repo).resolve_path("src/x.py")
        assert ids(result.owners) == ["jan"]
        assert result.source == "default_owner"
        assert result.matched_rule is None

    def test_most_specific_rule_wins(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=owners_doc(
                paths={
                    "openspec/contracts/**": {"owners": ["jan"]},
                    "openspec/contracts/agent-coordinator/**": {"owners": ["kim"]},
                }
            ),
        )
        result = load_ownership(repo).resolve_path(
            "openspec/contracts/agent-coordinator/openapi/v1.yaml"
        )
        assert ids(result.owners) == ["kim"]
        assert result.matched_rule == "openspec/contracts/agent-coordinator/**"
        assert result.source == "explicit"

    def test_specificity_is_independent_of_file_order(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=owners_doc(
                paths={
                    "openspec/contracts/agent-coordinator/**": {"owners": ["kim"]},
                    "openspec/contracts/**": {"owners": ["jan"]},
                }
            ),
        )
        result = load_ownership(repo).resolve_path("openspec/contracts/agent-coordinator/x.yaml")
        assert ids(result.owners) == ["kim"]

    def test_equal_specificity_resolved_by_file_order(self, make_repo: MakeRepo) -> None:
        # Same literal-prefix length (docs/) and same pattern length (6), both match.
        repo = make_repo(
            humans=TWO,
            owners=owners_doc(paths={"docs/*.a": {"owners": ["jan"]}, "docs/?.a": {"owners": ["kim"]}}),
        )
        assert ids(load_ownership(repo).resolve_path("docs/x.a").owners) == ["kim"]
        repo2 = make_repo(
            humans=TWO,
            owners=owners_doc(paths={"docs/?.a": {"owners": ["kim"]}, "docs/*.a": {"owners": ["jan"]}}),
        )
        assert ids(load_ownership(repo2).resolve_path("docs/x.a").owners) == ["jan"]

    def test_capability_assignment_governs_spec_and_contract_paths(
        self, make_repo: MakeRepo
    ) -> None:
        repo = make_repo(
            humans=TWO, owners=owners_doc(capabilities={"agent-identity": {"owners": ["kim"]}})
        )
        ctx = load_ownership(repo)
        for path in (
            "openspec/specs/agent-identity/spec.md",
            "openspec/contracts/agent-identity/schemas/x.json",
        ):
            result = ctx.resolve_path(path)
            assert ids(result.owners) == ["kim"], path
            assert result.source == "explicit"
            assert result.matched_rule == "capability:agent-identity"
        other = ctx.resolve_path("openspec/specs/agent-identity-extra/spec.md")
        assert other.source == "default_owner"

    def test_explicit_path_rule_overrides_implied_capability_rule(
        self, make_repo: MakeRepo
    ) -> None:
        repo = make_repo(
            humans=TWO,
            owners=owners_doc(
                capabilities={"agent-identity": {"owners": ["kim"]}},
                paths={"openspec/specs/agent-identity/": {"owners": ["jan"]}},
            ),
        )
        result = load_ownership(repo).resolve_path("openspec/specs/agent-identity/spec.md")
        assert ids(result.owners) == ["jan"]
        assert result.matched_rule == "openspec/specs/agent-identity/"

    def test_more_specific_explicit_rule_beats_implied_rule(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=owners_doc(
                capabilities={"agent-identity": {"owners": ["kim"]}},
                paths={"openspec/specs/agent-identity/secret/**": {"owners": ["jan"]}},
            ),
        )
        ctx = load_ownership(repo)
        assert ids(ctx.resolve_path("openspec/specs/agent-identity/secret/a.md").owners) == ["jan"]
        assert ids(ctx.resolve_path("openspec/specs/agent-identity/spec.md").owners) == ["kim"]

    def test_single_segment_directory_rule_matches_at_any_depth(
        self, make_repo: MakeRepo
    ) -> None:
        unanchored = make_repo(
            humans=TWO, owners=owners_doc(paths={"schemas/": {"owners": ["kim"]}})
        )
        result = load_ownership(unanchored).resolve_path("openspec/schemas/owners.schema.json")
        assert ids(result.owners) == ["kim"]
        assert result.matched_rule == "schemas/"
        anchored = make_repo(
            humans=TWO, owners=owners_doc(paths={"/schemas/": {"owners": ["kim"]}})
        )
        result = load_ownership(anchored).resolve_path("openspec/schemas/owners.schema.json")
        assert result.source == "default_owner"

    def test_path_is_normalised(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=owners_doc(paths={"docs/**": {"owners": ["kim"]}}))
        ctx = load_ownership(repo)
        assert ids(ctx.resolve_path("./docs/a.md").owners) == ["kim"]
        assert ids(ctx.resolve_path("/docs/a.md").owners) == ["kim"]


MATCH_TABLE = [
    # (pattern, path, expected)
    ("*.md", "README.md", True),
    ("*.md", "docs/a/b.md", True),
    ("*.md", "README.txt", False),
    ("README.md", "README.md", True),
    ("README.md", "x/README.md", True),
    ("README.md", "xREADME.md", False),
    ("docs/*.md", "docs/a.md", True),
    ("docs/*.md", "docs/x/a.md", False),
    ("docs/*.md", "x/docs/a.md", False),
    ("/README.md", "README.md", True),
    ("/README.md", "x/README.md", False),
    ("schemas/", "schemas/a.json", True),
    ("schemas/", "openspec/schemas/a.json", True),
    ("schemas/", "myschemas/a.json", False),
    ("schemas/", "schemas", False),
    ("/schemas/", "schemas/a.json", True),
    ("/schemas/", "openspec/schemas/a.json", False),
    ("openspec/specs/x/", "openspec/specs/x/spec.md", True),
    ("openspec/specs/x/", "openspec/specs/x/a/b.md", True),
    ("openspec/specs/x/", "openspec/specs/xy/spec.md", False),
    ("openspec/specs/x/", "a/openspec/specs/x/spec.md", False),
    ("a/**", "a/b", True),
    ("a/**", "a/b/c", True),
    ("a/**", "a", False),
    ("**/foo", "foo", True),
    ("**/foo", "a/b/foo", True),
    ("**/foo", "a/foobar", False),
    ("a/**/b", "a/b", True),
    ("a/**/b", "a/x/b", True),
    ("a/**/b", "a/x/y/b", True),
    ("a/**/b", "a/xb", False),
    ("a/*", "a/b", True),
    ("a/*", "a/b/c", False),
    ("docs/*", "docs/getting-started.md", True),
    ("docs/*", "docs/build-app/troubleshooting.md", False),
    ("*", "a/b/c", True),
    ("a?.md", "ab.md", True),
    ("a?.md", "abc.md", False),
    ("docs/guide", "docs/guide/x.md", True),
    ("docs/guide", "docs/guide2/x.md", False),
]


@pytest.mark.parametrize(("pattern", "path", "expected"), MATCH_TABLE)
def test_matching_table(pattern: str, path: str, expected: bool) -> None:
    assert pattern_matches(pattern, path) is expected


def test_embedded_double_star_has_no_matcher() -> None:
    with pytest.raises(OwnershipConfigError, match="whole path segment"):
        pattern_matches("a/b**c", "a/bxc")


# --------------------------------------------------------------------------- solo / mode


class TestSoloAndMode:
    def test_single_declared_human_is_sole_principal(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN})
        ctx = load_ownership(repo)
        assert ctx.mode == "solo"
        assert ctx.has_map is False
        for result in (
            ctx.resolve_capability("anything"),
            ctx.resolve_roadmap_item("r", "i"),
            ctx.resolve_path("a/b"),
        ):
            assert ids(result.owners) == ["jan"]
            assert ids(result.decision_rights) == ["jan"]
            assert ids(result.acceptance_rights) == ["jan"]
            assert result.source == "solo"

    def test_git_identity_derived_when_registry_has_no_humans(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={}, git_email="dev@example.org")
        result = load_ownership(repo).resolve_capability("anything")
        assert ids(result.owners) == ["git:dev@example.org"]
        assert result.owners[0].source == "git-config"

    def test_sentinel_when_no_identity_available(self, make_repo: MakeRepo) -> None:
        repo = make_repo()
        result = load_ownership(repo).resolve_capability("anything")
        assert ids(result.owners) == ["repository-default"]
        assert result.owners[0].source == "sentinel"
        assert result.source == "solo"

    def test_no_git_checkout_still_resolves(self, make_repo: MakeRepo) -> None:
        repo = make_repo(git=False)
        assert ids(load_ownership(repo).resolve_path("a").owners) == ["repository-default"]

    def test_one_principal_repository_with_map_stays_solo(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            owners=owners_doc(capabilities={"agent-identity": {"owners": ["jan"]}}),
        )
        ctx = load_ownership(repo)
        assert ctx.mode == "solo"
        assert ctx.resolve_capability("agent-identity").source == "explicit"
        assert ctx.resolve_capability("other").source == "default_owner"

    def test_two_humans_with_map_is_team(self, make_repo: MakeRepo) -> None:
        assert load_ownership(make_repo(humans=TWO, owners=owners_doc())).mode == "team"

    def test_team_registry_without_map_raises(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO)
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_ownership(repo)
        assert excinfo.value.code == "team_registry_without_map"
        assert "openspec/owners.yaml" in str(excinfo.value)
        assert "default_owner" in str(excinfo.value)


# --------------------------------------------------------------------------- performance


def test_performance_budget(make_repo: MakeRepo) -> None:
    """200-rule map, 1,000 resolutions. Design budget 250 ms; asserted at 4x for CI variance."""
    paths = {f"area{i}/sub{i}/**": {"owners": ["jan" if i % 2 else "kim"]} for i in range(200)}
    repo = make_repo(humans=TWO, owners=owners_doc(paths=paths))
    ctx = load_ownership(repo)
    started = time.perf_counter()
    for i in range(1000):
        ctx.resolve_path(f"area{i % 250}/sub{i % 250}/dir/file{i}.py")
    assert time.perf_counter() - started < 1.0


def test_paths_with_newlines_still_match() -> None:
    assert pattern_matches("docs/**", "docs/a\nb.md") is True
    assert pattern_matches("*.md", "weird\nname.md") is True
