"""ORM metadata as an optional SQL schema source (D7).

A repository whose migrations are Python (Alembic) has nothing the SQL analyzers
parse. After the D5 skip landed it no longer *fails* the refresh, but it still
gets no schema analysis at all. `SCHEMA_SOURCE=sqlalchemy` gives it one: the
declared `MetaData` is compiled to `CREATE TABLE` DDL, written into a staging
directory, and handed to the existing SQL analyzers unchanged. No migration
replay, and — the property these tests pin hardest — no database connection.

Three invariants are load-bearing and each has its own test:

* **The default is untouched.** `SCHEMA_SOURCE` unset must leave `MIGRATIONS_DIR`
  handling byte-identical to the pipeline before this branch existed, because
  that is the path every existing caller takes.
* **Nothing dials a database.** The dumper reads declared metadata. The
  no-connection test runs it with `socket.socket.connect` replaced by a raising
  stub, so a connection attempt is an observed failure rather than an assumption.
* **An inapplicable source skips.** An unimportable target, or a `MetaData` with
  no tables, is a loud skip that writes no file — never a crash, and never a
  degenerate artifact that a later analyzer would "successfully" analyse.

`sqlalchemy` is an optional dependency of this repository. Tests that need it
resolve an interpreter that can import it (`ARCH_SQLALCHEMY_PYTHON`, else the
running interpreter) and skip when there is none; the tests that pin the skip
and default-unchanged behaviour need no SQLAlchemy at all and always run.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
REFRESH_SH = SCRIPTS_DIR / "refresh_architecture.sh"
DUMPER = SCRIPTS_DIR / "dump_sqlalchemy_schema.py"

EXIT_SKIP = 3

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_ROW_RE = re.compile(r"^\s{2}(\S+)\s+\[(PASS|FAIL|SKIP|N/A)\]\s*$", re.MULTILINE)
_ERRORS_RE = re.compile(r"^\s*Errors:\s+(\d+)\s*$", re.MULTILINE)
_ELAPSED_RE = re.compile(r"^\s*Elapsed:\s+\d+s\s*$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# Interpreter resolution
# --------------------------------------------------------------------------- #
def _has_sqlalchemy(interpreter: str) -> bool:
    return (
        subprocess.run(
            [interpreter, "-c", "import sqlalchemy"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _sqlalchemy_interpreter() -> str | None:
    """An interpreter that can import SQLAlchemy, or None.

    `ARCH_SQLALCHEMY_PYTHON` exists because the ORM source is imported by the
    *consumer's* interpreter, not the analysis one — a repository whose models
    need its application venv points the pipeline at that venv the same way.
    """
    for candidate in (os.environ.get("ARCH_SQLALCHEMY_PYTHON"), sys.executable):
        if candidate and _has_sqlalchemy(candidate):
            return candidate
    return None


@pytest.fixture(scope="module")
def sa_python() -> str:
    interpreter = _sqlalchemy_interpreter()
    if interpreter is None:
        pytest.skip(
            "sqlalchemy is an optional dependency and no interpreter here can "
            "import it (set ARCH_SQLALCHEMY_PYTHON to one that can)"
        )
    return interpreter


# --------------------------------------------------------------------------- #
# Fixtures: a tiny repository with SQLAlchemy models
# --------------------------------------------------------------------------- #
MODELS_SRC = '''\
"""Declared schema — no engine, no connection, no migrations."""

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(255), nullable=False),
)

orders = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("total_cents", Integer, nullable=False),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("note", String(1024)),
)
'''

DECLARATIVE_SRC = '''\
"""The shape most consumers hand over: a declarative Base, not a MetaData."""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Widget(Base):
    __tablename__ = "widgets"

    id = Column(Integer, primary_key=True)
    label = Column(String(64), nullable=False)
'''

EMPTY_METADATA_SRC = '''\
"""A MetaData that declares nothing — the degenerate-artifact case."""

from sqlalchemy import MetaData

metadata = MetaData()
'''

BROKEN_MODELS_SRC = '''\
"""Import-time failure, the way a consumer's settings module fails."""

import no_such_settings_module  # noqa: F401

metadata = None
'''

# Blocks every outbound connection for the interpreter that imports it. Placed
# on PYTHONPATH, `sitecustomize` is imported at startup before the dumper runs,
# so a database connection attempt raises instead of quietly succeeding.
SITECUSTOMIZE_SRC = '''\
import socket


def _forbid(*args, **kwargs):
    raise RuntimeError("BLOCKED: the schema dumper attempted a network connection")


socket.socket.connect = _forbid
socket.socket.connect_ex = _forbid
socket.create_connection = _forbid
'''


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


@pytest.fixture
def models_repo(repo: Path) -> Path:
    (repo / "models.py").write_text(MODELS_SRC, encoding="utf-8")
    return repo


def run_dumper(
    interpreter: str,
    cwd: Path,
    *,
    target: str,
    output: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [
            interpreter,
            str(DUMPER),
            "--target",
            target,
            "--output",
            str(output),
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------------- #
# 3.1 — the dumper emits DDL, in a subprocess, without a database
# --------------------------------------------------------------------------- #
def test_dumper_emits_one_create_table_per_declared_table(
    sa_python: str, models_repo: Path
) -> None:
    out = models_repo / "schema" / "0001_schema.sql"

    result = run_dumper(sa_python, models_repo, target="models:metadata", output=out)

    assert result.returncode == 0, result.stderr
    ddl = out.read_text(encoding="utf-8")
    statements = re.findall(r"CREATE TABLE\s+(\w+)", ddl)
    assert sorted(statements) == ["audit_log", "orders", "users"], ddl
    assert "email VARCHAR(255) NOT NULL" in ddl
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in ddl


def test_dumper_accepts_a_declarative_base_target(sa_python: str, repo: Path) -> None:
    """Consumers hand over `app.models:Base`, not its `.metadata`."""
    (repo / "declarative.py").write_text(DECLARATIVE_SRC, encoding="utf-8")
    out = repo / "schema" / "0001_schema.sql"

    result = run_dumper(sa_python, repo, target="declarative:Base", output=out)

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE widgets" in out.read_text(encoding="utf-8")


def test_dumper_opens_no_database_connection(
    sa_python: str, models_repo: Path, tmp_path: Path
) -> None:
    """Proven, not assumed: connect() raises for the duration of the run.

    Every database driver reaches the network through `socket` — TCP or a Unix
    socket alike — so replacing `connect` with a raising stub turns any dial
    attempt into a non-zero exit carrying BLOCKED. A clean run under that stub
    is evidence the dumper reads declared metadata and nothing else.
    """
    guard = tmp_path / "no_network"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(SITECUSTOMIZE_SRC, encoding="utf-8")
    out = models_repo / "schema" / "0001_schema.sql"

    result = run_dumper(
        sa_python,
        models_repo,
        target="models:metadata",
        output=out,
        extra_env={"PYTHONPATH": str(guard)},
    )

    assert "BLOCKED" not in result.stdout + result.stderr, (
        "the dumper attempted a connection:\n" + result.stderr
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE users" in out.read_text(encoding="utf-8")


def test_metadata_without_tables_writes_no_file(sa_python: str, repo: Path) -> None:
    """Zero tables is a skip, never an empty artifact.

    An empty DDL file analyses "successfully" into zero tables, which is
    indistinguishable from a real result and would make every later byte
    comparison agree with itself forever. Writing nothing keeps the absence
    visible.
    """
    (repo / "empty_models.py").write_text(EMPTY_METADATA_SRC, encoding="utf-8")
    out = repo / "schema" / "0001_schema.sql"

    result = run_dumper(sa_python, repo, target="empty_models:metadata", output=out)

    assert result.returncode == EXIT_SKIP, result.stderr
    assert not out.exists(), "an empty MetaData must not produce a DDL file"
    assert "no tables" in result.stderr.lower(), result.stderr


# --------------------------------------------------------------------------- #
# 3.2 — an unimportable source skips, carrying the error
# --------------------------------------------------------------------------- #
def test_unimportable_target_is_a_skip_carrying_the_import_error(
    sa_python: str, repo: Path
) -> None:
    (repo / "broken_models.py").write_text(BROKEN_MODELS_SRC, encoding="utf-8")
    out = repo / "schema" / "0001_schema.sql"

    result = run_dumper(sa_python, repo, target="broken_models:metadata", output=out)

    assert result.returncode == EXIT_SKIP, result.stdout + result.stderr
    assert not out.exists()
    assert "no_such_settings_module" in result.stderr, (
        "the operator cannot act on a skip that hides the import error:\n"
        + result.stderr
    )


def test_absent_target_attribute_is_a_skip(sa_python: str, models_repo: Path) -> None:
    out = models_repo / "schema" / "0001_schema.sql"

    result = run_dumper(sa_python, models_repo, target="models:nonexistent", output=out)

    assert result.returncode == EXIT_SKIP, result.stdout + result.stderr
    assert not out.exists()
    assert "nonexistent" in result.stderr


def test_missing_sqlalchemy_is_a_skip_not_a_crash(repo: Path, tmp_path: Path) -> None:
    """SQLAlchemy is optional; its absence must not traceback.

    The stub package shadows any real install, so this test exercises the
    same branch on a machine that has SQLAlchemy and one that does not.
    """
    shadow = tmp_path / "shadow"
    (shadow / "sqlalchemy").mkdir(parents=True)
    (shadow / "sqlalchemy" / "__init__.py").write_text(
        'raise ImportError("simulated missing sqlalchemy")\n', encoding="utf-8"
    )
    (repo / "models.py").write_text(MODELS_SRC, encoding="utf-8")
    out = repo / "schema" / "0001_schema.sql"

    result = run_dumper(
        sys.executable,
        repo,
        target="models:metadata",
        output=out,
        extra_env={"PYTHONPATH": str(shadow)},
    )

    assert result.returncode == EXIT_SKIP, result.stdout + result.stderr
    assert not out.exists()
    assert "sqlalchemy" in result.stderr.lower()
    assert "Traceback (most recent call last)" not in result.stdout


# --------------------------------------------------------------------------- #
# Pipeline wiring
# --------------------------------------------------------------------------- #
class PipelineRun:
    """Parsed outcome of one `refresh_architecture.sh` invocation."""

    def __init__(self, completed: subprocess.CompletedProcess[str], arch_dir: Path):
        self.stdout = _ANSI_RE.sub("", completed.stdout)
        self.stderr = completed.stderr
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


def run_pipeline(
    repo: Path,
    *,
    migrations_dir: str = "migrations",
    scripts_dir: Path = SCRIPTS_DIR,
    script: Path = REFRESH_SH,
    extra_env: dict[str, str] | None = None,
) -> PipelineRun:
    env = dict(os.environ)
    for key in ("SCHEMA_SOURCE", "SCHEMA_TARGET", "SCHEMA_SOURCE_DIR", "SCHEMA_SOURCE_PYTHON"):
        env.pop(key, None)
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
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        ["bash", str(script), "--quick"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return PipelineRun(completed, repo / "out")


@pytest.fixture
def alembic_repo(models_repo: Path) -> Path:
    """Models in Python, migrations in Python — the case D7 exists for."""
    versions = models_repo / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_initial.py").write_text(
        "revision = '0001'\n\n\ndef upgrade():\n    pass\n", encoding="utf-8"
    )
    return models_repo


def test_pipeline_with_sqlalchemy_source_analyzes_the_orm_schema(
    sa_python: str, alembic_repo: Path
) -> None:
    """The whole point: an Alembic repository gets a Postgres analysis."""
    run = run_pipeline(
        alembic_repo,
        migrations_dir="alembic/versions",
        extra_env={
            "SCHEMA_SOURCE": "sqlalchemy",
            "SCHEMA_TARGET": "models:metadata",
            "SCHEMA_SOURCE_PYTHON": sa_python,
        },
    )

    assert run.result("schema_source") == "PASS", run.stdout
    assert run.result("postgres_analyzer") == "PASS", run.stdout
    assert run.errors == 0, run.stdout
    assert run.returncode == 0, run.stdout

    analysis = (run.arch_dir / "postgres_analysis.json").read_text(encoding="utf-8")
    for table in ("users", "orders", "audit_log"):
        assert table in analysis, f"{table} missing from the analysis:\n{analysis[:2000]}"


def test_pipeline_unimportable_target_skips_and_still_promotes(
    alembic_repo: Path,
) -> None:
    """The source is inapplicable; the pipeline continues and exits clean."""
    run = run_pipeline(
        alembic_repo,
        migrations_dir="alembic/versions",
        extra_env={
            "SCHEMA_SOURCE": "sqlalchemy",
            "SCHEMA_TARGET": "no_such_models:metadata",
        },
    )

    assert run.result("schema_source") == "SKIP", run.stdout
    assert run.result("postgres_analyzer") == "SKIP", run.stdout
    assert run.errors == 0, run.stdout
    assert run.returncode == 0, run.stdout
    assert not (run.arch_dir / "postgres_analysis.json").exists()
    assert "no_such_models" in run.stdout, (
        "the pipeline must surface the import error, not just the skip:\n" + run.stdout
    )


# --------------------------------------------------------------------------- #
# 3.2 — `SCHEMA_SOURCE` unset changes nothing (Rule 4, safe defaults)
# --------------------------------------------------------------------------- #
SENTINEL_DUMPER = """\
import os
import pathlib
import sys

pathlib.Path(os.environ["DUMPER_SENTINEL"]).write_text("invoked", encoding="utf-8")
sys.exit(3)
"""


@pytest.fixture
def stub_scripts(tmp_path: Path) -> Path:
    """A copy of the scripts tree whose dumper only records that it ran."""
    stub = tmp_path / "stub_scripts"
    shutil.copytree(
        SCRIPTS_DIR,
        stub,
        ignore=shutil.ignore_patterns("tests", "__pycache__", ".venv"),
    )
    (stub / "dump_sqlalchemy_schema.py").write_text(SENTINEL_DUMPER, encoding="utf-8")
    return stub


def test_default_run_never_invokes_the_schema_dumper(
    alembic_repo: Path, stub_scripts: Path, tmp_path: Path
) -> None:
    """With `SCHEMA_SOURCE` unset the ORM branch must not exist at runtime.

    The positive control matters as much as the negative one: a sentinel that
    never fires proves nothing unless it fires when the source *is* configured.
    """
    sentinel = tmp_path / "dumper-was-invoked"

    default_run = run_pipeline(
        alembic_repo,
        migrations_dir="alembic/versions",
        scripts_dir=stub_scripts,
        extra_env={"DUMPER_SENTINEL": str(sentinel)},
    )

    assert not sentinel.exists(), "the default path must not run the ORM dumper"
    assert "schema_source" not in default_run.results, (
        "an unset SCHEMA_SOURCE must not add a row to the summary:\n"
        + default_run.stdout
    )
    assert default_run.result("postgres_analyzer") == "SKIP", default_run.stdout

    configured_run = run_pipeline(
        alembic_repo,
        migrations_dir="alembic/versions",
        scripts_dir=stub_scripts,
        extra_env={
            "DUMPER_SENTINEL": str(sentinel),
            "SCHEMA_SOURCE": "sqlalchemy",
            "SCHEMA_TARGET": "models:metadata",
        },
    )

    assert sentinel.exists(), "the configured path must run the ORM dumper"
    assert configured_run.result("schema_source") == "SKIP", configured_run.stdout


def _git(args: list[str], cwd: Path) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else None


def _pre_change_script(limit: int = 25) -> str | None:
    """The newest revision of the pipeline script that predates this branch.

    Identified by content, not by a pinned SHA: the newest commit touching the
    file whose blob knows nothing about `SCHEMA_SOURCE`. That keeps the baseline
    correct as the file keeps changing for other reasons.
    """
    root = _git(["rev-parse", "--show-toplevel"], SCRIPTS_DIR)
    if not root:
        return None
    repo_root = Path(root.strip())
    rel = REFRESH_SH.relative_to(repo_root).as_posix()
    log = _git(["log", f"-{limit}", "--format=%H", "--", rel], repo_root)
    if not log:
        return None
    for sha in log.split():
        blob = _git(["show", f"{sha}:{rel}"], repo_root)
        if blob and "SCHEMA_SOURCE" not in blob:
            return blob
    return None


def _digests(directory: Path) -> dict[str, str]:
    return {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def test_default_run_is_byte_identical_to_the_pre_change_pipeline(
    repo: Path, tmp_path: Path
) -> None:
    """Rule 4, pinned against the actual previous script rather than a promise.

    Both runs use the same working directory, the same interpreter and a fixed
    `SOURCE_DATE_EPOCH`, so the artifacts are comparable byte for byte and the
    normalized transcripts are comparable line for line.
    """
    baseline_src = _pre_change_script()
    if baseline_src is None:
        pytest.skip("no pre-change revision of refresh_architecture.sh reachable here")
    baseline = tmp_path / "baseline_refresh.sh"
    baseline.write_text(baseline_src, encoding="utf-8")

    migrations = repo / "database" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "001_create_users.sql").write_text(
        "CREATE TABLE users (\n  id SERIAL PRIMARY KEY,\n  email TEXT NOT NULL\n);\n",
        encoding="utf-8",
    )
    env = {"SOURCE_DATE_EPOCH": "1700000000"}

    before = run_pipeline(
        repo, migrations_dir="database/migrations", script=baseline, extra_env=env
    )
    before_digests = _digests(before.arch_dir)
    shutil.rmtree(before.arch_dir)

    after = run_pipeline(
        repo, migrations_dir="database/migrations", script=REFRESH_SH, extra_env=env
    )

    assert after.returncode == before.returncode
    assert _digests(after.arch_dir) == before_digests, (
        "SCHEMA_SOURCE unset must produce the same artifact bytes as before"
    )
    assert _ELAPSED_RE.sub("", after.stdout) == _ELAPSED_RE.sub("", before.stdout), (
        "SCHEMA_SOURCE unset must produce the same transcript as before"
    )
