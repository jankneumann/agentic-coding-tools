"""Tests for the real PLAN/IMPL/VAL phase fixer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / "autopilot" / "scripts")
_PARALLEL_DIR = str(
    Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts"
)
for _p in (_SCRIPTS_DIR, _PARALLEL_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from phase_fixer import (  # noqa: E402
    FixDispatchError,
    apply_phase_fixes,
    build_scoped_fix_prompt,
)


def test_build_scoped_fix_prompt_forbids_out_of_scope() -> None:
    prompt = build_scoped_fix_prompt(
        [{
            "id": 1,
            "type": "bug",
            "criticality": "high",
            "allowed_paths": ["src/api.py"],
            "description": "Null check missing",
        }],
        fix_mode="inline",
    )
    assert "allowed_paths" in prompt
    assert "src/api.py" in prompt
    assert "Do not add architecture" in prompt


def test_apply_phase_fixes_writes_payload_and_dispatches(tmp_path: Path) -> None:
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    dispatched: list[tuple[list, str]] = []

    def dispatch_fn(blocking: list, _worktree: Path, **kwargs: object) -> None:
        dispatched.append((blocking, str(kwargs["prompt"])))

    items = [{
        "id": 1,
        "allowed_paths": ["src/api.py"],
        "description": "fix me",
    }]
    apply_phase_fixes(
        items,
        tmp_path,
        fix_mode="inline",
        change_dir=change_dir,
        dispatch_fn=dispatch_fn,
    )
    pending = json.loads(
        (change_dir / ".review-ledger" / "pending-fixes.json").read_text()
    )
    assert pending["fix_mode"] == "inline"
    assert pending["items"][0]["id"] == 1
    assert dispatched
    assert "fix me" in dispatched[0][1]


def test_apply_phase_fixes_without_adapter_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptyOrch:
        adapters: dict = {}

        @classmethod
        def from_coordinator(cls) -> "EmptyOrch":
            return cls()

    import review_dispatcher
    monkeypatch.setattr(
        review_dispatcher.ReviewOrchestrator,
        "from_coordinator",
        classmethod(lambda cls: EmptyOrch()),
    )
    with pytest.raises(FixDispatchError):
        apply_phase_fixes(
            [{"id": 1, "allowed_paths": ["src/api.py"]}],
            tmp_path,
            fix_mode="targeted",
            dispatch_fn=None,
        )
