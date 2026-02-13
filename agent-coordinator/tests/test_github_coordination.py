"""Tests for the GitHub-mediated coordination service."""


import pytest
from httpx import Response

from src.github_coordination import (
    BranchInfo,
    GitHubCoordinationService,
    WebhookSyncResult,
)


class TestBranchParsing:
    """Tests for branch naming convention parsing."""

    def test_parse_valid_agent_branch(self):
        """Test parsing a valid agent branch name."""
        info = BranchInfo.parse("agent/claude-1/task-42")
        assert info is not None
        assert info.agent_id == "claude-1"
        assert info.task_id == "task-42"
        assert info.branch == "agent/claude-1/task-42"

    def test_parse_with_refs_prefix(self):
        """Test parsing branch with refs/heads/ prefix."""
        info = BranchInfo.parse("refs/heads/agent/claude-1/task-42")
        assert info is not None
        assert info.agent_id == "claude-1"
        assert info.task_id == "task-42"

    def test_parse_non_agent_branch(self):
        """Test parsing returns None for non-agent branches."""
        assert BranchInfo.parse("main") is None
        assert BranchInfo.parse("feature/add-tests") is None
        assert BranchInfo.parse("fix/bug-123") is None

    def test_parse_incomplete_agent_branch(self):
        """Test parsing returns None for incomplete agent branches."""
        assert BranchInfo.parse("agent/claude-1") is None
        assert BranchInfo.parse("agent/") is None


class TestLabelLockParsing:
    """Tests for GitHub issue label lock parsing."""

    def test_parse_lock_labels(self):
        """Test parsing lock labels from issue labels."""
        service = GitHubCoordinationService()
        labels = [
            "locked:src/main.py",
            "locked:src/config.py",
            "bug",
            "enhancement",
        ]
        locks = service.parse_lock_labels(labels)
        assert len(locks) == 2
        assert locks[0].file_path == "src/main.py"
        assert locks[1].file_path == "src/config.py"

    def test_parse_no_lock_labels(self):
        """Test parsing when no lock labels are present."""
        service = GitHubCoordinationService()
        labels = ["bug", "enhancement", "priority:high"]
        locks = service.parse_lock_labels(labels)
        assert len(locks) == 0

    def test_parse_empty_labels(self):
        """Test parsing empty labels list."""
        service = GitHubCoordinationService()
        locks = service.parse_lock_labels([])
        assert len(locks) == 0


class TestGitHubCoordinationService:
    """Tests for GitHubCoordinationService async methods."""

    @pytest.mark.asyncio
    async def test_sync_label_locks(self, mock_supabase, db_client):
        """Test syncing label locks to coordination DB."""
        # Mock the query for existing locks (none yet)
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/file_locks"
        ).mock(return_value=Response(200, json=[]))

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/acquire_lock"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "action": "acquired",
                    "file_path": "src/main.py",
                },
            )
        )

        service = GitHubCoordinationService(db_client)
        result = await service.sync_label_locks(
            labels=["locked:src/main.py"],
            issue_number=42,
        )

        assert result.success is True
        assert result.locks_created == 1

    @pytest.mark.asyncio
    async def test_sync_label_locks_releases_stale(self, mock_supabase, db_client):
        """Test that removed labels release their locks."""
        # Mock existing locks — src/old.py was previously locked
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/file_locks"
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "file_path": "src/old.py",
                        "locked_by": "test-agent-1",
                        "session_id": "issue-42",
                    },
                ],
            )
        )

        # Mock release_lock RPC
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/release_lock"
        ).mock(
            return_value=Response(
                200,
                json={"success": True, "action": "released", "file_path": "src/old.py"},
            )
        )

        service = GitHubCoordinationService(db_client)
        # No lock labels remain — all old locks should be released
        result = await service.sync_label_locks(
            labels=["bug"],
            issue_number=42,
        )

        assert result.success is True
        assert result.locks_released == 1
        assert result.locks_created == 0

    @pytest.mark.asyncio
    async def test_sync_branch_tracking(self, mock_supabase, db_client):
        """Test tracking agent branch with implicit file locks."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/acquire_lock"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "action": "acquired",
                    "file_path": "src/config.py",
                },
            )
        )

        service = GitHubCoordinationService(db_client)
        result = await service.sync_branch_tracking(
            branch_ref="refs/heads/agent/claude-1/task-42",
            changed_files=["src/config.py", "src/db.py"],
        )

        assert result.success is True
        assert result.branches_tracked == 1
        assert result.locks_created == 2

    @pytest.mark.asyncio
    async def test_sync_non_agent_branch(self, mock_supabase, db_client):
        """Test tracking a non-agent branch is a no-op."""
        service = GitHubCoordinationService(db_client)
        result = await service.sync_branch_tracking(
            branch_ref="refs/heads/main",
            changed_files=["README.md"],
        )

        assert result.success is True
        assert result.branches_tracked == 0
        assert result.locks_created == 0

    @pytest.mark.asyncio
    async def test_handle_push_webhook(self, mock_supabase, db_client):
        """Test handling a GitHub push webhook."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/acquire_lock"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "action": "acquired",
                    "file_path": "src/main.py",
                },
            )
        )

        service = GitHubCoordinationService(db_client)
        result = await service.handle_push_webhook({
            "ref": "refs/heads/agent/claude-1/task-99",
            "commits": [
                {
                    "added": ["src/new_file.py"],
                    "modified": ["src/main.py"],
                    "removed": [],
                },
            ],
        })

        assert result.success is True
        assert result.branches_tracked == 1

    @pytest.mark.asyncio
    async def test_handle_issues_webhook_labeled(
        self, mock_supabase, db_client
    ):
        """Test handling an issues webhook with lock labels."""
        # Mock query for existing locks (none yet)
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/file_locks"
        ).mock(return_value=Response(200, json=[]))

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/acquire_lock"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "action": "acquired",
                    "file_path": "src/db.py",
                },
            )
        )

        service = GitHubCoordinationService(db_client)
        result = await service.handle_issues_webhook({
            "action": "labeled",
            "issue": {
                "number": 123,
                "labels": [
                    {"name": "locked:src/db.py"},
                    {"name": "bug"},
                ],
            },
        })

        assert result.success is True
        assert result.locks_created == 1


class TestWebhookSyncResultDataClass:
    """Tests for WebhookSyncResult dataclass."""

    def test_from_dict(self):
        """Test creating WebhookSyncResult from dict."""
        result = WebhookSyncResult.from_dict({
            "success": True,
            "locks_created": 3,
            "locks_released": 1,
            "branches_tracked": 2,
        })
        assert result.success is True
        assert result.locks_created == 3
        assert result.branches_tracked == 2

    def test_from_dict_defaults(self):
        """Test WebhookSyncResult defaults."""
        result = WebhookSyncResult.from_dict({})
        assert result.success is False
        assert result.locks_created == 0
