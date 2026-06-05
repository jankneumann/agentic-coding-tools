"""Tests for report_status.py phase_archetype handling.

Change: wire-autopilot-phase-subagents — closes deferred D-2.

The Stop-hook reporter at agent-coordinator/scripts/report_status.py is the
production path that connects autopilot's loop-state.json to the
coordinator's POST /status/report endpoint. It must:

- Read state.phase_archetype from loop-state.json.
- Validate the value against the archetype enum (defense in depth — task 3.10).
- Include it in the POST body when valid; drop + warn when invalid.
- Omit it gracefully when the loop-state.json predates the field.

These tests exercise the script's helper functions and main() in-process
via importlib (matching the existing test_status_reporting.py pattern).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_REPO_ROOT = _SCRIPTS_DIR.parent


@pytest.fixture()
def report_status_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Reload the report_status module pointing at tmp_path as cwd."""
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(_REPO_ROOT))
    try:
        import scripts.report_status as rs_mod

        importlib.reload(rs_mod)
        yield rs_mod
    finally:
        if str(_REPO_ROOT) in sys.path:
            sys.path.remove(str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# 3.5: report_status.py reads phase_archetype from loop-state.json
# ---------------------------------------------------------------------------


def _write_loop_state(tmp_path: Path, **fields: Any) -> None:
    (tmp_path / "loop-state.json").write_text(json.dumps(fields))


def _captured_post_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env: dict[str, str]
) -> dict[str, Any]:
    """Run main() with stubbed urllib.urlopen and return the captured payload."""
    monkeypatch.chdir(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    sys.path.insert(0, str(_REPO_ROOT))
    try:
        import scripts.report_status as rs_mod

        importlib.reload(rs_mod)

        captured: dict[str, Any] = {}

        class _StubResp:
            status = 200

            def __enter__(self) -> _StubResp:
                return self

            def __exit__(self, *a: object) -> None:
                pass

        def fake_urlopen(req: Any, timeout: float = 0) -> _StubResp:
            captured["url"] = req.full_url
            captured["headers"] = dict(req.headers)
            captured["body"] = json.loads(req.data.decode())
            return _StubResp()

        monkeypatch.setattr(rs_mod, "urlopen", fake_urlopen)
        rs_mod.main()
        return captured
    finally:
        if str(_REPO_ROOT) in sys.path:
            sys.path.remove(str(_REPO_ROOT))


def test_payload_includes_phase_archetype_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_loop_state(
        tmp_path,
        current_phase="PLAN",
        change_id="my-change",
        phase_archetype="architect",
    )

    captured = _captured_post_payload(
        monkeypatch,
        tmp_path,
        env={
            "AGENT_ID": "test-agent",
            "COORDINATION_API_URL": "http://127.0.0.1:65535",
            "COORDINATION_API_KEY": "k",
        },
    )

    assert captured["body"].get("phase_archetype") == "architect"
    assert captured["body"]["phase"] == "PLAN"
    assert captured["body"]["change_id"] == "my-change"


def test_payload_omits_phase_archetype_when_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Older loop-state.json without the key MUST NOT cause a 400."""
    _write_loop_state(
        tmp_path,
        current_phase="PLAN",
        change_id="my-change",
    )

    captured = _captured_post_payload(
        monkeypatch,
        tmp_path,
        env={
            "AGENT_ID": "test-agent",
            "COORDINATION_API_URL": "http://127.0.0.1:65535",
        },
    )

    # The hook MUST tolerate the missing key; the payload either omits the
    # field or sends None. Both forms are accepted by the FastAPI endpoint.
    body = captured["body"]
    assert body.get("phase_archetype") is None


def test_payload_phase_archetype_null_in_state_is_passed_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Explicit null in loop-state.json (state-only INIT phase) maps to None."""
    _write_loop_state(
        tmp_path,
        current_phase="INIT",
        change_id="my-change",
        phase_archetype=None,
    )

    captured = _captured_post_payload(
        monkeypatch,
        tmp_path,
        env={
            "AGENT_ID": "test-agent",
            "COORDINATION_API_URL": "http://127.0.0.1:65535",
        },
    )

    body = captured["body"]
    assert body.get("phase_archetype") is None


# ---------------------------------------------------------------------------
# 3.10: client-side enum validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valid_archetype",
    ["architect", "reviewer", "implementer", "analyst", "runner"],
)
def test_payload_includes_each_valid_archetype(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_archetype: str,
) -> None:
    _write_loop_state(
        tmp_path,
        current_phase="PLAN",
        change_id="c",
        phase_archetype=valid_archetype,
    )

    captured = _captured_post_payload(
        monkeypatch,
        tmp_path,
        env={
            "AGENT_ID": "test-agent",
            "COORDINATION_API_URL": "http://127.0.0.1:65535",
        },
    )

    assert captured["body"].get("phase_archetype") == valid_archetype


@pytest.mark.parametrize(
    "invalid_archetype",
    [
        "ADMIN",
        "wizard",
        "../etc/passwd",
        "implementer; DROP TABLE",
        "  architect  ",
        "",
    ],
)
def test_payload_drops_invalid_phase_archetype_and_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    invalid_archetype: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """3.10: Invalid phase_archetype MUST be dropped, NOT forwarded.

    Per spec scenario "report_status.py drops invalid phase_archetype values
    from POST": the hook validates against the closed enum locally as
    defense-in-depth, sends ``null`` (or omits) instead of forwarding the
    invalid value, and emits a structured warning.
    """
    _write_loop_state(
        tmp_path,
        current_phase="PLAN",
        change_id="c",
        phase_archetype=invalid_archetype,
    )

    captured = _captured_post_payload(
        monkeypatch,
        tmp_path,
        env={
            "AGENT_ID": "test-agent",
            "COORDINATION_API_URL": "http://127.0.0.1:65535",
        },
    )

    body = captured["body"]
    # Must NOT forward the invalid value to the coordinator.
    assert body.get("phase_archetype") != invalid_archetype
    # Either absent or explicit null are valid sentinel values.
    assert body.get("phase_archetype") is None


# ---------------------------------------------------------------------------
# Cache de-duplication interaction with phase_archetype
# ---------------------------------------------------------------------------


def test_cache_dedupe_respects_phase_archetype_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When phase + change_id are the same but phase_archetype differs,
    we MUST NOT silently drop the report.

    Either the cache key is expanded to include phase_archetype, or the
    duplicate-when-only-archetype-changes case is accepted and the report
    fires anyway. The contract is: a phase_archetype change in loop-state
    must reach the coordinator at some point — not be permanently masked
    by cached state.
    """
    # First run with archetype=architect
    _write_loop_state(
        tmp_path,
        current_phase="PLAN",
        change_id="c",
        phase_archetype="architect",
    )
    captured_1 = _captured_post_payload(
        monkeypatch,
        tmp_path,
        env={
            "AGENT_ID": "test-agent",
            "COORDINATION_API_URL": "http://127.0.0.1:65535",
        },
    )
    assert captured_1["body"].get("phase_archetype") == "architect"

    # Second run with same phase but archetype=reviewer (force-refresh case)
    _write_loop_state(
        tmp_path,
        current_phase="PLAN",
        change_id="c",
        phase_archetype="reviewer",
    )
    captured_2 = _captured_post_payload(
        monkeypatch,
        tmp_path,
        env={
            "AGENT_ID": "test-agent",
            "COORDINATION_API_URL": "http://127.0.0.1:65535",
        },
    )

    # Either: (a) the cache included phase_archetype and we get a fresh POST,
    # OR (b) the report skipped — but in case (b) we lose the archetype change
    # signal forever. We require case (a): the dedupe key MUST include
    # phase_archetype, OR the change MUST trigger a non-cached POST.
    assert captured_2.get("body") is not None, (
        "Second report MUST fire when phase_archetype changes — otherwise the "
        "coordinator never learns about the new archetype"
    )
    assert captured_2["body"].get("phase_archetype") == "reviewer"


# ---------------------------------------------------------------------------
# Helper-function unit tests
# ---------------------------------------------------------------------------


def test_validation_helper_accepts_all_five_archetypes(
    report_status_module: Any,
) -> None:
    """The validation helper MUST accept every value in the closed enum."""
    rs_mod = report_status_module
    # The implementation may name this helper anything; we look for an
    # exported `_validate_phase_archetype` (preferred) or fall back to
    # main() integration tests above. This test asserts the helper exists
    # and its enum is correct.
    helper = getattr(rs_mod, "_validate_phase_archetype", None)
    if helper is None:
        pytest.skip(
            "_validate_phase_archetype helper not exposed; covered by "
            "main() integration tests above"
        )
    for ok in ["architect", "reviewer", "implementer", "analyst", "runner",
               "gatekeeper"]:
        assert helper(ok) == ok, f"{ok} should be accepted"


def test_validation_helper_rejects_unknowns(report_status_module: Any) -> None:
    rs_mod = report_status_module
    helper = getattr(rs_mod, "_validate_phase_archetype", None)
    if helper is None:
        pytest.skip("_validate_phase_archetype helper not exposed")
    for bad in ["ADMIN", "implementer; DROP", "", "  architect  ", None]:
        assert helper(bad) is None, f"{bad!r} should be rejected"
