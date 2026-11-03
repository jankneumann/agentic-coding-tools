"""GitHub publication of a terminal review job (``src.review_publisher``)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.config import ReviewQueueConfig
from src.review_publisher import (
    GitHubReviewPublisher,
    PublishError,
    app_jwt,
    render_review_body,
)

_API = "https://github.test"
_HEAD = "e" * 40
_PULL = f"{_API}/repos/acme/widgets/pulls/9"
_TOKEN_URL = f"{_API}/app/installations/77/access_tokens"


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def cfg(private_key: rsa.RSAPrivateKey) -> ReviewQueueConfig:
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return ReviewQueueConfig(
        github_app_id="123",
        github_app_installation_id="77",
        github_app_private_key=pem,
        github_api_url=_API,
    )


def _job(**updates: Any) -> dict[str, Any]:
    job: dict[str, Any] = {
        "job_id": "j1",
        "repo": "acme/widgets",
        "pr": 9,
        "head_sha": _HEAD,
        "round": 2,
        "lanes_required": 2,
        "status": "quorum_met",
        "lanes": [
            {
                "vendor": "codex",
                "verified": True,
                "model": "m-1",
                "verdict": "changes_requested",
                "findings": [
                    {
                        "criticality": "high",
                        "file_path": "src/a.py",
                        "line": 4,
                        "description": "bug",
                    }
                ],
            },
            {"vendor": "gemini", "verified": True, "findings": []},
        ],
    }
    job.update(updates)
    return job


def test_app_jwt_is_short_lived_and_backdated(
    cfg: ReviewQueueConfig, private_key: rsa.RSAPrivateKey
) -> None:
    token = app_jwt(cfg, now=1_000_000)

    claims = jwt.decode(token, private_key.public_key(), algorithms=["RS256"],
                        options={"verify_exp": False, "verify_iat": False})
    assert claims == {"iat": 999_940, "exp": 1_000_480, "iss": "123"}


def test_body_lists_verified_lanes_and_findings() -> None:
    body = render_review_body(_job())

    assert body.startswith(f"## Factory review — round 2 at `{_HEAD[:12]}`")
    assert "Verified lanes: 2 of 2 required (codex, gemini)." in body
    assert "### codex (verified, m-1)" in body
    assert "Verdict: **changes_requested**" in body
    assert "- **high** `src/a.py:4` — bug" in body
    assert "### gemini (verified)\n_No findings._" in body
    assert "Partial review" not in body


def test_body_flags_a_partial_review() -> None:
    lanes = [{"vendor": "codex", "verified": False, "error": "timeout"}]

    body = render_review_body(_job(status="unreachable", lanes=lanes))

    assert "Verified lanes: 0 of 2 required (none)." in body
    assert "> **Partial review.**" in body
    assert "Error: timeout" in body


def test_body_is_truncated_below_the_github_limit() -> None:
    findings = [{"description": "x" * 1000} for _ in range(100)]
    lanes = [{"vendor": "codex", "verified": True, "findings": findings}]

    body = render_review_body(_job(lanes=lanes))

    assert len(body) < 65536
    assert body.endswith("_…truncated; full findings are in the coordinator._")


@respx.mock
async def test_publish_posts_one_comment_review_on_the_head(cfg: ReviewQueueConfig) -> None:
    token = respx.post(_TOKEN_URL).mock(return_value=httpx.Response(201, json={"token": "inst"}))
    respx.get(_PULL).mock(return_value=httpx.Response(200, json={"head": {"sha": _HEAD}}))
    review = respx.post(f"{_PULL}/reviews").mock(return_value=httpx.Response(200, json={"id": 555}))

    review_id = await GitHubReviewPublisher(cfg).publish(_job())

    assert review_id == 555
    assert token.calls.last.request.headers["Authorization"].startswith("Bearer ey")
    sent = review.calls.last.request
    assert sent.headers["Authorization"] == "Bearer inst"
    payload = json.loads(sent.content)
    assert payload["event"] == "COMMENT"
    assert payload["commit_id"] == _HEAD
    assert "Factory review" in payload["body"]


@respx.mock
async def test_publish_refuses_when_the_head_moved(cfg: ReviewQueueConfig) -> None:
    respx.post(_TOKEN_URL).mock(return_value=httpx.Response(201, json={"token": "inst"}))
    respx.get(_PULL).mock(return_value=httpx.Response(200, json={"head": {"sha": "f" * 40}}))
    review = respx.post(f"{_PULL}/reviews")

    with pytest.raises(PublishError) as raised:
        await GitHubReviewPublisher(cfg).publish(_job())

    assert raised.value.code == "head_moved"
    assert not review.called


@pytest.mark.parametrize(
    ("failing", "code"),
    [
        ("token", "installation_token_failed"),
        ("pull", "pull_lookup_failed"),
        ("review", "review_post_failed"),
    ],
)
@respx.mock
async def test_publish_names_the_failing_step(
    cfg: ReviewQueueConfig, failing: str, code: str
) -> None:
    def respond(step: str, ok: httpx.Response) -> httpx.Response:
        return httpx.Response(403, text="nope") if step == failing else ok

    respx.post(_TOKEN_URL).mock(
        return_value=respond("token", httpx.Response(201, json={"token": "inst"}))
    )
    respx.get(_PULL).mock(
        return_value=respond("pull", httpx.Response(200, json={"head": {"sha": _HEAD}}))
    )
    respx.post(f"{_PULL}/reviews").mock(
        return_value=respond("review", httpx.Response(200, json={"id": 1}))
    )

    with pytest.raises(PublishError) as raised:
        await GitHubReviewPublisher(cfg).publish(_job())

    assert raised.value.code == code
    assert "HTTP 403" in str(raised.value)


def test_publisher_enabled_needs_all_three_app_settings() -> None:
    partial = ReviewQueueConfig(github_app_id="1", github_app_installation_id="2")
    assert not partial.publisher_enabled()
    assert ReviewQueueConfig(
        github_app_id="1", github_app_installation_id="2", github_app_private_key="k"
    ).publisher_enabled()
