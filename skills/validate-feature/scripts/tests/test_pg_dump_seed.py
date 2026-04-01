"""Tests for pg_dump/pg_restore seeding path in NeonBranchEnvironment.

TDD test-first: these tests define the expected behavior for:
- pg_dump invocation with correct flags (--format=custom, --no-owner, etc.)
- pg_restore invocation into Neon branch
- --exclude-extension=pg_search in pg_dump (D5)
- Error handling for pg_dump failures
- Error handling for pg_restore failures
- source_dsn requirement for dump_restore strategy
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, call, patch

import pytest


NEON_CREATE_RESPONSE = json.dumps(
    {
        "branch": {
            "id": "br-dump-12345",
            "name": "br-dump-12345",
            "project_id": "proj-123",
        },
        "connection_uri": "postgresql://user:pass@ep-dump-12345.us-east-2.aws.neon.tech/neondb",
        "endpoints": [
            {
                "host": "ep-dump-12345.us-east-2.aws.neon.tech",
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


def _make_success_result(
    args: str = "cmd",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[args], returncode=0, stdout="", stderr=""
    )


# ---------------------------------------------------------------------------
# dump_restore seeding tests
# ---------------------------------------------------------------------------


class TestDumpRestoreSeeding:
    """Test pg_dump/pg_restore seeding strategy."""

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_dump_restore_calls_pg_dump_with_correct_flags(
        self, mock_run: MagicMock, mock_which: MagicMock, tmp_path: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        # neonctl create, pg_dump, pg_restore
        mock_run.return_value = _make_neonctl_result()

        env = NeonBranchEnvironment(
            seed_strategy="dump_restore",
            source_dsn="postgresql://postgres:postgres@localhost:54322/postgres",
        )
        env.start()

        # Find the pg_dump call
        pg_dump_calls = [
            c for c in mock_run.call_args_list if "pg_dump" in str(c)
        ]
        assert len(pg_dump_calls) == 1

        cmd = pg_dump_calls[0].args[0] if pg_dump_calls[0].args else pg_dump_calls[0].kwargs["args"]
        assert "--format=custom" in cmd or ("--format" in cmd and "custom" in cmd)
        assert "--no-owner" in cmd
        assert "--no-privileges" in cmd
        assert "--exclude-extension=pg_search" in cmd

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_dump_restore_calls_pg_restore_with_correct_flags(
        self, mock_run: MagicMock, mock_which: MagicMock, tmp_path: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()

        env = NeonBranchEnvironment(
            seed_strategy="dump_restore",
            source_dsn="postgresql://postgres:postgres@localhost:54322/postgres",
        )
        env.start()

        pg_restore_calls = [
            c for c in mock_run.call_args_list if "pg_restore" in str(c)
        ]
        assert len(pg_restore_calls) == 1

        cmd = pg_restore_calls[0].args[0] if pg_restore_calls[0].args else pg_restore_calls[0].kwargs["args"]
        assert "--no-owner" in cmd
        assert "--no-privileges" in cmd

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_dump_restore_uses_source_dsn_for_dump(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()
        source = "postgresql://postgres:postgres@localhost:54322/postgres"

        env = NeonBranchEnvironment(
            seed_strategy="dump_restore",
            source_dsn=source,
        )
        env.start()

        pg_dump_calls = [
            c for c in mock_run.call_args_list if "pg_dump" in str(c)
        ]
        cmd = pg_dump_calls[0].args[0] if pg_dump_calls[0].args else pg_dump_calls[0].kwargs["args"]
        assert source in cmd

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_dump_restore_uses_neon_uri_for_restore(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()

        env = NeonBranchEnvironment(
            seed_strategy="dump_restore",
            source_dsn="postgresql://postgres:postgres@localhost:54322/postgres",
        )
        env.start()

        pg_restore_calls = [
            c for c in mock_run.call_args_list if "pg_restore" in str(c)
        ]
        cmd = pg_restore_calls[0].args[0] if pg_restore_calls[0].args else pg_restore_calls[0].kwargs["args"]
        # The Neon connection URI should be in the pg_restore command
        assert "ep-dump-12345" in str(cmd)

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    def test_dump_restore_without_source_dsn_raises(
        self, mock_which: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        env = NeonBranchEnvironment(
            seed_strategy="dump_restore",
            source_dsn=None,
        )
        with pytest.raises(RuntimeError, match="source_dsn.*required"):
            env.start()


# ---------------------------------------------------------------------------
# pg_dump failure tests
# ---------------------------------------------------------------------------


class TestPgDumpFailures:
    """Error handling for pg_dump and pg_restore failures."""

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_pg_dump_failure_raises(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        # neonctl succeeds, pg_dump fails
        mock_run.side_effect = [
            _make_neonctl_result(),
            subprocess.CompletedProcess(
                args=["pg_dump"],
                returncode=1,
                stdout="",
                stderr="pg_dump: error: connection to server failed",
            ),
        ]

        env = NeonBranchEnvironment(
            seed_strategy="dump_restore",
            source_dsn="postgresql://postgres:postgres@localhost:54322/postgres",
        )
        with pytest.raises(RuntimeError, match="pg_dump.*failed"):
            env.start()

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_pg_restore_failure_raises(
        self, mock_run: MagicMock, mock_which: MagicMock, tmp_path: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        # neonctl succeeds, pg_dump succeeds, pg_restore fails
        mock_run.side_effect = [
            _make_neonctl_result(),
            _make_success_result("pg_dump"),
            subprocess.CompletedProcess(
                args=["pg_restore"],
                returncode=1,
                stdout="",
                stderr="pg_restore: error: could not connect",
            ),
        ]

        env = NeonBranchEnvironment(
            seed_strategy="dump_restore",
            source_dsn="postgresql://postgres:postgres@localhost:54322/postgres",
        )
        with pytest.raises(RuntimeError, match="pg_restore.*failed"):
            env.start()


# ---------------------------------------------------------------------------
# pg_dump uses temp file
# ---------------------------------------------------------------------------


class TestDumpRestoreTempFile:
    """pg_dump should write to a temp file, pg_restore reads from it."""

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_dump_writes_to_file_and_restore_reads_it(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()

        env = NeonBranchEnvironment(
            seed_strategy="dump_restore",
            source_dsn="postgresql://postgres:postgres@localhost:54322/postgres",
        )
        env.start()

        pg_dump_calls = [
            c for c in mock_run.call_args_list if "pg_dump" in str(c)
        ]
        pg_restore_calls = [
            c for c in mock_run.call_args_list if "pg_restore" in str(c)
        ]

        dump_cmd = pg_dump_calls[0].args[0] if pg_dump_calls[0].args else pg_dump_calls[0].kwargs["args"]
        restore_cmd = pg_restore_calls[0].args[0] if pg_restore_calls[0].args else pg_restore_calls[0].kwargs["args"]

        # pg_dump should have -f <file> and pg_restore should reference the same file
        assert "-f" in dump_cmd or "--file" in dump_cmd
        # Find the dump file path from pg_dump command
        for i, arg in enumerate(dump_cmd):
            if arg in ("-f", "--file") and i + 1 < len(dump_cmd):
                dump_file = dump_cmd[i + 1]
                break
        else:
            pytest.fail("pg_dump command missing -f flag")

        # pg_restore should reference the dump file
        assert dump_file in restore_cmd


# ---------------------------------------------------------------------------
# dump_restore with source_branch_id
# ---------------------------------------------------------------------------


class TestDumpRestoreWithSourceBranch:
    """When source_branch_id is set with dump_restore, seeding is skipped."""

    @patch.dict(
        "os.environ",
        {"NEON_PROJECT_ID": "proj-123", "NEON_API_KEY": "key-abc"},
        clear=True,
    )
    @patch("shutil.which", return_value="/usr/local/bin/neonctl")
    @patch("subprocess.run")
    def test_source_branch_skips_dump_restore(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Neon-to-Neon branching gets data from parent, no dump needed."""
        from environments.neon_branch import NeonBranchEnvironment

        mock_run.return_value = _make_neonctl_result()

        env = NeonBranchEnvironment(
            seed_strategy="dump_restore",
            source_branch_id="br-source-999",
            source_dsn="postgresql://postgres:postgres@localhost:54322/postgres",
        )
        env.start()

        # No pg_dump or pg_restore calls
        pg_calls = [
            c
            for c in mock_run.call_args_list
            if "pg_dump" in str(c) or "pg_restore" in str(c)
        ]
        assert len(pg_calls) == 0
