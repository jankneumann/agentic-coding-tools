"""Canonical isolation vocabulary and precedence helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

ISOLATION_MODES: tuple[str, ...] = ("none", "worktree", "sandbox")
type IsolationMode = Literal["none", "worktree", "sandbox"]
type IsolationSource = Literal["router", "agents_yaml", "default"]


class IsolationContractError(ValueError):
    """A supplied isolation value is not part of the pinned contract."""


@dataclass(frozen=True, slots=True)
class IsolationResolution:
    value: IsolationMode
    source: IsolationSource


def validate_isolation(value: object, *, rung: str) -> IsolationMode:
    """Validate a present value and name its provenance on failure."""
    if not isinstance(value, str) or value not in ISOLATION_MODES:
        raise IsolationContractError(f"invalid isolation value at {rung}: {value!r}")
    return cast(IsolationMode, value)


def configured_isolation_value(
    configured: Mapping[str, object], dispatch_mode: str | None
) -> object | None:
    """Return a present mode override, then the entry-level value.

    Values are intentionally returned without truthiness coercion so callers
    can distinguish absence from an invalid present value such as ``""``.
    ``sandbox`` is a posture label here; enforcement remains a separate concern.
    """
    cli = configured.get("cli")
    if dispatch_mode is not None and isinstance(cli, Mapping):
        dispatch_modes = cli.get("dispatch_modes")
        if isinstance(dispatch_modes, Mapping):
            mode = dispatch_modes.get(dispatch_mode)
            if isinstance(mode, Mapping) and "isolation" in mode:
                return mode["isolation"]
    return configured.get("isolation")


def resolve_isolation(
    *,
    router_reachable: bool,
    router_value: object | None,
    configured_value: object | None,
) -> IsolationResolution:
    """Resolve router, configured, and default rungs without silent coercion."""
    if router_reachable and router_value is not None:
        return IsolationResolution(validate_isolation(router_value, rung="router"), "router")
    if configured_value is not None:
        return IsolationResolution(
            validate_isolation(configured_value, rung="agents_yaml"), "agents_yaml"
        )
    return IsolationResolution("none", "default")
