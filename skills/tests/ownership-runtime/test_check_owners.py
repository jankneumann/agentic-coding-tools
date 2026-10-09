"""The ownership check: error/warning/info semantics, exit codes and --json (design D9, D14)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from check_owners import CODES, check, exit_code, main

MakeRepo = Callable[..., Path]

JAN = {"display_name": "Jan Neumann", "github": "jankneumann"}
KIM = {"display_name": "Kim Lee", "github": "kimlee"}
TWO = {"jan": JAN, "kim": KIM}


def doc(**assignments: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"schema_version": 1, "default_owner": "jan"}
    if assignments:
        out["assignments"] = assignments
    return out


def codes(report: dict[str, Any]) -> list[str]:
    return [f["code"] for f in report["findings"]]


def finding(report: dict[str, Any], code: str) -> dict[str, Any]:
    matches = [f for f in report["findings"] if f["code"] == code]
    assert matches, f"no {code} finding in {report['findings']}"
    return matches[0]


class TestAdvisoryFindingsInTeamMode:
    def test_unowned_capability_reported_as_warning(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc(), specs=["model-routing"])
        report = check(repo)
        f = finding(report, "unowned_capability")
        assert f["severity"] == "warning"
        assert f["subject"] == "model-routing"
        assert exit_code(report, strict=False) == 0
        assert exit_code(report, strict=True) == 1

    def test_assigned_capability_not_reported(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=doc(capabilities={"model-routing": {"owners": ["kim"]}}),
            specs=["model-routing"],
        )
        assert "unowned_capability" not in codes(check(repo))

    def test_unowned_roadmap_item_reported(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=doc(roadmap_items={"r1/i1": {"owners": ["kim"]}}),
            roadmaps={"r1": ["i1", "i2"]},
        )
        subjects = [f["subject"] for f in check(repo)["findings"] if f["code"] == "unowned_roadmap_item"]
        assert subjects == ["r1/i2"]

    def test_archived_roadmaps_are_excluded(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc(), archived_roadmaps={"old": ["x"]})
        assert "unowned_roadmap_item" not in codes(check(repo))


class TestSoloModeSuppression:
    def test_solo_mode_emits_no_unowned_findings(self, make_repo: MakeRepo) -> None:
        specs = [f"cap-{i}" for i in range(40)]
        repo = make_repo(
            humans={"jan": JAN},
            owners=doc(),
            specs=specs,
            roadmaps={"r1": ["i1", "i2"]},
        )
        report = check(repo)
        assert report["mode"] == "solo"
        assert not {"unowned_capability", "unowned_roadmap_item"} & set(codes(report))
        assert exit_code(report, strict=True) == 0
        assert report["findings"] == []


class TestDanglingKeys:
    def test_dangling_capability_reported_in_every_mode(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            owners=doc(capabilities={"agent-identiy": {"owners": ["jan"]}}),
            specs=["agent-identity"],
        )
        f = finding(check(repo), "unknown_capability")
        assert f["severity"] == "warning"
        assert f["subject"] == "agent-identiy"

    def test_dangling_roadmap_item_reported(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            owners=doc(roadmap_items={"r1/i9": {"owners": ["jan"]}}),
            roadmaps={"r1": ["i1"]},
        )
        assert finding(check(repo), "unknown_roadmap_item")["subject"] == "r1/i9"

    def test_roadmap_item_in_archived_roadmap_is_dangling(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            owners=doc(roadmap_items={"old/x": {"owners": ["jan"]}}),
            archived_roadmaps={"old": ["x"]},
        )
        assert finding(check(repo), "unknown_roadmap_item")["subject"] == "old/x"

    def test_path_keys_are_not_checked_for_existence(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN}, owners=doc(paths={"does/not/exist/yet/**": {"owners": ["jan"]}})
        )
        assert check(repo)["findings"] == []


class TestErrors:
    def test_unregistered_owner(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN}, owners=doc(capabilities={"agent-identity": {"owners": ["nobody"]}})
        )
        report = check(repo)
        f = finding(report, "unknown_owner")
        assert (f["severity"], f["subject"]) == ("error", "nobody")
        assert exit_code(report, strict=False) == 1

    def test_agent_as_owner(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            agents=["claude-local"],
            owners=doc(capabilities={"x": {"owners": ["claude-local"]}}),
        )
        f = finding(check(repo), "agent_as_owner")
        assert f["severity"] == "error"
        assert f["subject"] == "claude-local"

    def test_every_bad_owner_is_reported_not_just_the_first(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN},
            owners=doc(capabilities={"a": {"owners": ["x1"]}, "b": {"owners": ["x2"]}}),
        )
        subjects = [f["subject"] for f in check(repo)["findings"] if f["code"] == "unknown_owner"]
        assert subjects == ["x1", "x2"]

    def test_invalid_map(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, owners={"schema_version": 1})
        report = check(repo)
        assert finding(report, "invalid_map")["severity"] == "error"
        assert "default_owner" in finding(report, "invalid_map")["message"]

    def test_team_registry_without_map(self, make_repo: MakeRepo) -> None:
        report = check(make_repo(humans=TWO))
        f = finding(report, "team_registry_without_map")
        assert f["severity"] == "error"
        assert "openspec/owners.yaml" in f["message"]
        assert "default_owner" in f["message"]
        assert exit_code(report, strict=False) == 1

    def test_registry_outside_repo(self, make_repo: MakeRepo, tmp_path: Path) -> None:
        repo = make_repo(owners={**doc(), "registry": "link.yaml"})
        outside = tmp_path / "outside.yaml"
        outside.write_text("humans: {jan: {display_name: Jan}}\n", encoding="utf-8")
        (repo / "link.yaml").symlink_to(outside)
        assert finding(check(repo), "registry_outside_repo")["severity"] == "error"

    def test_invalid_registry(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": {"github": "jankneumann"}}, owners=doc())
        assert finding(check(repo), "invalid_registry")["severity"] == "error"


class TestSentinel:
    def test_sentinel_principal_warning(self, make_repo: MakeRepo) -> None:
        report = check(make_repo())
        f = finding(report, "sentinel_principal")
        assert f["severity"] == "warning"
        assert exit_code(report, strict=False) == 0
        assert exit_code(report, strict=True) == 1

    def test_git_identity_is_not_a_sentinel(self, make_repo: MakeRepo) -> None:
        report = check(make_repo(git_email="dev@example.org"))
        assert report["findings"] == []


class TestExitCodes:
    def test_info_is_never_promoted(self) -> None:
        report = {"findings": [{"severity": "info", "code": "no_ownership_map", "subject": "", "message": ""}]}
        assert exit_code(report, strict=True) == 0

    def test_warning_promoted_only_when_strict(self) -> None:
        report = {"findings": [{"severity": "warning", "code": "unknown_capability", "subject": "x", "message": ""}]}
        assert exit_code(report, strict=False) == 0
        assert exit_code(report, strict=True) == 1

    def test_error_always_fails(self) -> None:
        report = {"findings": [{"severity": "error", "code": "unknown_owner", "subject": "x", "message": ""}]}
        assert exit_code(report, strict=False) == 1


class TestJsonContract:
    def test_every_emitted_code_is_in_the_d9_table(self, make_repo: MakeRepo, tmp_path: Path) -> None:
        scenarios = [
            make_repo(humans=TWO, owners=doc(), specs=["a"], roadmaps={"r": ["i"]}),
        ]
        for repo in scenarios:
            for f in check(repo)["findings"]:
                assert f["code"] in CODES
                assert f["severity"] in {"error", "warning", "info"}

    def test_codes_table_has_the_documented_codes(self) -> None:
        documented = {
            "invalid_map", "unknown_owner", "agent_as_owner", "team_registry_without_map",
            "registry_outside_repo", "missing_github_handle", "codeowners_disagreement",
            "not_a_git_checkout", "unowned_capability", "unowned_roadmap_item",
            "unknown_capability", "unknown_roadmap_item", "sentinel_principal",
            "codeowners_stale", "codeowners_missing", "orphan_managed_block", "no_ownership_map",
        }
        assert documented <= set(CODES)

    def test_json_shape_is_stable(
        self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = make_repo(humans=TWO, owners=doc(), specs=["model-routing"])
        rc = main(["--repo-root", str(repo), "--json"])
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert set(out) == {"schema_version", "mode", "strict", "exit_code", "findings"}
        assert out["schema_version"] == 1
        assert out["mode"] == "team"
        assert out["strict"] is False
        assert out["exit_code"] == 0
        assert set(out["findings"][0]) == {"severity", "code", "subject", "message"}

    def test_main_strict_exit_code(self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]) -> None:
        repo = make_repo(humans=TWO, owners=doc(), specs=["model-routing"])
        assert main(["--repo-root", str(repo), "--strict"]) == 1
        capsys.readouterr()

    def test_clean_repository_has_empty_findings(
        self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = make_repo(humans={"jan": JAN}, owners=doc())
        assert main(["--repo-root", str(repo), "--strict", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["findings"] == []
