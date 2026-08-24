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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import validate

# JSON Schema for crew manifest validation. Structural only — cross-references
# to archetypes.yaml / providers are checked semantically in validate_against.
CREW_SCHEMA: dict[str, Any] = {
    # 2020-12, matching every other schema in this repo. The draft-07 URI this
    # previously carried was also spelled with https://, which jsonschema
    # cannot resolve to a metaschema — it fell back to the latest draft and
    # emitted a DeprecationWarning that is scheduled to become a hard error.
    "$schema": "https://json-schema.org/draft/2020-12/schema",
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


@dataclass(frozen=True)
class AgentClaimant:
    """A registered agent, reduced to what decides whether it can claim a role.

    Built from ``agents.yaml`` entries. ``vendor`` is the agent's ``type``
    (``claude_code``, ``codex``, …) — the same vocabulary teams.yaml rosters
    use. ``archetypes`` is the agent's declared list; an EMPTY list is a
    wildcard, not "claims nothing", mirroring ``claim_task``:

        OR p_agent_archetypes IS NULL  -- agents without declared archetypes
                                       -- can claim anything
    """

    name: str
    vendor: str
    archetypes: tuple[str, ...] = ()

    def can_claim(self, archetype: str) -> bool:
        """True when this agent would match a task requiring *archetype*."""
        return not self.archetypes or archetype in self.archetypes


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
        agents: Sequence[AgentClaimant] | None = None,
    ) -> list[str]:
        """Cross-validate against the live archetypes + provider roster.

        Args:
            known_archetypes: Mapping of archetype name -> ``write_capable``
                flag, as loaded from ``archetypes.yaml``.
            known_vendors: The set of known provider ids from the provider
                model map.
            agents: Optional registered agents, as :class:`AgentClaimant`
                records derived from ``agents.yaml``. When supplied, every
                roster role is additionally checked for *claimability*. Omit
                it to skip that check (structure-only validation).

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

        if agents is not None:
            errors.extend(self._claimability_errors(agents))

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

    def _claimability_errors(
        self, agents: Sequence[AgentClaimant]
    ) -> list[str]:
        """Every rostered role must have at least one agent able to claim it.

        The existing cross-checks confirm a roster archetype *exists* and its
        vendors are real providers. Neither implies anyone can take the work:
        ``claim_task`` matches on the agent's own declared ``archetypes``, so a
        role that no registered agent declares is unclaimable and its tasks sit
        pending indefinitely — no error, no rejection, just silence (#390).

        A vendor is only eligible for a role if the roster lists it, so the
        check is per-role over that role's vendor pool. Reported errors name
        the vendor pool and the agents in it, because the fix is always one of
        two edits: widen the pool in teams.yaml, or add the archetype to an
        agent in agents.yaml.
        """
        errors: list[str] = []
        for role in self.roster:
            eligible = [a for a in agents if a.vendor in role.vendors]
            claimants = [a.name for a in eligible if a.can_claim(role.archetype)]
            if claimants:
                continue
            if not eligible:
                detail = (
                    f"no registered agent has a vendor type in "
                    f"{sorted(role.vendors)}"
                )
            else:
                detail = (
                    f"eligible agents {sorted(a.name for a in eligible)} do "
                    f"not declare it"
                )
            errors.append(
                f"Roster archetype '{role.archetype}' is unclaimable: "
                f"{detail}. A task requiring it would stay pending forever. "
                f"Add '{role.archetype}' to an agent's archetypes in "
                f"agents.yaml, or widen the role's vendors in teams.yaml"
            )
        return errors


# Global config instance
_crew_manifest: CrewManifest | None = None
# Tracks whether the cached manifest has passed cross-validation, so a
# `cross_validate=True` caller is never served an unchecked cached object.
_crew_manifest_cross_validated: bool = False


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
    global _crew_manifest, _crew_manifest_cross_validated
    if _crew_manifest is None:
        if path is None:
            path = Path(__file__).parent.parent / "teams.yaml"
        _crew_manifest = CrewManifest.from_file(path)
        _crew_manifest_cross_validated = False

    # Cross-validate whenever the caller asks for it, not only on the call that
    # happened to populate the singleton. Gating this on `_crew_manifest is
    # None` meant one early `get_crew_manifest(p, cross_validate=False)` cached
    # an unchecked manifest, and every later default call returned it while
    # believing it had been validated — the fail-loud guarantee silently
    # disabled for the life of the process.
    if cross_validate and not _crew_manifest_cross_validated:
        from src.agents_config import (
            get_agents_config,
            get_provider_model_map,
            load_archetypes_config,
        )

        archetypes = load_archetypes_config()
        known_archetypes = {
            name: cfg.write_capable for name, cfg in archetypes.items()
        }
        providers = set((get_provider_model_map().get("providers") or {}).keys())
        # agents.yaml is what decides claimability — the roster can name a role
        # every part of the config agrees exists and still have nobody able to
        # take it (#390), so the registered agents are part of cross-validation.
        agents = [
            AgentClaimant(
                name=entry.name,
                vendor=entry.type,
                archetypes=tuple(entry.archetypes),
            )
            for entry in get_agents_config()
        ]
        errors = _crew_manifest.validate_against(
            known_archetypes=known_archetypes,
            known_vendors=providers,
            agents=agents,
        )
        if errors:
            # Do not cache a manifest that failed: a retry must re-raise rather
            # than hand back the bad object.
            _crew_manifest = None
            raise ValueError(
                f"Crew manifest cross-validation failed: {'; '.join(errors)}"
            )
        _crew_manifest_cross_validated = True
    return _crew_manifest


def reset_crew_manifest() -> None:
    """Reset the global crew manifest. Useful for testing."""
    global _crew_manifest, _crew_manifest_cross_validated
    _crew_manifest = None
    _crew_manifest_cross_validated = False
