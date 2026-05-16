#!/usr/bin/env python3
"""Manual dry-run smoke for provider-neutral autopilot dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[2]
for candidate in (
    _THIS_DIR,
    _THIS_DIR.parent.parent / "session-log" / "scripts",
    _REPO_ROOT / "agent-coordinator",
):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import phase_agent  # type: ignore[import-not-found]  # noqa: E402
from phase_record import PhaseRecord  # type: ignore[import-not-found]  # noqa: E402
from provider_dispatch import PhaseDispatchPayload, dispatch_phase  # noqa: E402
from src.agents_config import (  # type: ignore[import-not-found]  # noqa: E402
    ProviderModelMappingError,
    load_archetypes_config,
    resolve_archetype_for_phase,
)

_CLAUDE_ALIASES = {"opus", "sonnet", "haiku"}


def _build_payload(provider: str, model_override: str | None) -> PhaseDispatchPayload:
    if provider != "claude_code" and model_override in _CLAUDE_ALIASES:
        raise ProviderModelMappingError(provider, model_override or "")

    load_archetypes_config()
    resolved = resolve_archetype_for_phase(
        "IMPLEMENT",
        {"loc_estimate": 25, "write_allow": ["skills/autopilot/**"], "dependencies": []},
        provider=provider,
    )
    model = model_override or resolved.model
    if provider != "claude_code" and model in _CLAUDE_ALIASES:
        raise ProviderModelMappingError(provider, model)

    incoming = PhaseRecord(
        change_id="vendor-neutral-autopilot-smoke",
        phase_name="smoke",
        agent_type="autopilot",
        summary="dry-run provider dispatch smoke",
    )
    prompt = phase_agent._build_prompt(  # noqa: SLF001 - smoke uses canonical helper
        "IMPLEMENT",
        {"change_id": "vendor-neutral-autopilot-smoke", "current_phase": "IMPLEMENT"},
        incoming,
        artifacts_manifest=["openspec/changes/vendor-neutral-autopilot/design.md"],
    )
    if resolved.system_prompt:
        prompt = f"{resolved.system_prompt}{phase_agent._PROMPT_SEPARATOR}{prompt}"  # noqa: SLF001

    return PhaseDispatchPayload(
        schema_version=1,
        change_id="vendor-neutral-autopilot-smoke",
        phase="IMPLEMENT",
        provider=provider,
        archetype=resolved.archetype,
        model=model,
        prompt=prompt,
        system_prompt=resolved.system_prompt,
        isolation="worktree",
        expected_outcomes=["complete", "failed"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=["claude_code", "codex", "gemini"])
    parser.add_argument("--model", help="Optional model override for negative smoke tests")
    parser.add_argument("--dry-run", action="store_true", help="Do not invoke a real provider")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    try:
        payload = _build_payload(args.provider, args.model)
    except ProviderModelMappingError as exc:
        print(f"Provider model mapping error: Claude alias or missing mapping: {exc}", file=sys.stderr)
        return 2

    result = dispatch_phase(payload, dry_run=args.dry_run)
    body = {
        "provider": args.provider,
        "payload": payload.to_dict(),
        "result": result.to_dict(),
    }
    if args.json_output:
        print(json.dumps(body, indent=2, sort_keys=True))
    else:
        print(
            f"provider={args.provider} phase={payload.phase} model={payload.model} "
            f"outcome={result.outcome} handoff_id={result.handoff_id} "
            f"tier={result.dispatch_tier}"
        )
        for warning in result.warnings:
            print(f"WARN: {warning}", file=sys.stderr)
    return 0 if result.outcome != "failed" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
