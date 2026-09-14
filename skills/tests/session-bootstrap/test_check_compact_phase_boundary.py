"""Tests for the phase-boundary gate in check_compact.py.

`_recent_phase_boundary()` must only treat a recently-modified handoff JSON as
a phase-completion signal when that handoff has been recorded as the change's
most-recently-applied outcome (``loop-state.json.last_handoff_id``). These
tests exercise the gate directly at the function level, materializing fake
worktrees under ``tmp_path`` and stubbing ``_all_worktree_roots``.

Every boundary must also belong to the session in the hook payload: the
handoff's worktree must be one the session worked in (transcript ``cwd``) and
its change id must appear in the session transcript. ``_session_payload``
builds such a payload; the session-scope tests at the bottom cover the cases
where it is deliberately missing.

See design.md D3 for the case matrix.
"""

from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

_HOOK_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "session-bootstrap" / "scripts" / "hooks" / "check_compact.py"
)


@pytest.fixture(scope="module")
def hook_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_compact",
                                                  _HOOK_MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_handoff(root: Path, change_id: str, phase: str, n: int = 1) -> Path:
    handoff_dir = root / "openspec" / "changes" / change_id / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    target = handoff_dir / f"{phase}-{n}.json"
    target.write_text("{}")
    return target


def _write_loop_state(
    root: Path, change_id: str, last_handoff_id: str | None,
    raw: str | None = None,
) -> Path:
    change_dir = root / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    target = change_dir / "loop-state.json"
    if raw is not None:
        target.write_text(raw)
    else:
        target.write_text(json.dumps({"last_handoff_id": last_handoff_id}))
    return target


def _session_payload(
    tmp_path: Path, cwds: list[Path], mentions: list[str],
    session_id: str = "sess-1",
) -> dict:
    """A Stop-hook payload whose transcript records ``cwds`` as working
    directories and mentions each change id in ``mentions``."""
    transcript = tmp_path / f"{session_id}.jsonl"
    rows = [
        {"cwd": str(cwd), "sessionId": session_id,
         "message": {"role": "user",
                     "content": " ".join(f"/autopilot {m}" for m in mentions)}}
        for cwd in cwds
    ]
    transcript.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return {"session_id": session_id, "transcript_path": str(transcript),
            "cwd": str(cwds[0])}


def _backdate(path: Path, seconds_ago: float) -> None:
    when = time.time() - seconds_ago
    os.utime(path, (when, when))


def test_applied_handoff_triggers_boundary(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh handoff whose filename matches last_handoff_id → phase name."""
    _write_handoff(tmp_path, "test-change", "plan_review", 3)
    _write_loop_state(
        tmp_path, "test-change",
        "openspec/changes/test-change/handoffs/plan_review-3.json",
    )
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])
    payload = _session_payload(tmp_path, [tmp_path], ["test-change"])
    assert hook_module._recent_phase_boundary(payload) == "plan_review"


def test_unapplied_handoff_does_not_trigger(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sub-agent in flight: fresh implement handoff on disk, but last_handoff_id
    still points at the previous phase → no boundary."""
    _write_handoff(tmp_path, "test-change", "implement", 1)
    _write_loop_state(
        tmp_path, "test-change",
        "openspec/changes/test-change/handoffs/plan_review-3.json",
    )
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])
    payload = _session_payload(tmp_path, [tmp_path], ["test-change"])
    assert hook_module._recent_phase_boundary(payload) is None


def test_stale_mtime_touch_ignored(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An old archived handoff got a fresh mtime (git checkout / IDE touch),
    but last_handoff_id points at a different, also-fresh applied handoff.
    The applied one wins; the stale touched one is ignored."""
    stale = _write_handoff(tmp_path, "test-change", "plan-iteration-1", 1)
    applied = _write_handoff(tmp_path, "test-change", "plan_review", 3)
    _write_loop_state(
        tmp_path, "test-change",
        "openspec/changes/test-change/handoffs/plan_review-3.json",
    )
    # Make the stale handoff the newest by mtime — it must still be ignored
    # because it is not the applied handoff.
    _backdate(applied, 30)
    os.utime(stale, None)  # now
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])
    payload = _session_payload(tmp_path, [tmp_path], ["test-change"])
    assert hook_module._recent_phase_boundary(payload) == "plan_review"


def test_missing_loop_state_fails_closed(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh handoff, no loop-state.json → fail closed, no boundary."""
    _write_handoff(tmp_path, "test-change", "implement", 1)
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])
    payload = _session_payload(tmp_path, [tmp_path], ["test-change"])
    assert hook_module._recent_phase_boundary(payload) is None


def test_malformed_loop_state_fails_closed(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh handoff, loop-state.json contains non-JSON → fail closed."""
    _write_handoff(tmp_path, "test-change", "implement", 1)
    _write_loop_state(tmp_path, "test-change", None, raw="not json {{{")
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])
    payload = _session_payload(tmp_path, [tmp_path], ["test-change"])
    assert hook_module._recent_phase_boundary(payload) is None


def test_outside_window(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handoff matches last_handoff_id but mtime is older than the window."""
    handoff = _write_handoff(tmp_path, "test-change", "plan_review", 3)
    _write_loop_state(
        tmp_path, "test-change",
        "openspec/changes/test-change/handoffs/plan_review-3.json",
    )
    _backdate(handoff, hook_module.PHASE_BOUNDARY_WINDOW_SEC + 60)
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])
    payload = _session_payload(tmp_path, [tmp_path], ["test-change"])
    assert hook_module._recent_phase_boundary(payload) is None


def test_null_last_handoff_id(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """loop-state.json exists but last_handoff_id is null → no boundary."""
    _write_handoff(tmp_path, "test-change", "plan_review", 3)
    _write_loop_state(tmp_path, "test-change", None)  # {"last_handoff_id": null}
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])
    payload = _session_payload(tmp_path, [tmp_path], ["test-change"])
    assert hook_module._recent_phase_boundary(payload) is None


def test_absent_last_handoff_id(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """loop-state.json exists but has no last_handoff_id key → no boundary."""
    _write_handoff(tmp_path, "test-change", "plan_review", 3)
    _write_loop_state(tmp_path, "test-change", None, raw=json.dumps({"phase": 1}))
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])
    payload = _session_payload(tmp_path, [tmp_path], ["test-change"])
    assert hook_module._recent_phase_boundary(payload) is None


def test_sibling_worktree_handoff_isolated(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two worktree roots. The sibling has a fresh handoff that does NOT match
    its own loop-state (an in-flight sub-agent write on a different change).
    It must not propagate as a boundary into the current session; only the
    current worktree's applied handoff counts."""
    current = tmp_path / "current"
    sibling = tmp_path / "sibling"
    current.mkdir()
    sibling.mkdir()

    # Sibling: fresh handoff, but last_handoff_id points elsewhere.
    _write_handoff(sibling, "other-change", "implement", 1)
    _write_loop_state(
        sibling, "other-change",
        "openspec/changes/other-change/handoffs/plan_review-2.json",
    )

    # Current worktree: an applied handoff that should be the only boundary.
    current_handoff = _write_handoff(current, "this-change", "validation", 4)
    _write_loop_state(
        current, "this-change",
        "openspec/changes/this-change/handoffs/validation-4.json",
    )
    # Make the sibling's unapplied handoff the newest by mtime to prove the
    # gate — not recency — decides.
    _backdate(current_handoff, 30)

    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [current, sibling])
    # The session worked in both worktrees and mentioned both changes, so
    # only the applied-handoff gate can reject the sibling handoff here.
    payload = _session_payload(tmp_path, [current, sibling],
                               ["this-change", "other-change"])
    assert hook_module._recent_phase_boundary(payload) == "validation"


def test_sibling_unapplied_alone_yields_none(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a sibling worktree has a fresh but unapplied handoff → None."""
    current = tmp_path / "current"
    sibling = tmp_path / "sibling"
    current.mkdir()
    sibling.mkdir()
    _write_handoff(sibling, "other-change", "implement", 1)
    _write_loop_state(
        sibling, "other-change",
        "openspec/changes/other-change/handoffs/plan_review-2.json",
    )
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [current, sibling])
    # The session worked in both worktrees and mentioned both changes, so
    # only the applied-handoff gate can reject the sibling handoff here.
    payload = _session_payload(tmp_path, [current, sibling],
                               ["this-change", "other-change"])
    assert hook_module._recent_phase_boundary(payload) is None


# ---------------------------------------------------------------------------
# Session ownership: an applied handoff must also belong to THIS session.
# ---------------------------------------------------------------------------


def test_unvisited_worktree_applied_handoff_ignored(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another session applied a handoff in a worktree this session never
    worked in. It passes the applied-handoff gate but is not our boundary."""
    current = tmp_path / "current"
    sibling = tmp_path / "sibling"
    current.mkdir()
    sibling.mkdir()
    _write_handoff(sibling, "other-change", "implement", 1)
    _write_loop_state(
        sibling, "other-change",
        "openspec/changes/other-change/handoffs/implement-1.json",
    )
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [current, sibling])
    # Even a mention of the change id does not make the worktree ours.
    payload = _session_payload(tmp_path, [current], ["other-change"])
    assert hook_module._recent_phase_boundary(payload) is None


def test_unmentioned_change_applied_handoff_ignored(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same checkout, but the applied handoff is for a change this session
    never mentioned (e.g. a pull brought in another run's loop-state)."""
    _write_handoff(tmp_path, "their-change", "plan_review", 3)
    _write_loop_state(
        tmp_path, "their-change",
        "openspec/changes/their-change/handoffs/plan_review-3.json",
    )
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])
    payload = _session_payload(tmp_path, [tmp_path], ["my-change"])
    assert hook_module._recent_phase_boundary(payload) is None


def test_nested_linked_worktree_is_not_owned_by_main_checkout_session(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linked worktrees live under the main checkout (.git-worktrees/<id>).
    A session that only worked in the main checkout does not own them, even
    though their paths are nested inside the main root."""
    main_root = tmp_path / "repo"
    nested = main_root / ".git-worktrees" / "their-change"
    nested.mkdir(parents=True)
    _write_handoff(nested, "their-change", "implement", 1)
    _write_loop_state(
        nested, "their-change",
        "openspec/changes/their-change/handoffs/implement-1.json",
    )
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [main_root, nested])
    payload = _session_payload(tmp_path, [main_root], ["their-change"])
    assert hook_module._recent_phase_boundary(payload) is None

    # Working inside the nested worktree (any subdirectory) makes it ours.
    payload = _session_payload(
        tmp_path, [main_root, nested / "skills"], ["their-change"],
    )
    assert hook_module._recent_phase_boundary(payload) == "implement"


def test_transcript_not_read_without_applied_candidate(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ownership check runs after the cheap gates, so a Stop with no
    applied handoff never pays for reading a large transcript."""
    _write_handoff(tmp_path, "test-change", "implement", 1)  # unapplied
    monkeypatch.setattr(hook_module, "_all_worktree_roots",
                        lambda: [tmp_path])

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("transcript read without an applied candidate")

    monkeypatch.setattr(hook_module.session_scope, "load_session_scope", fail)
    assert hook_module._recent_phase_boundary({"transcript_path": "x"}) is None
