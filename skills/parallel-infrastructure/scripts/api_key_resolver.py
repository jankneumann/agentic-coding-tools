"""Secure API key resolution for SDK dispatch.

Resolves vendor API keys at runtime using OpenBao (preferred) with
environment variable fallback.  Keys are cached for the lifetime of
the resolver instance to avoid repeated vault lookups.

Usage:
    resolver = ApiKeyResolver()
    key = resolver.resolve("claude-code-web", "ANTHROPIC_API_KEY")
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class ApiKeyResolver:
    """Resolve API keys from OpenBao or environment variables.

    Resolution order per call:
    1. OpenBao via ``openbao_role_id`` (if ``BAO_ADDR`` is set)
    2. Environment variable via ``api_key_env``
    3. ``None`` (vendor skipped)

    Results are cached for the resolver's lifetime.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str | None] = {}
        self._bao_available: bool | None = None

    def resolve(
        self,
        openbao_role_id: str | None,
        api_key_env: str,
    ) -> str | None:
        """Resolve an API key, returning cached value if available."""
        cache_key = f"{openbao_role_id or ''}:{api_key_env}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._resolve_uncached(openbao_role_id, api_key_env)
        self._cache[cache_key] = result
        return result

    def _resolve_uncached(
        self,
        openbao_role_id: str | None,
        api_key_env: str,
    ) -> str | None:
        # Tier 1: Try OpenBao
        if openbao_role_id and self._is_bao_available():
            key = self._resolve_from_openbao(openbao_role_id, api_key_env)
            if key:
                logger.info(
                    "API key resolved from OpenBao (role: %s)", openbao_role_id,
                )
                return key

        # Tier 2: Environment variable
        if api_key_env:
            key = os.environ.get(api_key_env)
            if key:
                logger.info("API key resolved from env var %s", api_key_env)
                return key

        # Tier 3: Not available
        logger.debug(
            "No API key available (role=%s, env=%s)",
            openbao_role_id, api_key_env,
        )
        return None

    def _is_bao_available(self) -> bool:
        """Check if OpenBao is configured (cached)."""
        if self._bao_available is None:
            self._bao_available = bool(os.environ.get("BAO_ADDR"))
        return self._bao_available

    def _resolve_from_openbao(
        self,
        openbao_role_id: str,
        api_key_env: str,
    ) -> str | None:
        """Resolve API key directly via hvac client using OpenBao AppRole auth.

        Authenticates with the agent's ``openbao_role_id`` and reads
        the secret named ``api_key_env`` from the vault.
        """
        try:
            import hvac

            bao_addr = os.environ.get("BAO_ADDR", "")
            secret_id = os.environ.get("BAO_SECRET_ID", "")
            mount_path = os.environ.get("BAO_MOUNT_PATH", "secret")
            secret_path = os.environ.get("BAO_SECRET_PATH", "agents")

            if not bao_addr or not secret_id:
                return None

            client = hvac.Client(url=bao_addr, timeout=10)
            client.auth.approle.login(
                role_id=openbao_role_id,
                secret_id=secret_id,
            )
            response = client.secrets.kv.v2.read_secret_version(
                path=secret_path,
                mount_point=mount_path,
            )
            data = response.get("data", {}).get("data", {})
            return data.get(api_key_env) if api_key_env else None
        except ImportError:
            logger.debug("hvac not installed — OpenBao resolution unavailable")
            return None
        except Exception:  # noqa: BLE001
            logger.warning(
                "OpenBao resolution failed for role '%s'",
                openbao_role_id,
                exc_info=True,
            )
            return None
