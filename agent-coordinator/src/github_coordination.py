"""GitHub-mediated coordination for Agent Coordinator.

Provides coordination through GitHub conventions:
- Issue label lock signaling (e.g., `locked:path/to/file`)
- Branch naming convention parsing (`agent/{agent_id}/{task_id}`)
- Webhook-driven state sync from GitHub to coordination database
"""

import re
from dataclasses import dataclass
from typing import Any

from .config import get_config
from .db import DatabaseClient, get_db

# =============================================================================
# Branch naming convention
# =============================================================================

BRANCH_PATTERN = re.compile(
    r"^agent/(?P<agent_id>[^/]+)/(?P<task_id>[^/]+)$"
)

LOCK_LABEL_PATTERN = re.compile(
    r"^locked:(?P<file_path>.+)$"
)


@dataclass
class BranchInfo:
    """Parsed agent branch naming convention."""

    branch: str
    agent_id: str
    task_id: str
    is_agent_branch: bool = True

    @classmethod
    def parse(cls, branch_ref: str) -> "BranchInfo | None":
        """Parse a branch name into agent/task components.

        Args:
            branch_ref: Branch name (e.g., 'agent/claude-1/task-42')

        Returns:
            BranchInfo if pattern matches, None otherwise
        """
        # Strip refs/heads/ prefix if present
        branch = branch_ref.removeprefix("refs/heads/")
        match = BRANCH_PATTERN.match(branch)
        if not match:
            return None
        return cls(
            branch=branch,
            agent_id=match.group("agent_id"),
            task_id=match.group("task_id"),
        )


@dataclass
class LabelLock:
    """A file lock parsed from a GitHub issue label."""

    file_path: str
    issue_number: int | None = None


@dataclass
class WebhookSyncResult:
    """Result of syncing GitHub webhook state to coordination DB."""

    success: bool
    locks_created: int = 0
    locks_released: int = 0
    branches_tracked: int = 0
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebhookSyncResult":
        return cls(
            success=data.get("success", False),
            locks_created=data.get("locks_created", 0),
            locks_released=data.get("locks_released", 0),
            branches_tracked=data.get("branches_tracked", 0),
            error=data.get("error"),
        )


class GitHubCoordinationService:
    """Service for GitHub-mediated coordination."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    def parse_lock_labels(
        self, labels: list[str]
    ) -> list[LabelLock]:
        """Parse GitHub issue labels into file lock requests.

        Args:
            labels: List of label strings from a GitHub issue

        Returns:
            List of LabelLock for labels matching 'locked:path'
        """
        locks = []
        for label in labels:
            match = LOCK_LABEL_PATTERN.match(label)
            if match:
                locks.append(
                    LabelLock(file_path=match.group("file_path"))
                )
        return locks

    def parse_branch(self, branch_ref: str) -> BranchInfo | None:
        """Parse a branch name into agent coordination info.

        Args:
            branch_ref: Branch reference (e.g., 'refs/heads/agent/a1/t1')

        Returns:
            BranchInfo if pattern matches, None otherwise
        """
        return BranchInfo.parse(branch_ref)

    async def sync_label_locks(
        self,
        labels: list[str],
        issue_number: int,
        agent_id: str | None = None,
    ) -> WebhookSyncResult:
        """Sync issue label locks to the coordination database.

        Creates file locks for labels matching 'locked:path/to/file'
        and releases locks for labels that were removed.

        Args:
            labels: Current label strings on the issue
            issue_number: GitHub issue number
            agent_id: Agent ID to associate locks with

        Returns:
            WebhookSyncResult with counts
        """
        config = get_config()
        agent_id = agent_id or config.agent.agent_id

        label_locks = self.parse_lock_labels(labels)
        current_paths = {lock.file_path for lock in label_locks}
        locks_created = 0
        locks_released = 0

        try:
            # Find existing label-derived locks for this issue
            session_id = f"issue-{issue_number}"
            existing_locks = await self.db.query(
                "file_locks",
                f"locked_by=eq.{agent_id}&session_id=eq.{session_id}",
            )
            existing_paths = {
                row["file_path"] for row in existing_locks
            }

            # Release locks whose labels were removed
            stale_paths = existing_paths - current_paths
            for file_path in stale_paths:
                await self.db.rpc(
                    "release_lock",
                    {
                        "p_file_path": file_path,
                        "p_agent_id": agent_id,
                    },
                )
                locks_released += 1

            # Acquire locks for new labels
            new_paths = current_paths - existing_paths
            for lock in label_locks:
                if lock.file_path in new_paths:
                    await self.db.rpc(
                        "acquire_lock",
                        {
                            "p_file_path": lock.file_path,
                            "p_agent_id": agent_id,
                            "p_agent_type": "github_label",
                            "p_session_id": session_id,
                            "p_reason": f"GitHub issue #{issue_number} label lock",
                            "p_ttl_minutes": 480,  # 8 hours for label locks
                        },
                    )
                    locks_created += 1
        except Exception as e:
            return WebhookSyncResult(
                success=False,
                locks_created=locks_created,
                locks_released=locks_released,
                error=str(e),
            )

        return WebhookSyncResult(
            success=True,
            locks_created=locks_created,
            locks_released=locks_released,
        )

    async def sync_branch_tracking(
        self,
        branch_ref: str,
        changed_files: list[str] | None = None,
    ) -> WebhookSyncResult:
        """Track an agent branch and create implicit file locks.

        When an agent pushes to a branch matching the naming convention,
        create implicit locks for files modified on that branch.

        Args:
            branch_ref: Branch reference from push event
            changed_files: Files modified in the push

        Returns:
            WebhookSyncResult with tracking counts
        """
        info = BranchInfo.parse(branch_ref)
        if not info:
            return WebhookSyncResult(
                success=True,
                branches_tracked=0,
            )

        locks_created = 0
        try:
            for file_path in changed_files or []:
                await self.db.rpc(
                    "acquire_lock",
                    {
                        "p_file_path": file_path,
                        "p_agent_id": info.agent_id,
                        "p_agent_type": "github_branch",
                        "p_session_id": f"branch-{info.task_id}",
                        "p_reason": f"Implicit lock from branch {info.branch}",
                        "p_ttl_minutes": 240,
                    },
                )
                locks_created += 1
        except Exception as e:
            return WebhookSyncResult(
                success=False,
                locks_created=locks_created,
                branches_tracked=1 if locks_created > 0 else 0,
                error=str(e),
            )

        return WebhookSyncResult(
            success=True,
            locks_created=locks_created,
            branches_tracked=1,
        )

    async def handle_push_webhook(
        self, payload: dict[str, Any]
    ) -> WebhookSyncResult:
        """Handle a GitHub push webhook event.

        Parses the push payload, tracks the branch if it matches
        the agent naming convention, and creates implicit file locks.

        Args:
            payload: GitHub push webhook payload

        Returns:
            WebhookSyncResult with sync details
        """
        branch_ref = payload.get("ref", "")
        changed_files: list[str] = []

        for commit in payload.get("commits", []):
            changed_files.extend(commit.get("added", []))
            changed_files.extend(commit.get("modified", []))

        # Deduplicate
        changed_files = list(set(changed_files))

        return await self.sync_branch_tracking(
            branch_ref=branch_ref,
            changed_files=changed_files,
        )

    async def handle_issues_webhook(
        self, payload: dict[str, Any]
    ) -> WebhookSyncResult:
        """Handle a GitHub issues webhook event.

        Syncs issue label locks when labels are added/removed.

        Args:
            payload: GitHub issues webhook payload

        Returns:
            WebhookSyncResult with sync details
        """
        action = payload.get("action", "")
        if action not in ("labeled", "unlabeled", "opened"):
            return WebhookSyncResult(success=True)

        issue = payload.get("issue", {})
        issue_number = issue.get("number", 0)
        labels = [
            label.get("name", "")
            for label in issue.get("labels", [])
        ]

        return await self.sync_label_locks(
            labels=labels,
            issue_number=issue_number,
        )


# Global service instance
_github_coordination_service: GitHubCoordinationService | None = None


def get_github_coordination_service() -> GitHubCoordinationService:
    """Get the global GitHub coordination service instance."""
    global _github_coordination_service
    if _github_coordination_service is None:
        _github_coordination_service = GitHubCoordinationService()
    return _github_coordination_service
