"""Tests for scripts/contract_gate/check_breaking.py (design D4).

Run explicitly (scripts/ is outside every pyproject testpath):

    pytest scripts/contract_gate/tests -q

Each test builds a throwaway git repository, commits a base tree, makes a
"pull request" commit on top, and runs the gate with an injected oasdiff
callable that returns a recorded oasdiff JSON fixture. Neither the oasdiff
binary nor the network is needed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

GATE_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(GATE_DIR))
import check_breaking as cb

DOC = "openspec/contracts/agent-coordinator/openapi/features.yaml"
CHANGE = "openspec/changes/some-change"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo whose `main` branch holds one promoted contract; HEAD is a PR branch."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _write(tmp_path, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '1'}\npaths: {}\n")
    _write(tmp_path, "README.md", "base\n")
    _commit(tmp_path, "base")
    _git(tmp_path, "checkout", "-q", "-b", "pr")
    return tmp_path


def _fixture_oasdiff(name: str, calls: list[tuple[str, str]] | None = None):
    text = (FIXTURES / name).read_text()

    def run(base_file: str, head_file: str) -> str:
        if calls is not None:
            # The base file is a temp file the gate deletes; capture its content now.
            calls.append((Path(base_file).read_text(), head_file))
        return text

    return run


def _ack(repo: Path, entries: list[dict[str, str]], change: str = CHANGE) -> None:
    import yaml

    _write(
        repo,
        f"{change}/contracts/accepted-breaking-changes.yaml",
        yaml.safe_dump({"accepted": entries}),
    )


def _run(repo: Path, oasdiff, capsys) -> tuple[int, str]:
    code = cb.run_gate(repo_root=repo, base="main", run_oasdiff=oasdiff)
    return code, capsys.readouterr().out


def test_unacknowledged_break_fails_and_names_document_operation_rule(repo, capsys):
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _commit(repo, "break")
    calls: list[tuple[str, str]] = []

    code, out = _run(repo, _fixture_oasdiff("breaking_int_level.json", calls), capsys)

    assert code == 1
    assert DOC in out
    assert "GET /features/{feature_id}" in out
    assert "response-required-property-removed" in out
    assert "removed the required property 'status'" in out
    # INFO-level findings never count as breaking.
    assert "response-optional-property-added" not in out
    # oasdiff compared the merge-base version against the working tree file.
    assert len(calls) == 1
    base_text, head_file = calls[0]
    assert "version: '1'" in base_text
    assert Path(head_file) == repo / DOC


def test_exact_acknowledgement_passes_and_is_listed(repo, capsys):
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _ack(
        repo,
        [
            {
                "document": DOC,
                "operation": "GET /features/{feature_id}",
                "rule_id": "response-required-property-removed",
                "rationale": "contract-only correction",
            }
        ],
    )
    _commit(repo, "break + ack")

    code, out = _run(repo, _fixture_oasdiff("breaking_int_level.json"), capsys)

    assert code == 0
    assert "ACKNOWLEDGED" in out
    assert "response-required-property-removed" in out
    assert "GET /features/{feature_id}" in out


def test_acknowledgement_must_match_exactly(repo, capsys):
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _ack(
        repo,
        [
            {
                "document": DOC,
                "operation": "POST /features/{feature_id}",  # wrong method
                "rule_id": "response-required-property-removed",
                "rationale": "x",
            }
        ],
    )
    _commit(repo, "break + wrong ack")

    code, out = _run(repo, _fixture_oasdiff("breaking_int_level.json"), capsys)

    assert code == 1
    assert "WARNING" in out  # the non-matching entry is stale


def test_acknowledgement_outside_touched_change_dirs_is_ignored(repo, capsys):
    # The ack file lands on main, so the PR does not touch its change directory.
    _git(repo, "checkout", "-q", "main")
    _ack(
        repo,
        [
            {
                "document": DOC,
                "operation": "GET /features/{feature_id}",
                "rule_id": "response-required-property-removed",
                "rationale": "x",
            }
        ],
        change="openspec/changes/other-change",
    )
    _commit(repo, "ack on main")
    _git(repo, "checkout", "-q", "pr")
    _git(repo, "merge", "-q", "main")
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _commit(repo, "break")

    code, out = _run(repo, _fixture_oasdiff("breaking_int_level.json"), capsys)

    assert code == 1
    assert "ACKNOWLEDGED" not in out


def test_additive_change_passes_without_acknowledgement(repo, capsys):
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _commit(repo, "additive")

    code, out = _run(repo, _fixture_oasdiff("additive_only.json"), capsys)

    assert code == 0
    assert "BREAKING" not in out


def test_null_oasdiff_output_means_no_changes(repo, capsys):
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _commit(repo, "cosmetic")

    assert _run(repo, _fixture_oasdiff("no_changes_null.json"), capsys)[0] == 0
    assert _run(repo, lambda b, h: "", capsys)[0] == 0


def test_change_local_contracts_are_not_gated(repo, capsys):
    _write(repo, f"{CHANGE}/contracts/openapi/v1.yaml", "openapi: 3.1.0\n")
    _commit(repo, "change-local only")

    def must_not_run(base_file: str, head_file: str) -> str:
        raise AssertionError("oasdiff must not run for change-local contracts")

    code, out = _run(repo, must_not_run, capsys)

    assert code == 0
    assert "no promoted contracts changed" in out


def test_stale_acknowledgement_warns_but_passes(repo, capsys):
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _ack(
        repo,
        [
            {
                "document": DOC,
                "operation": "DELETE /features/{feature_id}",
                "rule_id": "api-removed-without-deprecation",
                "rationale": "no longer applies",
            }
        ],
    )
    _commit(repo, "additive + stale ack")

    code, out = _run(repo, _fixture_oasdiff("additive_only.json"), capsys)

    assert code == 0
    assert "WARNING" in out
    assert "api-removed-without-deprecation" in out


def test_deleted_promoted_document_fails_unless_acknowledged(repo, capsys):
    (repo / DOC).unlink()
    _commit(repo, "delete")

    def must_not_run(base_file: str, head_file: str) -> str:
        raise AssertionError("no comparison for a deleted document")

    code, out = _run(repo, must_not_run, capsys)
    assert code == 1
    assert DOC in out
    assert "contract-document-deleted" in out

    _ack(
        repo,
        [
            {
                "document": DOC,
                "operation": "*",
                "rule_id": "contract-document-deleted",
                "rationale": "retired",
            }
        ],
    )
    _commit(repo, "ack delete")

    code, out = _run(repo, must_not_run, capsys)
    assert code == 0
    assert "ACKNOWLEDGED" in out


def test_added_promoted_document_is_reported_and_passes(repo, capsys):
    new_doc = "openspec/contracts/agent-coordinator/openapi/new.yaml"
    _write(repo, new_doc, "openapi: 3.1.0\n")
    _commit(repo, "add")

    def must_not_run(base_file: str, head_file: str) -> str:
        raise AssertionError("no comparison for a new document")

    code, out = _run(repo, must_not_run, capsys)
    assert code == 0
    assert new_doc in out
    assert "new" in out.lower()


def test_archived_change_dir_acknowledgement_is_collected(repo, capsys):
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _ack(
        repo,
        [
            {
                "document": DOC,
                "operation": "GET /features/{feature_id}",
                "rule_id": "response-required-property-removed",
                "rationale": "x",
            }
        ],
        change="openspec/changes/archive/2026-10-09-some-change",
    )
    _commit(repo, "break + archived ack")

    code, _ = _run(repo, _fixture_oasdiff("breaking_int_level.json"), capsys)
    assert code == 0


def test_string_levels_and_lowercase_methods(repo, capsys):
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _commit(repo, "break")

    code, out = _run(repo, _fixture_oasdiff("breaking_string_level.json"), capsys)

    assert code == 1
    assert "GET /features/{feature_id}" in out
    assert "api-security-added" in out
    assert "request-property-became-enum" not in out  # WARN is not breaking


@pytest.mark.parametrize(
    ("level", "breaking"),
    [
        (3, True),
        (2, False),
        (1, False),
        ("error", True),
        ("ERR", True),
        ("err", True),
        ("warning", False),
        ("WARN", False),
        ("info", False),
        (None, False),
    ],
)
def test_is_error_level(level, breaking):
    assert cb.is_error_level(level) is breaking


def test_parse_findings_rejects_non_list():
    with pytest.raises(cb.GateError):
        cb.parse_oasdiff_output('{"not": "a list"}')


def test_cli_with_fake_oasdiff_script(repo, tmp_path_factory):
    _write(repo, DOC, "openapi: 3.1.0\ninfo: {title: f, version: '2'}\npaths: {}\n")
    _commit(repo, "break")
    bindir = tmp_path_factory.mktemp("bin")
    fake = bindir / "oasdiff"
    fake.write_text(
        "#!/bin/sh\n"
        f'[ "$1" = breaking ] && [ "$2" = -f ] && [ "$3" = json ] || exit 9\n'
        f"cat {FIXTURES / 'breaking_int_level.json'}\n"
    )
    fake.chmod(0o755)

    proc = subprocess.run(
        [
            sys.executable,
            str(GATE_DIR / "check_breaking.py"),
            "--base",
            "main",
            "--oasdiff",
            str(fake),
            "--repo-root",
            str(repo),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "response-required-property-removed" in proc.stdout
