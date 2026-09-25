"""Atomic, fail-closed coordinator API-key identities from the Bao reader."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from openbao_credentials import (
    BaoCredentialError,
    ErrorCode,
    OpenBaoClient,
    PrincipalOpenBaoConfig,
)

if TYPE_CHECKING:
    from .agents_config import AgentEntry

_LOGGER = logging.getLogger(__name__)
IDENTITY_PRINCIPAL = "spiffe://coordinator.rotkohl.ai/service/identity-reader"
IDENTITY_ROLE = "service-identity-reader"
RELOAD_SECONDS = 30
GRACE_SECONDS = 120


async def run_reload_loop(runtime: IdentityRuntime, interval: float = RELOAD_SECONDS) -> None:
    """Refresh off the event loop until the server cancels this task."""
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(runtime.reload)


class IdentityReader(Protocol):
    def ensure_session(self, principal_id: str, role_name: str) -> object: ...
    def read_agent_key(self, name: str) -> str: ...


def build_identity_snapshot(
    reader: IdentityReader, agents: list[AgentEntry]
) -> dict[str, dict[str, str]]:
    """Read every keyed agent document; reject incomplete or ambiguous maps."""
    reader.ensure_session(IDENTITY_PRINCIPAL, IDENTITY_ROLE)
    result: dict[str, dict[str, str]] = {}
    for agent in agents:
        if agent.api_key is None:
            continue
        key = reader.read_agent_key(agent.name)
        if not isinstance(key, str) or not key.strip() or key in result:
            raise BaoCredentialError(ErrorCode.SECRET_MALFORMED, "identity")
        result[key] = {"agent_id": agent.name, "agent_type": agent.type}
    return result


@dataclass(frozen=True)
class IdentityState:
    identities: Mapping[str, Mapping[str, str]]
    installed_at: float | None
    failed: bool


class IdentityRuntime:
    """One installed snapshot shared by authentication and readiness."""

    def __init__(
        self,
        reader_factory: Callable[[], IdentityReader] | None = None,
        agents_loader: Callable[[], list[AgentEntry]] | None = None,
        required_static_keys: tuple[str, ...] = (),
    ) -> None:
        if reader_factory is None:
            def reader_factory() -> IdentityReader:
                return OpenBaoClient(PrincipalOpenBaoConfig.from_env())
        if agents_loader is None:
            from .agents_config import load_agents_config

            agents_loader = load_agents_config
        self._reader_factory = reader_factory
        self._agents_loader = agents_loader
        self._required_static_keys = required_static_keys
        self.preflight_blockers: tuple[str, ...] = ()
        self._state = IdentityState(MappingProxyType({}), None, True)

    @property
    def state(self) -> IdentityState:
        return self._state

    @property
    def usable(self) -> bool:
        return self.readiness()[1]

    @property
    def identity_status(self) -> str:
        return self.readiness()[0]

    def readiness(self) -> tuple[str, bool]:
        """Read one state for both component status and routability."""
        state = self._state
        usable = (
            state.installed_at is not None
            and time.monotonic() - state.installed_at <= GRACE_SECONDS
        )
        return ("ready" if usable and not state.failed else "degraded", usable)

    def lookup(self, key: str) -> Mapping[str, str] | None:
        state = self._state
        if state.installed_at is None or time.monotonic() - state.installed_at > GRACE_SECONDS:
            return None
        return state.identities.get(key)

    def reload(self) -> bool:
        """Build a complete candidate before one state assignment."""
        previous = self._state
        if previous.installed_at is None:
            self.preflight_blockers = ()
        try:
            candidate = build_identity_snapshot(self._reader_factory(), self._agents_loader())
            if previous.installed_at is None:
                self.preflight_blockers = tuple(
                    f"COORDINATION_API_KEYS[{index}]"
                    for index, key in enumerate(self._required_static_keys)
                    if key not in candidate
                )
                if self.preflight_blockers:
                    raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "identity")
        except Exception as exc:  # noqa: BLE001 — failed candidate must not replace state
            code = (
                exc.code if isinstance(exc, BaoCredentialError)
                else ErrorCode.CONFIGURATION_INVALID
            )
            self._state = IdentityState(previous.identities, previous.installed_at, True)
            if self.preflight_blockers:
                _LOGGER.warning("OpenBao cutover blocked by unbound static entries: %s",
                                ", ".join(self.preflight_blockers))
            self._emit("refresh_failed", "failure", code=code)
            return False

        frozen = MappingProxyType({key: MappingProxyType(identity.copy())
                                   for key, identity in candidate.items()})
        self._state = IdentityState(frozen, time.monotonic(), False)
        self.preflight_blockers = ()
        self._emit("refresh_succeeded", "success")
        return True

    def _emit(self, event: str, outcome: str, *, code: ErrorCode | None = None) -> None:
        state = self._state
        record: dict[str, object] = {
            "version": 1,
            "event": f"openbao.identity.{event}",
            "occurred_at": datetime.now(UTC).isoformat(),
            "action": "refresh",
            "outcome": outcome,
            "principal_id": IDENTITY_PRINCIPAL,
            "resource": "identity_snapshot",
        }
        if code is not None:
            record["error_code"] = code.value
        if state.installed_at is not None:
            record["snapshot_age_seconds"] = max(0.0, time.monotonic() - state.installed_at)
        _LOGGER.log(logging.WARNING if code else logging.INFO,
                    "OpenBao identity event %s", json.dumps(record, sort_keys=True))
