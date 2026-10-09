"""Registry location, human reader, solo derivation and mode (design D5, D6, D10)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from principals import (
    OwnershipConfigError,
    derive_mode,
    derive_solo_principal,
    default_repo_root,
    load_human_principals,
    locate_registry,
)

MakeRepo = Callable[..., Path]


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


JAN = {"display_name": "Jan Neumann", "github": "jankneumann"}
KIM = {"display_name": "Kim Lee", "github": "kimlee"}


class TestLocateRegistry:
    def test_default_coordinator_location(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN})
        assert locate_registry(repo) == repo / "agent-coordinator" / "agents.yaml"

    def test_root_agents_yaml_is_the_fourth_location(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, registry="agents.yaml")
        assert locate_registry(repo) == repo / "agents.yaml"

    def test_coordinator_location_beats_root(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN})
        write_yaml(repo / "agents.yaml", {"humans": {"kim": KIM}})
        assert locate_registry(repo) == repo / "agent-coordinator" / "agents.yaml"

    def test_registry_field_beats_defaults(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN})
        write_yaml(repo / "config" / "people.yaml", {"humans": {"kim": KIM}})
        assert locate_registry(repo, registry_field="config/people.yaml") == (
            repo / "config" / "people.yaml"
        )

    def test_env_var_beats_registry_field(
        self, make_repo: MakeRepo, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        repo = make_repo(humans={"jan": JAN})
        elsewhere = tmp_path / "elsewhere.yaml"
        write_yaml(elsewhere, {"humans": {"kim": KIM}})
        write_yaml(repo / "config" / "people.yaml", {"humans": {"jan": JAN}})
        monkeypatch.setenv("OWNERSHIP_REGISTRY_PATH", str(elsewhere))
        # The environment variable is operator-controlled and not confined to the repo.
        assert locate_registry(repo, registry_field="config/people.yaml") == elsewhere

    def test_none_when_nothing_exists(self, make_repo: MakeRepo) -> None:
        assert locate_registry(make_repo()) is None

    def test_registry_field_escaping_repo_rejected(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN})
        with pytest.raises(OwnershipConfigError) as excinfo:
            locate_registry(repo, registry_field="../outside/agents.yaml")
        assert excinfo.value.code == "registry_outside_repo"

    def test_symlinked_default_escaping_repo_rejected(
        self, make_repo: MakeRepo, tmp_path: Path
    ) -> None:
        repo = make_repo()
        outside = tmp_path / "outside.yaml"
        write_yaml(outside, {"humans": {"kim": KIM}})
        (repo / "agents.yaml").symlink_to(outside)
        with pytest.raises(OwnershipConfigError) as excinfo:
            locate_registry(repo)
        assert excinfo.value.code == "registry_outside_repo"


class TestLoadHumanPrincipals:
    def test_reads_humans(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN, "kim": KIM})
        humans = load_human_principals(repo)
        assert [p.id for p in humans] == ["jan", "kim"]
        assert humans[0].kind == "human"
        assert humans[0].source == "registry"
        assert humans[0].github == "jankneumann"
        assert humans[0].display_name == "Jan Neumann"

    def test_only_humans_and_agent_keys_are_read(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            agents={"claude-local": {"trust_level": "not-an-int", "garbage": True}},
        )
        assert [p.id for p in load_human_principals(repo)] == ["jan"]

    def test_invalid_human_entry_raises(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": {"github": "jankneumann"}})
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_human_principals(repo)
        assert excinfo.value.code == "invalid_registry"
        assert "jan" in str(excinfo.value)
        assert "display_name" in str(excinfo.value)

    def test_agent_human_collision_raises(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"claude-local": JAN}, agents=["claude-local"])
        with pytest.raises(OwnershipConfigError, match="claude-local"):
            load_human_principals(repo)

    def test_no_registry_means_no_humans(self, make_repo: MakeRepo) -> None:
        assert load_human_principals(make_repo()) == []

    def test_unparseable_registry_raises(self, make_repo: MakeRepo) -> None:
        repo = make_repo()
        (repo / "agents.yaml").write_text("humans: [unclosed\n", encoding="utf-8")
        with pytest.raises(OwnershipConfigError) as excinfo:
            load_human_principals(repo)
        assert excinfo.value.code == "invalid_registry"

    def test_consumer_repository_registry_at_root(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, registry="agents.yaml")
        assert not (repo / "agent-coordinator").exists()
        assert [p.id for p in load_human_principals(repo)] == ["jan"]


class TestSoloDerivation:
    def test_single_declared_human_is_the_sole_principal(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, git_email="dev@example.org")
        principal = derive_solo_principal(repo, load_human_principals(repo))
        assert principal.id == "jan"
        assert principal.source == "registry"

    def test_git_identity_when_registry_has_no_humans(self, make_repo: MakeRepo) -> None:
        repo = make_repo(git_email="dev@example.org", git_name="Dev Eloper")
        principal = derive_solo_principal(repo, [])
        assert principal.id == "git:dev@example.org"
        assert principal.source == "git-config"
        assert principal.display_name == "Dev Eloper"
        assert principal.kind == "human"

    def test_git_identity_display_name_falls_back_to_email(self, make_repo: MakeRepo) -> None:
        repo = make_repo(git_email="dev@example.org")
        assert derive_solo_principal(repo, []).display_name == "dev@example.org"

    def test_registry_email_is_not_matched_against_git_email(self, make_repo: MakeRepo) -> None:
        # D5: no email matching. Two humans -> no sole principal is derived from git either.
        repo = make_repo(
            humans={"jan": {**JAN, "email": "dev@example.org"}, "kim": KIM},
            git_email="dev@example.org",
        )
        humans = load_human_principals(repo)
        principal = derive_solo_principal(repo, humans)
        assert principal.id == "git:dev@example.org"

    def test_sentinel_without_any_identity(self, make_repo: MakeRepo) -> None:
        repo = make_repo()
        principal = derive_solo_principal(repo, [])
        assert principal.id == "repository-default"
        assert principal.source == "sentinel"

    def test_sentinel_outside_a_git_checkout(self, make_repo: MakeRepo) -> None:
        repo = make_repo(git=False)
        assert derive_solo_principal(repo, []).source == "sentinel"


class TestMode:
    def test_zero_or_one_human_is_solo(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN})
        assert derive_mode(load_human_principals(repo)) == "solo"
        assert derive_mode([]) == "solo"

    def test_two_humans_is_team(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN, "kim": KIM})
        assert derive_mode(load_human_principals(repo)) == "team"


class TestDefaultRepoRoot:
    def test_defaults_to_git_toplevel(
        self, make_repo: MakeRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = make_repo()
        nested = repo / "a" / "b"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        assert default_repo_root() == repo.resolve()

    def test_falls_back_to_cwd_outside_git(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bare = tmp_path / "bare"
        bare.mkdir()
        monkeypatch.chdir(bare)
        assert default_repo_root() == bare.resolve()
