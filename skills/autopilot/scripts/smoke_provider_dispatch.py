#!/usr/bin/env python3
"""Manual dry-run smoke for provider-neutral autopilot dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
for candidate in (
    _THIS_DIR,
    _THIS_DIR.parent.parent / "session-log" / "scripts",
):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import phase_agent  # type: ignore[import-not-found]  # noqa: E402
from phase_record import PhaseRecord  # type: ignore[import-not-found]  # noqa: E402
from provider_dispatch import (  # type: ignore[import-not-found]  # noqa: E402
    PhaseDispatchPayload,
    dispatch_phase,
)

_CLAUDE_ALIASES = {"opus", "sonnet", "haiku"}
# Offline dry-run fallback models. The antigravity provider is intentionally
# absent — its model family resolves through the coordinator at runtime and
# its slugs are not duplicated here; an offline dry run falls through to the
# generic default below.
_FALLBACK_MODELS = {
    "claude_code": "sonnet",
    "codex": "gpt-5.4",
    "grok": "grok-4.5",
    "pi": "qwen/qwen3-coder",
    # `local` economy-tier roster identifier (OpenSpec
    # add-local-model-provider-tier, D7). Used only when the coordinator does
    # not resolve a local roster model for the phase.
    "local": "qwen3-coder-30b-a3b",
}
_DEFAULT_FALLBACK_MODEL = "default"
_SUPPORTED_PROVIDERS = ["claude_code", "codex", "antigravity", "grok", "pi", "local"]

_LOCAL_PROVIDER = "local"
_DEFAULT_SMOKE_PHASE = "IMPLEMENT"
# `local` sits behind the resolver's archetype trust boundary (OpenSpec
# add-local-model-provider-tier, D3): only archetypes whose output is cheap to
# discard or verified downstream may be served locally. IMPLEMENT resolves to
# `implementer`, which the resolver refuses — so the smoke drives INIT (which
# maps to `runner`) for `local` instead of building a payload that can only ever
# be refused, or worse, dispatched behind the resolver's back.
_LOCAL_SMOKE_PHASE = "INIT"
_LOCAL_TRUSTED_ARCHETYPES = frozenset({"runner", "analyst", "documenter", "validator"})
# Offline dry-run fixture: no resolver, no dispatch, so the smoke declares the
# phase's static archetype from archetypes.yaml (INIT -> runner) alongside the
# fallback model. Real mode never uses it — see _build_payload.
_LOCAL_DRY_RUN_ARCHETYPE = "runner"


class ProviderModelMappingError(ValueError):
    """Raised when a provider is paired with a Claude-only model alias."""


class LocalTrustBoundaryError(RuntimeError):
    """Raised when a real-mode `local` smoke cannot prove a permitted archetype.

    The resolver is the single decision point for the `local` trust boundary. If
    it refuses the pairing (or is unreachable, which is indistinguishable from a
    refusal at this layer), the smoke fails here: it must not fall through to a
    hardcoded model and dispatch to the endpoint anyway.
    """


def _smoke_phase(provider: str) -> str:
    return _LOCAL_SMOKE_PHASE if provider == _LOCAL_PROVIDER else _DEFAULT_SMOKE_PHASE


def _build_payload(
    provider: str,
    model_override: str | None,
    *,
    dry_run: bool = False,
) -> PhaseDispatchPayload:
    if provider != "claude_code" and model_override in _CLAUDE_ALIASES:
        raise ProviderModelMappingError(provider, model_override or "")

    phase = _smoke_phase(provider)
    state = {
        "loc_estimate": 25,
        "write_allow": ["skills/autopilot/**"],
        "dependencies": [],
    }
    options = phase_agent._build_options(  # noqa: SLF001 - canonical public bridge path
        phase, state, provider=provider
    )
    archetype = state.get("_resolved_archetype")

    if provider == _LOCAL_PROVIDER:
        if dry_run:
            # Offline fixture; nothing leaves the process.
            archetype = archetype or _LOCAL_DRY_RUN_ARCHETYPE
        elif not archetype:
            raise LocalTrustBoundaryError(
                f"the resolver returned no archetype for phase {phase} under "
                f"provider 'local' (refusal or coordinator unavailable); "
                f"permitted archetypes: {', '.join(sorted(_LOCAL_TRUSTED_ARCHETYPES))}. "
                "No dispatch attempted."
            )
        if archetype not in _LOCAL_TRUSTED_ARCHETYPES:
            raise LocalTrustBoundaryError(
                f"archetype {archetype!r} (phase {phase}) is outside the 'local' "
                f"provider trust boundary; permitted archetypes: "
                f"{', '.join(sorted(_LOCAL_TRUSTED_ARCHETYPES))}. No dispatch attempted."
            )

    model = model_override or options.get("model")
    if not model:
        if provider == _LOCAL_PROVIDER and not dry_run:
            # Unreachable in practice (a resolved archetype carries a model), but
            # the invariant is explicit: real local mode never ships a hardcoded
            # model to the endpoint.
            raise LocalTrustBoundaryError(
                f"the resolver returned no model for phase {phase} under provider "
                "'local'. No dispatch attempted."
            )
        model = _FALLBACK_MODELS.get(provider, _DEFAULT_FALLBACK_MODEL)
    if provider != "claude_code" and model in _CLAUDE_ALIASES:
        raise ProviderModelMappingError(provider, model)

    incoming = PhaseRecord(
        change_id="vendor-neutral-autopilot-smoke",
        phase_name="smoke",
        agent_type="autopilot",
        summary="dry-run provider dispatch smoke",
    )
    prompt = phase_agent._build_prompt(  # noqa: SLF001 - smoke uses canonical helper
        phase,
        {"change_id": "vendor-neutral-autopilot-smoke", "current_phase": phase},
        incoming,
        artifacts_manifest=["openspec/changes/vendor-neutral-autopilot/design.md"],
    )
    system_prompt = options.get("system_prompt")
    if system_prompt:
        prompt = f"{system_prompt}{phase_agent._PROMPT_SEPARATOR}{prompt}"  # noqa: SLF001

    return PhaseDispatchPayload(
        schema_version=1,
        change_id="vendor-neutral-autopilot-smoke",
        phase=phase,
        provider=provider,
        archetype=archetype,
        model=model,
        prompt=prompt,
        system_prompt=system_prompt,
        isolation=options.get("isolation"),
        expected_outcomes=["complete", "failed"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        required=True,
        choices=_SUPPORTED_PROVIDERS,
        help=(
            "Provider selector, restricted to the supported roster. `local` "
            "runs the INIT phase (archetype `runner`) to stay inside the local "
            "provider trust boundary, and dispatches over the OpenAI-compatible "
            "protocol to LOCAL_INFERENCE_BASE_URL in real mode; with that "
            "variable unset or the endpoint unreachable the run reports the "
            "structured fallback degradation instead of hanging. A real-mode run "
            "whose archetype the resolver will not confirm fails without "
            "dispatching."
        ),
    )
    parser.add_argument("--model", help="Optional model override for negative smoke tests")
    parser.add_argument("--dry-run", action="store_true", help="Do not invoke a real provider")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    try:
        payload = _build_payload(args.provider, args.model, dry_run=args.dry_run)
    except ProviderModelMappingError as exc:
        print(f"Provider model mapping error: Claude alias or missing mapping: {exc}", file=sys.stderr)
        return 2
    except LocalTrustBoundaryError as exc:
        print(f"Local provider trust boundary error: {exc}", file=sys.stderr)
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
