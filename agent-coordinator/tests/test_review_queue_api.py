"""HTTP tests for the cross-host review queue (``/reviews/*``).

The service is replaced by a fake so these tests pin the route layer: which
credential reaches which route, how RPC reasons map to status codes, and when
the coordinator attempts publication. The SQL state machine itself is covered
by ``tests/integration/postgres/test_review_queue_postgres.py``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import src.review_queue
import src.review_routes
from src.config import reset_config
from src.coordination_api import create_coordination_api
from src.review_publisher import PublishError

_TEST_KEY = "review-test-key"
_PRODUCER_TOKEN = "producer-secret"
_REPO = "acme/widgets"
_HEAD = "a" * 40
_BASE = "b" * 40


def _job(**updates: Any) -> dict[str, Any]:
    job = {
        "job_id": "job-1",
        "repo": _REPO,
        "pr": 7,
        "head_sha": _HEAD,
        "round": 1,
        "lanes_required": 2,
        "status": "quorum_met",
        "lanes": [],
    }
    job.update(updates)
    return job


class FakeReviewQueue:
    def __init__(self) -> None:
        self.submit_job = AsyncMock(
            return_value={"success": True, "created": True, "job": _job(status="active")}
        )
        self.record_lanes = AsyncMock(
            return_value={"success": True, "publish_ready": False, "job": _job(status="active")}
        )
        self.get_round = AsyncMock(return_value={"found": True, "job": _job()})
        self.claim_publication = AsyncMock(return_value={"claimed": True, "job": _job()})
        self.finish_publication = AsyncMock(return_value=None)


@pytest.fixture()
def fake_service(monkeypatch: pytest.MonkeyPatch) -> FakeReviewQueue:
    fake = FakeReviewQueue()
    monkeypatch.setattr(src.review_queue, "_review_queue_service", fake)
    return fake


@pytest.fixture()
def authorize(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    # Captured by install_review_routes when the app is built, so patch first.
    mock = AsyncMock()
    monkeypatch.setattr("src.coordination_api.authorize_operation", mock)
    return mock


def _configure(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    for name in (
        "REVIEW_PRODUCER_TOKEN",
        "REVIEW_ALLOWED_REPOS",
        "REVIEW_GITHUB_APP_ID",
        "REVIEW_GITHUB_APP_INSTALLATION_ID",
        "REVIEW_GITHUB_APP_PRIVATE_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    reset_config()


@pytest.fixture()
def client(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeReviewQueue, authorize: AsyncMock
) -> TestClient:
    _configure(
        monkeypatch,
        REVIEW_PRODUCER_TOKEN=_PRODUCER_TOKEN,
        REVIEW_ALLOWED_REPOS=_REPO,
    )
    return TestClient(create_coordination_api())


def _job_body(**updates: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"repo": _REPO, "pr": 7, "head_sha": _HEAD, "base_sha": _BASE}
    body.update(updates)
    return body


def _producer() -> dict[str, str]:
    return {"X-Review-Producer-Token": _PRODUCER_TOKEN}


def _api_key() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


# --------------------------------------------------------------------------- #
# POST /reviews/jobs
# --------------------------------------------------------------------------- #


def test_producer_token_submits_as_review_producer(
    client: TestClient, fake_service: FakeReviewQueue, authorize: AsyncMock
) -> None:
    response = client.post("/reviews/jobs", headers=_producer(), json=_job_body())

    assert response.status_code == 200
    assert response.json()["created"] is True
    request, submitted_by = fake_service.submit_job.await_args.args
    assert submitted_by == "review-producer"
    assert request.head_sha == _HEAD
    authorize.assert_not_awaited()


def test_wrong_producer_token_is_rejected(
    client: TestClient, fake_service: FakeReviewQueue
) -> None:
    response = client.post(
        "/reviews/jobs", headers={"X-Review-Producer-Token": "nope"}, json=_job_body()
    )

    assert response.status_code == 401
    fake_service.submit_job.assert_not_awaited()


def test_producer_header_without_configured_token_is_rejected(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeReviewQueue, authorize: AsyncMock
) -> None:
    _configure(monkeypatch, REVIEW_ALLOWED_REPOS=_REPO)
    client = TestClient(create_coordination_api())

    response = client.post(
        "/reviews/jobs", headers={"X-Review-Producer-Token": ""}, json=_job_body()
    )

    assert response.status_code == 401
    fake_service.submit_job.assert_not_awaited()


def test_producer_cannot_reach_unlisted_repo(
    client: TestClient, fake_service: FakeReviewQueue
) -> None:
    response = client.post(
        "/reviews/jobs", headers=_producer(), json=_job_body(repo="acme/other")
    )

    assert response.status_code == 403
    fake_service.submit_job.assert_not_awaited()


def test_producer_with_empty_allowlist_reaches_nothing(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeReviewQueue, authorize: AsyncMock
) -> None:
    _configure(monkeypatch, REVIEW_PRODUCER_TOKEN=_PRODUCER_TOKEN)
    client = TestClient(create_coordination_api())

    response = client.post("/reviews/jobs", headers=_producer(), json=_job_body())

    assert response.status_code == 403


def test_submit_without_credentials_is_rejected(
    client: TestClient, fake_service: FakeReviewQueue
) -> None:
    response = client.post("/reviews/jobs", json=_job_body())

    assert response.status_code == 401
    fake_service.submit_job.assert_not_awaited()


def test_api_key_submission_is_policy_checked(
    client: TestClient, fake_service: FakeReviewQueue, authorize: AsyncMock
) -> None:
    response = client.post("/reviews/jobs", headers=_api_key(), json=_job_body())

    assert response.status_code == 200
    kwargs = authorize.await_args.kwargs
    assert kwargs["operation"] == "submit_work"
    assert kwargs["resource"] == _REPO
    assert kwargs["context"] == {"task_type": "review", "pr": 7}
    assert fake_service.submit_job.await_args.args[1] == "cloud-agent"


def test_api_key_with_empty_allowlist_falls_back_to_policy(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeReviewQueue, authorize: AsyncMock
) -> None:
    _configure(monkeypatch)
    client = TestClient(create_coordination_api())

    response = client.post(
        "/reviews/jobs", headers=_api_key(), json=_job_body(repo="acme/other")
    )

    assert response.status_code == 200
    authorize.assert_awaited_once()


def test_rejected_submission_is_422(client: TestClient, fake_service: FakeReviewQueue) -> None:
    fake_service.submit_job.return_value = {"success": False, "reason": "round_conflict"}

    response = client.post("/reviews/jobs", headers=_producer(), json=_job_body())

    assert response.status_code == 422
    assert response.json()["detail"] == "round_conflict"


def test_malformed_sha_is_rejected_before_the_service(
    client: TestClient, fake_service: FakeReviewQueue
) -> None:
    response = client.post(
        "/reviews/jobs", headers=_producer(), json=_job_body(head_sha="HEAD")
    )

    assert response.status_code == 422
    fake_service.submit_job.assert_not_awaited()


# --------------------------------------------------------------------------- #
# POST /reviews/results
# --------------------------------------------------------------------------- #


_LANES = {"task_id": "task-1", "lanes": [{"vendor": "codex", "verified": True}]}


def test_results_are_policy_checked_as_complete_work(
    client: TestClient, fake_service: FakeReviewQueue, authorize: AsyncMock
) -> None:
    response = client.post("/reviews/results", headers=_api_key(), json=_LANES)

    assert response.status_code == 200
    assert authorize.await_args.kwargs["operation"] == "complete_work"
    task_id, agent_id, lanes = fake_service.record_lanes.await_args.args
    assert (task_id, agent_id, lanes[0].vendor) == ("task-1", "cloud-agent", "codex")
    assert "publication" not in response.json()


def test_results_reject_the_producer_token(
    client: TestClient, fake_service: FakeReviewQueue
) -> None:
    response = client.post("/reviews/results", headers=_producer(), json=_LANES)

    assert response.status_code == 401
    fake_service.record_lanes.assert_not_awaited()


@pytest.mark.parametrize(
    ("reason", "status"),
    [("not_claimant", 403), ("task_not_found", 404), ("job_not_found", 404)],
)
def test_result_errors_map_to_status_codes(
    client: TestClient, fake_service: FakeReviewQueue, reason: str, status: int
) -> None:
    fake_service.record_lanes.return_value = {"success": False, "reason": reason}

    response = client.post("/reviews/results", headers=_api_key(), json=_LANES)

    assert response.status_code == status
    assert response.json()["detail"] == reason


def test_superseded_pass_is_reported_in_the_body(
    client: TestClient, fake_service: FakeReviewQueue
) -> None:
    fake_service.record_lanes.return_value = {"success": False, "reason": "superseded"}

    response = client.post("/reviews/results", headers=_api_key(), json=_LANES)

    assert response.status_code == 200
    assert response.json()["reason"] == "superseded"


def test_publish_ready_without_github_app_reports_disabled(
    client: TestClient, fake_service: FakeReviewQueue
) -> None:
    fake_service.record_lanes.return_value = {
        "success": True,
        "publish_ready": True,
        "job": _job(),
    }

    response = client.post("/reviews/results", headers=_api_key(), json=_LANES)

    assert response.json()["publication"] == {
        "published": False,
        "reason": "publisher_disabled",
    }
    fake_service.claim_publication.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Publication (_publish)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def publisher_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(
        monkeypatch,
        REVIEW_GITHUB_APP_ID="1",
        REVIEW_GITHUB_APP_INSTALLATION_ID="2",
        REVIEW_GITHUB_APP_PRIVATE_KEY="unused-by-the-fake",
    )


def _stub_publisher(monkeypatch: pytest.MonkeyPatch, publish: AsyncMock) -> None:
    class StubPublisher:
        def __init__(self, cfg: Any) -> None:
            self.publish = publish

    monkeypatch.setattr(src.review_routes, "GitHubReviewPublisher", StubPublisher)


async def test_publish_records_the_review_id(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeReviewQueue, publisher_enabled: None
) -> None:
    _stub_publisher(monkeypatch, AsyncMock(return_value=991))

    outcome = await src.review_routes._publish("job-1")

    assert outcome == {"published": True, "review_id": 991}
    fake_service.finish_publication.assert_awaited_once_with("job-1", review_id=991)


async def test_publish_skips_a_job_already_claimed(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeReviewQueue, publisher_enabled: None
) -> None:
    publish = AsyncMock()
    _stub_publisher(monkeypatch, publish)
    fake_service.claim_publication.return_value = {"claimed": False}

    outcome = await src.review_routes._publish("job-1")

    assert outcome == {"published": False, "reason": "already_claimed"}
    publish.assert_not_awaited()
    fake_service.finish_publication.assert_not_awaited()


async def test_publish_failure_releases_the_claim_with_its_error(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeReviewQueue, publisher_enabled: None
) -> None:
    _stub_publisher(monkeypatch, AsyncMock(side_effect=PublishError("head_moved")))

    outcome = await src.review_routes._publish("job-1")

    assert outcome == {"published": False, "reason": "head_moved"}
    fake_service.finish_publication.assert_awaited_once_with("job-1", error="head_moved")


async def test_publish_network_failure_is_github_unreachable(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeReviewQueue, publisher_enabled: None
) -> None:
    import httpx

    _stub_publisher(monkeypatch, AsyncMock(side_effect=httpx.ConnectError("down")))

    outcome = await src.review_routes._publish("job-1")

    assert outcome == {"published": False, "reason": "github_unreachable"}
    assert fake_service.finish_publication.await_args.kwargs["error"] == "down"


# --------------------------------------------------------------------------- #
# GET /reviews/rounds
# --------------------------------------------------------------------------- #


def test_round_lookup_returns_the_service_result(
    client: TestClient, fake_service: FakeReviewQueue
) -> None:
    response = client.get(
        "/reviews/rounds",
        headers=_api_key(),
        params={"repo": _REPO, "pr": 7, "head_sha": _HEAD, "round": 2},
    )

    assert response.status_code == 200
    assert response.json()["found"] is True
    fake_service.get_round.assert_awaited_once_with(_REPO, 7, _HEAD, 2)


def test_round_lookup_validates_the_sha(
    client: TestClient, fake_service: FakeReviewQueue
) -> None:
    response = client.get(
        "/reviews/rounds",
        headers=_api_key(),
        params={"repo": _REPO, "pr": 7, "head_sha": "abc"},
    )

    assert response.status_code == 422
    fake_service.get_round.assert_not_awaited()


def test_round_lookup_requires_a_key(client: TestClient) -> None:
    response = client.get(
        "/reviews/rounds", params={"repo": _REPO, "pr": 7, "head_sha": _HEAD}
    )

    assert response.status_code == 401
