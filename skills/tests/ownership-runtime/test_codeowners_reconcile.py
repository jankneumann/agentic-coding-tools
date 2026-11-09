"""CODEOWNERS reconcile: probe set, last-match-wins matcher, disagreements, stale (design D8)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from check_owners import check, exit_code
from check_owners import main as check_main
from codeowners import (
    build_probes,
    main,
    parse_codeowners,
    reconcile,
    selected_handles,
    tracked_files,
)
from owners import load_ownership

MakeRepo = Callable[..., Path]

JAN = {"display_name": "Jan Neumann", "github": "jankneumann"}
KIM = {"display_name": "Kim Lee", "github": "kimlee"}
TWO = {"jan": JAN, "kim": KIM}


def doc(**assignments: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"schema_version": 1, "default_owner": "jan"}
    if assignments:
        out["assignments"] = assignments
    return out


def track(repo: Path, *files: str) -> None:
    import subprocess

    for rel in files:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)


def emit_write(repo: Path) -> None:
    assert main(["emit", "--repo-root", str(repo), "--write"]) == 0
    track(repo)


def finding_codes(report: dict[str, Any]) -> list[str]:
    return [f["code"] for f in report["findings"]]


class TestTrackedFiles:
    @pytest.mark.parametrize(
        "failure",
        [subprocess.TimeoutExpired(["git", "ls-files"], 60), OSError("git binary missing")],
        ids=["timeout", "oserror"],
    )
    def test_git_failure_yields_no_tracked_files(
        self, make_repo: MakeRepo, monkeypatch: pytest.MonkeyPatch, failure: Exception
    ) -> None:
        """A hung or missing ``git`` is handled like a non-zero exit, as ``principals._git`` does."""
        import codeowners

        repo = make_repo(humans=TWO, owners=doc())

        def boom(*args: Any, **kwargs: Any) -> None:
            raise failure

        monkeypatch.setattr(codeowners.subprocess, "run", boom)
        assert tracked_files(repo) == []


class TestMatcher:
    def test_last_matching_line_wins_over_the_whole_file(self) -> None:
        entries = parse_codeowners(
            "# comment\n\n* @a\ndocs/ @b\n/docs/x.md @c\nunmanaged/ @d @e\n"
        )
        assert selected_handles(entries, "src/m.py") == frozenset({"@a"})
        assert selected_handles(entries, "docs/y.md") == frozenset({"@b"})
        assert selected_handles(entries, "docs/x.md") == frozenset({"@c"})
        assert selected_handles(entries, "unmanaged/z") == frozenset({"@d", "@e"})

    def test_no_match_selects_nothing(self) -> None:
        assert selected_handles(parse_codeowners("docs/ @b\n"), "src/a.py") == frozenset()

    def test_inline_comments_and_blank_lines_ignored(self) -> None:
        entries = parse_codeowners("docs/ @b # trailing comment\n   \n")
        assert [(e.pattern, e.handles) for e in entries] == [("docs/", ("@b",))]

    def test_pattern_without_owners_selects_nobody(self) -> None:
        entries = parse_codeowners("* @a\nvendor/\n")
        assert selected_handles(entries, "vendor/x") == frozenset()

    def test_embedded_double_star_is_treated_as_single_star(self) -> None:
        entries = parse_codeowners("a/b**c @x\n")
        assert selected_handles(entries, "a/bzzc") == frozenset({"@x"})
        assert selected_handles(entries, "a/b/zzc") == frozenset()


class TestProbeSet:
    def test_probe_set_construction(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=doc(
                capabilities={"agent-identity": {"owners": ["kim"]}},
                paths={"docs/guides/**": {"owners": ["kim"]}, "*.lock": {"owners": ["jan"]}},
            ),
            specs=["agent-identity"],
        )
        track(repo, "openspec/contracts/agent-identity/x.json", "docs/guides/a.md", "uv.lock", "src/m.py")
        ctx = load_ownership(repo)
        tracked = [
            "openspec/specs/agent-identity/spec.md",
            "openspec/contracts/agent-identity/x.json",
            "docs/guides/a.md",
            "uv.lock",
            "src/m.py",
        ]
        probes = build_probes(ctx, tracked)
        assert "openspec/specs/agent-identity/spec.md" in probes  # tracked spec file
        assert "openspec/contracts/agent-identity/x.json" in probes  # tracked contract file
        assert "docs/guides/a.md" in probes  # matches an explicit paths rule
        assert "uv.lock" in probes  # matches an explicit paths rule
        assert "src/m.py" not in probes  # matches nothing and is not under specs/contracts
        assert any(p.startswith("docs/guides/") and p != "docs/guides/a.md" for p in probes)  # literal prefix
        assert len([p for p in probes if p.startswith("zz-")]) == 1  # one unmatched path
        assert probes == sorted(set(probes))


class TestReconcile:
    def test_clean_emit_reconciles_with_zero_disagreements(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=doc(
                capabilities={"agent-identity": {"owners": ["kim"]}},
                paths={"openspec/contracts/**": {"owners": ["jan"]}, "schemas/": {"owners": ["kim"]}},
            ),
            specs=["agent-identity", "other"],
        )
        track(repo, "openspec/contracts/agent-identity/x.json", "openspec/contracts/other/y.json", "a/schemas/s.json")
        emit_write(repo)
        report = reconcile(repo)
        assert report["disagreements"] == 0
        assert report["stale"] is False
        assert report["exit_code"] == 0
        assert report["findings"] == []

    def test_emit_ordering_yields_agreement(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=doc(
                paths={
                    "openspec/contracts/**": {"owners": ["jan"]},
                    "openspec/contracts/agent-coordinator/**": {"owners": ["kim"]},
                }
            ),
        )
        track(repo, "openspec/contracts/agent-coordinator/openapi/v1.yaml", "openspec/contracts/other/z.yaml")
        emit_write(repo)
        text = (repo / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
        assert text.index("*") < text.index("openspec/contracts/**") < text.index(
            "openspec/contracts/agent-coordinator/**"
        )
        assert reconcile(repo)["disagreements"] == 0

    def test_hand_edited_conflicting_line_is_a_disagreement(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=doc(capabilities={"agent-identity": {"owners": ["kim"]}}),
            specs=["agent-identity"],
        )
        emit_write(repo)
        path = repo / ".github" / "CODEOWNERS"
        path.write_text(
            path.read_text(encoding="utf-8") + "openspec/specs/agent-identity/ @someone-else\n",
            encoding="utf-8",
        )
        report = reconcile(repo)
        assert report["exit_code"] == 1
        hits = [f for f in report["findings"] if f["code"] == "codeowners_disagreement"]
        assert any(f["subject"] == "openspec/specs/agent-identity/spec.md" for f in hits)
        message = next(f["message"] for f in hits if f["subject"] == "openspec/specs/agent-identity/spec.md")
        assert "@someone-else" in message and "@kimlee" in message

    def test_stale_block_reported_with_diff(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        emit_write(repo)
        owners_file = repo / "openspec" / "owners.yaml"
        owners_file.write_text(
            owners_file.read_text(encoding="utf-8").replace("default_owner: jan", "default_owner: kim"),
            encoding="utf-8",
        )
        report = reconcile(repo)
        assert report["stale"] is True
        stale = next(f for f in report["findings"] if f["code"] == "codeowners_stale")
        assert stale["severity"] == "warning"
        assert "-*" in stale["message"] and "+*" in stale["message"]
        assert "@kimlee" in stale["message"]

    def test_missing_codeowners_file_is_a_warning(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        report = reconcile(repo)
        assert finding_codes(report) == ["codeowners_missing"]
        assert report["exit_code"] == 0

    def test_codeowners_without_a_managed_block_is_missing(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        (repo / ".github").mkdir()
        (repo / ".github" / "CODEOWNERS").write_text("* @jankneumann\n", encoding="utf-8")
        report = reconcile(repo)
        assert "codeowners_missing" in finding_codes(report)

    def test_orphaned_managed_block_is_a_warning_with_exit_zero(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        emit_write(repo)
        (repo / "openspec" / "owners.yaml").unlink()
        track(repo)
        # two humans without a map would be an error elsewhere; use a single-human registry
        (repo / "agent-coordinator" / "agents.yaml").write_text(
            "humans:\n  jan:\n    display_name: Jan\n    github: jankneumann\n", encoding="utf-8"
        )
        report = reconcile(repo)
        assert finding_codes(report) == ["orphan_managed_block"]
        assert report["exit_code"] == 0

    def test_no_map_and_no_block_is_informational(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN})
        report = reconcile(repo)
        assert finding_codes(report) == ["no_ownership_map"]
        assert report["findings"][0]["severity"] == "info"
        assert report["exit_code"] == 0

    def test_outside_a_git_checkout_is_an_error(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc(), git=False)
        report = reconcile(repo)
        assert finding_codes(report) == ["not_a_git_checkout"]
        assert report["exit_code"] == 1

    def test_missing_github_handle_reported(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": {"display_name": "Jan"}}, owners=doc())
        report = reconcile(repo)
        assert "missing_github_handle" in finding_codes(report)
        assert report["exit_code"] == 1

    def test_invalid_map_surfaces_its_error(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, owners={"schema_version": 1})
        assert reconcile(repo)["exit_code"] == 1


class TestCli:
    def test_reconcile_json(self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        emit_write(repo)
        capsys.readouterr()
        assert main(["reconcile", "--repo-root", str(repo), "--json"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert {"schema_version", "disagreements", "stale", "exit_code", "findings"} <= set(out)

    def test_reconcile_exit_code_on_disagreement(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        emit_write(repo)
        path = repo / ".github" / "CODEOWNERS"
        path.write_text(path.read_text(encoding="utf-8") + "* @someone-else\n", encoding="utf-8")
        assert main(["reconcile", "--repo-root", str(repo)]) == 1


class TestCheckIntegration:
    def test_check_codeowners_flag_includes_reconcile_findings(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        report = check(repo, codeowners=True)
        assert "codeowners_missing" in finding_codes(report)

    def test_clean_run_with_codeowners_has_no_findings(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        emit_write(repo)
        report = check(repo, codeowners=True)
        assert report["findings"] == []

    def test_info_finding_is_not_promoted_by_strict(
        self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = make_repo(humans={"jan": JAN})
        report = check(repo, codeowners=True)
        assert finding_codes(report) == ["no_ownership_map"]
        assert exit_code(report, strict=True) == 0
        assert check_main(["--repo-root", str(repo), "--codeowners", "--strict"]) == 0
        capsys.readouterr()

    def test_disagreement_is_an_error_in_check(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        emit_write(repo)
        path = repo / ".github" / "CODEOWNERS"
        path.write_text(path.read_text(encoding="utf-8") + "* @someone-else\n", encoding="utf-8")
        report = check(repo, codeowners=True)
        assert "codeowners_disagreement" in finding_codes(report)
        assert exit_code(report, strict=False) == 1


class TestUnreadableCodeowners:
    """A CODEOWNERS that cannot be decoded is a finding, never a traceback (--json contract)."""

    def test_undecodable_file_is_an_error_finding(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        emit_write(repo)
        path = repo / ".github" / "CODEOWNERS"
        path.write_bytes(b"\xff\xfe* @someone\n")
        report = reconcile(repo)
        assert finding_codes(report) == ["codeowners_unreadable"]
        unreadable = report["findings"][0]
        assert unreadable["severity"] == "error"
        assert unreadable["subject"] == ".github/CODEOWNERS"
        assert "utf-8" in unreadable["message"].lower()
        assert report["exit_code"] == 1
        assert report["disagreements"] == 0 and report["stale"] is False

    def test_check_reports_it_too(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        emit_write(repo)
        (repo / ".github" / "CODEOWNERS").write_bytes(b"\xff\xfe* @someone\n")
        report = check(repo, codeowners=True)
        assert finding_codes(report) == ["codeowners_unreadable"]
        assert exit_code(report, strict=False) == 1
