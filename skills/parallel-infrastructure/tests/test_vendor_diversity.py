"""Tests for vendor-diversity dispatcher logic (WP6).

Covers the spec scenarios from
``openspec/changes/factory-missions-architecture-alignment/specs/agent-archetypes/spec.md``:

* Worker and validator dispatch to different vendors (3-vendor exclusion)
* Single-vendor environment falls back gracefully (warn-and-continue)
* Policy disabled allows same-vendor dispatch
* Vendor-tracking session state is change-scoped and tamper-resistant
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

# Add scripts directory to path so review_dispatcher can be imported standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from review_dispatcher import (  # noqa: E402
    load_vendor_diversity_policy,
    read_dispatch_state,
    record_worker_vendor,
    select_validator_vendor,
    write_dispatch_state,
)


CHANGE_ID = "example-feature"


def _state_path(tmp_path: Path) -> Path:
    return tmp_path / "openspec" / "changes" / CHANGE_ID / ".dispatch-state.json"


def _agents_yaml(
    tmp_path: Path,
    *,
    enforce_for: list[str] | None = None,
) -> Path:
    """Write a minimal agents.yaml with a configurable policies block."""
    enforce_for = ["worker_vs_validator"] if enforce_for is None else enforce_for
    body = textwrap.dedent(
        f"""\
        policies:
          vendor_diversity:
            enforce_for: {json.dumps(enforce_for)}
            fallback: warn_and_continue
            scope: per_change
        agents: {{}}
        """
    )
    path = tmp_path / "agents.yaml"
    path.write_text(body)
    return path


# ---------------------------------------------------------------------------
# Scenario 1: Worker and validator dispatch to different vendors
# ---------------------------------------------------------------------------

class TestThreeVendorExclusion:
    """Worker dispatched with claude; dispatcher MUST select codex or gemini."""

    def test_excludes_worker_vendor(self, tmp_path, caplog):
        agents_yaml = _agents_yaml(tmp_path)
        state_path = _state_path(tmp_path)

        # Simulate worker dispatched with claude.
        record_worker_vendor(
            CHANGE_ID, "claude", state_path=state_path,
        )

        with caplog.at_level(logging.INFO, logger="review_dispatcher"):
            selected, msg = select_validator_vendor(
                candidates=["claude", "codex", "gemini"],
                change_id=CHANGE_ID,
                agents_yaml_path=agents_yaml,
                state_path=state_path,
            )

        assert selected != "claude"
        assert selected in {"codex", "gemini"}
        # Spec requires the log line format.
        assert "vendor_diversity: excluded" in msg
        assert "claude (worker)" in msg
        assert f"selected {selected} (validator)" in msg
        assert CHANGE_ID in msg

    def test_persists_validator_selection(self, tmp_path):
        agents_yaml = _agents_yaml(tmp_path)
        state_path = _state_path(tmp_path)

        record_worker_vendor(CHANGE_ID, "claude", state_path=state_path)
        selected, _ = select_validator_vendor(
            candidates=["claude", "codex", "gemini"],
            change_id=CHANGE_ID,
            agents_yaml_path=agents_yaml,
            state_path=state_path,
        )

        state = read_dispatch_state(CHANGE_ID, state_path=state_path)
        assert state["worker_vendors"] == ["claude"]
        assert selected in state["validator_vendors"]
        assert state["change_id"] == CHANGE_ID


# ---------------------------------------------------------------------------
# Scenario 2: Single-vendor environment falls back gracefully
# ---------------------------------------------------------------------------

class TestSingleVendorFallback:
    """Only claude available; warn but still select claude (no error)."""

    def test_single_vendor_warns_and_continues(self, tmp_path, caplog):
        agents_yaml = _agents_yaml(tmp_path)
        state_path = _state_path(tmp_path)
        record_worker_vendor(CHANGE_ID, "claude", state_path=state_path)

        with caplog.at_level(logging.WARNING, logger="review_dispatcher"):
            selected, msg = select_validator_vendor(
                candidates=["claude"],
                change_id=CHANGE_ID,
                agents_yaml_path=agents_yaml,
                state_path=state_path,
            )

        assert selected == "claude"
        assert "only 1 vendor available" in msg
        assert "violating policy but continuing" in msg
        # Must log at WARNING level (not ERROR — this is warn_and_continue).
        warning_records = [
            r for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert any("violating policy" in r.message for r in warning_records)

    def test_does_not_raise_on_single_vendor(self, tmp_path):
        agents_yaml = _agents_yaml(tmp_path)
        state_path = _state_path(tmp_path)
        record_worker_vendor(CHANGE_ID, "claude", state_path=state_path)

        # Must not raise.
        selected, _ = select_validator_vendor(
            candidates=["claude"],
            change_id=CHANGE_ID,
            agents_yaml_path=agents_yaml,
            state_path=state_path,
        )
        assert selected is not None


# ---------------------------------------------------------------------------
# Scenario 3: Policy disabled allows same-vendor dispatch
# ---------------------------------------------------------------------------

class TestPolicyDisabled:
    """enforce_for: [] -> dispatcher may select same vendor without warning."""

    def test_policy_disabled_allows_same_vendor(self, tmp_path, caplog):
        agents_yaml = _agents_yaml(tmp_path, enforce_for=[])
        state_path = _state_path(tmp_path)
        record_worker_vendor(CHANGE_ID, "claude", state_path=state_path)

        with caplog.at_level(logging.INFO, logger="review_dispatcher"):
            selected, msg = select_validator_vendor(
                candidates=["claude", "codex", "gemini"],
                change_id=CHANGE_ID,
                agents_yaml_path=agents_yaml,
                state_path=state_path,
            )

        # Policy disabled — first candidate is fine.
        assert selected == "claude"
        assert "policy disabled by config" in msg

        # No WARNING records expected (no fallback, no violation).
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings == []


# ---------------------------------------------------------------------------
# Dispatch state: read/write/tamper-resistance
# ---------------------------------------------------------------------------

class TestDispatchState:
    def test_read_returns_empty_for_missing_file(self, tmp_path):
        state_path = _state_path(tmp_path)
        assert state_path.exists() is False
        assert read_dispatch_state(CHANGE_ID, state_path=state_path) == {}

    def test_write_then_read_roundtrip(self, tmp_path):
        state_path = _state_path(tmp_path)
        write_dispatch_state(
            CHANGE_ID,
            {"worker_vendors": ["claude"], "validator_vendors": ["codex"]},
            state_path=state_path,
        )
        loaded = read_dispatch_state(CHANGE_ID, state_path=state_path)
        assert loaded["worker_vendors"] == ["claude"]
        assert loaded["validator_vendors"] == ["codex"]
        assert loaded["change_id"] == CHANGE_ID

    def test_write_uses_mode_0644(self, tmp_path):
        state_path = _state_path(tmp_path)
        write_dispatch_state(
            CHANGE_ID, {"worker_vendors": ["claude"]}, state_path=state_path,
        )
        mode = state_path.stat().st_mode & 0o777
        assert mode == 0o644

    def test_world_writable_file_refused(self, tmp_path, caplog):
        state_path = _state_path(tmp_path)
        write_dispatch_state(
            CHANGE_ID, {"worker_vendors": ["claude"]}, state_path=state_path,
        )
        # Tamper: set world-write bit.
        os.chmod(state_path, 0o646)

        with caplog.at_level(logging.ERROR, logger="review_dispatcher"):
            data = read_dispatch_state(CHANGE_ID, state_path=state_path)

        # Falls back to no-history mode.
        assert data == {}
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert any("world-writable" in r.message for r in errors)

    def test_record_worker_vendor_idempotent(self, tmp_path):
        state_path = _state_path(tmp_path)
        record_worker_vendor(CHANGE_ID, "claude", state_path=state_path)
        record_worker_vendor(CHANGE_ID, "claude", state_path=state_path)
        state = read_dispatch_state(CHANGE_ID, state_path=state_path)
        assert state["worker_vendors"] == ["claude"]


# ---------------------------------------------------------------------------
# Policy loader
# ---------------------------------------------------------------------------

class TestLoadPolicy:
    def test_default_when_missing_file(self, tmp_path):
        policy = load_vendor_diversity_policy(tmp_path / "missing.yaml")
        assert policy["enforce_for"] == ["worker_vs_validator"]
        assert policy["fallback"] == "warn_and_continue"

    def test_reads_disabled_policy(self, tmp_path):
        agents_yaml = _agents_yaml(tmp_path, enforce_for=[])
        policy = load_vendor_diversity_policy(agents_yaml)
        assert policy["enforce_for"] == []

    def test_reads_default_policy(self, tmp_path):
        agents_yaml = _agents_yaml(tmp_path)
        policy = load_vendor_diversity_policy(agents_yaml)
        assert policy["enforce_for"] == ["worker_vs_validator"]
        assert policy["scope"] == "per_change"


# ---------------------------------------------------------------------------
# Iteration-1 fix: vendor exhaustion per-role tracking (spec scenario coverage)
# ---------------------------------------------------------------------------


class TestVendorExhaustionPerRole:
    """Per agent-archetypes spec: 'Vendor exhaustion within a session is tracked'.

    The worker_vs_validator constraint applies once per role pair, NOT
    transitively. After a worker (claude) and validator (codex) are both
    dispatched on a change, a SECOND validator request MAY pick either vendor
    again — the constraint doesn't cascade.
    """

    def test_second_validator_after_pair_dispatch_excludes_worker_again(self, tmp_path: Path):
        """A second validator on the same change still excludes the worker's vendor.

        The implementation tracks worker_vendors and validator_vendors in
        dispatch state. The worker_vs_validator constraint excludes vendors in
        ``worker_vendors`` from validator selection — so once worker=claude is
        recorded, EVERY subsequent validator selection on that change excludes
        claude. This test locks in that behavior so a refactor doesn't drop
        the persistent worker exclusion.
        """
        from review_dispatcher import (
            record_worker_vendor,
            select_validator_vendor,
        )

        change_id = "feat-x"
        repo_root = tmp_path

        record_worker_vendor(change_id, "claude", repo_root=repo_root)

        # First validator request: must exclude claude.
        first, _ = select_validator_vendor(
            ["claude", "codex", "gemini"],
            change_id=change_id,
            repo_root=repo_root,
        )
        assert first in {"codex", "gemini"}, first

        # Second validator request: still excludes claude.
        second, log_msg = select_validator_vendor(
            ["claude", "codex", "gemini"],
            change_id=change_id,
            repo_root=repo_root,
        )
        assert second in {"codex", "gemini"}, second
        assert "claude" in log_msg, log_msg

    def test_pair_constraint_logs_role_check(self, tmp_path: Path):
        """The dispatcher's log MUST reference vendor_diversity and name what was excluded."""
        from review_dispatcher import (
            record_worker_vendor,
            select_validator_vendor,
        )

        change_id = "feat-y"
        record_worker_vendor(change_id, "claude", repo_root=tmp_path)
        chosen, log_msg = select_validator_vendor(
            ["claude", "codex"],
            change_id=change_id,
            repo_root=tmp_path,
        )
        assert "vendor_diversity" in log_msg.lower(), log_msg
        assert "claude" in log_msg, log_msg


# ---------------------------------------------------------------------------
# Iteration-1 fix F6: dispatch_state_path rejects invalid change-ids
# ---------------------------------------------------------------------------


class TestDispatchStatePathValidation:
    """Defense-in-depth: ``_dispatch_state_path`` rejects path-traversal change-ids.

    Public callers (record_worker_vendor, record_validator_vendor,
    select_validator_vendor) accept change_id strings and pass them to the path
    builder. Rather than trust upstream validation, the path builder itself
    validates against ``^[a-zA-Z0-9_-]+$``.
    """

    def test_rejects_path_traversal(self, tmp_path: Path):
        from review_dispatcher import _dispatch_state_path

        with pytest.raises(ValueError, match=r"change_id MUST match"):
            _dispatch_state_path("../etc/passwd", repo_root=tmp_path)

    def test_rejects_slash_in_change_id(self, tmp_path: Path):
        from review_dispatcher import _dispatch_state_path

        with pytest.raises(ValueError):
            _dispatch_state_path("foo/bar", repo_root=tmp_path)

    def test_rejects_shell_metacharacters(self, tmp_path: Path):
        from review_dispatcher import _dispatch_state_path

        with pytest.raises(ValueError):
            _dispatch_state_path("foo;rm -rf /", repo_root=tmp_path)

    def test_accepts_valid_change_id(self, tmp_path: Path):
        from review_dispatcher import _dispatch_state_path

        path = _dispatch_state_path("feat-123_abc", repo_root=tmp_path)
        assert path.name == ".dispatch-state.json"
        assert "feat-123_abc" in str(path)
