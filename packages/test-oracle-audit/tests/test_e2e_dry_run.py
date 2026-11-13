"""End-to-end dry-run of the whole audit pipeline (task 8.1, wp-integration).

Expectations come from the spec ("Oracle-Source Vocabulary and Label Ledger",
"Read-Only Audit Execution", and the degraded behaviour of each stage
requirement) and from design D1/D3/D15 only. ``cli.py`` does not exist yet, so
this module also fixes the CLI surface it relies on:

    test_oracle_audit.cli.main(argv) -> int
    global options (given before the subcommand):
        --repo-root PATH  --suites-file PATH  --suite NAME  --out DIR
        --dry-run  --python PATH  --max-mutants N  --seed N  --ledger PATH
    subcommand ``run-all`` writes <out>/<stage>.jsonl for the seven stages
    (inventory, static, judged, mutation, rename, history, explain),
    <out>/analysis.json and <out>/report.md, and exits 0 regardless of findings.

The audited project is ``tests/fixtures/e2e_repo``; the suites file is written
into a temp dir and points at it. Audited pytest runs with the current
interpreter (``--python sys.executable``), so no ``uv`` and no network are used.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SUITE = "e2e"
SEED = 7
STAGE_FILES = (
    "inventory",
    "static",
    "judged",
    "mutation",
    "rename",
    "history",
    "explain",
)
ASSERTION_FREE_TEST = "test_add_runs_without_checking"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


# --------------------------------------------------------------------- helpers


def _git(cwd: Path, *args: str) -> str:
    env = dict(GIT_ENV, HOME=str(cwd))
    done = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env
    )
    return done.stdout


def snapshot(root: Path) -> dict[str, str]:
    """sha256 of every file under ``root`` except the ``.git`` directory."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            out[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return out


def write_suites_file(path: Path) -> Path:
    spec = {
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
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return path


def cli_main(argv: list[str]) -> int:
    cli = importlib.import_module("test_oracle_audit.cli")
    return cli.main(argv)


def global_args(repo: Path, suites_file: Path, out: Path, ledger: Path) -> list[str]:
    return [
        "--repo-root", str(repo),
        "--suites-file", str(suites_file),
        "--suite", SUITE,
        "--out", str(out),
        "--python", sys.executable,
        "--max-mutants", "6",
        "--seed", str(SEED),
        "--ledger", str(ledger),
    ]  # fmt: skip


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def short_name(node_id: str) -> str:
    return node_id.split("::")[-1].split("[")[0]


def make_repo(dest: Path) -> Path:
    shutil.copytree(FIXTURES / "e2e_repo", dest)
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "fixture: initial commit")
    return dest


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No keys, no network, and no bytecode written into the audited tree."""
    for name in ("TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """Run ``run-all --dry-run`` once over a fresh copy of the fixture repo."""
    mp = pytest.MonkeyPatch()
    for name in ("TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        mp.delenv(name, raising=False)
    mp.setenv("PYTHONDONTWRITEBYTECODE", "1")
    try:
        tmp = tmp_path_factory.mktemp("e2e")
        repo = make_repo(tmp / "repo")
        suites_file = write_suites_file(tmp / "suites.json")
        out = tmp / "out"
        ledger = tmp / "ledger" / "labels.json"
        before = snapshot(repo)
        argv = [*global_args(repo, suites_file, out, ledger), "--dry-run", "run-all"]
        code = cli_main(argv)
        return SimpleNamespace(
            tmp=tmp, repo=repo, out=out, suites_file=suites_file, ledger=ledger,
            before=before, after=snapshot(repo), code=code,
        )  # fmt: skip
    finally:
        mp.undo()


# ------------------------------------------------------------------------ tests


def test_run_all_dry_run_exits_zero_and_writes_every_artifact(pipeline: SimpleNamespace) -> None:
    """test-oracle-audit.6 (full pipeline), D15 (CI dry-run with no keys): every
    stage runs, exit code is 0 although the fixture has findings, and all
    outputs land in --out."""
    assert pipeline.code == 0
    for stage in STAGE_FILES:
        assert (pipeline.out / f"{stage}.jsonl").is_file(), stage
    assert (pipeline.out / "analysis.json").is_file()
    assert (pipeline.out / "report.md").is_file()


def test_full_pipeline_leaves_working_tree_clean(pipeline: SimpleNamespace) -> None:
    """test-oracle-audit.6 "Full pipeline leaves the working tree clean": after
    every stage ran in dry-run, git status --porcelain is empty (untracked files
    included)."""
    assert pipeline.code == 0
    assert _git(pipeline.repo, "status", "--porcelain").strip() == ""


def test_pipeline_leaves_no_isolated_copy_behind(pipeline: SimpleNamespace) -> None:
    """test-oracle-audit.6 "Isolated copy is removed" and D3: after the mutation
    and rename stages return, no extra git worktree is registered."""
    assert pipeline.code == 0
    listing = _git(pipeline.repo, "worktree", "list", "--porcelain")
    assert listing.count("worktree ") == 1


def test_test_files_and_pytest_config_are_untouched(pipeline: SimpleNamespace) -> None:
    """test-oracle-audit.5 "Audit leaves test files and pytest configuration
    untouched": no test file, conftest.py, pyproject.toml or pytest.ini changes."""
    assert pipeline.code == 0
    protected = [
        p
        for p in pipeline.before
        if p.startswith("tests/") or p in {"pyproject.toml", "pytest.ini"}
    ]
    assert "tests/conftest.py" in protected and "pyproject.toml" in protected
    assert {p: pipeline.after.get(p) for p in protected} == {p: pipeline.before[p] for p in protected}


def test_audited_tree_is_byte_identical_after_the_run(pipeline: SimpleNamespace) -> None:
    """test-oracle-audit.6 (read-only execution): the audit writes only to --out
    and the ledger path, so the audited repository is byte-identical afterwards
    (sources included, no new files)."""
    assert pipeline.code == 0
    assert pipeline.after == pipeline.before


def test_audit_writes_only_to_out_and_ledger_path(pipeline: SimpleNamespace) -> None:
    """test-oracle-audit.6 (Read-Only Audit Execution): outside the repo, only
    --out is created; a dry-run pipeline never creates the label ledger."""
    assert pipeline.code == 0
    entries = {p.name for p in pipeline.tmp.iterdir()}
    assert entries <= {"repo", "out", "suites.json", "ledger"}
    assert not pipeline.ledger.exists()


def test_every_jsonl_line_validates_against_stage_record(
    pipeline: SimpleNamespace, schema_validator: Any
) -> None:
    """test-oracle-audit.6 / D1 (record contract): every line of every stage's
    jsonl validates against the stage-record schema and names its own stage."""
    assert pipeline.code == 0
    for stage in STAGE_FILES:
        records = read_jsonl(pipeline.out / f"{stage}.jsonl")
        assert records, f"{stage}.jsonl is empty"
        for record in records:
            schema_validator(record)
            assert record["stage"] == stage


def test_stage_records_join_on_the_inventory(pipeline: SimpleNamespace) -> None:
    """D1 "Joining": every per-test stage keys its records by test ids that the
    inventory produced (same node id and content hash). Explain covers a subset."""
    inventory = {
        (r["test_id"]["node_id"], r["test_id"]["content_hash"])
        for r in read_jsonl(pipeline.out / "inventory.jsonl")
    }
    # test_calc: 4 tests, test_text: 1 + 2 parametrized cases
    assert len(inventory) == 7
    for stage in ("static", "judged", "mutation", "rename", "history"):
        ids = {
            (r["test_id"]["node_id"], r["test_id"]["content_hash"])
            for r in read_jsonl(pipeline.out / f"{stage}.jsonl")
        }
        assert ids == inventory, stage
    explained = {
        (r["test_id"]["node_id"], r["test_id"]["content_hash"])
        for r in read_jsonl(pipeline.out / "explain.jsonl")
    }
    assert explained <= inventory


def test_parametrized_cases_share_one_content_hash(pipeline: SimpleNamespace) -> None:
    """Test Inventory "Parametrized tests are distinct entries sharing one content
    hash", observed through the CLI output."""
    cases = [
        r["test_id"]
        for r in read_jsonl(pipeline.out / "inventory.jsonl")
        if short_name(r["test_id"]["node_id"]) == "test_shout_appends_bang"
    ]
    assert len(cases) == 2
    assert len({c["node_id"] for c in cases}) == 2
    assert len({c["content_hash"] for c in cases}) == 1


def test_static_stage_flags_the_assertion_free_test_only(pipeline: SimpleNamespace) -> None:
    """Static "Assertion-free test is flagged" and "Behaviour-only test fires no
    rule", observed via the CLI; findings do not change the exit code (0)."""
    assert pipeline.code == 0
    rules = {
        short_name(r["test_id"]["node_id"]): set(r["payload"].get("rules", []))
        for r in read_jsonl(pipeline.out / "static.jsonl")
    }
    assert "assertion_free" in rules[ASSERTION_FREE_TEST]
    assert "assertion_free" not in rules["test_add_sums_integers"]
    assert "assertion_free" not in rules["test_clamp_limits_value"]


def test_judged_records_are_degraded_in_dry_run(pipeline: SimpleNamespace) -> None:
    """Judged "Missing key degrades without failing": with --dry-run and no key,
    every judged record is degraded with a reason, carries evidence_class
    judgment, and the run exits 0."""
    assert pipeline.code == 0
    records = read_jsonl(pipeline.out / "judged.jsonl")
    assert records
    for record in records:
        assert record["status"] == "degraded"
        assert record["reason"]
        assert record["evidence_class"] == "judgment"


def test_explain_records_degrade_with_no_backend(pipeline: SimpleNamespace) -> None:
    """Explanations "No backend degrades": each flagged test (the assertion-free
    one at minimum) has an explain record with status degraded, reason no_backend."""
    records = read_jsonl(pipeline.out / "explain.jsonl")
    assert records
    for record in records:
        assert record["status"] == "degraded"
        assert record["reason"] == "no_backend"
    assert ASSERTION_FREE_TEST in {short_name(r["test_id"]["node_id"]) for r in records}


def test_history_for_a_single_commit_repo_has_no_co_change_ratio(pipeline: SimpleNamespace) -> None:
    """History "Small denominator is insufficient" (fewer than three commits touch
    the covered modules); a non-shallow repo does not degrade for shallow_history."""
    records = read_jsonl(pipeline.out / "history.jsonl")
    assert records
    for record in records:
        if record["status"] == "ok":
            assert record["payload"]["co_change_ratio"] == "insufficient"
            assert record["payload"]["added_with_fix"] is False
        else:
            assert record["status"] == "degraded"
            assert record["reason"] != "shallow_history"


def test_mutation_and_rename_stages_record_every_test(pipeline: SimpleNamespace) -> None:
    """Mutation/Refactor stages never abort the pipeline: each test has a record
    whose status is a legal one and which carries a reason unless ok."""
    for stage in ("mutation", "rename"):
        for record in read_jsonl(pipeline.out / f"{stage}.jsonl"):
            assert record["status"] in {"ok", "degraded", "skipped", "error"}
            if record["status"] != "ok":
                assert record["reason"]


def test_analysis_json_validates_against_analysis_report_schema(
    pipeline: SimpleNamespace, schema_validator: Any
) -> None:
    """Pilot Report / Agreement and Predictive Analysis: analysis.json validates
    against the analysis-report schema, is advisory, and records suite and seed."""
    analysis = json.loads((pipeline.out / "analysis.json").read_text(encoding="utf-8"))
    schema_validator(analysis, "analysis-report")
    assert analysis["advisory"] is True
    assert analysis["suites"] == [SUITE]
    assert analysis["seed"] == SEED


def test_analysis_marks_judged_approach_not_run_with_degraded_count(
    pipeline: SimpleNamespace,
) -> None:
    """Pilot Report "Degraded stages are visible": the judged approach is present,
    marked not_run, with its degraded count rather than being omitted."""
    analysis = json.loads((pipeline.out / "analysis.json").read_text(encoding="utf-8"))
    judged_keys = [k for k in analysis["approach_coverage"] if "judg" in k.lower()]
    assert judged_keys, "judged approach missing from approach_coverage"
    cov = analysis["approach_coverage"][judged_keys[0]]
    assert cov["not_run"] is True
    assert cov["ok"] == 0
    assert cov["degraded"] == 7


def test_analysis_open_decisions_cover_ratchet_and_marker_question(
    pipeline: SimpleNamespace,
) -> None:
    """Pilot Report "Open decisions are recorded": analysis.json lists at least the
    coverage-ratchet and in-file-marker decisions."""
    analysis = json.loads((pipeline.out / "analysis.json").read_text(encoding="utf-8"))
    text = json.dumps(analysis["open_decisions"]).lower()
    assert "ratchet" in text
    assert "marker" in text


def test_report_states_advisory_status_on_first_line(pipeline: SimpleNamespace) -> None:
    """Pilot Report "Report states its advisory status": the first line declares
    the report advisory and not a gate."""
    first = (pipeline.out / "report.md").read_text(encoding="utf-8").splitlines()[0].lower()
    assert "advisory" in first
    assert "gate" in first


def test_report_shows_judged_as_not_run_and_lists_open_decisions(
    pipeline: SimpleNamespace,
) -> None:
    """Pilot Report "Degraded stages are visible" and "Open decisions are
    recorded": judged appears as `not run`; the Open decisions section names the
    ratchet options and the in-file-marker question."""
    text = (pipeline.out / "report.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "not run" in lowered
    assert "open decisions" in lowered
    for needle in ("keep", "deletion manifest", "mutation-score ratchet", "marker"):
        assert needle in lowered, needle


def test_run_all_is_deterministic_for_a_fixed_seed(tmp_path: Path) -> None:
    """Inventory "Inventory is deterministic" and Mutation "Seeded sampling is
    reproducible", observed end to end: two dry runs with the same seed produce
    identical inventory and static files."""
    suites_file = write_suites_file(tmp_path / "suites.json")
    outs = []
    for i in (1, 2):
        repo = make_repo(tmp_path / f"repo{i}")
        out = tmp_path / f"out{i}"
        argv = [*global_args(repo, suites_file, out, tmp_path / "labels.json"), "--dry-run", "run-all"]
        assert cli_main(argv) == 0
        outs.append(out)
    for stage in ("inventory", "static"):
        a = (outs[0] / f"{stage}.jsonl").read_bytes()
        b = (outs[1] / f"{stage}.jsonl").read_bytes()
        assert a == b, stage
