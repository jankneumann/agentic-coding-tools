"""Path-traversal rejection tests for `build_phase_dispatch_kwargs`.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Scenario: "build_phase_dispatch_kwargs rejects path-traversal change_id"
Design decisions: D4 (cache file path validation).

The validation regex `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` is asserted before
any filesystem access — the assertion order matters for the security
posture, so these tests are explicit about that.
"""

from __future__ import annotations

from pathlib import Path

import phase_agent
import pytest


@pytest.fixture()
def chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    "bad_change_id",
    [
        "../../etc/passwd",
        "..",
        "../sibling",
        "foo/bar",
        "a/b/c",
        "",
        ".hidden",  # leading dot — first char must be alphanumeric
        "-leading-dash",  # leading dash — first char must be alphanumeric
        "a" * 129,  # 129 chars > 128 max
        "weirdéchars",  # non-ASCII (e-acute)
        "with space",
        "abc;rm -rf",
        "abc\nnewline",
        "abc\x00null",
    ],
)
def test_build_phase_dispatch_kwargs_rejects_invalid_change_id(
    chdir_tmp: Path,
    bad_change_id: str,
) -> None:
    with pytest.raises(ValueError):
        phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", bad_change_id)


def test_build_phase_dispatch_kwargs_validates_before_filesystem_access(
    chdir_tmp: Path,
) -> None:
    """Confirm the regex check fires BEFORE any path is touched.

    We achieve this by placing a file at the only path that could
    conceivably be touched if validation deferred (none, since the regex
    excludes `/` and `..`) and asserting no read/write happens. A simpler
    proxy is to confirm the cache file is not created for the rejected
    input — and that no openspec/changes/ subtree exists at all.
    """
    with pytest.raises(ValueError):
        phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "../escape")

    # No openspec/changes/ subtree should have been created in the cwd.
    assert not (chdir_tmp / "openspec" / "changes").exists()


def test_build_phase_dispatch_kwargs_accepts_valid_change_id_shapes(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid shapes per the OpenSpec regex pass validation."""
    import coordination_bridge
    monkeypatch.setattr(
        coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda phase, signals=None, **_: None,
    )

    valid_ids = [
        "a",
        "abc",
        "ABC",
        "a1b2c3",
        "with-dashes",
        "with_underscores",
        "with.dots",
        "a" * 128,  # exactly the max length
        "2026-05-05-feature",
    ]
    for change_id in valid_ids:
        # Seed a state file so build_phase_dispatch_kwargs has something to read.
        change_dir = chdir_tmp / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True, exist_ok=True)
        (change_dir / "loop-state.json").write_text('{"change_id": "%s"}' % change_id)

        result = phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", change_id)
        assert isinstance(result, dict)
