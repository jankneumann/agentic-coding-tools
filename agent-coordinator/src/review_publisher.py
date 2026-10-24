"""Post a terminal review job to GitHub as one consolidated COMMENT review.

The coordinator, not the review hosts, holds the GitHub credential: a GitHub
App installation token minted per publication. Hosts therefore need no write
access to the repository at all. The review event is always ``COMMENT`` —
the factory's reviewers advise; approval stays with a human or with the
repository's own approval check.
"""

import time
from typing import Any

import httpx
import jwt

from .config import ReviewQueueConfig

_GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
# GitHub rejects review bodies over 65536 characters.
_MAX_BODY = 60000


class PublishError(Exception):
    """A publication that did not post; ``code`` is stored on the job."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def app_jwt(cfg: ReviewQueueConfig, now: float | None = None) -> str:
    """Sign the short-lived JWT that authenticates as the GitHub App."""
    issued = int(now if now is not None else time.time()) - 60  # clock skew
    return jwt.encode(
        {"iat": issued, "exp": issued + 540, "iss": cfg.github_app_id},
        cfg.github_app_private_key,
        algorithm="RS256",
    )


def render_review_body(job: dict[str, Any]) -> str:
    """Consolidate every lane's findings into one markdown review body."""
    lanes: list[dict[str, Any]] = job.get("lanes") or []
    verified = [lane for lane in lanes if lane.get("verified")]
    lines = [
        f"## Factory review — round {job['round']} at `{job['head_sha'][:12]}`",
        "",
        f"Verified lanes: {len(verified)} of {job['lanes_required']} required "
        f"({', '.join(lane['vendor'] for lane in verified) or 'none'}).",
    ]
    if job.get("status") != "quorum_met":
        lines += [
            "",
            "> **Partial review.** Quorum was not reached within the pass budget; "
            "treat this as advisory from the lanes listed.",
        ]
    for lane in lanes:
        findings: list[dict[str, Any]] = lane.get("findings") or []
        detail = "verified" if lane.get("verified") else "unverified"
        if lane.get("model"):
            detail += f", {lane['model']}"
        lines += ["", f"### {lane['vendor']} ({detail})"]
        if lane.get("verdict"):
            lines.append(f"Verdict: **{lane['verdict']}**")
        if lane.get("error"):
            lines.append(f"Error: {lane['error']}")
        if not findings:
            lines.append("_No findings._")
        for finding in findings:
            lines.append(_render_finding(finding))
    body = "\n".join(lines)
    if len(body) > _MAX_BODY:
        body = body[:_MAX_BODY] + "\n\n_…truncated; full findings are in the coordinator._"
    return body


def _render_finding(finding: dict[str, Any]) -> str:
    severity = finding.get("criticality") or finding.get("severity") or "info"
    where = finding.get("file_path") or finding.get("file") or ""
    if where and finding.get("line"):
        where = f"{where}:{finding['line']}"
    text = finding.get("description") or finding.get("title") or str(finding)
    location = f" `{where}`" if where else ""
    return f"- **{severity}**{location} — {text}"


class GitHubReviewPublisher:
    """Mint an installation token, re-check the head, and post the review."""

    def __init__(self, cfg: ReviewQueueConfig):
        self._cfg = cfg

    async def publish(self, job: dict[str, Any]) -> int:
        """Post ``job`` as a COMMENT review; return the GitHub review id."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await self._installation_token(client)
            auth = {**_GITHUB_HEADERS, "Authorization": f"Bearer {token}"}
            base = f"{self._cfg.github_api_url}/repos/{job['repo']}/pulls/{job['pr']}"

            pull = await client.get(base, headers=auth)
            _raise_for(pull, "pull_lookup_failed")
            if pull.json().get("head", {}).get("sha") != job["head_sha"]:
                raise PublishError("head_moved")

            resp = await client.post(
                f"{base}/reviews",
                headers=auth,
                json={
                    "commit_id": job["head_sha"],
                    "event": "COMMENT",
                    "body": render_review_body(job),
                },
            )
            _raise_for(resp, "review_post_failed")
            return int(resp.json()["id"])

    async def _installation_token(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            f"{self._cfg.github_api_url}/app/installations/"
            f"{self._cfg.github_app_installation_id}/access_tokens",
            headers={**_GITHUB_HEADERS, "Authorization": f"Bearer {app_jwt(self._cfg)}"},
        )
        _raise_for(resp, "installation_token_failed")
        return str(resp.json()["token"])


def _raise_for(resp: httpx.Response, code: str) -> None:
    if resp.status_code >= 400:
        raise PublishError(code, f"HTTP {resp.status_code}: {resp.text[:300]}")
