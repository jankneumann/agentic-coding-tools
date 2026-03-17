"""YAML-based deployment profile loader with inheritance and secret interpolation.

Loads profiles from ``agent-coordinator/profiles/<name>.yaml``, resolves
``extends:`` inheritance via deep merge, interpolates ``${VAR}`` / ``${VAR:-default}``
from ``.secrets.yaml`` and environment variables, and injects resolved settings into
``os.environ`` as defaults (existing env vars always win).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Explicit mapping: YAML path → environment variable name.
# Only keys listed here are injected into os.environ.
# The ``docker`` and ``providers`` blocks are profile-only metadata.
# ---------------------------------------------------------------------------
FIELD_ENV_MAP: dict[str, str] = {
    "settings.db_backend": "DB_BACKEND",
    "settings.postgres_dsn": "POSTGRES_DSN",
    "settings.postgres_pool_min": "POSTGRES_POOL_MIN",
    "settings.postgres_pool_max": "POSTGRES_POOL_MAX",
    "settings.agent_id": "AGENT_ID",
    "settings.agent_type": "AGENT_TYPE",
    "settings.lock_ttl_minutes": "LOCK_TTL_MINUTES",
    "settings.guardrails_cache_ttl": "GUARDRAILS_CACHE_TTL",
    "settings.guardrails_code_fallback": "GUARDRAILS_CODE_FALLBACK",
    "settings.profiles_default_trust": "PROFILES_DEFAULT_TRUST",
    "settings.profiles_enforce_limits": "PROFILES_ENFORCE_LIMITS",
    "settings.audit_retention_days": "AUDIT_RETENTION_DAYS",
    "settings.audit_async": "AUDIT_ASYNC",
    "settings.network_default_policy": "NETWORK_DEFAULT_POLICY",
    "settings.policy_engine": "POLICY_ENGINE",
    "settings.policy_cache_ttl": "POLICY_CACHE_TTL",
    "api.host": "API_HOST",
    "api.port": "API_PORT",
    "api.workers": "API_WORKERS",
    "api.timeout_keep_alive": "API_TIMEOUT_KEEP_ALIVE",
    "api.access_log": "API_ACCESS_LOG",
    "api.coordination_api_keys": "COORDINATION_API_KEYS",
    "api.coordination_api_key_identities": "COORDINATION_API_KEY_IDENTITIES",
    "api.coordination_allowed_hosts": "COORDINATION_ALLOWED_HOSTS",
    "transport": "COORDINATION_TRANSPORT",
}

# Regex: matches ${VAR} and ${VAR:-default}, but not $${…} (escaped).
_INTERPOLATION_RE = re.compile(
    r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}"
)


# ---------------------------------------------------------------------------
# Deep merge
# ---------------------------------------------------------------------------

def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into a copy of *base*.

    - Dict values are merged recursively (child keys override parent keys).
    - Scalars and lists in *override* replace *base* values entirely.
    """
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# Secret + env interpolation
# ---------------------------------------------------------------------------

def _load_secrets_file(secrets_path: Path) -> dict[str, str]:
    """Load ``.secrets.yaml`` if it exists, returning a flat str→str dict.

    Non-string values (booleans, integers, nulls) are logged and skipped
    to prevent silent ``"None"`` or ``"True"`` interpolation.
    """
    if not secrets_path.is_file():
        return {}
    with open(secrets_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        logger.debug("Secrets file %s is empty", secrets_path)
        return {}
    if not isinstance(data, dict):
        logger.warning("Secrets file %s is not a YAML mapping — ignored", secrets_path)
        return {}
    result: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(v, str):
            logger.warning(
                "Secret '%s' has non-string type %s — skipped", k, type(v).__name__
            )
            continue
        result[str(k)] = v
    return result


def _load_secrets_openbao() -> dict[str, str]:
    """Load secrets from OpenBao KV v2, returning a flat str→str dict.

    Requires ``BAO_ADDR``, ``BAO_ROLE_ID``, and ``BAO_SECRET_ID`` environment
    variables to be set.

    Raises:
        RuntimeError: On authentication failure.
        ValueError: When required env vars are missing.
        ConnectionError: When OpenBao is unreachable.
    """
    from src.config import OpenBaoConfig

    bao_config = OpenBaoConfig.from_env()
    client = bao_config.create_client()

    try:
        response = client.secrets.kv.v2.read_secret_version(
            path=bao_config.secret_path,
            mount_point=bao_config.mount_path,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to read secrets from OpenBao at {bao_config.addr} "
            f"(mount={bao_config.mount_path!r}, path={bao_config.secret_path!r}): {exc}"
        ) from exc

    data = response.get("data", {}).get("data", {})
    if not isinstance(data, dict):
        logger.warning("OpenBao secret data is not a mapping — returning empty dict")
        return {}

    result: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(v, str):
            logger.warning(
                "OpenBao secret '%s' has non-string type %s — skipped",
                k,
                type(v).__name__,
            )
            continue
        result[str(k)] = v
    return result


def _load_secrets(secrets_path: Path) -> dict[str, str]:
    """Load secrets from OpenBao (when ``BAO_ADDR`` is set) or ``.secrets.yaml``.

    When ``BAO_ADDR`` is set in the environment, secrets are fetched from
    OpenBao via AppRole auth. Otherwise, falls back to the file-based backend.
    """
    if os.environ.get("BAO_ADDR"):
        logger.info("BAO_ADDR is set — loading secrets from OpenBao")
        return _load_secrets_openbao()
    return _load_secrets_file(secrets_path)


def resolve_dynamic_dsn(agent_id: str | None = None) -> str | None:
    """Resolve a dynamic PostgreSQL DSN from the OpenBao database secrets engine.

    When the database secrets engine is configured in OpenBao (i.e., the
    ``database/`` mount exists and a ``coordinator-agent`` role is available),
    generates per-agent dynamic credentials. Otherwise returns ``None`` so the
    caller falls back to static DSN interpolation.

    Args:
        agent_id: Agent identifier for credential scoping. Defaults to
            ``AGENT_ID`` from the environment.

    Returns:
        A PostgreSQL DSN with dynamic credentials, or ``None`` if the database
        engine is not configured.
    """
    from src.config import OpenBaoConfig

    bao_config = OpenBaoConfig.from_env()
    if not bao_config.is_enabled():
        return None

    try:
        client = bao_config.create_client()
        response = client.secrets.database.generate_credentials(
            name="coordinator-agent",
            mount_point="database",
        )
    except Exception:  # noqa: BLE001
        logger.debug(
            "Database secrets engine not available — falling back to static DSN",
            exc_info=True,
        )
        return None

    creds = response.get("data", {})
    username = creds.get("username", "")
    password = creds.get("password", "")
    if not username or not password:
        logger.warning("Dynamic credentials empty — falling back to static DSN")
        return None

    # Lease info for renewal tracking
    lease_id = response.get("lease_id", "")
    lease_duration = response.get("lease_duration", 3600)
    if lease_id:
        logger.info(
            "Dynamic DB credentials issued (lease=%s, ttl=%ds, agent=%s)",
            lease_id,
            lease_duration,
            agent_id or os.environ.get("AGENT_ID", "unknown"),
        )

    # Build DSN using the default PostgreSQL connection parameters
    db_host = os.environ.get("POSTGRES_HOST", "localhost")
    db_port = os.environ.get("POSTGRES_PORT", "54322")
    db_name = os.environ.get("POSTGRES_DB", "postgres")
    return f"postgresql://{username}:{password}@{db_host}:{db_port}/{db_name}"


def interpolate(value: str, secrets: dict[str, str]) -> str:
    """Resolve ``${VAR}`` and ``${VAR:-default}`` in *value*.

    Resolution order: secrets dict → ``os.environ``.
    - ``$${VAR}`` produces the literal ``${VAR}`` (escape).
    - Unresolvable ``${VAR}`` (no default, not in secrets or env) is left as-is.
    """

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2)  # None when no ``:-`` clause
        # Secrets take priority; use explicit ``in`` check so empty strings
        # are honoured (``or`` would skip falsy values).
        if var_name in secrets:
            return secrets[var_name]
        resolved = os.environ.get(var_name)
        if resolved is not None:
            return resolved
        if default is not None:
            return default
        # Leave unresolvable as literal so downstream can surface a clear error.
        return match.group(0)

    result = _INTERPOLATION_RE.sub(_replace, value)
    # Un-escape $${…} → ${…}
    result = result.replace("$${", "${")
    return result


def _interpolate_tree(
    data: Any, secrets: dict[str, str]
) -> Any:
    """Walk a nested dict/list and interpolate all string leaves."""
    if isinstance(data, str):
        return interpolate(data, secrets)
    if isinstance(data, dict):
        return {k: _interpolate_tree(v, secrets) for k, v in data.items()}
    if isinstance(data, list):
        return [_interpolate_tree(item, secrets) for item in data]
    return data


# ---------------------------------------------------------------------------
# Profile loading with inheritance
# ---------------------------------------------------------------------------

def _resolve_profile(
    name: str,
    profiles_dir: Path,
    secrets: dict[str, str],
    seen: set[str] | None = None,
) -> dict[str, Any]:
    """Load *name*.yaml, recursively resolve ``extends:``, and interpolate."""
    if seen is None:
        seen = set()
    if name in seen:
        raise ValueError(
            f"Circular profile inheritance detected: {' -> '.join(seen)} -> {name}"
        )
    seen.add(name)

    path = profiles_dir / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Profile not found: {path}")

    with open(path) as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    parent_name = raw.pop("extends", None)
    if parent_name:
        parent = _resolve_profile(parent_name, profiles_dir, secrets, seen)
        raw = deep_merge(parent, raw)

    return _interpolate_tree(raw, secrets)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Flatten + inject
# ---------------------------------------------------------------------------

def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten a nested dict to dotted-path keys with string values."""
    flat: dict[str, str] = {}
    for key, value in data.items():
        full = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, full))
        else:
            flat[full] = str(value)
    return flat


def _inject_env(profile: dict[str, Any]) -> None:
    """Inject mapped profile values into ``os.environ`` as defaults.

    Existing env vars always take precedence (are not overwritten).
    """
    flat = _flatten(profile)
    for yaml_path, env_var in FIELD_ENV_MAP.items():
        if yaml_path in flat and env_var not in os.environ:
            os.environ[env_var] = flat[yaml_path]
            logger.debug("profile → %s=%s", env_var, flat[yaml_path])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_profile(
    profile_name: str | None = None,
    *,
    profiles_dir: Path | None = None,
    secrets_path: Path | None = None,
) -> dict[str, Any]:
    """Load and resolve a deployment profile.

    Args:
        profile_name: Profile to load. Falls back to ``COORDINATOR_PROFILE``
            env var, then ``"local"``.
        profiles_dir: Directory containing profile YAML files.
        secrets_path: Path to ``.secrets.yaml``.

    Returns:
        Fully resolved profile dict (with inheritance merged and variables
        interpolated).

    Raises:
        FileNotFoundError: If the profile YAML file doesn't exist.
        ValueError: On circular inheritance.
    """
    base = Path(__file__).resolve().parent.parent
    if profiles_dir is None:
        profiles_dir = base / "profiles"
    if secrets_path is None:
        secrets_path = base / ".secrets.yaml"

    name = profile_name or os.environ.get("COORDINATOR_PROFILE", "local")
    secrets = _load_secrets(secrets_path)
    return _resolve_profile(name, profiles_dir, secrets)


def apply_profile(
    profile_name: str | None = None,
    *,
    profiles_dir: Path | None = None,
    secrets_path: Path | None = None,
) -> dict[str, Any] | None:
    """Load a profile and inject its values into ``os.environ``.

    Profile loading only activates when *profile_name* is given explicitly
    **or** the ``COORDINATOR_PROFILE`` environment variable is set.  When
    neither is provided the function returns ``None`` immediately so that
    existing env-var-only behaviour is preserved.

    Returns the resolved profile dict, or ``None`` when profiles are not
    active.
    """
    # Only activate when the caller or the environment explicitly requests a
    # profile.  This keeps tests and legacy setups unaffected.
    if profile_name is None and "COORDINATOR_PROFILE" not in os.environ:
        return None

    base = Path(__file__).resolve().parent.parent
    if profiles_dir is None:
        profiles_dir = base / "profiles"

    if not profiles_dir.is_dir():
        logger.debug("No profiles directory at %s — skipping profile loading", profiles_dir)
        return None

    profile = load_profile(
        profile_name, profiles_dir=profiles_dir, secrets_path=secrets_path
    )
    _inject_env(profile)
    return profile
