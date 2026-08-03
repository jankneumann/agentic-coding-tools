"""Fail-closed capability tests for semantic code search."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import coordination_bridge

REPO_ROOT = Path(__file__).resolve().parents[4]
CHECKER_PATHS = (
    REPO_ROOT / "skills/coordination-bridge/scripts/check_coordinator.py",
    REPO_ROOT / "agent-coordinator/scripts/check_coordinator.py",
)


class _Response:
    def __init__(self, status: int, body: dict[str, Any] | str) -> None:
        self.status = status
        self._body = (
            json.dumps(body).encode("utf-8") if isinstance(body, dict) else body.encode("utf-8")
        )

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _load_checker(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"capability_checker_{path.parent.name}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _http_error(status: int, body: str = "{}") -> HTTPError:
    return HTTPError(
        "http://coordinator.test/search/code/status",
        status,
        "probe failed",
        hdrs=None,
        fp=io.BytesIO(body.encode("utf-8")),
    )


@pytest.mark.parametrize("checker_path", CHECKER_PATHS)
def test_checker_defaults_code_search_capability_to_false(
    checker_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker(checker_path)
    monkeypatch.setattr(checker, "check_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(checker, "detect_mcp_server", lambda: False)

    result = checker.detect("http://coordinator.test")

    assert result["CAN_CODE_SEARCH"] is False


@pytest.mark.parametrize("checker_path", CHECKER_PATHS)
@pytest.mark.parametrize("status", [404, 422, 500])
def test_checker_rejects_non_successful_status_probe(
    checker_path: Path,
    status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker(checker_path)
    monkeypatch.setattr(
        checker, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(_http_error(status))
    )

    assert checker.probe_code_search_status("http://coordinator.test") is False


@pytest.mark.parametrize("checker_path", CHECKER_PATHS)
@pytest.mark.parametrize(
    "body",
    [
        "not json",
        {},
        {
            "available": False,
            "state": "unavailable",
            "reason": "no_usable_index",
            "usable_index_count": 0,
        },
        {"available": True, "state": "unavailable", "reason": "ready", "usable_index_count": 1},
        {"available": True, "state": "ready", "reason": "ready", "usable_index_count": 0},
        {"available": True, "state": "ready", "reason": "ready", "usable_index_count": True},
        {
            "available": True,
            "state": "ready",
            "reason": "ready",
            "usable_index_count": 1,
            "unexpected": "field",
        },
    ],
)
def test_checker_rejects_false_malformed_or_contradictory_status_body(
    checker_path: Path,
    body: dict[str, Any] | str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker(checker_path)
    monkeypatch.setattr(checker, "urlopen", lambda *_args, **_kwargs: _Response(200, body))

    assert checker.probe_code_search_status("http://coordinator.test") is False


@pytest.mark.parametrize("checker_path", CHECKER_PATHS)
def test_checker_accepts_only_valid_ready_status_body(
    checker_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker(checker_path)
    monkeypatch.setattr(
        checker,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            200,
            {
                "available": True,
                "state": "ready",
                "reason": "ready",
                "usable_index_count": 2,
            },
        ),
    )

    assert checker.probe_code_search_status("http://coordinator.test") is True


@pytest.mark.parametrize("checker_path", CHECKER_PATHS)
def test_checker_http_detection_publishes_body_verified_capability(
    checker_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker(checker_path)
    monkeypatch.setattr(checker, "check_health", lambda *_args, **_kwargs: {"status": "ok"})
    monkeypatch.setattr(checker, "probe_route", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(checker, "probe_code_search_status", lambda *_args, **_kwargs: True)

    result = checker.detect("http://coordinator.test")

    assert result["COORDINATOR_AVAILABLE"] is True
    assert result["COORDINATION_TRANSPORT"] == "http"
    assert result["CAN_CODE_SEARCH"] is True


@pytest.mark.parametrize("checker_path", CHECKER_PATHS)
def test_checker_keeps_code_search_false_for_unverifiable_mcp_only_transport(
    checker_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker(checker_path)
    monkeypatch.setattr(checker, "check_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(checker, "detect_mcp_server", lambda: True)

    result = checker.detect("http://coordinator.test")

    assert result["COORDINATOR_AVAILABLE"] is True
    assert result["COORDINATION_TRANSPORT"] == "mcp"
    assert result["CAN_CODE_SEARCH"] is False


def test_bridge_defaults_code_search_capability_to_false() -> None:
    result = coordination_bridge._coordinator_state(
        available=False,
        transport="none",
        http_url=None,
    )

    assert result["CAN_CODE_SEARCH"] is False
    assert result["capabilities"]["code_search"] is False


@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [
        (404, {}, False),
        (422, {}, False),
        (500, {}, False),
        (200, "not-json", False),
        (
            200,
            {
                "available": False,
                "state": "unavailable",
                "reason": "no_usable_index",
                "usable_index_count": 0,
            },
            False,
        ),
        (
            200,
            {
                "available": True,
                "state": "unavailable",
                "reason": "ready",
                "usable_index_count": 1,
            },
            False,
        ),
        (
            200,
            {
                "available": True,
                "state": "ready",
                "reason": "ready",
                "usable_index_count": 1,
            },
            True,
        ),
    ],
)
def test_bridge_uses_body_aware_code_search_status(
    status_code: int,
    body: dict[str, Any] | str,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        coordination_bridge,
        "_resolve_http_url",
        lambda http_url=None: "http://coord.example",
    )
    monkeypatch.setattr(coordination_bridge, "_probe_capability", lambda **_kwargs: False)

    def fake_http_request(*, path: str, **_kwargs: Any) -> dict[str, Any]:
        if path == "/health":
            return {"status_code": 200, "data": {"status": "ok"}, "error": None}
        assert path == "/search/code/status"
        return {"status_code": status_code, "data": body, "error": None}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake_http_request)

    result = coordination_bridge.detect_coordination()

    assert result["CAN_CODE_SEARCH"] is expected
    assert result["capabilities"]["code_search"] is expected
