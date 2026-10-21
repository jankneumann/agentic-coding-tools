"""Tests for ``spend_recorder`` (openrouter-review-lane, task 4.3).

Every test injects a transport, so no request reaches a coordinator. The
transport mirrors ``coordination_bridge._http_request``'s keyword signature and
return shape (``{"status_code", "data", "error"}``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import spend_recorder

CHANGE_ID = "example-change"
SENTINEL_KEY = "sk-sentinel-coordinator-key-0123456789"


def _row(generation_id: str = "gen-abc", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "vendor": "openrouter",
        "model": "openai/gpt-5",
        "endpoint_kind": "openrouter",
        "generation_id": generation_id,
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "actual_usd": 0.0042,
        "tokens_estimated": False,
        "work_unit_ref": f"{CHANGE_ID}:PLAN_REVIEW:round-1",
    }
    row.update(overrides)
    return row


class FakeCoordinator:
    """Scripted transport; with ``ledger`` it behaves like the idempotent route."""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []
        self.ledger: dict[str, dict[str, Any]] = {}

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.responses:
            return self.responses.pop(0)
        payload = kwargs["payload"]
        gid = payload["generation_id"]
        if gid in self.ledger:
            return {"status_code": 200, "data": self.ledger[gid], "error": None}
        self.ledger[gid] = {"id": len(self.ledger) + 1, **payload}
        return {"status_code": 201, "data": self.ledger[gid], "error": None}


def _spool(repo: Path) -> Path:
    return spend_recorder.spool_path(CHANGE_ID, repo_root=repo)


def _spool_lines(repo: Path) -> list[dict[str, Any]]:
    path = _spool(repo)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "openspec" / "changes" / CHANGE_ID).mkdir(parents=True)
    return tmp_path


def test_spool_path_is_under_the_change_reviews_dir(repo: Path) -> None:
    path = _spool(repo)
    assert path.name == "spend-spool.jsonl"
    assert path.parent.name == "reviews"
    assert path.parent.parent == repo / "openspec" / "changes" / CHANGE_ID


def test_spool_path_follows_an_archived_change(tmp_path: Path) -> None:
    archived = tmp_path / "openspec" / "changes" / "archive" / f"2026-10-01-{CHANGE_ID}"
    archived.mkdir(parents=True)
    assert spend_recorder.spool_path(CHANGE_ID, repo_root=tmp_path).parent.parent == archived


@pytest.mark.parametrize("bad", ["", "../escape", "a/b", "."])
def test_spool_path_rejects_unsafe_change_ids(repo: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        spend_recorder.spool_path(bad, repo_root=repo)


def test_record_posts_the_row(repo: Path) -> None:
    coordinator = FakeCoordinator()

    outcome = spend_recorder.record(
        _row(), change_id=CHANGE_ID, repo_root=repo, transport=coordinator,
        http_url="http://localhost:8081", api_key=SENTINEL_KEY,
    )

    assert outcome.recorded is True
    assert outcome.spooled is False
    assert outcome.status_code == 201
    assert len(coordinator.calls) == 1
    call = coordinator.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/routing/spend"
    assert call["payload"] == _row()
    assert call["api_key"] == SENTINEL_KEY
    assert not _spool(repo).exists()


def test_duplicate_generation_counts_as_recorded(repo: Path) -> None:
    coordinator = FakeCoordinator([{"status_code": 200, "data": {"id": 7}, "error": None}])

    outcome = spend_recorder.record(
        _row(), change_id=CHANGE_ID, repo_root=repo, transport=coordinator,
        http_url="http://localhost:8081",
    )

    assert outcome.recorded is True
    assert outcome.status_code == 200
    assert not _spool(repo).exists()


def test_record_drops_unknown_fields_before_posting(repo: Path) -> None:
    coordinator = FakeCoordinator()

    spend_recorder.record(
        _row(api_key=SENTINEL_KEY, headers={"Authorization": SENTINEL_KEY}),
        change_id=CHANGE_ID, repo_root=repo, transport=coordinator,
        http_url="http://localhost:8081",
    )

    assert set(coordinator.calls[0]["payload"]) == set(_row())


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ({"status_code": None, "data": None, "error": "<urlopen error refused>"}, "connection_error"),
        ({"status_code": 403, "data": {"detail": "forbidden"}, "error": "HTTP Error 403"}, "http_403"),
        ({"status_code": 503, "data": {}, "error": "HTTP Error 503"}, "http_503"),
    ],
    ids=["connection-error", "forbidden", "unavailable"],
)
def test_failed_write_spools_and_returns_not_recorded(
    repo: Path, response: dict[str, Any], reason: str
) -> None:
    coordinator = FakeCoordinator([response])

    outcome = spend_recorder.record(
        _row(), change_id=CHANGE_ID, repo_root=repo, transport=coordinator,
        http_url="http://localhost:8081", api_key=SENTINEL_KEY,
    )

    assert outcome.recorded is False
    assert outcome.spooled is True
    assert outcome.reason == reason
    lines = _spool_lines(repo)
    assert len(lines) == 1
    assert lines[0]["row"] == _row()
    assert lines[0]["reason"] == reason


def test_spool_appends_one_line_per_failed_write(repo: Path) -> None:
    down = {"status_code": None, "data": None, "error": "refused"}
    coordinator = FakeCoordinator([down, down])

    for gid in ("gen-1", "gen-2"):
        spend_recorder.record(
            _row(gid), change_id=CHANGE_ID, repo_root=repo, transport=coordinator,
            http_url="http://localhost:8081",
        )

    assert [line["row"]["generation_id"] for line in _spool_lines(repo)] == ["gen-1", "gen-2"]


def test_no_api_key_value_appears_in_the_spool(repo: Path) -> None:
    # The transport error text echoes the key, as a careless transport might.
    coordinator = FakeCoordinator(
        [{"status_code": 403, "data": {"echo": SENTINEL_KEY}, "error": f"bad key {SENTINEL_KEY}"}]
    )

    outcome = spend_recorder.record(
        _row(api_key=SENTINEL_KEY), change_id=CHANGE_ID, repo_root=repo,
        transport=coordinator, http_url="http://localhost:8081", api_key=SENTINEL_KEY,
    )

    assert outcome.spooled is True
    assert SENTINEL_KEY not in _spool(repo).read_text()
    assert SENTINEL_KEY not in repr(outcome)


def test_record_without_change_dir_creates_reviews_dir(tmp_path: Path) -> None:
    coordinator = FakeCoordinator([{"status_code": None, "data": None, "error": "down"}])

    outcome = spend_recorder.record(
        _row(), change_id=CHANGE_ID, repo_root=tmp_path, transport=coordinator,
        http_url="http://localhost:8081",
    )

    assert outcome.spooled is True
    assert spend_recorder.spool_path(CHANGE_ID, repo_root=tmp_path).exists()


def test_spooled_total_sums_actual_usd(repo: Path) -> None:
    down = {"status_code": None, "data": None, "error": "down"}
    coordinator = FakeCoordinator([down, down])
    spend_recorder.record(
        _row("gen-1", actual_usd=0.25), change_id=CHANGE_ID, repo_root=repo,
        transport=coordinator, http_url="http://localhost:8081",
    )
    spend_recorder.record(
        _row("gen-2", actual_usd=0.75), change_id=CHANGE_ID, repo_root=repo,
        transport=coordinator, http_url="http://localhost:8081",
    )

    assert spend_recorder.spooled_total_usd(CHANGE_ID, repo_root=repo) == pytest.approx(1.0)
    assert spend_recorder.spooled_total_usd("other-change", repo_root=repo) == 0.0


def test_replay_is_idempotent_and_empties_the_spool(repo: Path) -> None:
    down = FakeCoordinator([{"status_code": None, "data": None, "error": "down"}])
    spend_recorder.record(
        _row(), change_id=CHANGE_ID, repo_root=repo, transport=down,
        http_url="http://localhost:8081",
    )
    assert len(_spool_lines(repo)) == 1

    coordinator = FakeCoordinator()
    first = spend_recorder.replay(
        CHANGE_ID, repo_root=repo, transport=coordinator, http_url="http://localhost:8081"
    )
    second = spend_recorder.replay(
        CHANGE_ID, repo_root=repo, transport=coordinator, http_url="http://localhost:8081"
    )

    assert first.replayed == 1
    assert first.remaining == 0
    assert second.replayed == 0
    assert second.remaining == 0
    assert list(coordinator.ledger) == ["gen-abc"]
    assert _spool_lines(repo) == []
    assert spend_recorder.spooled_total_usd(CHANGE_ID, repo_root=repo) == 0.0


def test_replay_of_an_already_recorded_generation_removes_it(repo: Path) -> None:
    down = FakeCoordinator([{"status_code": None, "data": None, "error": "down"}])
    spend_recorder.record(
        _row(), change_id=CHANGE_ID, repo_root=repo, transport=down,
        http_url="http://localhost:8081",
    )
    coordinator = FakeCoordinator()
    coordinator.ledger["gen-abc"] = {"id": 1, **_row()}

    outcome = spend_recorder.replay(
        CHANGE_ID, repo_root=repo, transport=coordinator, http_url="http://localhost:8081"
    )

    assert outcome.already_recorded == 1
    assert outcome.replayed == 0
    assert outcome.remaining == 0
    assert len(coordinator.ledger) == 1
    assert _spool_lines(repo) == []


def test_replay_keeps_rows_that_still_fail(repo: Path) -> None:
    down = {"status_code": None, "data": None, "error": "down"}
    spend_recorder.record(
        _row("gen-1"), change_id=CHANGE_ID, repo_root=repo,
        transport=FakeCoordinator([down]), http_url="http://localhost:8081",
    )
    spend_recorder.record(
        _row("gen-2"), change_id=CHANGE_ID, repo_root=repo,
        transport=FakeCoordinator([down]), http_url="http://localhost:8081",
    )
    created = {"status_code": 201, "data": {"id": 1}, "error": None}
    coordinator = FakeCoordinator([created, down])

    outcome = spend_recorder.replay(
        CHANGE_ID, repo_root=repo, transport=coordinator, http_url="http://localhost:8081"
    )

    assert outcome.replayed == 1
    assert outcome.remaining == 1
    assert [line["row"]["generation_id"] for line in _spool_lines(repo)] == ["gen-2"]
    # Replay posts only the row, never the spool metadata.
    assert set(coordinator.calls[0]["payload"]) == set(_row())


def test_replay_with_no_spool_is_a_no_op(repo: Path) -> None:
    coordinator = FakeCoordinator()

    outcome = spend_recorder.replay(
        CHANGE_ID, repo_root=repo, transport=coordinator, http_url="http://localhost:8081"
    )

    assert (outcome.replayed, outcome.remaining) == (0, 0)
    assert coordinator.calls == []


def test_row_from_review_result_maps_the_metered_fields() -> None:
    class _Result:
        vendor = "openrouter"
        model_used = "openai/gpt-5"
        generation_id = "gen-host"
        prompt_tokens = 10
        completion_tokens = 5
        cost_usd = None
        cost_source = "estimated"

    row = spend_recorder.row_from_review_result(
        _Result(), lane_id="openrouter", work_unit_ref="c:IMPL_REVIEW:round-1"
    )

    assert row == {
        "vendor": "openrouter",
        "model": "openai/gpt-5",
        "endpoint_kind": "openrouter",
        "generation_id": "gen-host",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "tokens_estimated": True,
        "work_unit_ref": "c:IMPL_REVIEW:round-1",
    }


def test_cli_replay_reports_counts_as_json(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    spend_recorder.record(
        _row(), change_id=CHANGE_ID, repo_root=repo,
        transport=FakeCoordinator([{"status_code": None, "data": None, "error": "down"}]),
        http_url="http://localhost:8081",
    )
    coordinator = FakeCoordinator()
    monkeypatch.setattr(spend_recorder, "_default_transport", coordinator)
    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:8081")
    monkeypatch.setenv("COORDINATION_API_KEY", SENTINEL_KEY)

    code = spend_recorder.main(
        ["replay", "--change-id", CHANGE_ID, "--repo-root", str(repo), "--json"]
    )

    out = capsys.readouterr().out
    assert code == 0
    report = json.loads(out)
    assert report["replayed"] == 1
    assert report["remaining"] == 0
    assert SENTINEL_KEY not in out
    # The bridge's credential path supplied the key; the CLI never echoes it.
    assert coordinator.calls[0]["api_key"] == SENTINEL_KEY


def test_cli_replay_exits_nonzero_when_rows_remain(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    down = {"status_code": None, "data": None, "error": "down"}
    spend_recorder.record(
        _row(), change_id=CHANGE_ID, repo_root=repo,
        transport=FakeCoordinator([down]), http_url="http://localhost:8081",
    )
    monkeypatch.setattr(spend_recorder, "_default_transport", FakeCoordinator([down]))
    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:8081")

    code = spend_recorder.main(["replay", "--change-id", CHANGE_ID, "--repo-root", str(repo)])

    assert code == 1
    assert "remaining=1" in capsys.readouterr().out
