"""Human principals in ``agents.yaml`` (agent-identity spec, change ownership-map).

Covers the ``humans:`` block: schema, the agent/human namespace collision check,
``load_human_principals()``, the guarantee that ``load_agents_config()`` is
unchanged by the block, and the pin between the inline ``HUMAN_PRINCIPAL_SCHEMA``
and the canonical ``openspec/schemas/human-principals.schema.json`` (design D2).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import ValidationError
from openspec_paths import repo_root_from

from src.agents_config import (
    HUMAN_PRINCIPAL_SCHEMA,
    HumanEntry,
    get_api_key_identities,
    get_dispatch_configs,
    load_agents_config,
    load_human_principals,
)
from tests.test_profile_sync import FakeAudit, FakeDb

REPO_ROOT = repo_root_from(__file__, 2)
SCHEMA_JSON = REPO_ROOT / "openspec" / "schemas" / "human-principals.schema.json"
METADATA_KEYS = ("$schema", "$id", "title", "description")

AGENTS_ONLY = """\
credential_vendors: []
agents:
  claude-local:
    type: claude_code
    profile: claude_code_cli
    trust_level: 3
    transport: mcp
    capabilities: [lock, queue, memory]
    description: Test local agent
"""

HUMANS_BLOCK = """\
humans:
  jan:
    display_name: "Jan Neumann"
    github: jankneumann
    email: jan@example.org
    domains: [agent-coordinator, skills]
    availability:
      timezone: Europe/Berlin
      hours: "09:00-18:00"
      days: [mon, tue, wed, thu, fri]
    description: Repository maintainer
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "agents.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _strings(obj: Any) -> Iterator[str]:
    """Every string reachable in ``obj`` (dataclasses, mappings, sequences)."""
    if isinstance(obj, str):
        yield obj
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from _strings(getattr(obj, f.name))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from _strings(key)
            yield from _strings(value)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            yield from _strings(item)
    elif hasattr(obj, "__dict__"):
        yield from _strings(vars(obj))


class TestHumansBlock:
    def test_humans_block_validates_and_loads(self, tmp_path: Path) -> None:
        path = _write(tmp_path, AGENTS_ONLY + HUMANS_BLOCK)
        humans = load_human_principals(path)
        assert len(humans) == 1
        jan = humans[0]
        assert isinstance(jan, HumanEntry)
        assert jan.name == "jan"
        assert jan.display_name == "Jan Neumann"
        assert jan.github == "jankneumann"
        assert jan.email == "jan@example.org"
        assert jan.domains == ["agent-coordinator", "skills"]
        assert jan.availability == {
            "timezone": "Europe/Berlin",
            "hours": "09:00-18:00",
            "days": ["mon", "tue", "wed", "thu", "fri"],
        }
        assert jan.description == "Repository maintainer"

    def test_minimal_entry_defaults(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path, AGENTS_ONLY + 'humans:\n  kim:\n    display_name: "Kim"\n'
        )
        (kim,) = load_human_principals(path)
        assert kim.name == "kim"
        assert kim.github is None
        assert kim.email is None
        assert kim.domains == []
        assert kim.availability == {}
        assert kim.description == ""

    def test_missing_display_name_rejected_naming_entry_and_field(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path, AGENTS_ONLY + "humans:\n  jan:\n    github: jankneumann\n")
        with pytest.raises(ValidationError) as excinfo:
            load_agents_config(path, secrets_path=tmp_path / "none")
        assert "display_name" in excinfo.value.message
        assert list(excinfo.value.absolute_path) == ["humans", "jan"]

    def test_unknown_field_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            AGENTS_ONLY + 'humans:\n  jan:\n    display_name: "Jan"\n    trust_level: 3\n',
        )
        with pytest.raises(ValidationError, match="trust_level"):
            load_agents_config(path, secrets_path=tmp_path / "none")

    def test_human_id_must_follow_the_slug_pattern(self, tmp_path: Path) -> None:
        path = _write(tmp_path, AGENTS_ONLY + 'humans:\n  Jan_N:\n    display_name: "Jan"\n')
        with pytest.raises(ValidationError):
            load_agents_config(path, secrets_path=tmp_path / "none")

    def test_human_id_colliding_with_agent_name_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            AGENTS_ONLY + 'humans:\n  claude-local:\n    display_name: "Not an agent"\n',
        )
        with pytest.raises(ValueError, match="claude-local") as excinfo:
            load_agents_config(path, secrets_path=tmp_path / "none")
        message = str(excinfo.value)
        assert "agent" in message
        assert "human" in message

    def test_collision_is_also_detected_by_load_human_principals(
        self, tmp_path: Path
    ) -> None:
        path = _write(
            tmp_path,
            AGENTS_ONLY + 'humans:\n  claude-local:\n    display_name: "Not an agent"\n',
        )
        with pytest.raises(ValueError, match="claude-local"):
            load_human_principals(path)


class TestRegistryWithoutHumansUnchanged:
    def test_no_humans_block_loads_empty_list(self, tmp_path: Path) -> None:
        path = _write(tmp_path, AGENTS_ONLY)
        assert load_human_principals(path) == []

    def test_load_agents_config_identical_with_and_without_block(
        self, tmp_path: Path
    ) -> None:
        without = load_agents_config(
            _write(tmp_path, AGENTS_ONLY), secrets_path=tmp_path / "none"
        )
        with_block = load_agents_config(
            _write(tmp_path, AGENTS_ONLY + HUMANS_BLOCK), secrets_path=tmp_path / "none"
        )
        assert with_block == without
        assert [a.name for a in with_block] == ["claude-local"]


class TestHumanNeverProjectedAsAgent:
    """Spec scenario: Human principal declared without agent projection."""

    async def test_no_projection_output_contains_the_human_id(
        self, tmp_path: Path
    ) -> None:
        from openbao_credentials import project_principals

        from src.agents_config import sync_profiles

        path = _write(tmp_path, AGENTS_ONLY + HUMANS_BLOCK)
        agents = load_agents_config(path, secrets_path=tmp_path / "none")

        db = FakeDb([])
        await sync_profiles(agents, db=db, audit=FakeAudit())
        topology = project_principals(
            {"credential_vendors": [], "agents": {a.name: {} for a in agents}}
        )

        outputs = {
            "agents": agents,
            "profile rows": db.rows,
            "assignments": db.assignments,
            "identities": get_api_key_identities(agents),
            "dispatch configs": get_dispatch_configs(agents),
            "principals": topology,
        }
        for label, output in outputs.items():
            assert "jan" not in set(_strings(output)), label

        (jan,) = load_human_principals(path)
        assert jan.name == "jan"


class TestSchemaMirror:
    """Spec scenario: Schema mirror pinned (design D2)."""

    def test_inline_schema_equals_canonical_json_minus_metadata(self) -> None:
        canonical = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
        stripped = {k: v for k, v in canonical.items() if k not in METADATA_KEYS}
        assert stripped == HUMAN_PRINCIPAL_SCHEMA

    def test_agents_schema_references_the_inline_human_schema(self) -> None:
        from src.agents_config import AGENTS_SCHEMA

        humans = AGENTS_SCHEMA["properties"]["humans"]
        assert humans["type"] == "object"
        assert humans["additionalProperties"] == HUMAN_PRINCIPAL_SCHEMA
        assert "humans" not in AGENTS_SCHEMA.get("required", [])

    def test_principal_id_key_constraint_matches_the_owners_schema(self) -> None:
        """The ``humans:`` key constraint lives outside the mirrored entry schema.

        Pin it to ``owners.schema.json`` ``$defs.PrincipalId``, which the skills-side
        reader validates human ids against, so the two readers accept the same ids.
        """
        from src.agents_config import AGENTS_SCHEMA, PRINCIPAL_ID_PATTERN

        owners_schema = json.loads(
            (REPO_ROOT / "openspec" / "schemas" / "owners.schema.json").read_text(
                encoding="utf-8"
            )
        )
        principal_id = owners_schema["$defs"]["PrincipalId"]
        names = AGENTS_SCHEMA["properties"]["humans"]["propertyNames"]
        assert principal_id["pattern"] == PRINCIPAL_ID_PATTERN == names["pattern"]
        assert principal_id["maxLength"] == names["maxLength"] == 64
