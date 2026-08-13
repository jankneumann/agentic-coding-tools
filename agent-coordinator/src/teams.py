"""Crew manifest for supervisor-orchestrated dispatch.

Loads the crew manifest from ``teams.yaml``: the supervisor archetype at the
crew's apex, the archetype roster, and which vendors may fill each role.
Validates structure against a JSON Schema and cross-checks every referenced
archetype and vendor against the live ``archetypes.yaml`` roster so a stale
manifest fails loud instead of routing work to a nonexistent role or vendor.

This is the documented reader for the crew model. Before this repurposing,
``teams.yaml`` was a vestigial team-composition file that nothing in dispatch
consulted; it now declares the supervisor + archetype roster + vendor
eligibility that the supervisor-orchestration layer reads when it decomposes
an objective and assigns each work package a role and an eligible vendor pool.

Consumers:
- :func:`get_crew_manifest` — process-wide singleton accessor. By default it
  cross-validates the manifest against the loaded archetypes config and the
  provider model map (``agents_config``), which is the wiring that keeps the
  manifest honest.
- :meth:`CrewManifest.vendors_for` / :meth:`CrewManifest.get_role` — role and
  vendor-pool lookup for a dispatch target.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import validate

# JSON Schema for crew manifest validation. Structural only — cross-references
# to archetypes.yaml / providers are checked semantically in validate_against.
CREW_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["crew", "supervisor", "roster"],
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "crew": {"type": "string", "minLength": 1},
        "supervisor": {"type": "string", "minLength": 1},
        "roster": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["archetype", "vendors"],
                "properties": {
                    "archetype": {"type": "string", "minLength": 1},
                    "vendors": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


@dataclass
class RoleAssignment:
    """One roster entry: an archetype role and the vendors permitted to fill it."""

    archetype: str
    vendors: list[str]


@dataclass
class CrewManifest:
    """Crew manifest: supervisor apex + archetype roster + vendor eligibility.

    Loaded from ``teams.yaml``, validated structurally against
    :data:`CREW_SCHEMA` and semantically via :meth:`validate`. Optionally
    cross-validated against the live archetypes config with
    :meth:`validate_against`.
    """

    crew: str
    supervisor: str
    roster: list[RoleAssignment]
    schema_version: int = 1

    @classmethod
    def from_file(cls, path: Path) -> CrewManifest:
        """Load and validate a crew manifest from a YAML file.

        Raises:
            FileNotFoundError: If *path* does not exist.
            yaml.YAMLError: If the file is not valid YAML.
            jsonschema.ValidationError: If the data fails schema validation.
            ValueError: If semantic validation fails.
        """
        with open(path) as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError("Empty crew manifest file")

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrewManifest:
        """Create a validated manifest from a mapping.

        Raises:
            jsonschema.ValidationError: If the data fails schema validation.
            ValueError: If semantic validation fails.
        """
        validate(instance=data, schema=CREW_SCHEMA)

        roster = [
            RoleAssignment(
                archetype=entry["archetype"],
                vendors=list(entry["vendors"]),
            )
            for entry in data["roster"]
        ]

        manifest = cls(
            crew=data["crew"],
            supervisor=data["supervisor"],
            roster=roster,
            schema_version=data.get("schema_version", 1),
        )

        errors = manifest.validate()
        if errors:
            raise ValueError(
                f"Crew manifest validation failed: {'; '.join(errors)}"
            )

        return manifest

    def get_role(self, archetype: str) -> RoleAssignment | None:
        """Return the roster entry for *archetype*, or ``None`` if not listed."""
        for role in self.roster:
            if role.archetype == archetype:
                return role
        return None

    def vendors_for(self, archetype: str) -> list[str]:
        """Return the vendors permitted to fill *archetype*.

        Returns an empty list when the archetype is not in the roster.
        """
        role = self.get_role(archetype)
        return list(role.vendors) if role is not None else []

    def validate(self) -> list[str]:
        """Semantic validation the JSON Schema cannot express.

        Checks duplicate roster archetypes and that the declared supervisor
        appears in the roster. Returns a list of error messages (empty if OK).
        """
        errors: list[str] = []

        seen: set[str] = set()
        for role in self.roster:
            if role.archetype in seen:
                errors.append(f"Duplicate roster archetype: '{role.archetype}'")
            seen.add(role.archetype)

        if self.supervisor not in seen:
            errors.append(
                f"Supervisor archetype '{self.supervisor}' is not in the roster"
            )

        return errors

    def validate_against(
        self,
        *,
        known_archetypes: Mapping[str, bool],
        known_vendors: set[str],
    ) -> list[str]:
        """Cross-validate against the live archetypes + provider roster.

        Args:
            known_archetypes: Mapping of archetype name -> ``write_capable``
                flag, as loaded from ``archetypes.yaml``.
            known_vendors: The set of known provider ids from the provider
                model map.

        Checks that every roster archetype exists, every vendor is a known
        provider, and that the supervisor archetype exists AND is declared
        ``write_capable: false`` (a read-only orchestrator, mirroring the
        supervisor invariant enforced in ``agents_config``).

        Returns:
            A list of error messages (empty if the manifest is consistent).
        """
        errors: list[str] = []

        for role in self.roster:
            if role.archetype not in known_archetypes:
                errors.append(
                    f"Roster archetype '{role.archetype}' is not defined in "
                    f"archetypes.yaml"
                )
            unknown = [v for v in role.vendors if v not in known_vendors]
            if unknown:
                errors.append(
                    f"Roster archetype '{role.archetype}' lists unknown "
                    f"vendors: {unknown}"
                )

        if self.supervisor not in known_archetypes:
            errors.append(
                f"Supervisor archetype '{self.supervisor}' is not defined in "
                f"archetypes.yaml"
            )
        elif known_archetypes[self.supervisor]:
            errors.append(
                f"Supervisor archetype '{self.supervisor}' must be "
                f"write_capable: false (a read-only orchestrator that "
                f"delegates every change)"
            )

        return errors


# Global config instance
_crew_manifest: CrewManifest | None = None


def get_crew_manifest(
    path: Path | None = None,
    *,
    cross_validate: bool = True,
) -> CrewManifest:
    """Get the global crew manifest (lazy singleton).

    Loads from *path* (default: ``teams.yaml`` beside the coordinator package)
    on first call. When *cross_validate* is true (the default), the manifest is
    checked against the loaded ``archetypes.yaml`` roster and the provider model
    map — this is the wiring that keeps the crew model honest, failing loud on a
    stale archetype or vendor reference.

    Args:
        path: Optional path to the crew manifest YAML file.
        cross_validate: Whether to cross-check the manifest against the live
            archetypes config and provider map.

    Returns:
        The global :class:`CrewManifest` instance.

    Raises:
        ValueError: If cross-validation finds an undefined archetype/vendor or
            a write-capable supervisor.
    """
    global _crew_manifest
    if _crew_manifest is None:
        if path is None:
            path = Path(__file__).parent.parent / "teams.yaml"
        manifest = CrewManifest.from_file(path)
        if cross_validate:
            from src.agents_config import (
                get_provider_model_map,
                load_archetypes_config,
            )

            archetypes = load_archetypes_config()
            known_archetypes = {
                name: cfg.write_capable for name, cfg in archetypes.items()
            }
            providers = set((get_provider_model_map().get("providers") or {}).keys())
            errors = manifest.validate_against(
                known_archetypes=known_archetypes,
                known_vendors=providers,
            )
            if errors:
                raise ValueError(
                    f"Crew manifest cross-validation failed: {'; '.join(errors)}"
                )
        _crew_manifest = manifest
    return _crew_manifest


def reset_crew_manifest() -> None:
    """Reset the global crew manifest. Useful for testing."""
    global _crew_manifest
    _crew_manifest = None
