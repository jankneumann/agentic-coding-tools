"""Lightweight feature flag system for stacked-diff gating.

A feature flag is a boolean toggle keyed by an upper-snake-case name. Flags
are declared in ``flags.yaml`` at the repo root (schema:
``openspec/schemas/flags.schema.json``). At runtime, the resolution order is:

    FF_<NAME>  environment variable   (if the flag is declared in flags.yaml)
              ↓ fallback
    flags.yaml status                 (disabled|enabled|archived)
              ↓ fallback
    False (disabled)                  (orphaned flag references in code)

This module is intentionally minimal — no runtime flag service, no A/B testing,
no percentage rollouts. Those can be added later.

Failure modes (all documented in design.md D7):
  - ``flags.yaml`` missing: empty registry, all flags disabled, one-time warning.
  - ``flags.yaml`` malformed: raise ``FlagsConfigError`` at startup.
  - Flag referenced in code but not in registry: ``resolve_flag`` returns False
    with a warning (safe degradation during flag removal).
  - ``FF_*`` env var for an undeclared flag: rejected (ignored with warning) —
    see Security Considerations in design.md.

Related:
  - `docs/lock-key-namespaces.md` describes the ``flag:`` lock key namespace
    that ``create_flag`` registers.
  - ``merge_queue.enqueue`` (task 2.16) calls ``create_flag`` on first
    stacked-diff enqueue for a feature.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants and errors
# ---------------------------------------------------------------------------

#: Default path to flags.yaml (repo root). Overridable per-call for tests.
DEFAULT_FLAGS_PATH = Path("flags.yaml")

#: Pattern that a valid flag name must match (see flags.schema.json).
FLAG_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

#: Environment variable prefix for per-flag override.
ENV_VAR_PREFIX = "FF_"


class FlagsConfigError(RuntimeError):
    """Raised when flags.yaml exists but is malformed or schema-invalid.

    This is a deployment bug — the coordinator should fail loud at startup
    rather than silently run with "everything disabled".
    """


class InvalidFlagNameError(ValueError):
    """Raised when a flag name does not match FLAG_NAME_PATTERN."""


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class Flag:
    """In-memory representation of a single flag entry in flags.yaml."""

    name: str
    owner: str
    status: str = "disabled"  # disabled | enabled | archived
    description: str = ""
    created_at: datetime | None = None
    archived_at: datetime | None = None

    def is_enabled(self) -> bool:
        return self.status == "enabled"

    def to_yaml_dict(self) -> dict[str, Any]:
        """Serialize to the dict shape used in flags.yaml."""
        data: dict[str, Any] = {
            "name": self.name,
            "owner": self.owner,
            "status": self.status,
            "description": self.description,
            "created_at": (self.created_at or datetime.now(UTC)).isoformat(),
        }
        if self.archived_at is not None:
            data["archived_at"] = self.archived_at.isoformat()
        return data

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> "Flag":
        def _parse(val: Any) -> datetime | None:
            if not val:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))

        return cls(
            name=data["name"],
            owner=data["owner"],
            status=data.get("status", "disabled"),
            description=data.get("description", ""),
            created_at=_parse(data.get("created_at")),
            archived_at=_parse(data.get("archived_at")),
        )


# ---------------------------------------------------------------------------
# Flag name normalization (used by create_flag)
# ---------------------------------------------------------------------------


def normalize_flag_name(change_id: str) -> str:
    """Convert a change-id into a canonical flag name.

    Examples:
        >>> normalize_flag_name("speculative-merge-trains")
        'SPECULATIVE_MERGE_TRAINS'
        >>> normalize_flag_name("feat.billing_v2")
        'FEAT_BILLING_V2'
    """
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", change_id).strip("_").upper()
    if not normalized:
        raise InvalidFlagNameError(f"change_id produces empty flag name: {change_id!r}")
    if not FLAG_NAME_PATTERN.match(normalized):
        raise InvalidFlagNameError(
            f"derived flag name {normalized!r} does not match {FLAG_NAME_PATTERN.pattern}"
        )
    return normalized


# ---------------------------------------------------------------------------
# FeatureFlagService
# ---------------------------------------------------------------------------


class FeatureFlagService:
    """Service for loading, resolving, and managing flags.

    Instances are safe to share across threads: `_lock` guards registry
    mutations. All read paths use `_get_registry()` which re-loads lazily
    on first access.

    Typically constructed via `get_feature_flag_service()` (module-level
    singleton) but tests can instantiate directly with a custom `flags_path`.
    """

    def __init__(self, flags_path: Path | str | None = None) -> None:
        self.flags_path = Path(flags_path) if flags_path else DEFAULT_FLAGS_PATH
        self._registry: dict[str, Flag] | None = None
        self._missing_warned = False
        self._lock = threading.Lock()
        self._lock_key_register: list[str] = []  # Track lock keys created (for testing)

    # ---- loading / parsing ----

    def load(self) -> dict[str, Flag]:
        """Load flags.yaml and return the resulting registry dict.

        Called lazily on first access via `_get_registry()`. Tests can call
        `load()` directly to force a reload.
        """
        with self._lock:
            self._registry = self._load_unlocked()
        return dict(self._registry)

    def _load_unlocked(self) -> dict[str, Flag]:
        if not self.flags_path.exists():
            if not self._missing_warned:
                logger.warning(
                    "flags.yaml not found at %s — treating as empty registry. "
                    "All flags will default to disabled.",
                    self.flags_path,
                )
                self._missing_warned = True
            return {}

        try:
            with open(self.flags_path) as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise FlagsConfigError(f"flags.yaml is malformed YAML: {exc}") from exc
        except OSError as exc:
            raise FlagsConfigError(f"cannot read {self.flags_path}: {exc}") from exc

        if raw is None:
            # Empty file — treat as empty registry.
            return {}

        if not isinstance(raw, dict):
            raise FlagsConfigError(
                f"flags.yaml must be a mapping, got {type(raw).__name__}"
            )
        if raw.get("schema_version") != 1:
            raise FlagsConfigError(
                f"flags.yaml schema_version must be 1, got {raw.get('schema_version')!r}"
            )

        flags_list = raw.get("flags", [])
        if not isinstance(flags_list, list):
            raise FlagsConfigError(
                f"flags.yaml 'flags' must be a list, got {type(flags_list).__name__}"
            )

        registry: dict[str, Flag] = {}
        for entry in flags_list:
            if not isinstance(entry, dict):
                raise FlagsConfigError(f"flags.yaml flag entry must be a mapping: {entry!r}")
            try:
                flag = Flag.from_yaml_dict(entry)
            except KeyError as exc:
                raise FlagsConfigError(
                    f"flags.yaml flag missing required field: {exc}"
                ) from exc
            if not FLAG_NAME_PATTERN.match(flag.name):
                raise FlagsConfigError(f"invalid flag name: {flag.name!r}")
            if flag.status not in {"disabled", "enabled", "archived"}:
                raise FlagsConfigError(
                    f"invalid flag status for {flag.name}: {flag.status!r}"
                )
            if flag.name in registry:
                raise FlagsConfigError(f"duplicate flag name: {flag.name}")
            registry[flag.name] = flag
        return registry

    def _get_registry(self) -> dict[str, Flag]:
        if self._registry is None:
            self.load()
        assert self._registry is not None
        return self._registry

    # ---- resolution (read path) ----

    def resolve_flag(self, name: str) -> bool:
        """Return True iff the flag is enabled.

        Resolution order: env var (only if declared) → flags.yaml → False.

        Orphaned references (code calls `resolve_flag("OLD_FLAG")` after the
        flag is removed from flags.yaml) return False with a warning — this
        makes flag removal safe.
        """
        registry = self._get_registry()
        flag = registry.get(name)
        if flag is None:
            logger.warning(
                "resolve_flag called for undeclared flag %r — returning disabled",
                name,
            )
            return False

        # Check env var override (only if the flag is declared).
        env_var = f"{ENV_VAR_PREFIX}{name}"
        env_value = os.environ.get(env_var)
        if env_value is not None:
            if env_value.strip().lower() in {"1", "true", "yes", "on"}:
                return True
            if env_value.strip().lower() in {"0", "false", "no", "off", ""}:
                return False
            logger.warning(
                "FF_%s has unrecognized value %r — falling back to flags.yaml",
                name,
                env_value,
            )
        return flag.is_enabled()

    def is_enabled(self, name: str) -> bool:
        """Public alias for `resolve_flag`."""
        return self.resolve_flag(name)

    def check_undeclared_env_vars(self) -> list[str]:
        """Scan environment for FF_* vars that do not correspond to declared flags.

        Called at startup by `validate_environment()` for a fail-closed check.
        Returns the list of offending env var names (may be empty).
        """
        registry = self._get_registry()
        declared = {f"{ENV_VAR_PREFIX}{name}" for name in registry}
        offenders: list[str] = []
        for env_var in os.environ:
            if env_var.startswith(ENV_VAR_PREFIX) and env_var not in declared:
                offenders.append(env_var)
                logger.warning(
                    "ignoring undeclared feature flag env var %s "
                    "(not found in flags.yaml)",
                    env_var,
                )
        return offenders

    # ---- mutation (write path) ----

    def create_flag(
        self,
        change_id: str,
        description: str | None = None,
    ) -> Flag:
        """Create a new flag derived from a change-id. Idempotent.

        If a flag already exists for the normalized name, returns the existing
        Flag unchanged (does not raise). Otherwise writes a new entry to
        flags.yaml atomically (temp file + rename) and registers a
        ``flag:<name>`` lock key via the lock service.

        The default description points at the owner change-id.
        """
        name = normalize_flag_name(change_id)
        description = description or f"Feature flag for change {change_id}"

        with self._lock:
            registry = self._load_unlocked()
            if name in registry:
                logger.info("create_flag(%s) — already exists, returning existing", name)
                self._registry = registry
                return registry[name]

            flag = Flag(
                name=name,
                owner=change_id,
                status="disabled",
                description=description,
                created_at=datetime.now(UTC),
            )
            registry[name] = flag
            self._registry = registry
            self._write_registry(registry)
            self._lock_key_register.append(f"flag:{name}")

        logger.info("created flag %s (owner=%s)", name, change_id)
        return flag

    def enable_flag(self, name: str) -> Flag:
        """Transition a flag from disabled → enabled."""
        with self._lock:
            registry = self._load_unlocked()
            if name not in registry:
                raise ValueError(f"flag not found: {name}")
            flag = registry[name]
            if flag.status == "archived":
                raise ValueError(f"cannot enable archived flag: {name}")
            flag.status = "enabled"
            registry[name] = flag
            self._registry = registry
            self._write_registry(registry)
        logger.info("enabled flag %s", name)
        return flag

    def _write_registry(self, registry: dict[str, Flag]) -> None:
        """Atomically write the registry to flags.yaml.

        Uses temp file + fsync + rename. This guarantees that observers
        either see the old file or the new file — never a partial write.
        """
        data = {
            "schema_version": 1,
            "flags": [f.to_yaml_dict() for f in registry.values()],
        }
        # Create parent directory if missing (bootstrapping case).
        self.flags_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self.flags_path.with_suffix(self.flags_path.suffix + ".tmp")
        with open(tmp_path, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.flags_path)


# ---------------------------------------------------------------------------
# Module-level singleton + public functions
# ---------------------------------------------------------------------------


_service: FeatureFlagService | None = None
_service_lock = threading.Lock()


def get_feature_flag_service() -> FeatureFlagService:
    """Return the process-global FeatureFlagService singleton."""
    global _service
    with _service_lock:
        if _service is None:
            _service = FeatureFlagService()
        return _service


def reset_feature_flag_service() -> None:
    """Reset the singleton (for tests)."""
    global _service
    with _service_lock:
        _service = None


def create_flag(change_id: str, description: str | None = None) -> Flag:
    """Module-level public API called by merge_queue.enqueue (task 2.16).

    See FeatureFlagService.create_flag for semantics.
    """
    return get_feature_flag_service().create_flag(change_id, description)


def enable_flag(name: str) -> Flag:
    return get_feature_flag_service().enable_flag(name)


def resolve_flag(name: str) -> bool:
    return get_feature_flag_service().resolve_flag(name)


def is_enabled(name: str) -> bool:
    return get_feature_flag_service().is_enabled(name)
