"""GitHub Issues backing store for coordination_bridge issue APIs.

Interim durability layer for issue #429: coordinator writes return success
with a generated UUID and then vanish from every subsequent read. Callers
keep speaking ``try_issue_*``; this module stores identity and state in
GitHub Issues so a create followed by a list-by-label in a separate
process observes the record.

``depends_on`` has no GitHub primitive. It is rendered into the issue body
as a metadata comment plus a task-list, and parsed back on read.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

_GITHUB_API = "https://api.github.com"
_USER_AGENT = "agentic-coding-tools-coordination-bridge/0.1"
_METADATA_RE = re.compile(
    r"<!-- coordinator-issue\n(?P<body>.*?)\n-->",
    re.DOTALL,
)
_TOKEN_ENV_KEYS = ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT")
_REPO_ENV_KEYS = ("COORDINATION_GITHUB_REPO", "GITHUB_REPOSITORY")

_CANONICAL_ACTIVE_STATUSES = frozenset({"pending", "claimed", "running"})
_CANONICAL_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
_CANONICAL_STATUSES = _CANONICAL_ACTIVE_STATUSES | _CANONICAL_TERMINAL_STATUSES
_FRIENDLY_STATUS_ALIASES = {
    "open": "pending",
    "in_progress": "running",
    "closed": "completed",
}


def _canonical_status(status: str | None, *, fallback: str) -> str:
    value = str(status or "").strip().lower()
    return _FRIENDLY_STATUS_ALIASES.get(value, value if value in _CANONICAL_STATUSES else fallback)


def _github_token() -> str | None:
    for key in _TOKEN_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def _github_repo() -> str | None:
    for key in _REPO_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value and "/" in value and not value.startswith("/"):
            return value
    return None


def github_configured() -> bool:
    return bool(_github_token() and _github_repo())


def issues_backend() -> str:
    """Select the issue store.

    GitHub is opt-in: ``COORDINATION_ISSUES_BACKEND=github``, or the dedicated
    ``COORDINATION_GITHUB_REPO`` env (not ``GITHUB_REPOSITORY``, which GitHub
    Actions always sets and would silently retarget CI onto live Issues).
    """
    explicit = os.environ.get("COORDINATION_ISSUES_BACKEND", "").strip().lower()
    if explicit in {"github", "coordinator"}:
        return explicit
    if os.environ.get("COORDINATION_GITHUB_REPO", "").strip() and _github_token():
        return "github"
    return "coordinator"


def _ok(
    operation: str,
    *,
    status_code: int,
    data: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": "ok",
        "operation": operation,
        "COORDINATOR_AVAILABLE": True,
        "COORDINATION_TRANSPORT": "github",
        "status_code": status_code,
        "response": extra or data,
        "data": data,
    }
    if "issue" in (extra or {}):
        result["issue"] = extra["issue"]  # type: ignore[index]
    if "issues" in (extra or {}):
        result["issues"] = extra["issues"]  # type: ignore[index]
    return result


def _error(
    operation: str,
    *,
    status_code: int | None,
    error: str | None,
    data: Any = None,
) -> dict[str, Any]:
    status = "error" if status_code and status_code >= 400 else "skipped"
    return {
        "status": status,
        "operation": operation,
        "COORDINATOR_AVAILABLE": True,
        "COORDINATION_TRANSPORT": "github",
        "status_code": status_code,
        "response": data,
        "data": data if isinstance(data, dict) else {},
        "error": error,
        "reason": error or "github_error",
    }


def _render_body(
    *,
    description: str | None,
    issue_type: str,
    priority: int,
    depends_on: list[str] | None,
    parent_id: str | None,
    status: str = "pending",
) -> str:
    deps = ",".join(depends_on or [])
    meta = (
        "<!-- coordinator-issue\n"
        f"issue_type: {issue_type}\n"
        f"priority: {priority}\n"
        f"status: {status}\n"
        f"depends_on: {deps}\n"
        f"parent_id: {parent_id or ''}\n"
        "-->"
    )
    parts = [meta]
    if description:
        parts.append(description.strip())
    if depends_on:
        parts.append("Depends on:")
        parts.extend(f"- [ ] #{dep}" for dep in depends_on)
    return "\n\n".join(parts)


def _parse_metadata(body: str) -> dict[str, Any]:
    match = _METADATA_RE.search(body or "")
    parsed: dict[str, Any] = {
        "issue_type": "task",
        "priority": 5,
        "depends_on": [],
        "parent_id": None,
        "description": body or "",
        "status": None,
    }
    if match:
        for line in match.group("body").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == "issue_type" and value:
                parsed["issue_type"] = value
            elif key == "priority" and value.isdigit():
                parsed["priority"] = int(value)
            elif key == "depends_on":
                parsed["depends_on"] = [part for part in value.split(",") if part]
            elif key == "parent_id":
                parsed["parent_id"] = value or None
            elif key == "status" and value in _CANONICAL_STATUSES:
                parsed["status"] = value
        parsed["description"] = _METADATA_RE.sub("", body or "").strip()
        parsed["description"] = re.sub(
            r"^Depends on:\n(?:- \[[ x]\] .+\n?)*",
            "",
            parsed["description"],
            flags=re.MULTILINE,
        ).strip()
    return parsed


def _map_issue(raw: dict[str, Any]) -> dict[str, Any]:
    meta = _parse_metadata(str(raw.get("body") or ""))
    labels = []
    for label in raw.get("labels") or []:
        if isinstance(label, dict) and label.get("name"):
            labels.append(str(label["name"]))
        elif isinstance(label, str):
            labels.append(label)
    state = raw.get("state") or "open"
    fallback_status = "pending" if state == "open" else "completed"
    status = _canonical_status(meta.get("status"), fallback=fallback_status)
    if state == "closed" and status in _CANONICAL_ACTIVE_STATUSES:
        status = "completed"
    elif state == "open" and status in _CANONICAL_TERMINAL_STATUSES:
        status = "pending"
    assignee = None
    raw_assignee = raw.get("assignee")
    if isinstance(raw_assignee, dict):
        assignee = raw_assignee.get("login")
    issue_id = str(raw.get("number") or raw.get("id"))
    change_id = None
    task_key = None
    for label in labels:
        if label.startswith("change:"):
            change_id = label.split(":", 1)[1] or None
        elif label.startswith("task:"):
            task_key = label.split(":", 1)[1] or None
    return {
        "id": issue_id,
        "title": raw.get("title"),
        "description": meta["description"],
        "body": meta["description"],
        "status": status,
        "priority": meta["priority"],
        "issue_type": meta["issue_type"],
        "labels": labels,
        "assignee": assignee,
        "parent_id": meta["parent_id"],
        "depends_on": meta["depends_on"],
        "created_at": raw.get("created_at"),
        "completed_at": raw.get("closed_at"),
        "closed_at": raw.get("closed_at"),
        "close_reason": None,
        "metadata": {},
        "html_url": raw.get("html_url"),
        "change_id": change_id,
        "task_key": task_key,
    }


class GitHubIssuesClient:
    """Thin GitHub Issues client with the coordinator issue vocabulary."""

    def __init__(
        self,
        *,
        token: str,
        repo: str,
        request_fn: Any | None = None,
    ) -> None:
        self.token = token
        self.repo = repo
        self._request_fn = request_fn

    def _http(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self._request_fn is not None:
            return self._request_fn(method, path, payload)
        url = f"{_GITHUB_API}{path}" if path.startswith("/") else path
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": _USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        body: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        request_obj = url_request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with url_request.urlopen(request_obj, timeout=20) as response:
                return {
                    "status_code": response.getcode(),
                    "data": json.loads(response.read().decode("utf-8") or "null"),
                    "error": None,
                }
        except url_error.HTTPError as exc:
            raw = exc.read()
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                data = {"raw": raw.decode("utf-8", errors="replace")}
            return {"status_code": exc.code, "data": data, "error": str(exc)}
        except (url_error.URLError, TimeoutError, OSError) as exc:
            return {"status_code": None, "data": None, "error": str(exc)}

    def _ensure_labels(self, labels: list[str]) -> None:
        for name in labels:
            self._http(
                "POST",
                f"/repos/{self.repo}/labels",
                {"name": name, "color": "ededed"},
            )

    def create(
        self,
        *,
        title: str,
        description: str | None = None,
        issue_type: str = "task",
        priority: int = 5,
        labels: list[str] | None = None,
        parent_id: str | None = None,
        assignee: str | None = None,
        depends_on: list[str] | None = None,
    ) -> dict[str, Any]:
        label_list = list(labels or [])
        self._ensure_labels(label_list)
        payload: dict[str, Any] = {
            "title": title,
            "body": _render_body(
                description=description,
                issue_type=issue_type,
                priority=priority,
                depends_on=depends_on,
                parent_id=parent_id,
                status="pending",
            ),
            "labels": label_list,
        }
        if assignee:
            payload["assignees"] = [assignee]
        response = self._http("POST", f"/repos/{self.repo}/issues", payload)
        if response["status_code"] not in (200, 201):
            return _error(
                "try_issue_create",
                status_code=response["status_code"],
                error=response.get("error") or "github_write_failed",
                data=response.get("data"),
            )
        mapped = _map_issue(response["data"])
        return _ok(
            "try_issue_create",
            status_code=response["status_code"],
            data=mapped,
            extra={"success": True, "issue": mapped},
        )

    def list_issues(
        self,
        *,
        status: str | None = None,
        issue_type: str | None = None,
        labels: list[str] | None = None,
        parent_id: str | None = None,
        assignee: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        requested_status = str(status or "").strip().lower()
        params: dict[str, str] = {"state": "all", "per_page": str(min(limit or 100, 100))}
        if requested_status in _CANONICAL_ACTIVE_STATUSES | {"open", "in_progress"}:
            params["state"] = "open"
        elif requested_status in _CANONICAL_TERMINAL_STATUSES | {"closed"}:
            params["state"] = "closed"
        if labels:
            params["labels"] = ",".join(labels)
        query = url_parse.urlencode(params)
        response = self._http("GET", f"/repos/{self.repo}/issues?{query}")
        if response["status_code"] != 200:
            return _error(
                "try_issue_list",
                status_code=response["status_code"],
                error=response.get("error") or "github_list_failed",
                data=response.get("data"),
            )
        raw_issues = response["data"] or []
        if not isinstance(raw_issues, list):
            raw_issues = []
        mapped = [_map_issue(item) for item in raw_issues if "pull_request" not in item]
        if requested_status in _CANONICAL_STATUSES:
            mapped = [
                item for item in mapped if item.get("status") == requested_status
            ]
        if issue_type:
            mapped = [item for item in mapped if item.get("issue_type") == issue_type]
        if parent_id:
            mapped = [item for item in mapped if item.get("parent_id") == parent_id]
        if assignee:
            mapped = [item for item in mapped if item.get("assignee") == assignee]
        if limit is not None:
            mapped = mapped[:limit]
        extra = {"success": True, "issues": mapped, "count": len(mapped)}
        return _ok(
            "try_issue_list",
            status_code=200,
            data=extra,
            extra=extra,
        )

    def show(self, issue_id: str) -> dict[str, Any]:
        response = self._http("GET", f"/repos/{self.repo}/issues/{issue_id}")
        if response["status_code"] != 200:
            return _error(
                "try_issue_show",
                status_code=response["status_code"],
                error=response.get("error") or "issue_not_found",
                data=response.get("data"),
            )
        mapped = _map_issue(response["data"])
        return _ok(
            "try_issue_show",
            status_code=200,
            data=mapped,
            extra={"success": True, "issue": mapped},
        )

    def update(
        self,
        *,
        issue_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        labels: list[str] | None = None,
        assignee: str | None = None,
        issue_type: str | None = None,
    ) -> dict[str, Any]:
        current = self.show(issue_id)
        if current["status"] != "ok":
            return current
        existing = current["data"]
        new_type = issue_type if issue_type is not None else existing.get("issue_type", "task")
        new_priority = priority if priority is not None else existing.get("priority", 5)
        new_description = (
            description if description is not None else existing.get("description")
        )
        new_status = _canonical_status(
            status,
            fallback=str(existing.get("status") or "pending"),
        )
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        payload["body"] = _render_body(
            description=new_description,
            issue_type=str(new_type),
            priority=int(new_priority),
            depends_on=list(existing.get("depends_on") or []),
            parent_id=existing.get("parent_id"),
            status=new_status,
        )
        if status is not None and new_status in _CANONICAL_TERMINAL_STATUSES:
            payload["state"] = "closed"
        elif status is not None and new_status in _CANONICAL_ACTIVE_STATUSES:
            payload["state"] = "open"
        if labels is not None:
            self._ensure_labels(labels)
            payload["labels"] = labels
        if assignee is not None:
            payload["assignees"] = [assignee] if assignee else []
        response = self._http("PATCH", f"/repos/{self.repo}/issues/{issue_id}", payload)
        if response["status_code"] != 200:
            return _error(
                "try_issue_update",
                status_code=response["status_code"],
                error=response.get("error") or "github_update_failed",
                data=response.get("data"),
            )
        mapped = _map_issue(response["data"])
        return _ok(
            "try_issue_update",
            status_code=200,
            data=mapped,
            extra={"success": True, "issue": mapped},
        )

    def close(
        self,
        *,
        issue_id: str | None = None,
        issue_ids: list[str] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        del reason
        ids = list(issue_ids or [])
        if issue_id is not None:
            ids.append(issue_id)
        closed = []
        for item_id in ids:
            updated = self.update(issue_id=item_id, status="completed")
            if updated["status"] != "ok":
                return _error(
                    "try_issue_close",
                    status_code=updated.get("status_code"),
                    error=updated.get("error") or "github_close_failed",
                    data=updated.get("data"),
                )
            closed.append(updated["data"])
        extra = {"success": True, "issues": closed, "count": len(closed)}
        return _ok("try_issue_close", status_code=200, data=extra, extra=extra)

    def comment(self, *, issue_id: str, body: str) -> dict[str, Any]:
        response = self._http(
            "POST",
            f"/repos/{self.repo}/issues/{issue_id}/comments",
            {"body": body},
        )
        if response["status_code"] not in (200, 201):
            return _error(
                "try_issue_comment",
                status_code=response["status_code"],
                error=response.get("error") or "github_comment_failed",
                data=response.get("data"),
            )
        extra = {"success": True, "comment": response["data"]}
        return _ok(
            "try_issue_comment",
            status_code=response["status_code"],
            data=extra,
            extra=extra,
        )

    def ready(
        self, *, parent_id: str | None = None, limit: int | None = None
    ) -> dict[str, Any]:
        listed = self.list_issues(status="open", parent_id=parent_id, limit=None)
        if listed["status"] != "ok":
            return listed
        open_ids = {item["id"] for item in listed["data"]["issues"]}
        ready = [
            item
            for item in listed["data"]["issues"]
            if not any(dep in open_ids for dep in item.get("depends_on") or [])
        ]
        if limit is not None:
            ready = ready[:limit]
        extra = {"success": True, "issues": ready, "count": len(ready)}
        return _ok("try_issue_ready", status_code=200, data=extra, extra=extra)

    def blocked(self, *, limit: int | None = None) -> dict[str, Any]:
        listed = self.list_issues(status="open", limit=None)
        if listed["status"] != "ok":
            return listed
        open_ids = {item["id"] for item in listed["data"]["issues"]}
        blocked = [
            item
            for item in listed["data"]["issues"]
            if any(dep in open_ids for dep in item.get("depends_on") or [])
        ]
        if limit is not None:
            blocked = blocked[:limit]
        extra = {"success": True, "issues": blocked, "count": len(blocked)}
        return _ok("try_issue_blocked", status_code=200, data=extra, extra=extra)

    def search(self, *, query: str, limit: int | None = None) -> dict[str, Any]:
        listed = self.list_issues(limit=None)
        if listed["status"] != "ok":
            return listed
        needle = query.lower()
        matches = [
            item
            for item in listed["data"]["issues"]
            if needle in str(item.get("title") or "").lower()
            or needle in str(item.get("description") or "").lower()
        ]
        if limit is not None:
            matches = matches[:limit]
        extra = {"success": True, "issues": matches, "count": len(matches)}
        return _ok("try_issue_search", status_code=200, data=extra, extra=extra)


def _default_client() -> GitHubIssuesClient:
    token = _github_token()
    repo = _github_repo()
    if not token or not repo:
        raise RuntimeError("GitHub issues backend is not configured")
    return GitHubIssuesClient(token=token, repo=repo)


def _unconfigured(operation: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "operation": operation,
        "reason": "github_unconfigured",
        "COORDINATOR_AVAILABLE": False,
        "COORDINATION_TRANSPORT": "none",
    }
