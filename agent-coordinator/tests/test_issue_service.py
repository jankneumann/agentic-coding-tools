"""Tests for IssueService — issue tracking extension of work_queue."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.issue_service import Comment, Issue, IssueService


@pytest.fixture
def mock_db():
    """Create a mock DatabaseClient."""
    db = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    """Create an IssueService with mocked DB."""
    return IssueService(db=mock_db)


def _make_issue_row(
    *,
    issue_id: UUID | None = None,
    title: str = "Test issue",
    status: str = "pending",
    priority: int = 5,
    issue_type: str = "task",
    labels: list[str] | None = None,
    parent_id: UUID | None = None,
    assignee: str | None = None,
    depends_on: list[UUID] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Build a work_queue row dict for testing."""
    return {
        "id": str(issue_id or uuid4()),
        "task_type": "issue",
        "description": title,
        "status": status,
        "priority": priority,
        "issue_type": issue_type,
        "labels": labels or [],
        "parent_id": str(parent_id) if parent_id else None,
        "assignee": assignee,
        "depends_on": [str(d) for d in depends_on] if depends_on else None,
        "input_data": None,
        "claimed_by": None,
        "claimed_at": None,
        "result": None,
        "error_message": None,
        "deadline": None,
        "created_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "closed_at": None,
        "close_reason": None,
        "metadata": metadata or {},
    }


# ===========================================================================
# Issue Creation
# ===========================================================================


class TestIssueCreate:
    @pytest.mark.asyncio
    async def test_create_basic(self, service, mock_db):
        """Create a basic issue with title and type."""
        issue_id = uuid4()
        mock_db.insert.return_value = _make_issue_row(
            issue_id=issue_id, title="Fix CORS headers", issue_type="bug",
            priority=3, labels=["api", "followup"],
        )

        issue = await service.create(
            title="Fix CORS headers",
            issue_type="bug",
            priority=3,
            labels=["api", "followup"],
        )

        assert issue.title == "Fix CORS headers"
        assert issue.issue_type == "bug"
        assert issue.priority == 3
        assert issue.labels == ["api", "followup"]

        # Verify insert was called with task_type='issue'
        call_args = mock_db.insert.call_args
        assert call_args[0][0] == "work_queue"
        assert call_args[0][1]["task_type"] == "issue"

    @pytest.mark.asyncio
    async def test_create_with_parent(self, service, mock_db):
        """Create an issue with a parent (epic child)."""
        parent_id = uuid4()
        child_id = uuid4()
        mock_db.insert.return_value = _make_issue_row(
            issue_id=child_id, title="Subtask", parent_id=parent_id,
        )

        issue = await service.create(
            title="Subtask", parent_id=parent_id,
        )

        assert issue.parent_id == parent_id
        call_data = mock_db.insert.call_args[0][1]
        assert call_data["parent_id"] == str(parent_id)

    @pytest.mark.asyncio
    async def test_create_with_dependencies(self, service, mock_db):
        """Create an issue with depends_on."""
        dep1 = uuid4()
        dep2 = uuid4()
        mock_db.insert.return_value = _make_issue_row(
            title="Blocked task", depends_on=[dep1, dep2],
        )

        issue = await service.create(
            title="Blocked task", depends_on=[dep1, dep2],
        )

        assert len(issue.depends_on) == 2
        call_data = mock_db.insert.call_args[0][1]
        assert str(dep1) in call_data["depends_on"]

    @pytest.mark.asyncio
    async def test_create_defaults(self, service, mock_db):
        """Default issue_type='task', priority=5, labels=[]."""
        mock_db.insert.return_value = _make_issue_row(title="Default task")

        issue = await service.create(title="Default task")

        call_data = mock_db.insert.call_args[0][1]
        assert call_data["issue_type"] == "task"
        assert call_data["priority"] == 5
        assert call_data["labels"] == []

    @pytest.mark.asyncio
    async def test_create_invalid_type(self, service):
        """Invalid issue_type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid issue_type"):
            await service.create(title="Bad", issue_type="invalid")

    @pytest.mark.asyncio
    async def test_create_invalid_priority(self, service):
        """Priority out of range raises ValueError."""
        with pytest.raises(ValueError, match="Priority must be 1-10"):
            await service.create(title="Bad", priority=0)


# ===========================================================================
# Issue Listing
# ===========================================================================


class TestIssueList:
    @pytest.mark.asyncio
    async def test_list_all(self, service, mock_db):
        """List all issues."""
        mock_db.query.return_value = [
            _make_issue_row(title="Issue 1"),
            _make_issue_row(title="Issue 2"),
        ]

        issues = await service.list_issues()

        assert len(issues) == 2
        query = mock_db.query.call_args[0][1]
        assert "task_type=eq.issue" in query

    @pytest.mark.asyncio
    async def test_list_by_status_open(self, service, mock_db):
        """Filter by status 'open' maps to pending,claimed."""
        mock_db.query.return_value = [
            _make_issue_row(title="Open", status="pending"),
        ]

        await service.list_issues(status="open")

        query = mock_db.query.call_args[0][1]
        assert "status=in.(pending,claimed)" in query

    @pytest.mark.asyncio
    async def test_list_by_labels(self, service, mock_db):
        """Filter by labels uses post-filtering."""
        mock_db.query.return_value = [
            _make_issue_row(title="Match", labels=["api", "followup"]),
            _make_issue_row(title="No match", labels=["api"]),
        ]

        issues = await service.list_issues(labels=["api", "followup"])

        assert len(issues) == 1
        assert issues[0].title == "Match"

    @pytest.mark.asyncio
    async def test_list_by_parent(self, service, mock_db):
        """Filter by parent_id."""
        parent_id = uuid4()
        mock_db.query.return_value = [
            _make_issue_row(title="Child", parent_id=parent_id),
        ]

        await service.list_issues(parent_id=parent_id)

        query = mock_db.query.call_args[0][1]
        assert f"parent_id=eq.{parent_id}" in query

    @pytest.mark.asyncio
    async def test_list_limit_capped(self, service, mock_db):
        """Limit is capped at MAX_PAGE_SIZE."""
        mock_db.query.return_value = []

        await service.list_issues(limit=500)

        query = mock_db.query.call_args[0][1]
        assert "limit=100" in query


# ===========================================================================
# Issue Show
# ===========================================================================


class TestIssueShow:
    @pytest.mark.asyncio
    async def test_show_with_comments(self, service, mock_db):
        """Show includes comments."""
        issue_id = uuid4()
        comment_id = uuid4()
        mock_db.query.side_effect = [
            [_make_issue_row(issue_id=issue_id, title="My Issue")],
            [
                {
                    "id": str(comment_id),
                    "issue_id": str(issue_id),
                    "author": "agent-1",
                    "body": "Started work",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ],
        ]

        issue = await service.show(issue_id)

        assert issue is not None
        assert issue.title == "My Issue"
        assert len(issue.comments) == 1
        assert issue.comments[0]["body"] == "Started work"

    @pytest.mark.asyncio
    async def test_show_epic_with_children(self, service, mock_db):
        """Show epic includes children."""
        epic_id = uuid4()
        child_id = uuid4()
        mock_db.query.side_effect = [
            [_make_issue_row(issue_id=epic_id, title="Epic", issue_type="epic")],
            [],  # comments
            [_make_issue_row(issue_id=child_id, title="Child", parent_id=epic_id)],
        ]

        issue = await service.show(epic_id)

        assert issue is not None
        assert issue.children is not None
        assert len(issue.children) == 1
        assert issue.children[0]["title"] == "Child"

    @pytest.mark.asyncio
    async def test_show_not_found(self, service, mock_db):
        """Show returns None for missing issue."""
        mock_db.query.return_value = []

        issue = await service.show(uuid4())
        assert issue is None


# ===========================================================================
# Issue Update
# ===========================================================================


class TestIssueUpdate:
    @pytest.mark.asyncio
    async def test_update_labels(self, service, mock_db):
        """Update labels replaces the array."""
        issue_id = uuid4()
        mock_db.update.return_value = [
            _make_issue_row(issue_id=issue_id, labels=["api", "urgent"]),
        ]

        issue = await service.update(issue_id, labels=["api", "urgent"])

        assert issue is not None
        update_data = mock_db.update.call_args[1]["data"]
        assert update_data["labels"] == ["api", "urgent"]

    @pytest.mark.asyncio
    async def test_update_status_mapping(self, service, mock_db):
        """Update status maps friendly names to DB values."""
        issue_id = uuid4()
        mock_db.update.return_value = [
            _make_issue_row(issue_id=issue_id, status="running"),
        ]

        await service.update(issue_id, status="in_progress")

        update_data = mock_db.update.call_args[1]["data"]
        assert update_data["status"] == "running"

    @pytest.mark.asyncio
    async def test_update_not_found(self, service, mock_db):
        """Update returns None when issue doesn't exist."""
        mock_db.update.return_value = []

        issue = await service.update(uuid4(), title="New title")
        assert issue is None


# ===========================================================================
# Issue Close
# ===========================================================================


class TestIssueClose:
    @pytest.mark.asyncio
    async def test_close_with_reason(self, service, mock_db):
        """Close sets status, timestamps, and reason."""
        issue_id = uuid4()
        mock_db.update.return_value = [
            _make_issue_row(issue_id=issue_id, status="completed"),
        ]

        results = await service.close(issue_id=issue_id, reason="Done in PR #42")

        assert len(results) == 1
        update_data = mock_db.update.call_args[1]["data"]
        assert update_data["status"] == "completed"
        assert update_data["close_reason"] == "Done in PR #42"
        assert "closed_at" in update_data

    @pytest.mark.asyncio
    async def test_batch_close(self, service, mock_db):
        """Batch close multiple issues."""
        ids = [uuid4(), uuid4(), uuid4()]
        mock_db.update.return_value = [_make_issue_row(status="completed")]

        results = await service.close(issue_ids=ids)

        assert len(results) == 3
        assert mock_db.update.call_count == 3

    @pytest.mark.asyncio
    async def test_close_no_ids_raises(self, service):
        """Close with no IDs raises ValueError."""
        with pytest.raises(ValueError, match="Must provide"):
            await service.close()


# ===========================================================================
# Issue Comments
# ===========================================================================


class TestIssueComment:
    @pytest.mark.asyncio
    async def test_add_comment(self, service, mock_db):
        """Add a comment to an issue."""
        issue_id = uuid4()
        comment_id = uuid4()
        mock_db.insert.return_value = {
            "id": str(comment_id),
            "issue_id": str(issue_id),
            "author": "test-agent-1",
            "body": "Working on this",
            "created_at": datetime.now(UTC).isoformat(),
        }

        comment = await service.comment(issue_id, "Working on this")

        assert comment.body == "Working on this"
        assert comment.issue_id == issue_id
        call_data = mock_db.insert.call_args[0][1]
        assert call_data["issue_id"] == str(issue_id)


# ===========================================================================
# Ready and Blocked Queries
# ===========================================================================


class TestIssueReady:
    @pytest.mark.asyncio
    async def test_ready_no_deps(self, service, mock_db):
        """Issues with no dependencies are ready."""
        mock_db.query.return_value = [
            _make_issue_row(title="Ready"),
        ]

        issues = await service.ready()

        assert len(issues) == 1
        assert issues[0].title == "Ready"

    @pytest.mark.asyncio
    async def test_ready_deps_resolved(self, service, mock_db):
        """Issues with resolved dependencies are ready."""
        dep_id = uuid4()
        mock_db.query.side_effect = [
            [_make_issue_row(title="Has dep", depends_on=[dep_id])],
            [_make_issue_row(issue_id=dep_id, status="completed")],
        ]

        issues = await service.ready()

        assert len(issues) == 1

    @pytest.mark.asyncio
    async def test_ready_deps_unresolved(self, service, mock_db):
        """Issues with unresolved dependencies are not ready."""
        dep_id = uuid4()
        mock_db.query.side_effect = [
            [_make_issue_row(title="Blocked", depends_on=[dep_id])],
            [_make_issue_row(issue_id=dep_id, status="pending")],
        ]

        issues = await service.ready()

        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_ready_with_parent(self, service, mock_db):
        """Ready scoped to a parent."""
        parent_id = uuid4()
        mock_db.query.return_value = [
            _make_issue_row(title="Child", parent_id=parent_id),
        ]

        await service.ready(parent_id=parent_id)

        query = mock_db.query.call_args[0][1]
        assert f"parent_id=eq.{parent_id}" in query


class TestIssueBlocked:
    @pytest.mark.asyncio
    async def test_blocked_returns_unresolved(self, service, mock_db):
        """Blocked returns issues with unresolved deps."""
        dep_id = uuid4()
        mock_db.query.side_effect = [
            [_make_issue_row(title="Blocked", depends_on=[dep_id])],
            [_make_issue_row(issue_id=dep_id, status="pending")],
        ]

        issues = await service.blocked()

        assert len(issues) == 1
        assert issues[0].title == "Blocked"


# ===========================================================================
# Issue Search
# ===========================================================================


class TestIssueSearch:
    @pytest.mark.asyncio
    async def test_search_by_title(self, service, mock_db):
        """Search matches in title (case insensitive)."""
        mock_db.query.return_value = [
            _make_issue_row(title="Fix CORS headers"),
            _make_issue_row(title="Add /ready endpoint"),
        ]

        issues = await service.search("cors")

        assert len(issues) == 1
        assert issues[0].title == "Fix CORS headers"

    @pytest.mark.asyncio
    async def test_search_by_description(self, service, mock_db):
        """Search matches in description."""
        mock_db.query.return_value = [
            _make_issue_row(
                title="Task",
                metadata={"body": "Need to add CORS middleware"},
            ),
        ]

        issues = await service.search("CORS middleware")

        assert len(issues) == 1


# ===========================================================================
# Data Model
# ===========================================================================


class TestIssueModel:
    def test_from_row(self):
        """Issue.from_row correctly maps work_queue columns."""
        row = _make_issue_row(
            title="Test", issue_type="bug", priority=3,
            labels=["api"], assignee="agent-1",
        )
        issue = Issue.from_row(row)

        assert issue.title == "Test"
        assert issue.issue_type == "bug"
        assert issue.priority == 3
        assert issue.labels == ["api"]
        assert issue.assignee == "agent-1"

    def test_to_dict(self):
        """Issue.to_dict produces serializable output."""
        issue = Issue(
            id=uuid4(),
            title="Test",
            description=None,
            status="pending",
            priority=5,
            issue_type="task",
            labels=["api"],
        )
        d = issue.to_dict()

        assert isinstance(d["id"], str)
        assert d["title"] == "Test"
        assert d["labels"] == ["api"]

    def test_comment_from_row(self):
        """Comment.from_row correctly maps columns."""
        row = {
            "id": str(uuid4()),
            "issue_id": str(uuid4()),
            "author": "agent-1",
            "body": "Hello",
            "created_at": datetime.now(UTC).isoformat(),
        }
        comment = Comment.from_row(row)
        assert comment.body == "Hello"
        assert comment.author == "agent-1"
