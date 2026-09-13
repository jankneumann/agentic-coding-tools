"""Review dispatch derives model + thinking from archetypes.yaml premium tier."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from review_dispatcher import (  # noqa: E402
    CliConfig,
    CliVendorAdapter,
    ModeConfig,
    _resolve_review_model_spec,
    _thinking_cli_flags,
)


def test_resolve_premium_matches_archetypes_yaml() -> None:
    from skills.shared.archetype_roster import (  # type: ignore
        clear_archetypes_raw_cache,
        resolve_tier_for_provider,
    )

    clear_archetypes_raw_cache()
    for vendor in ("claude_code", "codex", "antigravity", "grok", "pi"):
        expected = resolve_tier_for_provider(vendor, "premium")
        assert _resolve_review_model_spec(vendor) == expected
        assert expected[0], f"{vendor} premium model missing"


def test_thinking_cli_flags_per_vendor() -> None:
    assert _thinking_cli_flags("claude_code", "medium") == ["--effort", "medium"]
    assert _thinking_cli_flags("codex", "high") == [
        "-c",
        "model_reasoning_effort=high",
    ]
    assert _thinking_cli_flags("grok", "high") == ["--reasoning-effort", "high"]
    assert _thinking_cli_flags("antigravity", "high") == []
    assert _thinking_cli_flags("pi", None) == []


def test_build_command_injects_tier_model_and_thinking() -> None:
    model, thinking = _resolve_review_model_spec("claude_code")
    adapter = CliVendorAdapter(
        agent_id="claude-local",
        vendor="claude_code",
        cli_config=CliConfig(
            command="claude",
            dispatch_modes={
                "review": ModeConfig(
                    args=[
                        "--print",
                        "--allowedTools",
                        "Read,Grep,Glob",
                        "--json-schema",
                        "@review-findings-schema",
                    ]
                )
            },
            model_flag="--model",
            model=None,
            prompt_via_stdin=True,
        ),
    )
    # Avoid schema file dependency: stub _resolve_args
    adapter._resolve_args = lambda args: [  # type: ignore[method-assign]
        a if a != "@review-findings-schema" else "<schema>" for a in args
    ]
    cmd = adapter.build_command("review", "prompt", model=model, thinking=thinking)
    assert cmd[0] == "claude"
    assert "--effort" in cmd and "medium" in cmd
    assert "--model" in cmd and model in cmd
    # Stale effort flags must not double up
    assert cmd.count("--effort") == 1
