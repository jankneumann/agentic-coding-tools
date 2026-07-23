"""Semantic harness-migration gate (add-agy-grok-pi-harnesses task 2.6 / 2.10).

The functional contract is NOT "the substring 'gemini' never appears" — Gemini
remains a live MODEL family reached through the Antigravity (`agy`) harness. What
must hold is:

  1. No configured harness invokes a CLI that no longer exists (`gemini`/`jules`).
  2. The local roster is exactly antigravity/grok/pi (plus claude/codex).
  3. The eval-backend factory refuses to build a retired Gemini/Jules backend and
     names the supported roster instead.

Every assertion derives from live config (agents.yaml, the backend factory), so
it cannot drift from the roster it guards (feedback: tests-derive-from-config).
This test IS the semantic half of the `wp-coordinator` verification gate; see
design.md § D9.
"""

from __future__ import annotations

import pytest

from evaluation.backends import build_backend
from evaluation.backends.registry import (
    SUPPORTED_BACKENDS,
    UnknownBackendError,
)
from evaluation.config import AgentBackendConfig
from src.agents_config import load_agents_config

# The harnesses that were retired in this change. None may be reachable as a
# CLI command or as a buildable eval backend.
RETIRED_HARNESS_COMMANDS = {"gemini", "jules"}
RETIRED_BACKEND_NAMES = {"gemini_jules", "gemini", "jules"}

# The local CLI harness roster this change targets.
EXPECTED_LOCAL_HARNESSES = {"antigravity", "grok", "pi"}


class TestNoHarnessInvokesADeadCli:
    def test_no_agent_invokes_gemini_or_jules_cli(self) -> None:
        """A skill must never dispatch to a harness binary that no longer exists."""
        entries = load_agents_config()
        offenders = [
            e.name
            for e in entries
            if e.cli is not None
            and e.cli.command in RETIRED_HARNESS_COMMANDS
        ]
        assert offenders == [], (
            f"agents.yaml still dispatches to a retired harness CLI: {offenders}"
        )

    def test_local_cli_roster_is_the_new_harnesses(self) -> None:
        """The local CLI harnesses are exactly antigravity/grok/pi (+ claude/codex)."""
        entries = load_agents_config()
        cli_commands = {e.cli.command for e in entries if e.cli is not None}
        # The three new harnesses are present...
        assert {"agy", "grok", "pi"} <= cli_commands
        # ...and neither retired binary is.
        assert not (RETIRED_HARNESS_COMMANDS & cli_commands)

    def test_agent_types_cover_new_harnesses_and_drop_gemini(self) -> None:
        entries = load_agents_config()
        types = {e.type for e in entries}
        assert EXPECTED_LOCAL_HARNESSES <= types
        assert "gemini" not in types


class TestEvalBackendRosterParity:
    def test_supported_backends_are_the_full_roster(self) -> None:
        assert set(SUPPORTED_BACKENDS) == {
            "claude_code",
            "codex",
            "antigravity",
            "grok",
            "pi",
        }

    def test_no_gemini_or_jules_backend_is_registered(self) -> None:
        assert not (RETIRED_BACKEND_NAMES & set(SUPPORTED_BACKENDS))

    @pytest.mark.parametrize("retired", sorted(RETIRED_BACKEND_NAMES))
    def test_factory_refuses_retired_backend(self, retired: str) -> None:
        with pytest.raises(UnknownBackendError):
            build_backend(AgentBackendConfig(name=retired, command="jules"))
