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
