"""CODEOWNERS emission: managed block, ordering, handle rendering (design D8)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from codeowners import BEGIN_MARKER, END_MARKER, main

MakeRepo = Callable[..., Path]

JAN = {"display_name": "Jan Neumann", "github": "jankneumann"}
KIM = {"display_name": "Kim Lee", "github": "kimlee"}
TWO = {"jan": JAN, "kim": KIM}


def doc(**assignments: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"schema_version": 1, "default_owner": "jan"}
    if assignments:
        out["assignments"] = assignments
    return out


def emit(repo: Path, *extra: str) -> int:
    return main(["emit", "--repo-root", str(repo), *extra])


def block_lines(text: str) -> list[tuple[str, list[str]]]:
    """``(pattern, handles)`` for every rule line between the markers."""
    lines = text.splitlines()
    begin = next(i for i, ln in enumerate(lines) if ln.startswith(BEGIN_MARKER))
    end = next(i for i, ln in enumerate(lines) if ln.startswith(END_MARKER))
    rules = []
    for line in lines[begin + 1 : end]:
        if line.strip() and not line.startswith("#"):
            pattern, *handles = line.split()
            rules.append((pattern, handles))
    return rules


def codeowners(repo: Path) -> Path:
    return repo / ".github" / "CODEOWNERS"


class TestBlockShape:
    def test_markers_and_default_line_first(
        self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        assert emit(repo, "--write") == 0
        text = codeowners(repo).read_text(encoding="utf-8")
        lines = text.splitlines()
        assert lines[0].startswith("# BEGIN ownership-map")
        assert "openspec/owners.yaml" in lines[0]
        assert lines[-1] == "# END ownership-map"
        assert block_lines(text) == [("*", ["@jankneumann"])]

    def test_two_lines_per_capability_and_one_per_path(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=doc(
                capabilities={"agent-identity": {"owners": ["kim"]}},
                paths={"docs/**": {"owners": ["jan", "kim"]}},
            ),
        )
        assert emit(repo, "--write") == 0
        rules = dict(block_lines(codeowners(repo).read_text(encoding="utf-8")))
        assert rules["openspec/specs/agent-identity/"] == ["@kimlee"]
        assert rules["openspec/contracts/agent-identity/"] == ["@kimlee"]
        assert rules["docs/**"] == ["@jankneumann", "@kimlee"]
        assert len(rules) == 4  # *, two capability lines, one path line

    def test_ascending_specificity_order(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans=TWO,
            owners=doc(
                paths={
                    "openspec/contracts/agent-coordinator/**": {"owners": ["kim"]},
                    "openspec/contracts/**": {"owners": ["jan"]},
                }
            ),
        )
        assert emit(repo, "--write") == 0
        patterns = [p for p, _ in block_lines(codeowners(repo).read_text(encoding="utf-8"))]
        assert patterns == [
            "*",
            "openspec/contracts/**",
            "openspec/contracts/agent-coordinator/**",
        ]

    def test_implied_capability_lines_precede_explicit_at_equal_specificity(
        self, make_repo: MakeRepo
    ) -> None:
        repo = make_repo(
            humans=TWO,
            owners=doc(
                capabilities={"agent-identity": {"owners": ["kim"]}},
                paths={"openspec/specs/agent-identity/": {"owners": ["jan"]}},
            ),
        )
        assert emit(repo, "--write") == 0
        rules = block_lines(codeowners(repo).read_text(encoding="utf-8"))
        same = [h for p, h in rules if p == "openspec/specs/agent-identity/"]
        assert same == [["@kimlee"], ["@jankneumann"]]  # implied first, explicit last (wins)

    def test_emit_without_write_prints_and_does_not_touch_the_file(
        self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        assert emit(repo) == 0
        out = capsys.readouterr().out
        assert BEGIN_MARKER in out and END_MARKER in out
        assert not codeowners(repo).exists()


class TestPreservation:
    def test_unmanaged_text_before_and_after_preserved_byte_for_byte(
        self, make_repo: MakeRepo
    ) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        assert emit(repo, "--write") == 0
        path = codeowners(repo)
        block = path.read_text(encoding="utf-8")
        before = "# hand-written header\n/legacy/  @someone\r\n\n"
        after = "\n# trailing\ntools/  @tooling-team  \n"
        path.write_bytes((before + block + after).encode("utf-8"))

        repo_owners = repo / "openspec" / "owners.yaml"
        repo_owners.write_text(
            repo_owners.read_text(encoding="utf-8").replace("default_owner: jan", "default_owner: kim"),
            encoding="utf-8",
        )
        assert emit(repo, "--write") == 0
        updated = path.read_bytes().decode("utf-8")
        assert updated.startswith(before)
        assert updated.endswith(after)
        assert "@kimlee" in updated and "@jankneumann" not in updated

    def test_block_appended_when_file_has_none(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        path = codeowners(repo)
        path.parent.mkdir(parents=True)
        path.write_text("/legacy/  @someone\n", encoding="utf-8")
        assert emit(repo, "--write") == 0
        text = path.read_text(encoding="utf-8")
        assert text.startswith("/legacy/  @someone\n")
        assert BEGIN_MARKER in text and text.endswith("# END ownership-map\n")

    def test_emit_is_idempotent(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc(paths={"docs/**": {"owners": ["kim"]}}))
        assert emit(repo, "--write") == 0
        first = codeowners(repo).read_bytes()
        assert emit(repo, "--write") == 0
        assert codeowners(repo).read_bytes() == first


class TestFailClosed:
    def test_missing_github_handle_fails_without_modifying_the_file(
        self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = make_repo(
            humans={"jan": {"display_name": "Jan Neumann"}, "kim": KIM}, owners=doc()
        )
        path = codeowners(repo)
        path.parent.mkdir(parents=True)
        path.write_text("# untouched\n", encoding="utf-8")
        assert emit(repo, "--write") == 1
        assert path.read_text(encoding="utf-8") == "# untouched\n"
        err = capsys.readouterr().err
        assert "jan" in err and "github" in err

    def test_only_humans_in_emitted_owner_sets_need_a_handle(self, make_repo: MakeRepo) -> None:
        repo = make_repo(
            humans={"jan": JAN, "kim": {"display_name": "Kim Lee"}}, owners=doc()
        )
        assert emit(repo, "--write") == 0

    def test_no_map_exits_1_and_creates_nothing(
        self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = make_repo(humans={"jan": JAN})
        assert emit(repo, "--write") == 1
        assert not codeowners(repo).exists()
        assert not (repo / ".github").exists()
        assert "no_ownership_map" in capsys.readouterr().err

    def test_invalid_map_fails_closed(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans={"jan": JAN}, owners={"schema_version": 1})
        assert emit(repo, "--write") == 1
        assert not codeowners(repo).exists()

    def test_json_error_shape(
        self, make_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = make_repo(humans={"jan": JAN})
        assert emit(repo, "--json") == 1
        out = json.loads(capsys.readouterr().out)
        assert out["code"] == "no_ownership_map"


class TestUnterminatedBlock:
    def test_emit_over_unterminated_block_is_idempotent(self, make_repo: MakeRepo) -> None:
        repo = make_repo(humans=TWO, owners=doc())
        codeowners(repo).parent.mkdir(parents=True, exist_ok=True)
        codeowners(repo).write_text(
            f"{BEGIN_MARKER} (truncated)\n* @someone\n", encoding="utf-8"
        )
        assert emit(repo, "--write") == 0
        first = codeowners(repo).read_text(encoding="utf-8")
        assert emit(repo, "--write") == 0
        assert codeowners(repo).read_text(encoding="utf-8") == first
