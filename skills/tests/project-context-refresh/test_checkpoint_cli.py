"""The ``checkpoint`` CLI subcommand (ri-09 tasks 3.9-3.10).

Spec scenarios: pcro "Checkpoint runs for a work package inside a feature
worktree", pcro "Checkpoint refuses to run against a shared checkout", pcro
"Inability to produce a report is a failure". Design decision: D8 — drift is
data, so it exits 0; the single non-zero exit is being unable to produce a valid
report at all, and ri-10 owns turning drift into a gate.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import checkpoint
import cli
from _runtime import (
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    Remediation,
)
from registry import Producer, ProducerError, ProducerSpec, register

CHANGE_ID = "add-branch-local-context-checkpoints"
PACKAGE_ID = "wp-checkpoint"
REPORT_PATH = f"openspec/changes/{CHANGE_ID}/context-checkpoints/{PACKAGE_ID}.json"

RULES_YAML = """\
schema_version: 1
rules:
  - surface: documentation
    globs:
      - "docs/**"
      - "**/*.md"
  - surface: semantic_code
    globs:
      - "**/*.py"
"""

WORK_PACKAGES_YAML = """\
schema_version: 1
feature:
  id: add-branch-local-context-checkpoints
packages:
  - package_id: wp-checkpoint
    scope:
      read_allow:
        - "docs/**"
      write_allow:
        - "docs/**"
      deny:
        - "**/.venv/**"
    context_impact:
      surfaces:
        - documentation
"""


class _Fake(Producer):
    """A registry producer with a settable status, so drift can be simulated."""

    status = ProducerStatus.FRESH

    spec = ProducerSpec(
        producer_id="documentation.inventory",
        producer_version="1.0.0",
        owner="docs",
        inputs=("docs/**",),
        outputs=(),
    )

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        if type(self).status is ProducerStatus.FRESH:
            return ProducerResult(
                producer_id=self.spec.producer_id,
                producer_version=self.spec.producer_version,
                status=ProducerStatus.FRESH,
            )
        return ProducerResult(
            producer_id=self.spec.producer_id,
            producer_version=self.spec.producer_version,
            status=ProducerStatus.DEGRADED,
            remediation=(Remediation(summary="regenerate docs"),),
            fallback=Fallback(kind=FallbackKind.CUSTOM, reason="check mode wrote nothing"),
        )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> tuple[Path, str]:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
        _git(tmp_path, "config", key, value)

    change_dir = tmp_path / "openspec" / "changes" / CHANGE_ID
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "work-packages.yaml").write_text(WORK_PACKAGES_YAML, encoding="utf-8")
    (tmp_path / "rules.yaml").write_text(RULES_YAML, encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "guide.md").write_text("committed\n", encoding="utf-8")

    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path, _git(tmp_path, "rev-parse", "HEAD")


def _argv(repo_root: Path, revision: str, *extra: str) -> list[str]:
    return [
        "--repo",
        str(repo_root),
        "--revision",
        revision,
        "checkpoint",
        "--change-id",
        CHANGE_ID,
        "--package-id",
        PACKAGE_ID,
        "--rules",
        str(repo_root / "rules.yaml"),
        "--changed-file",
        "docs/guide.md",
        *extra,
    ]


@pytest.fixture(autouse=True)
def _reset_fake_status():
    _Fake.status = ProducerStatus.FRESH
    yield
    _Fake.status = ProducerStatus.FRESH


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #
def test_checkpoint_writes_the_report_and_exits_zero(
    repo: tuple[Path, str], capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    repo_root, head = repo
    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)

    code = cli.main(_argv(repo_root, head))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["report_path"] == REPORT_PATH
    assert (repo_root / REPORT_PATH).is_file()
    assert payload["report"]["source_revision"] == head
    assert payload["report"]["namespace"]["kind"] == "work_package"
    assert payload["report"]["context_impact"]["status"] == "declared"
    # The package is read out of the change's own work-packages.yaml.
    assert payload["report"]["scope"]["deny"] == ["**/.venv/**"]


def test_changed_files_come_from_the_flag_not_a_git_range(
    repo: tuple[Path, str], capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    """D2: the decision must work on an uncommitted worktree, so no git range."""
    repo_root, head = repo
    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)

    # An uncommitted .py file inside the package's write scope. It implies
    # `semantic_code`, which the package never declared — so a decision derived
    # from a git range (or from the working tree) would flip the ri-08 status to
    # `undeclared` and refuse to produce a report at all.
    (repo_root / "docs" / "notes.py").write_text("x = 1\n", encoding="utf-8")

    code = cli.main(_argv(repo_root, head))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["report"]["context_impact"]["status"] == "declared"
    assert payload["report"]["context_impact"]["surfaces"] == ["documentation"]


def test_no_changed_files_still_honours_the_declaration(
    repo: tuple[Path, str], capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    """D2 is 'declared *or* inferred', so a declaration alone is enough."""
    repo_root, head = repo
    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)

    cli.main(
        [
            "--repo",
            str(repo_root),
            "--revision",
            head,
            "checkpoint",
            "--change-id",
            CHANGE_ID,
            "--package-id",
            PACKAGE_ID,
            "--rules",
            str(repo_root / "rules.yaml"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["decision"]["should_run"] is True
    assert payload["decision"]["surfaces"] == ["documentation"]


def test_merge_base_is_recorded_when_supplied(
    repo: tuple[Path, str], capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    repo_root, head = repo
    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)

    cli.main(_argv(repo_root, head, "--merge-base", head))
    payload = json.loads(capsys.readouterr().out)

    assert payload["report"]["merge_base_revision"] == head


def test_a_repeat_run_reports_no_change(
    repo: tuple[Path, str], capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    repo_root, head = repo
    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)

    cli.main(_argv(repo_root, head))
    capsys.readouterr()
    cli.main(_argv(repo_root, head))
    payload = json.loads(capsys.readouterr().out)

    assert payload["changed"] is False


# --------------------------------------------------------------------------- #
# D8 — drift exits 0
# --------------------------------------------------------------------------- #
def test_detected_drift_still_exits_zero(
    repo: tuple[Path, str], capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    repo_root, head = repo
    _Fake.status = ProducerStatus.DEGRADED
    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)

    code = cli.main(_argv(repo_root, head))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, "gating drift is ri-10's job, not the checkpoint's"
    assert payload["report"]["producer_results"][0]["status"] == "degraded"
    assert (repo_root / REPORT_PATH).is_file()


# --------------------------------------------------------------------------- #
# Checkout policy
# --------------------------------------------------------------------------- #
def test_checkpoint_refuses_a_real_shared_checkout(repo: tuple[Path, str]) -> None:
    # No monkeypatch: the REAL guard must reject a plain checkout that is not a
    # managed worktree, or the gate is decoration.
    repo_root, head = repo
    register(_Fake())

    with pytest.raises(ProducerError, match="managed worktree"):
        cli.main(_argv(repo_root, head))

    assert not (repo_root / REPORT_PATH).exists()


# --------------------------------------------------------------------------- #
# The single failure mode: no valid report
# --------------------------------------------------------------------------- #
def test_unknown_package_is_a_failure_with_no_report(
    repo: tuple[Path, str], capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    repo_root, head = repo
    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)

    code = cli.main(
        [
            "--repo",
            str(repo_root),
            "--revision",
            head,
            "checkpoint",
            "--change-id",
            CHANGE_ID,
            "--package-id",
            "wp-nope",
            "--rules",
            str(repo_root / "rules.yaml"),
            "--changed-file",
            "docs/guide.md",
        ]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert "wp-nope" in captured.err
    assert not (
        repo_root / "openspec" / "changes" / CHANGE_ID / "context-checkpoints"
    ).exists()


def test_a_blocking_context_impact_status_is_a_failure_with_no_report(
    repo: tuple[Path, str], capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    repo_root, head = repo
    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)

    # `notes.py` implies `semantic_code`, which the package never declared.
    code = cli.main(_argv(repo_root, head, "--changed-file", "docs/notes.py"))
    captured = capsys.readouterr()

    assert code == 1
    assert "undeclared" in captured.err
    assert not (repo_root / REPORT_PATH).exists()


def test_a_missing_work_packages_file_is_a_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
        _git(tmp_path, "config", key, value)
    (tmp_path / "seed.txt").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")
    head = _git(tmp_path, "rev-parse", "HEAD")

    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)

    code = cli.main(
        [
            "--repo",
            str(tmp_path),
            "--revision",
            head,
            "checkpoint",
            "--change-id",
            CHANGE_ID,
            "--package-id",
            PACKAGE_ID,
        ]
    )
    assert code == 1
    assert "work-packages.yaml" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #
def test_the_subcommand_is_registered_and_documented(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "checkpoint" in capsys.readouterr().out


def test_the_cli_delegates_to_the_checkpoint_module(
    repo: tuple[Path, str], monkeypatch
) -> None:
    """The CLI must not grow its own copy of the checkpoint's orchestration."""
    repo_root, head = repo
    register(_Fake())
    monkeypatch.setattr(cli, "_require_mutation", lambda repository: None)
    seen: dict[str, Any] = {}

    real = checkpoint.run_checkpoint

    def spy(repository, **kwargs):  # noqa: ANN001
        seen.update(kwargs)
        return real(repository, **kwargs)

    monkeypatch.setattr(cli.checkpoint, "run_checkpoint", spy)
    cli.main(_argv(repo_root, head))

    assert seen["change_id"] == CHANGE_ID
    assert seen["package_id"] == PACKAGE_ID
    assert seen["revision"] == head
    assert tuple(seen["changed_files"]) == ("docs/guide.md",)
