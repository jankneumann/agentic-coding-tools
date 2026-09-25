"""Principal-scoped vendor API key resolution for SDK dispatch."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence

_AGENT_ID = re.compile(r"^spiffe://coordinator\.rotkohl\.ai/agent/([a-z][a-z0-9]*(?:-[a-z0-9]+)*)$")


class ApiKeyResolver:
    """Authorize requested vendor against the dispatch config before any read.

    Non-OpenBao operation retains the configured development environment key.
    OpenBao operation always reads afresh so rotation is observable without a
    process restart. No shared SecretID or coordinator path is consulted.
    """

    def __init__(
        self,
        scopes: Mapping[str, Sequence[str]] | None = None,
        env_by_request: Mapping[tuple[str | None, str], str] | None = None,
    ) -> None:
        self._scopes = scopes or {}
        self._env_by_request = env_by_request or {}

    def resolve(self, principal_id: str | None, vendor_id: str) -> str | None:
        """Resolve one vendor key for one explicitly scoped principal."""
        if not os.environ.get("BAO_ADDR"):
            env_name = self._env_by_request.get((principal_id, vendor_id), "")
            return os.environ.get(env_name) or None if env_name else None

        from openbao_credentials import (
            BaoCredentialError,
            ErrorCode,
            OpenBaoClient,
            PrincipalOpenBaoConfig,
        )

        match = _AGENT_ID.fullmatch(principal_id or "")
        if match is None:
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "principal")
        if vendor_id not in self._scopes.get(principal_id, ()):
            raise BaoCredentialError(ErrorCode.AUTHORIZATION_DENIED, "vendor")

        client = OpenBaoClient(PrincipalOpenBaoConfig.from_env())
        client.ensure_session(principal_id, f"agent-{match.group(1)}")
        return client.read_vendor_key(vendor_id)
