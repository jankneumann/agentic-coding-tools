"""Tests for NeonBranchEnvironment.

TDD test-first: these tests define the expected behavior for:
- NeonBranchEnvironment protocol compliance
- Branch creation via neonctl CLI
- Neon-to-Neon branching with source_branch_id
- Migrations seeding strategy
- Missing credentials handling
- wait_ready polling via psql
- Teardown via neonctl branches delete
- Idempotent teardown
- env_vars before and after start
- neonctl failure handling
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Protocol compliance tests
# ---------------------------------------------------------------------------


class TestNeonBranchProtocolCompliance:
    """NeonBranchEnvironment must satisfy TestEnvironment protocol."""

    def test_satisfies_test_environment(self) -> None:
        from environments.neon_branch import NeonBranchEnvironment
        from environments.protocol import TestEnvironment

        env = NeonBranchEnvironment.__new__(NeonBranchEnvironment)
        assert callable(getattr(env, "start", None))
        assert callable(getattr(env, "wait_ready", None))
        assert callable(getattr(env, "teardown", None))
        assert callable(getattr(env, "env_vars", None))

    def test_isinstance_test_environment(self) -> None:
        from environments.neon_branch import NeonBranchEnvironment
        from environments.protocol import TestEnvironment

        env = NeonBranchEnvironment.__new__(NeonBranchEnvironment)
        assert isinstance(env, TestEnvironment)


# ---------------------------------------------------------------------------
# Prerequisites tests
# ---------------------------------------------------------------------------


class TestNeonPrerequisites:
    """NeonBranchEnvironment requires neonctl, NEON_PROJECT_ID, NEON_API_KEY."""

    @patch.dict("os.environ", {}, clear=True)
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    def test_missing_project_id_raises(self, mock_which: MagicMock) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        env = NeonBranchEnvironment()
        with pytest.raises(RuntimeError, match="NEON_PROJECT_ID"):
            env.start()

    @patch.dict("os.environ", {"NEON_PROJECT_ID": "proj-123"}, clear=True)
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    def test_missing_api_key_raises(self, mock_which: MagicMock) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        env = NeonBranchEnvironment()
        with pytest.raises(RuntimeError, match="NEON_API_KEY"):
            env.start()

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value=None)
    def test_missing_neonctl_raises(self, mock_which: MagicMock) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        env = NeonBranchEnvironment()
        with pytest.raises(RuntimeError, match="neonctl"):
            env.start()


# ---------------------------------------------------------------------------
# Branch creation tests
# ---------------------------------------------------------------------------


NEON_CREATE_RESPONSE = json.dumps(
    {
        "branch": {
            "id": "br-test-12345",
            "name": "br-test-12345",
            "project_id": "proj-123",
        },
        "connection_uri": "postgresql://user:pass@ep-test-12345.us-east-2.aws.neon.tech/neondb",
        "endpoints": [
            {
                "host": "ep-test-12345.us-east-2.aws.neon.tech",
            }
        ],
    }
)


def _make_neonctl_result(
    stdout: str = NEON_CREATE_RESPONSE,
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["neonctl"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _make_psql_result(
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["psql"],
        returncode=returncode,
        stdout="1\n",
        stderr=stderr,
    )


class TestBranchCreation:
    """Test neonctl branches create invocation."""

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_creates_branch_with_neonctl(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()
        env = NeonBranchEnvironment(seed_strategy="migrations")
        env.start()

        # Find the neonctl call
        neonctl_calls = [
            c for c in mock_run.call_args_list if "neonctl" in str(c)
        ]
        assert len(neonctl_calls) >= 1
        cmd = neonctl_calls[0].args[0] if neonctl_calls[0].args else neonctl_calls[0].kwargs["args"]
        assert "branches" in cmd
        assert "create" in cmd
        assert "--project-id" in cmd
        assert "proj-123" in cmd
        assert "--output" in cmd
        assert "json" in cmd

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_creates_branch_from_parent(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Neon-to-Neon branching: passes --parent flag."""
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()
        env = NeonBranchEnvironment(
            seed_strategy="migrations",
            source_branch_id="br-source-999",
        )
        env.start()

        neonctl_calls = [
            c for c in mock_run.call_args_list if "neonctl" in str(c)
        ]
        cmd = neonctl_calls[0].args[0] if neonctl_calls[0].args else neonctl_calls[0].kwargs["args"]
        assert "--parent" in cmd
        assert "br-source-999" in cmd

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_neonctl_failure_raises_runtime_error(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """neonctl stderr included in RuntimeError message."""
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result(
            returncode=1,
            stderr="ERROR: invalid API key",
            stdout="",
        )
        env = NeonBranchEnvironment()
        with pytest.raises(RuntimeError, match="invalid API key"):
            env.start()

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_stores_branch_id_and_connection_uri(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()
        env = NeonBranchEnvironment(seed_strategy="migrations")
        env.start()

        assert env._branch_id == "br-test-12345"
        assert "ep-test-12345" in (env._connection_uri or "")


# ---------------------------------------------------------------------------
# wait_ready tests
# ---------------------------------------------------------------------------


class TestWaitReady:
    """wait_ready polls psql -c 'SELECT 1' at 2-second intervals."""

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_wait_ready_succeeds_on_first_try(
        self,
        mock_run: MagicMock,
        mock_sleep: MagicMock,
        mock_which: MagicMock,
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        # First call: neonctl create, second call: psql SELECT 1
        mock_run.side_effect = [
            _make_neonctl_result(),
            _make_psql_result(returncode=0),
        ]
        env = NeonBranchEnvironment(seed_strategy="migrations")
        env.start()
        env.wait_ready(timeout_seconds=10)

        # psql call should include SELECT 1
        psql_calls = [
            c for c in mock_run.call_args_list if "psql" in str(c)
        ]
        assert len(psql_calls) >= 1

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("time.sleep")
    @patch("time.monotonic")
    @patch("subprocess.run")
    def test_wait_ready_timeout_raises(
        self,
        mock_run: MagicMock,
        mock_monotonic: MagicMock,
        mock_sleep: MagicMock,
        mock_which: MagicMock,
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.side_effect = [
            _make_neonctl_result(),  # create branch
            _make_psql_result(returncode=2),  # fail first poll
        ]
        # monotonic calls: (1) deadline calc, (2) check after first poll
        mock_monotonic.side_effect = [0.0, 65.0]

        env = NeonBranchEnvironment(seed_strategy="migrations")
        env.start()
        with pytest.raises(TimeoutError, match="not ready"):
            env.wait_ready(timeout_seconds=60)

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("time.sleep")
    @patch("time.monotonic")
    @patch("subprocess.run")
    def test_wait_ready_polls_at_2s_intervals(
        self,
        mock_run: MagicMock,
        mock_monotonic: MagicMock,
        mock_sleep: MagicMock,
        mock_which: MagicMock,
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.side_effect = [
            _make_neonctl_result(),
            _make_psql_result(returncode=2),  # fail first
            _make_psql_result(returncode=0),  # succeed second
        ]
        mock_monotonic.side_effect = [0.0, 0.0, 2.0, 4.0]

        env = NeonBranchEnvironment(seed_strategy="migrations")
        env.start()
        env.wait_ready(timeout_seconds=60)

        mock_sleep.assert_called_with(2)

    def test_wait_ready_before_start_raises(self) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        env = NeonBranchEnvironment.__new__(NeonBranchEnvironment)
        env._branch_id = None
        env._connection_uri = None
        with pytest.raises(RuntimeError, match="before start"):
            env.wait_ready()


# ---------------------------------------------------------------------------
# Teardown tests
# ---------------------------------------------------------------------------


class TestTeardown:
    """Teardown deletes branch via neonctl branches delete."""

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_teardown_deletes_branch(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()
        env = NeonBranchEnvironment(seed_strategy="migrations")
        env.start()

        # Reset mock and set up for teardown
        mock_run.reset_mock()
        mock_run.return_value = subprocess.CompletedProcess(
            args=["neonctl"], returncode=0, stdout="", stderr=""
        )
        env.teardown()

        # Should have called neonctl branches delete
        assert mock_run.called
        cmd = mock_run.call_args.args[0] if mock_run.call_args.args else mock_run.call_args.kwargs["args"]
        assert "branches" in cmd
        assert "delete" in cmd
        assert "br-test-12345" in cmd
        assert "--project-id" in cmd

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_teardown_is_idempotent(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Calling teardown twice should not raise."""
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()
        env = NeonBranchEnvironment(seed_strategy="migrations")
        env.start()

        mock_run.return_value = subprocess.CompletedProcess(
            args=["neonctl"], returncode=0, stdout="", stderr=""
        )
        env.teardown()
        # Second call should not raise
        env.teardown()

    def test_teardown_before_start_is_noop(self) -> None:
        """Teardown without start should not raise."""
        from environments.neon_branch import NeonBranchEnvironment

        env = NeonBranchEnvironment.__new__(NeonBranchEnvironment)
        env._branch_id = None
        env._connection_uri = None
        env._project_id = None
        env._api_key = None
        env._env = {}
        # Should not raise
        env.teardown()


# ---------------------------------------------------------------------------
# env_vars tests
# ---------------------------------------------------------------------------


class TestEnvVars:
    """env_vars returns connection details after start, empty dict before."""

    def test_env_vars_empty_before_start(self) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        env = NeonBranchEnvironment.__new__(NeonBranchEnvironment)
        env._branch_id = None
        env._connection_uri = None
        env._env = {}
        assert env.env_vars() == {}

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_env_vars_after_start_has_required_keys(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()
        env = NeonBranchEnvironment(seed_strategy="migrations")
        env.start()

        result = env.env_vars()
        assert "POSTGRES_DSN" in result
        assert "NEON_BRANCH_ID" in result
        assert "NEON_PROJECT_ID" in result
        assert "NEON_HOST" in result
        assert result["TEST_ENV_TYPE"] == "neon"
        assert result["NEON_BRANCH_ID"] == "br-test-12345"
        assert result["NEON_PROJECT_ID"] == "proj-123"


# ---------------------------------------------------------------------------
# Migrations seeding tests
# ---------------------------------------------------------------------------


class TestMigrationsSeeding:
    """Test migrations seeding strategy invokes psql for each migration file."""

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_migrations_seeding_runs_sql_files(
        self, mock_run: MagicMock, mock_which: MagicMock, tmp_path: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        # Create migration files
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_init.sql").write_text("CREATE TABLE t1();")
        (migrations_dir / "002_data.sql").write_text("CREATE TABLE t2();")

        # Create seed file
        seed_file = tmp_path / "seed.sql"
        seed_file.write_text("INSERT INTO t1 VALUES (1);")

        mock_run.return_value = _make_neonctl_result()

        env = NeonBranchEnvironment(
            seed_strategy="migrations",
            migrations_dir=str(migrations_dir),
            seed_file=str(seed_file),
        )
        env.start()

        # Should have called psql for each migration and seed
        psql_calls = [
            c for c in mock_run.call_args_list if "psql" in str(c)
        ]
        # 2 migrations + 1 seed = 3 psql calls
        assert len(psql_calls) == 3

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_migrations_applied_in_order(
        self, mock_run: MagicMock, mock_which: MagicMock, tmp_path: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "002_second.sql").write_text("-- second")
        (migrations_dir / "001_first.sql").write_text("-- first")

        mock_run.return_value = _make_neonctl_result()

        env = NeonBranchEnvironment(
            seed_strategy="migrations",
            migrations_dir=str(migrations_dir),
        )
        env.start()

        psql_calls = [
            c for c in mock_run.call_args_list if "psql" in str(c)
        ]
        # First migration should be 001, second should be 002
        first_cmd = psql_calls[0].args[0] if psql_calls[0].args else psql_calls[0].kwargs["args"]
        second_cmd = psql_calls[1].args[0] if psql_calls[1].args else psql_calls[1].kwargs["args"]
        assert "001_first.sql" in str(first_cmd)
        assert "002_second.sql" in str(second_cmd)

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_migration_failure_raises(
        self, mock_run: MagicMock, mock_which: MagicMock, tmp_path: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "001_fail.sql").write_text("INVALID SQL")

        # neonctl succeeds, psql fails
        mock_run.side_effect = [
            _make_neonctl_result(),  # branch creation
            subprocess.CompletedProcess(
                args=["psql"], returncode=1, stdout="", stderr="ERROR: syntax error"
            ),
        ]

        env = NeonBranchEnvironment(
            seed_strategy="migrations",
            migrations_dir=str(migrations_dir),
        )
        with pytest.raises(RuntimeError, match="Migration.*failed"):
            env.start()

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_neon_to_neon_skips_seeding(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """When source_branch_id is set, seeding is skipped (data comes from parent)."""
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()

        env = NeonBranchEnvironment(
            seed_strategy="migrations",
            source_branch_id="br-source-999",
        )
        env.start()

        # Only the neonctl create call, no psql calls for seeding
        psql_calls = [
            c for c in mock_run.call_args_list if "psql" in str(c)
        ]
        assert len(psql_calls) == 0
