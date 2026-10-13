"""CLI surface of ``test_oracle_audit.cli`` (task 8.1 / 8.2 contract).

Expectations come from the spec and design D1/D3/D15 only. Assumed surface:

    cli.main(argv: list[str]) -> int
    global options come before the subcommand:
        --repo-root PATH --suites-file PATH --suite NAME --out DIR --dry-run
        --python PATH --max-mutants N --seed N --ledger PATH
    subcommands: inventory static judge mutate refactor history explain label
                 analyze report run-all
    each stage subcommand also works standalone against an empty --out and
    writes <out>/<stage>.jsonl (judge -> judged.jsonl, mutate -> mutation.jsonl,
    refactor -> rename.jsonl); ``report --validate`` re-validates <out>/analysis.json.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SUITE = "e2e"
SEED = 7
ENV_KEYS = ("TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")
STAGE_COMMANDS = {
    "inventory": "inventory",
    "static": "static",
    "judge": "judged",
    "mutate": "mutation",
    "refactor": "rename",
    "history": "history",
}


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(root).parts
    }


def _suites_file(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suites": {
                    SUITE: {
                        "project_root": ".",
                        "test_paths": ["tests"],
                        "source_roots": ["mini"],
                        "pytest_args": ["-p", "no:cacheprovider"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


class Env:
    def __init__(self, repo: Path, tmp: Path) -> None:
        self.repo = repo
        self.out = tmp / "out"
        self.ledger = tmp / "ledger" / "labels.json"
        self.suites_file = _suites_file(tmp / "suites.json")

    def run(self, *command: str, dry_run: bool = True) -> int:
        cli = importlib.import_module("test_oracle_audit.cli")
        argv = [
            "--repo-root", str(self.repo),
            "--suites-file", str(self.suites_file),
            "--suite", SUITE,
            "--out", str(self.out),
            "--python", sys.executable,
            "--max-mutants", "6",
            "--seed", str(SEED),
            "--ledger", str(self.ledger),
        ]  # fmt: skip
        if dry_run:
            argv.append("--dry-run")
        code = cli.main([*argv, *command])
        assert isinstance(code, int)
        return code

    def records(self, stage: str) -> list[dict[str, Any]]:
        text = (self.out / f"{stage}.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.fixture
def env(fixture_project: Any, tmp_path: Path) -> Env:
    # The fixture copy lives in tmp_path/e2e_repo; keep out/ledger/suites beside it.
    repo = fixture_project("e2e_repo")
    return Env(repo, tmp_path)


@pytest.mark.parametrize("command", sorted(STAGE_COMMANDS))
def test_stage_subcommand_writes_valid_records_and_touches_nothing_else(
    env: Env, command: str, schema_validator: Any
) -> None:
    """test-oracle-audit.6 (Read-Only Audit Execution) and D1 (stages are
    independent and re-runnable): each stage subcommand exits 0 in dry-run,
    writes <out>/<stage>.jsonl with schema-valid records, and leaves the audited
    tree byte-identical."""
    before = _snapshot(env.repo)
    assert env.run(command) == 0
    stage = STAGE_COMMANDS[command]
    records = env.records(stage)
    assert records
    for record in records:
        schema_validator(record)
        assert record["stage"] == stage
    assert _snapshot(env.repo) == before
    assert subprocess.run(
        ["git", "status", "--porcelain"], cwd=env.repo, capture_output=True, text=True, check=True
    ).stdout.strip() == ""


def test_judge_dry_run_degrades_and_exits_zero(env: Env) -> None:
    """Judged "Missing key degrades without failing": --dry-run makes every
    judged record degraded with a reason, and the command exits 0."""
    assert env.run("judge") == 0
    records = env.records("judged")
    assert records
    assert {r["status"] for r in records} == {"degraded"}
    assert all(r["reason"] for r in records)


def test_judge_without_dry_run_and_without_key_degrades_and_exits_zero(env: Env) -> None:
    """Judged "Missing key degrades without failing": with TYPESAFE_API_KEY unset
    and no --dry-run, records are degraded and the exit code is still 0."""
    assert env.run("judge", dry_run=False) == 0
    records = env.records("judged")
    assert records
    assert {r["status"] for r in records} == {"degraded"}


def test_history_does_not_run_network_git_commands(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """History "Shallow clone degrades" / D6: the stage never fetches or unshallows.
    Every git invocation made by the audit process is recorded and none is a
    network subcommand."""
    seen: list[list[str]] = []
    real_run = subprocess.run

    def spy(args: Any, *a: Any, **kw: Any) -> Any:
        if isinstance(args, (list, tuple)) and args and Path(str(args[0])).name == "git":
            seen.append([str(x) for x in args])
        return real_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", spy)
    assert env.run("history") == 0
    network = {"fetch", "pull", "clone", "ls-remote", "push"}
    assert not [cmd for cmd in seen if network & set(cmd[1:3])]


def test_label_dry_run_renders_cards_and_does_not_create_the_ledger(env: Env) -> None:
    """Blind Stratified Human Labelling "Dry-run labelling writes no ledger entry"
    and test-oracle-audit.5 (labelling is part of the pipeline): the cards are
    rendered under --out, the ledger file is not created, and no test file or
    pytest config in the audited project changes."""
    before = _snapshot(env.repo)
    assert env.run("inventory") == 0
    assert env.run("static") == 0
    assert env.run("mutate") == 0
    assert env.run("label") == 0
    cards = [p for p in env.out.rglob("*") if p.is_file() and "card" in p.name.lower()]
    assert cards, "no card was rendered under --out"
    assert not env.ledger.exists()
    assert _snapshot(env.repo) == before


def test_analyze_then_report_regenerate_outputs_from_stage_files(env: Env) -> None:
    """Pilot Report / Analysis: stages are independent (D1), so after run-all the
    analysis and report can be deleted and rebuilt with `analyze` and `report`."""
    assert env.run("run-all") == 0
    (env.out / "analysis.json").unlink()
    (env.out / "report.md").unlink()
    assert env.run("analyze") == 0
    assert (env.out / "analysis.json").is_file()
    assert env.run("report") == 0
    first_line = (env.out / "report.md").read_text(encoding="utf-8").splitlines()[0].lower()
    assert "advisory" in first_line


def test_report_validate_accepts_a_good_analysis_and_rejects_a_broken_one(env: Env) -> None:
    """D1 "Schema runtime copy" (`report --validate` reads the runtime schemas):
    a pipeline-produced analysis.json validates; one missing required fields does
    not (non-zero exit)."""
    assert env.run("run-all") == 0
    assert env.run("report", "--validate") == 0
    broken = json.loads((env.out / "analysis.json").read_text(encoding="utf-8"))
    del broken["advisory"]
    (env.out / "analysis.json").write_text(json.dumps(broken), encoding="utf-8")
    assert env.run("report", "--validate") != 0


def test_run_all_without_dry_run_and_without_keys_still_exits_zero_and_clean(env: Env) -> None:
    """Read-Only Audit Execution "Full pipeline leaves the working tree clean" and
    Judged "Missing key degrades": a non-dry run with no keys degrades the judged
    and explain stages, exits 0 and leaves the audited tree byte-identical."""
    before = _snapshot(env.repo)
    assert env.run("run-all", dry_run=False) == 0
    assert {r["status"] for r in env.records("judged")} == {"degraded"}
    assert {r["status"] for r in env.records("explain")} <= {"degraded"}
    assert _snapshot(env.repo) == before


def test_stage_run_does_not_write_outside_out_and_ledger(env: Env, tmp_path: Path) -> None:
    """Read-Only Audit Execution: the audit writes only to --out and the ledger
    path; with a dry-run the siblings of the repo are the suites file and out/."""
    assert env.run("run-all") == 0
    assert {p.name for p in tmp_path.iterdir()} <= {"e2e_repo", "out", "suites.json", "ledger"}
    assert not env.ledger.exists()
