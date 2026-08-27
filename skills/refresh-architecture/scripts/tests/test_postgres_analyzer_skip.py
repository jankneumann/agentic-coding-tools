"""The Postgres analyzer must skip inapplicable input instead of failing it.

`refresh_architecture.sh` classified a missing `MIGRATIONS_DIR` as
`fail "postgres_analyzer"`, which increments `ERRORS`, which blocks staged
promotion, which means provenance is never written. A repository whose
migrations are Python (Alembic, Django, Prisma) therefore failed the refresh on
every run — it has nothing the SQL analyzer was built to parse, and "nothing to
do" is not an error.

The TypeScript analyzer in the same script already reached the opposite verdict
for the same condition. These tests pin the resolution recorded in the change's
D5: an absent or non-SQL input root is a loud skip that writes no artifact, and
a *present* root whose analyzer then fails is still a hard failure.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
REFRESH_SH = SCRIPTS_DIR / "refresh_architecture.sh"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_ROW_RE = re.compile(r"^\s{2}(\S+)\s+\[(PASS|FAIL|SKIP|N/A)\]\s*$", re.MULTILINE)
_ERRORS_RE = re.compile(r"^\s*Errors:\s+(\d+)\s*$", re.MULTILINE)


class PipelineRun:
    """Parsed outcome of one `refresh_architecture.sh` invocation."""

    def __init__(self, completed: subprocess.CompletedProcess[str], arch_dir: Path):
        self.stdout = _ANSI_RE.sub("", completed.stdout)
        self.returncode = completed.returncode
        self.arch_dir = arch_dir
        self.results = dict(_ROW_RE.findall(self.stdout))

    @property
    def errors(self) -> int:
        match = _ERRORS_RE.search(self.stdout)
        assert match is not None, f"no error count in pipeline output:\n{self.stdout}"
        return int(match.group(1))

    def result(self, step: str) -> str:
        assert step in self.results, f"no {step} row in pipeline output:\n{self.stdout}"
        return self.results[step]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal repository the pipeline can analyze end to end."""
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "mod.py").write_text(
        '"""Tiny module."""\n\n\ndef hello(name: str) -> str:\n    return f"hi {name}"\n',
        encoding="utf-8",
    )
    return tmp_path


def run_pipeline(
    repo: Path,
    *,
    migrations_dir: str = "migrations",
    scripts_dir: Path = SCRIPTS_DIR,
) -> PipelineRun:
    """Run the refresh in *repo* with Layer 3 and tree-sitter switched off.

    Tree-sitter is disabled so the run's verdicts depend only on the analyzers
    under test, and `--quick` keeps the report layer (which needs no new inputs)
    out of the way.
    """
    arch_dir = repo / "out"
    env = dict(os.environ)
    env.update(
        {
            "ARCH_DIR": "out",
            "PYTHON_SRC_DIR": "src",
            "TS_SRC_DIR": "no-such-typescript-root",
            "MIGRATIONS_DIR": migrations_dir,
            "PYTHON": sys.executable,
            "SCRIPTS_DIR": str(scripts_dir),
            "AUTO_INSTALL_DEPS": "false",
            "TREESITTER_ENABLED": "false",
        }
    )
    completed = subprocess.run(
        ["bash", str(REFRESH_SH), "--quick"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return PipelineRun(completed, arch_dir)


def test_absent_migrations_dir_is_a_skip_not_an_error(repo: Path) -> None:
    """A `MIGRATIONS_DIR` that does not exist must not block promotion.

    This is the failure that made the refresh unrunnable in the measured
    consumer: one absent directory, one incremented `ERRORS`, no provenance.
    """
    run = run_pipeline(repo, migrations_dir="no-such-migrations")

    assert run.result("postgres_analyzer") == "SKIP"
    assert run.errors == 0, run.stdout
    assert run.returncode == 0, run.stdout
    assert not (run.arch_dir / "postgres_analysis.json").exists(), (
        "an absent input root must not be recorded as an empty analysis"
    )
    assert "no-such-migrations" in run.stdout


def test_migrations_dir_without_sql_is_a_skip(repo: Path) -> None:
    """A present root holding a non-SQL migration chain has nothing to parse."""
    migrations = repo / "alembic" / "versions"
    migrations.mkdir(parents=True)
    (migrations / "0001_initial.py").write_text(
        "revision = '0001'\n\n\ndef upgrade():\n    pass\n", encoding="utf-8"
    )
    (migrations / "README").write_text("Alembic migrations.\n", encoding="utf-8")

    run = run_pipeline(repo, migrations_dir="alembic/versions")

    assert run.result("postgres_analyzer") == "SKIP"
    assert run.errors == 0, run.stdout
    assert run.returncode == 0, run.stdout
    assert not (run.arch_dir / "postgres_analysis.json").exists()
    assert "non-SQL migration tool" in run.stdout, (
        "the warning must name the condition, not just the absence of output"
    )


def test_migrations_dir_with_sql_still_runs_the_analyzer(repo: Path) -> None:
    """The configured, applicable case is unchanged — this is the safe default."""
    migrations = repo / "database" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "001_create_users.sql").write_text(
        "CREATE TABLE users (\n  id SERIAL PRIMARY KEY,\n  email TEXT NOT NULL\n);\n",
        encoding="utf-8",
    )

    run = run_pipeline(repo, migrations_dir="database/migrations")

    assert run.result("postgres_analyzer") == "PASS", run.stdout
    assert run.errors == 0, run.stdout
    assert (run.arch_dir / "postgres_analysis.json").exists()


def test_sql_present_and_analyzer_failing_is_still_a_hard_fail(
    repo: Path, tmp_path: Path
) -> None:
    """Skip is for inapplicable input, never for a broken analyzer.

    The scripts directory is copied so only `analyze_postgres.py` is replaced by
    a stub that exits 1; every other stage runs the real code. Other stages may
    warn (the copy is not a skill tree, so the sibling-skill validator lookup
    misses), which is why this asserts on the Postgres verdict and the exit
    code rather than on the total error count.
    """
    stub_scripts = tmp_path / "stub_scripts"
    shutil.copytree(
        SCRIPTS_DIR,
        stub_scripts,
        ignore=shutil.ignore_patterns("tests", "__pycache__", ".venv"),
    )
    (stub_scripts / "analyze_postgres.py").write_text(
        "import sys\n\nprint('stub analyzer failing', file=sys.stderr)\nsys.exit(1)\n",
        encoding="utf-8",
    )

    migrations = repo / "database" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "001_create_users.sql").write_text(
        "CREATE TABLE users (id SERIAL PRIMARY KEY);\n", encoding="utf-8"
    )

    run = run_pipeline(repo, migrations_dir="database/migrations", scripts_dir=stub_scripts)

    assert run.result("postgres_analyzer") == "FAIL", run.stdout
    assert run.errors >= 1
    assert run.returncode == 1, run.stdout
