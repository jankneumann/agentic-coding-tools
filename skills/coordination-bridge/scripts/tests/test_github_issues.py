"""GitHub-backed coordinator issues (issue #429).

The durability bug: coordinator create returns success with a UUID, then
list-by-label in a separate call returns nothing. The interim backing store
is GitHub Issues. This suite pins the round-trip that was missing, using an
in-memory GitHub stand-in so two client instances share durable state the
way two processes share GitHub.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import coordination_bridge
import github_issues


class FakeGitHub:
    """Minimal GitHub Issues API, shared across client instances."""

    def __init__(self) -> None:
        self.issues: dict[int, dict[str, Any]] = {}
        self.comments: dict[int, list[dict[str, Any]]] = {}
        self.labels: set[str] = set()
        self.next_number = 1
        self.fail_writes = False

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        method = method.upper()
        payload = payload or {}
        if self.fail_writes and method in {"POST", "PATCH"} and "/issues" in path:
            return {"status_code": 500, "data": {"message": "write discarded"}, "error": "server"}

        if method == "POST" and path.endswith("/labels"):
            name = str(payload.get("name", ""))
            self.labels.add(name)
            return {"status_code": 201, "data": {"name": name}, "error": None}

        if method == "POST" and path.endswith("/issues"):
            number = self.next_number
            self.next_number += 1
            labels = list(payload.get("labels") or [])
            self.labels.update(labels)
            issue = {
                "number": number,
                "title": payload.get("title"),
                "body": payload.get("body") or "",
                "state": "open",
                "labels": [{"name": name} for name in labels],
                "assignee": (
                    {"login": payload["assignees"][0]}
                    if payload.get("assignees")
                    else None
                ),
                "created_at": "2026-08-28T00:00:00Z",
                "closed_at": None,
                "html_url": f"https://github.com/example/repo/issues/{number}",
            }
            self.issues[number] = issue
            return {"status_code": 201, "data": issue, "error": None}

        if method == "GET" and "/issues/" in path and not path.endswith("/issues"):
            number = int(path.rsplit("/", 1)[-1].split("?")[0])
            issue = self.issues.get(number)
            if issue is None:
                return {"status_code": 404, "data": {"message": "Not Found"}, "error": None}
            return {"status_code": 200, "data": issue, "error": None}

        if method == "GET" and path.split("?")[0].endswith("/issues"):
            from urllib.parse import parse_qs, urlparse

            query = parse_qs(urlparse(path).query)
            wanted = [part for part in query.get("labels", [""])[0].split(",") if part]
            state = query.get("state", ["all"])[0]
            matches = []
            for issue in self.issues.values():
                if state != "all" and issue["state"] != state:
                    continue
                names = {label["name"] for label in issue.get("labels") or []}
                if wanted and not set(wanted).issubset(names):
                    continue
                matches.append(issue)
            return {"status_code": 200, "data": matches, "error": None}

        if method == "PATCH" and "/issues/" in path:
            number = int(path.rsplit("/", 1)[-1])
            issue = self.issues.get(number)
            if issue is None:
                return {"status_code": 404, "data": {"message": "Not Found"}, "error": None}
            if "title" in payload:
                issue["title"] = payload["title"]
            if "body" in payload:
                issue["body"] = payload["body"]
            if "state" in payload:
                issue["state"] = payload["state"]
                if payload["state"] == "closed":
                    issue["closed_at"] = "2026-08-28T01:00:00Z"
            if "labels" in payload:
                issue["labels"] = [{"name": name} for name in payload["labels"]]
            return {"status_code": 200, "data": issue, "error": None}

        if method == "POST" and path.endswith("/comments"):
            number = int(path.rsplit("/", 2)[-2])
            comment = {"id": 1, "body": payload.get("body"), "user": {"login": "bot"}}
            self.comments.setdefault(number, []).append(comment)
            return {"status_code": 201, "data": comment, "error": None}

        return {"status_code": 404, "data": {"message": "unhandled"}, "error": None}


def _client(store: FakeGitHub) -> github_issues.GitHubIssuesClient:
    return github_issues.GitHubIssuesClient(
        token="t",
        repo="jankneumann/agentic-coding-tools",
        request_fn=store.request,
    )


def test_create_then_list_by_label_from_separate_client() -> None:
    """The exact assertion that fails on the coordinator today (issue #429)."""
    store = FakeGitHub()
    writer = _client(store)
    reader = _client(store)

    created = writer.create(
        title="probe: seeding persistence check",
        issue_type="task",
        labels=["change:__probe__"],
    )
    assert created["status"] == "ok"
    issue_id = created["data"]["id"]
    assert issue_id

    listed = reader.list_issues(labels=["change:__probe__"])
    assert listed["status"] == "ok"
    issues = listed["data"]["issues"]
    assert len(issues) == 1
    assert issues[0]["id"] == issue_id
    assert "change:__probe__" in issues[0]["labels"]


def test_failed_github_write_is_loud() -> None:
    store = FakeGitHub()
    store.fail_writes = True
    client = _client(store)
    result = client.create(title="will not persist", labels=["change:__probe__"])
    assert result["status"] == "error"
    assert result["status_code"] == 500


def test_depends_on_round_trips_in_body() -> None:
    store = FakeGitHub()
    client = _client(store)
    first = client.create(title="upstream", labels=["change:demo", "task:1.1"])
    uid = first["data"]["id"]
    second = client.create(
        title="downstream",
        labels=["change:demo", "task:1.2"],
        depends_on=[uid],
    )
    shown = client.show(second["data"]["id"])
    assert shown["data"]["depends_on"] == [uid]


def test_close_is_visible_to_list() -> None:
    store = FakeGitHub()
    client = _client(store)
    created = client.create(title="done", labels=["change:demo", "task:1.1"])
    client.close(issue_id=created["data"]["id"])
    listed = client.list_issues(labels=["change:demo"], status="closed")
    assert len(listed["data"]["issues"]) == 1


def test_bridge_dispatches_to_github_when_configured(monkeypatch) -> None:
    store = FakeGitHub()
    monkeypatch.setenv("COORDINATION_ISSUES_BACKEND", "github")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "jankneumann/agentic-coding-tools")
    monkeypatch.setattr(
        github_issues,
        "_default_client",
        lambda: _client(store),
    )

    created = coordination_bridge.try_issue_create(
        title="from bridge", labels=["change:__probe__"]
    )
    assert created["status"] == "ok"
    listed = coordination_bridge.try_issue_list(labels=["change:__probe__"])
    assert listed["data"]["count"] == 1


def test_bridge_keeps_coordinator_path_when_github_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("COORDINATION_ISSUES_BACKEND", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_: {
            "status": "ok",
            "COORDINATOR_AVAILABLE": True,
            "COORDINATION_TRANSPORT": "http",
            "http_url": "http://coord.example",
            "CAN_ISSUES": True,
        }
    )
    captured: list[dict[str, Any]] = []

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs)
        return {
            "status_code": 200,
            "data": {"success": True, "issue": {"id": "uuid-1"}},
            "error": None,
        }

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)
    result = coordination_bridge.try_issue_create(title="coord path")
    assert result["status"] == "ok"
    assert captured[0]["path"] == "/issues/create"
    # Seeder compatibility: data.id is populated from the nested issue.
    assert result["data"]["id"] == "uuid-1"
