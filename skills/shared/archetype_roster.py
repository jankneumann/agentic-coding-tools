"""Read-only access to ``archetypes.yaml`` roster surfaces.

Skills and review dispatch MUST derive tier→model and phase→archetype→tier
from this file rather than maintaining parallel constants. The coordinator
loads the same file via ``agents_config.load_archetypes_config``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

_REPO_ROOT_MARKERS = ("agent-coordinator/archetypes.yaml", "openspec/project.md")


def find_repo_root(start: Path | None = None) -> Path:
    """Walk parents until ``agent-coordinator/archetypes.yaml`` is found."""
    cur = (start or Path(__file__).resolve()).parent
    for candidate in (cur, *cur.parents):
        if (candidate / "agent-coordinator" / "archetypes.yaml").is_file():
            return candidate
    raise FileNotFoundError(
        "could not locate agent-coordinator/archetypes.yaml above "
        f"{start or Path(__file__)}"
    )


def archetypes_yaml_path(repo_root: Path | None = None) -> Path:
    root = repo_root or find_repo_root()
    return root / "agent-coordinator" / "archetypes.yaml"


@lru_cache(maxsize=4)
def load_archetypes_raw(path_str: str | None = None) -> dict[str, Any]:
    """Load and cache the authored archetypes.yaml document."""
    import yaml

    path = Path(path_str) if path_str else archetypes_yaml_path()
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"archetypes.yaml at {path} is empty or not a mapping")
    return raw


def clear_archetypes_raw_cache() -> None:
    """Reset the load cache (tests)."""
    load_archetypes_raw.cache_clear()


def model_aliases(path: Path | None = None) -> dict[str, Any]:
    raw = load_archetypes_raw(str(path) if path else None)
    aliases = raw.get("model_aliases") or {}
    if not isinstance(aliases, dict):
        raise ValueError("archetypes.yaml model_aliases must be a mapping")
    return aliases


def phase_mapping(path: Path | None = None) -> dict[str, Any]:
    raw = load_archetypes_raw(str(path) if path else None)
    mapping = raw.get("phase_mapping") or {}
    if not isinstance(mapping, dict):
        raise ValueError("archetypes.yaml phase_mapping must be a mapping")
    return mapping


def phase_signal_keys(path: Path | None = None) -> dict[str, list[str]]:
    """Return ``{phase: [signal, …]}`` from authored ``phase_mapping``."""
    out: dict[str, list[str]] = {}
    for phase, entry in phase_mapping(path).items():
        if not isinstance(entry, dict):
            continue
        signals = entry.get("signals") or []
        out[str(phase)] = [str(s) for s in signals]
    return out


def tier_entry_model(entry: Any) -> str | None:
    if isinstance(entry, str) and entry:
        return entry
    if isinstance(entry, dict):
        model = entry.get("model")
        if isinstance(model, str) and model:
            return model
    return None


def tier_entry_thinking(entry: Any) -> str | None:
    if isinstance(entry, dict):
        thinking = entry.get("thinking")
        if isinstance(thinking, str) and thinking:
            return thinking
    return None


def resolve_tier_for_provider(
    provider: str,
    tier: str,
    *,
    path: Path | None = None,
) -> tuple[str | None, str | None]:
    """Return ``(model_id, thinking)`` for *provider*/*tier*.

    Optional tiers missing on a provider fall back to ``premium`` (same rule
    as the coordinator resolver).
    """
    aliases = model_aliases(path)
    provider_map = aliases.get(provider)
    if not isinstance(provider_map, dict):
        return None, None
    entry = provider_map.get(tier)
    if entry is None and tier == "frontier":
        entry = provider_map.get("premium")
    model = tier_entry_model(entry)
    thinking = tier_entry_thinking(entry)
    return model, thinking


def thinking_cli_flags(vendor: str, thinking: str | None) -> list[str]:
    """Translate a tier ``thinking`` value into vendor CLI argv tokens."""
    if not thinking:
        return []
    if vendor in {"claude_code", "claude"}:
        return ["--effort", thinking]
    if vendor == "codex":
        return ["-c", f"model_reasoning_effort={thinking}"]
    if vendor == "grok":
        return ["--reasoning-effort", thinking]
    # antigravity embeds effort in the model slug; pi uses model:thinking
    # shorthand when callers opt in — no separate flag here.
    return []
