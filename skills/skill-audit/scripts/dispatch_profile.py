"""Dispatch profile: which archetypes, and so which tiers, run a skill.

Lifecycle skills map to phases through ``references/dispatch-map.md``; the
roster's ``phase_mapping`` turns phases into archetypes. Other skills are
scanned for the archetype tokens their own ``Task(``/``Agent(`` examples use.
Providers are enumerated from ``model_aliases`` in the roster file, never
from a literal list (design D4; spec "Dispatch profile follows the roster").
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from audit_paths import REFERENCES_DIR, ensure_sibling_paths

ensure_sibling_paths()

from archetype_roster import (  # noqa: E402
    load_archetypes_raw,
    model_aliases,
    phase_mapping,
    resolve_tier_for_provider,
)

DISPATCH_MAP_PATH = REFERENCES_DIR / "dispatch-map.md"
_ROW_RE = re.compile(r"^\|\s*([a-z0-9-]+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$")
_ARCHETYPE_TOKEN_RE = re.compile(r"archetype\s*[=:]\s*[\"']?([a-z_]+)")
_MODEL_VAR_RE = re.compile(r"model\s*=\s*([a-z_]+?)_model\b")


def _split(cell: str) -> list[str]:
    cell = cell.strip()
    if not cell or cell in {"—", "-", "–"}:
        return []
    return [part.strip() for part in cell.split(",") if part.strip()]


# agent-archetypes "Local Provider Archetype Trust Boundary": the `local`
# provider is permitted only for archetypes whose output is cheap to discard or
# verified downstream. Resolution for these three must never return `local`.
LOCAL_PROVIDER = "local"
LOCAL_FORBIDDEN_ARCHETYPES = frozenset({"architect", "reviewer", "gatekeeper"})

# Best-to-worst. An omitted tier degrades rightwards, mirroring the
# coordinator's graceful-degradation rule.
TIER_PREFERENCE = ("frontier", "premium", "standard", "economy")


def load_dispatch_map(path: Path | None = None) -> dict[str, dict[str, list[str]]]:
    """Parse the skill → {phases, direct} table from ``references/dispatch-map.md``."""
    text = (path or DISPATCH_MAP_PATH).read_text(encoding="utf-8")
    out: dict[str, dict[str, list[str]]] = {}
    for line in text.splitlines():
        m = _ROW_RE.match(line)
        if not m or m.group(1) == "skill" or set(m.group(2)) <= {"-", " "}:
            continue
        out[m.group(1)] = {"phases": _split(m.group(2)), "direct": _split(m.group(3))}
    return out


def archetypes_from_text(skill_md: str, known: set[str]) -> list[str]:
    """Archetype names a non-lifecycle SKILL.md dispatches, in first-seen order."""
    seen: list[str] = []
    for pattern in (_ARCHETYPE_TOKEN_RE, _MODEL_VAR_RE):
        for m in pattern.finditer(skill_md):
            name = m.group(1)
            if name in known and name not in seen:
                seen.append(name)
    return seen


def archetypes_for_skill(
    skill: str,
    skill_md: str,
    *,
    roster_path: Path | None = None,
    dispatch_map: dict[str, dict[str, list[str]]] | None = None,
) -> dict[str, list[str]]:
    """Return ``{archetype: [phases]}`` for *skill* (phases empty for direct dispatch)."""
    mapping = phase_mapping(roster_path)
    raw = load_archetypes_raw(str(roster_path) if roster_path else None)
    known = set((raw.get("archetypes") or {}).keys())
    table = dispatch_map if dispatch_map is not None else load_dispatch_map()

    result: dict[str, list[str]] = {}
    entry = table.get(skill)
    if entry is not None:
        phases = list(mapping.keys()) if entry["phases"] == ["*"] else entry["phases"]
        for phase in phases:
            spec = mapping.get(phase)
            if not isinstance(spec, dict):
                continue
            archetype = spec.get("archetype")
            if archetype in known:
                result.setdefault(archetype, []).append(phase)
        for archetype in entry["direct"]:
            if archetype in known:
                result.setdefault(archetype, [])
    else:
        for archetype in archetypes_from_text(skill_md, known):
            result.setdefault(archetype, [])
    return result


def build_dispatch_profile(
    skill: str,
    skill_md: str,
    *,
    roster_path: Path | None = None,
    dispatch_map: dict[str, dict[str, list[str]]] | None = None,
) -> list[dict[str, Any]]:
    """One row per ``(archetype, provider)`` with the tier dispatch would resolve."""
    raw = load_archetypes_raw(str(roster_path) if roster_path else None)
    archetypes = raw.get("archetypes") or {}
    aliases = model_aliases(roster_path)
    rows: list[dict[str, Any]] = []
    for archetype, phases in archetypes_for_skill(
        skill, skill_md, roster_path=roster_path, dispatch_map=dispatch_map
    ).items():
        spec = archetypes.get(archetype) or {}
        tier = str(spec.get("model") or "standard")
        procedure_mode = spec.get("procedure_mode")
        for provider, provider_map in aliases.items():
            if not isinstance(provider_map, dict):
                continue
            if provider == LOCAL_PROVIDER and archetype in LOCAL_FORBIDDEN_ARCHETYPES:
                # agent-archetypes "Local Provider Archetype Trust Boundary":
                # resolution for these archetypes MUST NOT return provider
                # `local`. Stated here rather than left to the tier failing to
                # resolve, so a roster that later defines every local tier does
                # not silently start reporting a dispatch the coordinator
                # refuses.
                continue
            model, thinking = resolve_tier_for_provider(provider, tier, path=roster_path)
            degraded = "frontier" if tier == "frontier" and "frontier" not in provider_map else None
            if model is None:
                # The shared helper only falls back frontier -> premium, but the
                # coordinator degrades any omitted tier to the provider's best
                # defined one. Mirror that, or the profile under-reports which
                # tiers run the skill (the `local` roster defines only standard
                # and economy, so every premium archetype would vanish).
                for candidate in TIER_PREFERENCE[TIER_PREFERENCE.index(tier) + 1 :] if tier in TIER_PREFERENCE else []:
                    model, thinking = resolve_tier_for_provider(provider, candidate, path=roster_path)
                    if model is not None:
                        degraded = tier
                        break
            if model is None:
                continue
            rows.append(
                {
                    "archetype": archetype,
                    "tier": tier,
                    "provider": str(provider),
                    "model": model,
                    "thinking": thinking,
                    "procedure_mode": procedure_mode if isinstance(procedure_mode, str) else None,
                    "degraded_from": degraded,
                    "phases": sorted(phases),
                }
            )
    return rows


__all__ = [
    "DISPATCH_MAP_PATH",
    "archetypes_for_skill",
    "archetypes_from_text",
    "build_dispatch_profile",
    "load_dispatch_map",
]
