"""Principal registry reader, solo derivation and mode (design D5, D6, D10).

Reads only the ``humans:`` block of the principal registry (validated against
``human-principals.schema.json``) and the *keys* of ``agents:`` (for the
namespace-collision check). It deliberately does not interpolate ``${VAR}``,
read a secrets file or validate agent fields: those belong to the coordinator's
loader and this reader must not become a second one.

Nothing here imports from the coordinator or opens a network connection.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SENTINEL_ID = "repository-default"
REGISTRY_ENV_VAR = "OWNERSHIP_REGISTRY_PATH"
HUMAN_SCHEMA_NAME = "human-principals.schema.json"
_DEFAULT_REGISTRY_LOCATIONS = ("agent-coordinator/agents.yaml", "agents.yaml")


class OwnershipConfigError(Exception):
    """An authority input is present but invalid. Callers must not fall back to solo."""

    def __init__(self, code: str, message: str, subject: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.subject = subject
        self.message = message


@dataclass(frozen=True)
class Principal:
    """A human (or git-derived / sentinel) principal."""

    id: str
    kind: str = "human"
    display_name: str = ""
    github: str | None = None
    email: str | None = None
    source: str = "registry"  # registry | git-config | sentinel


def _git(repo_root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def is_git_checkout(repo_root: Path) -> bool:
    return _git(repo_root, "rev-parse", "--git-dir") is not None


def default_repo_root() -> Path:
    """``git rev-parse --show-toplevel`` from the current directory, else the cwd."""
    top = _git(Path.cwd(), "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else Path.cwd().resolve()


def _inside(repo_root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True


def locate_registry(repo_root: Path, registry_field: str | None = None) -> Path | None:
    """Locate the principal registry (design D10).

    Order: ``OWNERSHIP_REGISTRY_PATH`` -> ``registry_field`` (the map's ``registry:``)
    -> ``agent-coordinator/agents.yaml`` -> ``agents.yaml`` -> ``None``. The two
    repository-relative locations are confined to ``repo_root``; the environment
    variable is operator-controlled and is not.
    """
    env = os.environ.get(REGISTRY_ENV_VAR)
    if env:
        path = Path(env)
        if not path.is_file():
            raise OwnershipConfigError(
                "registry_not_found",
                f"{REGISTRY_ENV_VAR}={env} does not name a file",
                env,
            )
        return path
    candidates: list[str] = []
    if registry_field:
        candidates.append(registry_field)
    candidates.extend(_DEFAULT_REGISTRY_LOCATIONS)
    for index, rel in enumerate(candidates):
        explicit = bool(registry_field) and index == 0
        path = repo_root / rel
        if not _inside(repo_root, path):
            if not explicit and not path.exists():
                continue
            raise OwnershipConfigError(
                "registry_outside_repo",
                f"registry '{rel}' resolves outside the repository root",
                rel,
            )
        if path.is_file():
            return path
        if explicit:
            raise OwnershipConfigError(
                "registry_not_found", f"registry '{rel}' does not exist", rel
            )
    return None


def _human_schema(repo_root: Path) -> dict[str, Any]:
    """The shipped schema: the skill's own copy, else the installed ``openspec/schemas``."""
    here = Path(__file__).resolve().parent.parent
    for candidate in (
        here / "install_assets" / "openspec" / "schemas" / HUMAN_SCHEMA_NAME,
        repo_root / "openspec" / "schemas" / HUMAN_SCHEMA_NAME,
    ):
        if candidate.is_file():
            loaded: dict[str, Any] = json.loads(candidate.read_text(encoding="utf-8"))
            return loaded
    raise OwnershipConfigError(
        "invalid_registry", f"{HUMAN_SCHEMA_NAME} is not installed", HUMAN_SCHEMA_NAME
    )


def read_registry(
    repo_root: Path, registry_field: str | None = None
) -> tuple[list[Principal], set[str], Path | None]:
    """Return ``(humans, agent_names, registry_path)``; only ``humans`` and ``agents`` keys."""
    path = locate_registry(repo_root, registry_field)
    if path is None:
        return [], set(), None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise OwnershipConfigError(
            "invalid_registry", f"cannot parse registry {path}: {exc}", str(path)
        ) from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise OwnershipConfigError(
            "invalid_registry", f"registry {path} is not a mapping", str(path)
        )
    agents_raw = raw.get("agents")
    agent_names = {str(k) for k in agents_raw} if isinstance(agents_raw, dict) else set()
    humans_raw = raw.get("humans") or {}
    if not isinstance(humans_raw, dict):
        raise OwnershipConfigError(
            "invalid_registry", f"'humans' in {path} must be a mapping", "humans"
        )
    validator = Draft202012Validator(_human_schema(repo_root))
    humans: list[Principal] = []
    for key, entry in humans_raw.items():
        human_id = str(key)
        errors = sorted(validator.iter_errors(entry), key=lambda e: list(e.absolute_path))
        if errors:
            raise OwnershipConfigError(
                "invalid_registry",
                f"human '{human_id}' in {path.name} is invalid: {errors[0].message}",
                human_id,
            )
        if human_id in agent_names:
            raise OwnershipConfigError(
                "invalid_registry",
                f"'{human_id}' is declared as both an agent and a human principal",
                human_id,
            )
        humans.append(
            Principal(
                id=human_id,
                kind="human",
                display_name=entry["display_name"],
                github=entry.get("github"),
                email=entry.get("email"),
                source="registry",
            )
        )
    return humans, agent_names, path


def load_human_principals(repo_root: Path, registry_field: str | None = None) -> list[Principal]:
    """The registry's human principals (empty when no registry exists)."""
    return read_registry(repo_root, registry_field)[0]


def derive_solo_principal(repo_root: Path, humans: list[Principal]) -> Principal:
    """The sole repository principal when there is no ownership map (design D5)."""
    if len(humans) == 1:
        return humans[0]
    if is_git_checkout(repo_root):
        email = _git(repo_root, "config", "user.email")
        name = _git(repo_root, "config", "user.name")
        if email:
            return Principal(
                id=f"git:{email}",
                display_name=name or email,
                email=email,
                source="git-config",
            )
        if name:
            return Principal(id=f"git:{name}", display_name=name, source="git-config")
    return Principal(id=SENTINEL_ID, display_name=SENTINEL_ID, source="sentinel")


def derive_mode(humans: list[Principal]) -> str:
    """``team`` iff two or more distinct human principals are declared (design D6)."""
    return "team" if len({h.id for h in humans}) >= 2 else "solo"
