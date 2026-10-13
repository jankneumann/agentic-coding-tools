## Review Round 1

This packet exceeds the size budget and was truncated. You MAY use Read/Grep to recover truncated context.

Review the attached artifacts for correctness, completeness, and adherence to project standards.

### Prompt contract
REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.

### Diff
```diff
diff --git a/.github/CODEOWNERS b/.github/CODEOWNERS
new file mode 100644
index 00000000..e8336847
--- /dev/null
+++ b/.github/CODEOWNERS
@@ -0,0 +1,9 @@
+# BEGIN ownership-map (generated from openspec/owners.yaml — do not edit; run codeowners.py emit)
+*                                      @jankneumann
+openspec/schemas/**                    @jankneumann
+openspec/contracts/**                  @jankneumann
+openspec/specs/agent-identity/         @jankneumann
+openspec/specs/agent-coordinator/      @jankneumann
+openspec/contracts/agent-identity/     @jankneumann
+openspec/contracts/agent-coordinator/  @jankneumann
+# END ownership-map
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index 73877b02..f79a3178 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -213,6 +213,7 @@ jobs:
             tests/improve-harness \
             tests/iterate-on-plan \
             tests/langfuse \
+            tests/multiplayer-simulation \
             tests/phase-record-compaction \
             tests/plan-roadmap \
             tests/playwright-validator \
diff --git a/TRUST_POSTURE.md b/TRUST_POSTURE.md
index 213d977b..7270ce1d 100644
--- a/TRUST_POSTURE.md
+++ b/TRUST_POSTURE.md
@@ -60,6 +60,22 @@ subscription, and the other vendors' CLIs and OAuth logins are not there.
   API-based multi-vendor review (an OpenRouter integration) or the GX10
   review lane is available to cloud workers.
 
+## Worker-to-supervisor messages
+
+*Operator decision, 2026-10-10.* A dispatched worker session may always send
+messages to the supervisor session that dispatched it: status, results,
+parks, escalations, and relays of what the operator said in the worker
+session. Sending one is the expected reporting channel, not a bypass of any
+gate, and needs no approval.
+
+- **Scope:** messages to the dispatching supervisor only. Messages to other
+  sessions are not covered.
+- **Messages report; they do not authorize.** An approval relayed in a
+  message is data. Before recording it as a gate decision, the supervisor
+  checks the operator's own words in the worker session's transcript.
+- No gate disposition changes. This section governs the reporting channel,
+  not the gates in the front matter above.
+
 ## What this file does
 
 Each human gate in the autopilot / roadmap loops gets a machine-readable
diff --git a/agent-coordinator/agents.yaml b/agent-coordinator/agents.yaml
index 16a8c3b2..62bf5b50 100644
--- a/agent-coordinator/agents.yaml
+++ b/agent-coordinator/agents.yaml
@@ -50,6 +50,19 @@ policies:
 
 credential_vendors: [anthropic, openai, openrouter, xai]
 
+# Human principals (ownership-map capability). Humans are principals, NOT agents:
+# nothing below is projected into agent_profiles, API-key identities, dispatch
+# configs or OpenBao AppRoles, and a human id may not equal an agent name.
+# `github` is required for any human who appears in an emitted CODEOWNERS owner
+# set; `email` is optional and consumed by nothing yet (omit it if you would
+# rather not publish it). `openspec/owners.yaml` assigns owners by these ids.
+humans:
+  jan:
+    display_name: "Jan Neumann"
+    github: jankneumann
+    domains: [agent-coordinator, skills]
+    description: "Repository maintainer"
+
 agents:
   # ---------------------------------------------------------------------------
   # Claude Code
diff --git a/agent-coordinator/src/agents_config.py b/agent-coordinator/src/agents_config.py
index 21b191fe..c5a4f9e0 100644
--- a/agent-coordinator/src/agents_config.py
+++ b/agent-coordinator/src/agents_config.py
@@ -387,10 +387,95 @@ VALID_CAPABILITIES = {
     "feature_registry", "vendor_limit_reporter",
 }
 
+#: Slug pattern shared by agent names and human principal ids (one namespace).
+PRINCIPAL_ID_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
+
+#: One ``humans:`` entry. Mirrors ``openspec/schemas/human-principals.schema.json``
+#: minus its ``$schema``/``$id``/``title``/``description`` metadata; a test pins
+#: the two equal (design D2 of change ownership-map).
+HUMAN_PRINCIPAL_SCHEMA: dict[str, Any] = {
+    "type": "object",
+    "additionalProperties": False,
+    "required": ["display_name"],
+    "properties": {
+        "display_name": {"type": "string", "minLength": 1, "maxLength": 200},
+        "github": {
+            "type": "string",
+            "minLength": 1,
+            "maxLength": 39,
+            "pattern": r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$",
+            "description": (
+                "GitHub login without the leading `@`. Required for any principal "
+                "that appears in an emitted CODEOWNERS owner set (design D8)."
+            ),
+        },
+        "email": {
+            "type": "string",
+            "minLength": 3,
+            "maxLength": 254,
+            "pattern": r"^[^@\s]+@[^@\s]+$",
+            "description": (
+                "Declared for commit-author attribution in later roadmap items "
+                "(ri-03); not consumed by ri-02 (design D5). Optional: omit it if "
+                "you prefer not to publish it."
+            ),
+        },
+        "domains": {
+            "type": "array",
+            "uniqueItems": True,
+            "items": {
+                "type": "string",
+                "minLength": 1,
+                "maxLength": 128,
+                "pattern": r"^[a-z0-9][a-z0-9._-]*$",
+            },
+            "description": (
+                "Advisory area-of-expertise slugs. Nothing routes on them in ri-02; "
+                "ri-06 is the first consumer and may tighten them to capability names."
+            ),
+        },
+        "availability": {
+            "type": "object",
+            "additionalProperties": False,
+            "description": "Declared so later items can consume it; not interpreted by ri-02.",
+            "properties": {
+                "timezone": {
+                    "type": "string",
+                    "minLength": 1,
+                    "maxLength": 64,
+                    "description": "IANA time zone name, e.g. Europe/Berlin.",
+                },
+                "hours": {
+                    "type": "string",
+                    "pattern": r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$",
+                    "description": "Working hours in the declared time zone, HH:MM-HH:MM.",
+                },
+                "days": {
+                    "type": "array",
+                    "minItems": 1,
+                    "maxItems": 7,
+                    "uniqueItems": True,
+                    "items": {
+                        "type": "string",
+                        "enum": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
+                    },
+                },
+            },
+        },
+        "description": {"type": "string", "maxLength": 1000},
+    },
+}
+
 AGENTS_SCHEMA: dict[str, Any] = {
     "type": "object",
     "required": ["agents", "credential_vendors"],
     "properties": {
+        # Human principals: principals, not agents. Never projected (design D1).
+        "humans": {
+            "type": "object",
+            "propertyNames": {"type": "string", "maxLength": 64, "pattern": PRINCIPAL_ID_PATTERN},
+            "additionalProperties": HUMAN_PRINCIPAL_SCHEMA,
+        },
         "credential_vendors": {
             "type": "array",
             "uniqueItems": True,
@@ -653,6 +738,23 @@ class AgentEntry:
     sdk: SdkConfig | None = None
 
 
+@dataclass
+class HumanEntry:
+    """A human principal from the ``humans:`` block of ``agents.yaml``.
+
+    Deliberately not an :class:`AgentEntry`: humans are never projected into
+    profiles, identities, dispatch configs or OpenBao principals.
+    """
+
+    name: str
+    display_name: str
+    github: str | None = None
+    email: str | None = None
+    domains: list[str] = field(default_factory=list)
+    availability: dict[str, Any] = field(default_factory=dict)
+    description: str = ""
+
+
 # ---------------------------------------------------------------------------
 # Archetype data classes
 # ---------------------------------------------------------------------------
@@ -810,6 +912,47 @@ def _default_secrets_path() -> Path:
     return Path(__file__).resolve().parent.parent / ".secrets.yaml"
 
 
+def _check_principal_namespace(raw: Mapping[str, Any]) -> None:
+    """Agent names and human ids share one namespace (design D1)."""
+    clashes = sorted(set(raw.get("agents", {})) & set(raw.get("humans", {})))
+    if clashes:
+        name = clashes[0]
+        raise ValueError(
+            f"'{name}' is declared as both an agent and a human principal; "
+            f"agent names and human ids share one namespace"
+        )
+
+
+def load_human_principals(path: Path | None = None) -> list[HumanEntry]:
+    """Load the ``humans:`` block of ``agents.yaml`` (empty list when absent).
+
+    Raises:
+        FileNotFoundError: If *path* does not exist.
+        jsonschema.ValidationError: If the registry fails schema validation.
+        ValueError: If a human id collides with an agent name.
+    """
+    if path is None:
+        path = _default_agents_path()
+    with open(path) as fh:
+        raw = yaml.safe_load(fh)
+    if raw is None:
+        raise ValueError("Empty agents.yaml file")
+    validate(instance=raw, schema=AGENTS_SCHEMA)
+    _check_principal_namespace(raw)
+    return [
+        HumanEntry(
+            name=name,
+            display_name=data["display_name"],
+            github=data.get("github"),
+            email=data.get("email"),
+            domains=list(data.get("domains", [])),
+            availability=dict(data.get("availability", {})),
+            description=data.get("description", ""),
+        )
+        for name, data in raw.get("humans", {}).items()
+    ]
+
+
 def load_agents_config(
     path: Path | None = None,
     *,
@@ -842,6 +985,7 @@ def load_agents_config(
         raise ValueError("Empty agents.yaml file")
 
     validate(instance=raw, schema=AGENTS_SCHEMA)
+    _check_principal_namespace(raw)
     # Validate the cross-entry catalog and names once, before interpolation.
     project_principals({
         "credential_vendors": raw["credential_vendors"],
diff --git a/agent-coordinator/tests/test_human_principals.py b/agent-coordinator/tests/test_human_principals.py
new file mode 100644
index 00000000..08c5c21b
--- /dev/null
+++ b/agent-coordinator/tests/test_human_principals.py
@@ -0,0 +1,245 @@
+"""Human principals in ``agents.yaml`` (agent-identity spec, change ownership-map).
+
+Covers the ``humans:`` block: schema, the agent/human namespace collision check,
+``load_human_principals()``, the guarantee that ``load_agents_config()`` is
+unchanged by the block, and the pin between the inline ``HUMAN_PRINCIPAL_SCHEMA``
+and the canonical ``openspec/schemas/human-principals.schema.json`` (design D2).
+"""
+
+from __future__ import annotations
+
+import dataclasses
+import json
+from collections.abc import Iterator
+from pathlib import Path
+from typing import Any
+
+import pytest
+from jsonschema import ValidationError
+from openspec_paths import repo_root_from
+
+from src.agents_config import (
+    HUMAN_PRINCIPAL_SCHEMA,
+    HumanEntry,
+    get_api_key_identities,
+    get_dispatch_configs,
+    load_agents_config,
+    load_human_principals,
+)
+from tests.test_profile_sync import FakeAudit, FakeDb
+
+REPO_ROOT = repo_root_from(__file__, 2)
+SCHEMA_JSON = REPO_ROOT / "openspec" / "schemas" / "human-principals.schema.json"
+METADATA_KEYS = ("$schema", "$id", "title", "description")
+
+AGENTS_ONLY = """\
+credential_vendors: []
+agents:
+  claude-local:
+    type: claude_code
+    profile: claude_code_cli
+    trust_level: 3
+    transport: mcp
+    capabilities: [lock, queue, memory]
+    description: Test local agent
+"""
+
+HUMANS_BLOCK = """\
+humans:
+  jan:
+    display_name: "Jan Neumann"
+    github: jankneumann
+    email: jan@example.org
+    domains: [agent-coordinator, skills]
+    availability:
+      timezone: Europe/Berlin
+      hours: "09:00-18:00"
+      days: [mon, tue, wed, thu, fri]
+    description: Repository maintainer
+"""
+
+
+def _write(tmp_path: Path, body: str) -> Path:
+    path = tmp_path / "agents.yaml"
+    path.write_text(body, encoding="utf-8")
+    return path
+
+
+def _strings(obj: Any) -> Iterator[str]:
+    """Every string reachable in ``obj`` (dataclasses, mappings, sequences)."""
+    if isinstance(obj, str):
+        yield obj
+    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
+        for f in dataclasses.fields(obj):
+            yield from _strings(getattr(obj, f.name))
+    elif isinstance(obj, dict):
+        for key, value in obj.items():
+            yield from _strings(key)
+            yield from _strings(value)
+    elif isinstance(obj, (list, tuple, set, frozenset)):
+        for item in obj:
+            yield from _strings(item)
+    elif hasattr(obj, "__dict__"):
+        yield from _strings(vars(obj))
+
+
+class TestHumansBlock:
+    def test_humans_block_validates_and_loads(self, tmp_path: Path) -> None:
+        path = _write(tmp_path, AGENTS_ONLY + HUMANS_BLOCK)
+        humans = load_human_principals(path)
+        assert len(humans) == 1
+        jan = humans[0]
+        assert isinstance(jan, HumanEntry)
+        assert jan.name == "jan"
+        assert jan.display_name == "Jan Neumann"
+        assert jan.github == "jankneumann"
+        assert jan.email == "jan@example.org"
+        assert jan.domains == ["agent-coordinator", "skills"]
+        assert jan.availability == {
+            "timezone": "Europe/Berlin",
+            "hours": "09:00-18:00",
+            "days": ["mon", "tue", "wed", "thu", "fri"],
+        }
+        assert jan.description == "Repository maintainer"
+
+    def test_minimal_entry_defaults(self, tmp_path: Path) -> None:
+        path = _write(
+            tmp_path, AGENTS_ONLY + 'humans:\n  kim:\n    display_name: "Kim"\n'
+        )
+        (kim,) = load_human_principals(path)
+        assert kim.name == "kim"
+        assert kim.github is None
+        assert kim.email is None
+        assert kim.domains == []
+        assert kim.availability == {}
+        assert kim.description == ""
+
+    def test_missing_display_name_rejected_naming_entry_and_field(
+        self, tmp_path: Path
+    ) -> None:
+        path = _write(tmp_path, AGENTS_ONLY + "humans:\n  jan:\n    github: jankneumann\n")
+        with pytest.raises(ValidationError) as excinfo:
+            load_agents_config(path, secrets_path=tmp_path / "none")
+        assert "display_name" in excinfo.value.message
+        assert list(excinfo.value.absolute_path) == ["humans", "jan"]
+
+    def test_unknown_field_rejected(self, tmp_path: Path) -> None:
+        path = _write(
+            tmp_path,
+            AGENTS_ONLY + 'humans:\n  jan:\n    display_name: "Jan"\n    trust_level: 3\n',
+        )
+        with pytest.raises(ValidationError, match="trust_level"):
+            load_agents_config(path, secrets_path=tmp_path / "none")
+
+    def test_human_id_must_follow_the_slug_pattern(self, tmp_path: Path) -> None:
+        path = _write(tmp_path, AGENTS_ONLY + 'humans:\n  Jan_N:\n    display_name: "Jan"\n')
+        with pytest.raises(ValidationError):
+            load_agents_config(path, secrets_path=tmp_path / "none")
+
+    def test_human_id_colliding_with_agent_name_rejected(self, tmp_path: Path) -> None:
+        path = _write(
+            tmp_path,
+            AGENTS_ONLY + 'humans:\n  claude-local:\n    display_name: "Not an agent"\n',
+        )
+        with pytest.raises(ValueError, match="claude-local") as excinfo:
+            load_agents_config(path, secrets_path=tmp_path / "none")
+        message = str(excinfo.value)
+        assert "agent" in message
+        assert "human" in message
+
+    def test_collision_is_also_detected_by_load_human_principals(
+        self, tmp_path: Path
+    ) -> None:
+        path = _write(
+            tmp_path,
+            AGENTS_ONLY + 'humans:\n  claude-local:\n    display_name: "Not an agent"\n',
+        )
+        with pytest.raises(ValueError, match="claude-local"):
+            load_human_principals(path)
+
+
+class TestRegistryWithoutHumansUnchanged:
+    def test_no_humans_block_loads_empty_list(self, tmp_path: Path) -> None:
+        path = _write(tmp_path, AGENTS_ONLY)
+        assert load_human_principals(path) == []
+
+    def test_load_agents_config_identical_with_and_without_block(
+        self, tmp_path: Path
+    ) -> None:
+        without = load_agents_config(
+            _write(tmp_path, AGENTS_ONLY), secrets_path=tmp_path / "none"
+        )
+        with_block = load_agents_config(
+            _write(tmp_path, AGENTS_ONLY + HUMANS_BLOCK), secrets_path=tmp_path / "none"
+        )
+        assert with_block == without
+        assert [a.name for a in with_block] == ["claude-local"]
+
+
+class TestHumanNeverProjectedAsAgent:
+    """Spec scenario: Human principal declared without agent projection."""
+
+    async def test_no_projection_output_contains_the_human_id(
+        self, tmp_path: Path
+    ) -> None:
+        from openbao_credentials import project_principals
+
+        from src.agents_config import sync_profiles
+
+        path = _write(tmp_path, AGENTS_ONLY + HUMANS_BLOCK)
+        agents = load_agents_config(path, secrets_path=tmp_path / "none")
+
+        db = FakeDb([])
+        await sync_profiles(agents, db=db, audit=FakeAudit())
+        topology = project_principals(
+            {"credential_vendors": [], "agents": {a.name: {} for a in agents}}
+        )
+
+        outputs = {
+            "agents": agents,
+            "profile rows": db.rows,
+            "assignments": db.assignments,
+            "identities": get_api_key_identities(agents),
+            "dispatch configs": get_dispatch_configs(agents),
+            "principals": topology,
+        }
+        for label, output in outputs.items():
+            assert "jan" not in set(_strings(output)), label
+
+        (jan,) = load_human_principals(path)
+        assert jan.name == "jan"
+
+
+class TestSchemaMirror:
+    """Spec scenario: Schema mirror pinned (design D2)."""
+
+    def test_inline_schema_equals_canonical_json_minus_metadata(self) -> None:
+        canonical = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
+        stripped = {k: v for k, v in canonical.items() if k not in METADATA_KEYS}
+        assert stripped == HUMAN_PRINCIPAL_SCHEMA
+
+    def test_agents_schema_references_the_inline_human_schema(self) -> None:
+        from src.agents_config import AGENTS_SCHEMA
+
+        humans = AGENTS_SCHEMA["properties"]["humans"]
+        assert humans["type"] == "object"
+        assert humans["additionalProperties"] == HUMAN_PRINCIPAL_SCHEMA
+        assert "humans" not in AGENTS_SCHEMA.get("required", [])
+
+    def test_principal_id_key_constraint_matches_the_owners_schema(self) -> None:
+        """The ``humans:`` key constraint lives outside the mirrored entry schema.
+
+        Pin it to ``owners.schema.json`` ``$defs.PrincipalId``, which the skills-side
+        reader validates human ids against, so the two readers accept the same ids.
+        """
+        from src.agents_config import AGENTS_SCHEMA, PRINCIPAL_ID_PATTERN
+
+        owners_schema = json.loads(
+            (REPO_ROOT / "openspec" / "schemas" / "owners.schema.json").read_text(
+                encoding="utf-8"
+            )
+        )
+        principal_id = owners_schema["$defs"]["PrincipalId"]
+        names = AGENTS_SCHEMA["properties"]["humans"]["propertyNames"]
+        assert principal_id["pattern"] == PRINCIPAL_ID_PATTERN == names["pattern"]
+        assert principal_id["maxLength"] == names["maxLength"] == 64
diff --git a/agent-coordinator/tests/test_registry_projection.py b/agent-coordinator/tests/test_registry_projection.py
index 66475a5b..113c700f 100644
--- a/agent-coordinator/tests/test_registry_projection.py
+++ b/agent-coordinator/tests/test_registry_projection.py
@@ -51,9 +51,12 @@ from src.agents_config import (
     UNMANAGED_PROFILES,
     AgentEntry,
     DuplicateApiKeyError,
+    HumanEntry,
     ProfileSyncError,
     get_api_key_identities,
+    get_dispatch_configs,
     load_agents_config,
+    load_human_principals,
     sync_profiles,
 )
 from src.config import reset_config
@@ -774,3 +777,113 @@ def test_openbao_topology_matches_bundled_registry() -> None:
     keyed = {agent.name for agent in load_agents_config() if agent.api_key}
     projected = {p.name for p in topology.principals if p.kind == "agent"}
     assert keyed == projected
+
+
+# ---------------------------------------------------------------------------
+# Rule 6 — human principals are never projected as agents (ownership-map, D1/D12)
+# ---------------------------------------------------------------------------
+
+
+def _strings_in(obj: Any) -> set[str]:
+    """Every string reachable in *obj* (dataclasses, mappings, sequences)."""
+    import dataclasses
+
+    found: set[str] = set()
+    if isinstance(obj, str):
+        found.add(obj)
+    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
+        for f in dataclasses.fields(obj):
+            found |= _strings_in(getattr(obj, f.name))
+    elif isinstance(obj, dict):
+        for key, value in obj.items():
+            found |= _strings_in(key) | _strings_in(value)
+    elif isinstance(obj, (list, tuple, set, frozenset)):
+        for item in obj:
+            found |= _strings_in(item)
+    elif hasattr(obj, "to_dict"):
+        found |= _strings_in(obj.to_dict())
+    return found
+
+
+def _human_projection_violations(
+    humans: list[HumanEntry],
+    *,
+    rows: list[dict[str, Any]],
+    assignments: list[dict[str, Any]],
+    identities: dict[str, dict[str, str]],
+    dispatch: dict[str, Any],
+    principals: Any,
+) -> list[str]:
+    """Rule 6 — no human id appears in any agent runtime projection."""
+    surfaces: dict[str, Any] = {
+        "agent_profiles rows": rows,
+        "agent_profile_assignments": assignments,
+        "API-key identity map": identities,
+        "dispatch configs": dispatch,
+        "OpenBao principal projection": principals,
+    }
+    violations: list[str] = []
+    for human in humans:
+        for label, surface in surfaces.items():
+            if human.name in _strings_in(surface):
+                violations.append(
+                    f"human principal {human.name!r} appears in the {label} — humans "
+                    f"are principals, not agents, and must never be projected."
+                )
+    return violations
+
+
+class TestHumanProjectionInvariant:
+    """Rule 6, against the real registry and against a broken world."""
+
+    async def test_no_declared_human_is_projected_as_an_agent(
+        self, registry: list[AgentEntry]
+    ) -> None:
+        from openbao_credentials import project_principals
+
+        db = await _synced_db(registry)
+        violations = _human_projection_violations(
+            load_human_principals(),
+            rows=db.rows,
+            assignments=db.assignments,
+            identities=get_api_key_identities(registry),
+            dispatch=get_dispatch_configs(registry),
+            principals=project_principals(
+                {
+                    "credential_vendors": ["anthropic", "openai", "openrouter", "xai"],
+                    "agents": {a.name: {} for a in registry},
+                }
+            ),
+        )
+        assert not violations, _report(violations)
+
+    async def test_human_named_profile_row_is_reported(
+        self, registry: list[AgentEntry]
+    ) -> None:
+        """Negative: inject a human-named profile row and the checker fires."""
+        jan = HumanEntry(name="jan", display_name="Jan Neumann")
+        db = await _synced_db(registry)
+        rows = [*db.rows, _row("jan", agent_type="human", trust_level=2)]
+        violations = _human_projection_violations(
+            [jan],
+            rows=rows,
+            assignments=db.assignments,
+            identities={},
+            dispatch={},
+            principals=None,
+        )
+        assert any("'jan'" in v and "agent_profiles rows" in v for v in violations), (
+            _report(violations)
+        )
+
+    def test_human_named_assignment_is_reported(self) -> None:
+        jan = HumanEntry(name="jan", display_name="Jan Neumann")
+        violations = _human_projection_violations(
+            [jan],
+            rows=[],
+            assignments=[_assignment("jan", "claude_code_local")],
+            identities={},
+            dispatch={},
+            principals=None,
+        )
+        assert any("agent_profile_assignments" in v for v in violations)
diff --git a/docs/architecture-analysis/contracts-inventory.md b/docs/architecture-analysis/contracts-inventory.md
index 6c4eb00f..a899a5fa 100644
--- a/docs/architecture-analysis/contracts-inventory.md
+++ b/docs/architecture-analysis/contracts-inventory.md
@@ -3,7 +3,7 @@
 <!-- This file is generated by a project-context producer. Edit prose outside the generated markers only; content inside the markers is overwritten on regeneration. -->
 
 <!-- GENERATED: begin contracts-inventory -->
-_22 contract schema(s). Generated by api.contracts@1.0.0._
+_23 contract schema(s). Generated by api.contracts@1.0.0._
 
 | Capability | Schema | `$id` |
 | --- | --- | --- |
@@ -12,6 +12,7 @@ _22 contract schema(s). Generated by api.contracts@1.0.0._
 | `gen-eval-framework` | `openspec/contracts/gen-eval-framework/schemas/cli-contract.schema.json` | `https://raw.githubusercontent.com/jankneumann/agentic-coding-tools/main/openspec/contracts/gen-eval-framework/schemas/cli-contract.schema.json` |
 | `gen-eval-framework` | `openspec/contracts/gen-eval-framework/schemas/traceability-exclusions.schema.json` | `https://raw.githubusercontent.com/jankneumann/agentic-coding-tools/main/openspec/contracts/gen-eval-framework/schemas/traceability-exclusions.schema.json` |
 | `gen-eval-framework` | `openspec/contracts/gen-eval-framework/schemas/traceability.schema.json` | `https://raw.githubusercontent.com/jankneumann/agentic-coding-tools/main/openspec/contracts/gen-eval-framework/schemas/traceability.schema.json` |
+| `multiplayer-simulation` | `openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json` | `https://raw.githubusercontent.com/jankneumann/agentic-coding-tools/main/openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json` |
 | `phase-record` | `openspec/contracts/phase-record/schemas/handoff-local-fallback.schema.json` | `https://github.com/jankneumann/agentic-coding-tools/openspec/changes/phase-record-compaction/contracts/schemas/handoff-local-fallback.schema.json` |
 | `phase-record` | `openspec/contracts/phase-record/schemas/phase-record.schema.json` | `https://github.com/jankneumann/agentic-coding-tools/openspec/changes/phase-record-compaction/contracts/schemas/phase-record.schema.json` |
 | `project-context-refresh` | `openspec/contracts/project-context-refresh/schemas/context-checkpoint.schema.json` | `https://agentic-coding-tools.dev/schemas/context-checkpoint.schema.json` |
diff --git a/docs/architecture-analysis/skills-inventory.md b/docs/architecture-analysis/skills-inventory.md
index b7c3941e..5ec0a779 100644
--- a/docs/architecture-analysis/skills-inventory.md
+++ b/docs/architecture-analysis/skills-inventory.md
@@ -3,7 +3,7 @@
 <!-- This file is generated by a project-context producer. Edit prose outside the generated markers only; content inside the markers is overwritten on regeneration. -->
 
 <!-- GENERATED: begin skills-inventory -->
-_76 skills. Generated by documentation.inventory@1.0.0._
+_77 skills. Generated by documentation.inventory@1.0.0._
 
 | Skill | User-invocable | Description |
 | --- | --- | --- |
@@ -48,6 +48,7 @@ _76 skills. Generated by documentation.inventory@1.0.0._
 | `obsidian-bases` | no | Create and edit Obsidian Bases (.base files) with views, filters, formulas, and summaries. Use when working with .base files, creating database-like views of notes, or when the user mentions Bases, table views, card views, filters, or formulas in Obsidian. |
 | `obsidian-cli` | no | Interact with Obsidian vaults using the Obsidian CLI to read, create, search, and manage notes, tasks, properties, and more. Also supports plugin and theme development with commands to reload plugins, run JavaScript, capture errors, take screenshots, and inspect the DOM. Use when the user asks to interact with their Obsidian vault, manage notes, search vault content, perform vault operations from the command line, or develop and debug Obsidian plugins and themes. |
 | `obsidian-markdown` | no | Create and edit Obsidian Flavored Markdown with wikilinks, embeds, callouts, properties, and other Obsidian-specific syntax. Use when working with .md files in Obsidian, or when the user mentions wikilinks, callouts, frontmatter, tags, embeds, or Obsidian notes. |
+| `ownership-runtime` | no | Git-native ownership map resolver, check and CODEOWNERS projection: who owns a capability, roadmap item or path |
 | `parallel-infrastructure` | no | Shared parallel execution infrastructure: DAG scheduling, review dispatch, consensus synthesis, scope checking |
 | `parallel-review-implementation` | no | Per-package implementation review producing structured findings per review-findings.schema.json |
 | `parallel-review-plan` | no | Independent plan review producing structured findings per review-findings.schema.json |
diff --git a/docs/decisions/README.md b/docs/decisions/README.md
index a0526a7a..acd02fae 100644
--- a/docs/decisions/README.md
+++ b/docs/decisions/README.md
@@ -40,7 +40,11 @@ CI verifies the index is fresh by re-running `make decisions` and failing on any
 - [merge-infrastructure](./merge-infrastructure.md)
 - [merge-pull-requests](./merge-pull-requests.md)
 - [model-routing](./model-routing.md)
+- [multiplayer-collaboration](./multiplayer-collaboration.md)
+- [multiplayer-simulation](./multiplayer-simulation.md)
 - [observability](./observability.md)
+- [ownership-map](./ownership-map.md)
+- [parallel-infrastructure](./parallel-infrastructure.md)
 - [project-context-refresh](./project-context-refresh.md)
 - [project-context-refresh-orchestration](./project-context-refresh-orchestration.md)
 - [review-convergence-safety](./review-convergence-safety.md)
@@ -51,6 +55,7 @@ CI verifies the index is fresh by re-running `make decisions` and failing on any
 - [skill-workflow](./skill-workflow.md)
 - [software-factory-tooling](./software-factory-tooling.md)
 - [supervise](./supervise.md)
+- [toolkit-distribution](./toolkit-distribution.md)
 - [trust-posture](./trust-posture.md)
 - [validate-feature-ephemeral](./validate-feature-ephemeral.md)
 - [worktree](./worktree.md)
diff --git a/docs/decisions/agent-identity.md b/docs/decisions/agent-identity.md
index 9c7239ea..037c4570 100644
--- a/docs/decisions/agent-identity.md
+++ b/docs/decisions/agent-identity.md
@@ -5,6 +5,39 @@
 
 ---
 
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan
+
+**Human principals live in a `humans:` block of agents.yaml, share the agent namespace, and are never projected into agent runtime state** — Honors the no-parallel-registry constraint while keeping 'humans are not agents' structural; collisions are load errors; load_agents_config() keeps its return type.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D1)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan
+
+**One human-principal shape, two validators pinned equal by test** — The coordinator cannot read openspec/ at runtime and skills cannot import src.agents_config; a test asserts the inline dict equals openspec/schemas/human-principals.schema.json.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D2)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan Iteration 1
+
+**D5 drops email-to-human matching; the registry `email` field is declared for ri-03 and not consumed by ri-02, and is optional PII** — Step 1 fires whenever exactly one human is declared and two or more without a map is an error, so the match step was unreachable. Keeping the field optional preserves the schema contract later items build on.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D6)
+
+---
+
 ## 2026-09-25 — 2026-09-25-restructure-openbao-per-agent-secrets
 
 ### Phase: Implementation
diff --git a/docs/decisions/model-routing.md b/docs/decisions/model-routing.md
index c4afd2e7..ac869d5b 100644
--- a/docs/decisions/model-routing.md
+++ b/docs/decisions/model-routing.md
@@ -5,6 +5,17 @@
 
 ---
 
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**Spend: fail-closed budget check at probe time (coordinator ceiling > 0 or key credit limit); record through a new POST /routing/spend; spool and replay when the coordinator is unreachable, with a new degradation code metered_spend_unrecorded** — The existing ceiling is advisory and LedgerService.record has no caller. Cloud workers are known to hit coordinator_projection_forbidden, so the key limit bounds spend while records sit in the spool.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D4)
+
+---
+
 ## 2026-09-24 — 2026-09-27-retain-static-model-until-routing-evidence
 
 ### Phase: Implementation
diff --git a/docs/decisions/multiplayer-collaboration.md b/docs/decisions/multiplayer-collaboration.md
new file mode 100644
index 00000000..73b188fe
--- /dev/null
+++ b/docs/decisions/multiplayer-collaboration.md
@@ -0,0 +1,37 @@
+# Architectural Decisions — multiplayer-collaboration
+
+> Reverse-chronological timeline of decisions tagged `architectural: multiplayer-collaboration` in session-log Phase Entries.
+> Generated by `make decisions` — do not edit manually.
+
+---
+
+## 2026-10-09 — 2026-10-10-multiplayer-principles-guide
+
+### Phase: Implementation
+
+**Commit 1.2 after the guide** — Registering the test dir in testpaths before the guide exists would turn the default sweep red (Implementation Rule 2).
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md) (D1)
+
+---
+
+## 2026-10-09 — 2026-10-10-multiplayer-principles-guide
+
+### Phase: Implementation
+
+**Carry-forward fixes in design.md** — Added attention-budgets-digests to D3 P10 row; noted the Modes definitions have no test scenario and are checked in review.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md) (D2)
+
+---
+
+## 2026-10-06 — 2026-10-10-multiplayer-principles-guide
+
+### Phase: Plan Iteration 1
+
+**Register the guard-test directory in skills/pyproject.toml testpaths** — tests/ci_coverage/test_ci_test_coverage.py fails for any test directory CI does not reach, and running the directory by name bypasses testpaths, so the gap is invisible locally. Added as requirement 'Guard test runs in the default CI sweep' and task 1.2.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md) (D6)
diff --git a/docs/decisions/multiplayer-simulation.md b/docs/decisions/multiplayer-simulation.md
new file mode 100644
index 00000000..2e33b8c7
--- /dev/null
+++ b/docs/decisions/multiplayer-simulation.md
@@ -0,0 +1,147 @@
+# Architectural Decisions — multiplayer-simulation
+
+> Reverse-chronological timeline of decisions tagged `architectural: multiplayer-simulation` in session-log Phase Entries.
+> Generated by `make decisions` — do not edit manually.
+
+---
+
+## 2026-10-09 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Implementation
+
+**Agent.act takes (world, step, tick) and returns declared transitions** — Ledger 12. on_start data is read via declared_transitions(step, 'start') because it applies before the step runs; act returns the on_finish ones.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D2)
+
+---
+
+## 2026-10-09 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Implementation
+
+**Scheduler fast-forwards to the tick budget when nothing is running** — If no step is running and nobody was admitted, main cannot change again, so the result equals running idle ticks; it keeps blocked-budget runs fast.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D3)
+
+---
+
+## 2026-10-09 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Implementation
+
+**gen-eval pack test asserts scenario count and absence of 'Invalid scenario'** — gen-eval silently skips scenarios that fail to load (missing description), so the pass alone is not evidence.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D4)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Iteration 1
+
+**New capability multiplayer-simulation instead of the multiplayer-collaboration placeholder** — About 19 sibling deltas target the multiplayer-collaboration placeholder. Putting harness requirements there would mix test-harness content with collaboration behaviour, and would itself create the same-requirement collision the roadmap is trying to surface. This was an autonomous resolution of an assumptions finding.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D1)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Iteration 2
+
+**Roadmap status transitions are fixture data (on_start/on_finish set_status)** — Keeps the promise that ri-11 flips the blocked-time metric with fixture and rule changes only. Emitting contract_complete would otherwise need an edit to the harness agent.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D1)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Iteration 3
+
+**Lift D5's fixture-data transitions and intra-tick ordering into the requirement text** — The pinned blocked_ticks baseline and ri-11's no-harness-edit flip both depend on these rules. As design-only notes they were not part of the contract that downstream changes and validators read.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D1)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Review
+
+**Readiness reads roadmap.yaml from origin/main via a status applier** — Operator decision A1: mirrors the real supervisor/worker split; principals report transitions, sim-supervisor commits them to main.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D1)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Iteration 1
+
+**Harness at skills/tests/multiplayer-simulation, with gen-eval added to the skills test extra** — The systems under test (roadmap-runtime, and later the plan-feature scanner) live in skills/. skills/tests is not shipped by install.sh. A scratch uv lock with gen-eval as a path dependency resolved 56 packages.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D2)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Iteration 2
+
+**Fixed intra-tick order: finishers push, then waiters evaluate readiness, then admitted principals start** — The pinned blocked_ticks value depends on the order. Under this order, a dependency completed at tick t admits its dependent at tick t.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D2)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Review
+
+**Error reports relax principals/timeline via if/then** — Ledger item 3: a git failure before the world exists must still yield a schema-valid exit-1 report.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D2)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Iteration 1
+
+**Collision detection via a CollisionProbe seam plus a ground-truth fixture oracle** — No plan-time requirement-collision detector exists. The seam lets ri-06 attach its scanner without the harness fixing ri-06's interface. The oracle stops a broken fixture from making 'not detected' vacuously true.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D3)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Iteration 1
+
+**Blocked time measured in logical ticks with the real Roadmap.ready_items admission rule** — Ticks are deterministic, so exact baselines can be pinned. Using the real rule means ri-11's rule and schema change moves the metric without any edit to the harness code.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D4)
+
+---
+
+## 2026-10-05 — 2026-10-10-multiplayer-simulation-harness
+
+### Phase: Plan Iteration 1
+
+**Pinned baselines live in gen-eval scenario YAML, and flips are reviewed expectation edits** — The driver measures and the scenario decides what is expected. ri-06 and ri-11 flip a value in their own PRs, which keeps the before/after visible in review.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md](/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md) (D5)
diff --git a/docs/decisions/ownership-map.md b/docs/decisions/ownership-map.md
new file mode 100644
index 00000000..f0f0859d
--- /dev/null
+++ b/docs/decisions/ownership-map.md
@@ -0,0 +1,235 @@
+# Architectural Decisions — ownership-map
+
+> Reverse-chronological timeline of decisions tagged `architectural: ownership-map` in session-log Phase Entries.
+> Generated by `make decisions` — do not edit manually.
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Plan Review
+
+**Degradation single_vendor_review recorded: phase PLAN_REVIEW, vendor claude_code only; converge() ran with min_quorum=1** — Operator-committed policy for cloud containers (TRUST_POSTURE.md section 'Review quorum in cloud containers (temporary)', commit 479dcd9; gate-decision:f24d569f-0e1f-4378-89d5-4617d7e4bcf5). Discovery selected claude_code (Tier 1 CLI, claude-local) and codex (Tier 2 SDK, codex-remote); codex dispatch failed with 'No API key available for SDK dispatch' (auth_required), which is the expected verification that no second lane exists here. No environment variables, credentials or key files were read to probe vendors. Consensus therefore has quorum_received 1 of 2 requested; every finding is unconfirmed single-vendor opinion.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D1)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Implementation Review
+
+**Degradation single_vendor_review recorded: phase IMPL_REVIEW, vendor claude_code only; converge() ran with min_quorum=1** — Operator policy for cloud containers (TRUST_POSTURE.md section 'Review quorum in cloud containers (temporary)', commit 479dcd9 on the roadmap branch; gate-decision:f24d569f-0e1f-4378-89d5-4617d7e4bcf5). Discovery selected claude_code (Tier 1 CLI, claude-local, model fable, 250 s) and codex (Tier 2 SDK, codex-remote); codex failed with 'No API key available for SDK dispatch' (error_class auth_required), which is the required verification that no second lane exists here. No environment variables, credentials or key files were read. Consensus quorum_received 1 of 2; every finding is unconfirmed single-vendor judgment. Note: 479dcd9 is on the roadmap branch but not an ancestor of this change branch (stacked at 96ed991), so the policy text is not in this checkout's TRUST_POSTURE.md.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D1)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Validation Review
+
+**Degradation single_vendor_review recorded: phase VAL_REVIEW, vendor claude_code only; converge() ran with min_quorum=1** — Operator policy for cloud containers (TRUST_POSTURE.md "Review quorum in cloud containers (temporary)", commit 479dcd9 on the roadmap branch; gate-decision:f24d569f-0e1f-4378-89d5-4617d7e4bcf5). Discovery selected claude_code (Tier 1 CLI claude-local, model fable, 169 s) and codex (Tier 2 SDK codex-remote); codex failed with "No API key available for SDK dispatch" (error_class auth_required), which is the required verification that no second lane exists here; antigravity, grok, ocr and pi were skipped (no CLI, SDK or endpoint). No environment variables, credentials or key files were read. Quorum received 1 of 2; every finding is unconfirmed single-vendor judgment and none can block under ledger rule D3.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D1)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Validation Review
+
+**VAL_REVIEW ran as converge(review_type=implementation, fix_mode=targeted) with a real VAL_FIX applicator; the loop did not enter VAL_FIX** — The driver wired phase_fixer.apply_phase_fixes (persisting .review-ledger/pending-fixes.json) with a conductor dispatch_fn that blocks until this session applies the scoped edits, plus a post_fix_validator running the ownership-runtime and state-artifacts suites. Round 1 returned 9 findings, all low, 0 blocking, so converge() returned converged without calling fix_callback. Loop-state phase_history is orchestrator-owned and was not edited; this entry is the VAL_FIX sub-step record.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D2)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Plan Review
+
+**PLAN_FIX recorded as not entered: round-1 blocking set was empty, so converge() returned converged without calling the fix applicator** — A real inline PLAN_FIX applicator was wired as fix_callback (phase_fixer.apply_phase_fixes persisting .review-ledger/pending-fixes.json, then conductor edits of cited allowed_paths with converge()'s own out-of-scope rejection). It was never invoked because no ledger item was blocking (all six findings low, judgment class). Loop-state phase_history is orchestrator-owned and was not edited; this entry is the sub-step record.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D3)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Validation Review
+
+**Validation evidence critique: every claimed pass is backed, with five report errors corrected inline** — Reproduced: ownership-runtime 233 passed; state-artifacts 13 passed / 6 skipped (the report said "all pass"; the skips are the mirror-parity cases, environmental); coordinator schema/projection tests 133 passed; coordinator unit suite 2937 passed / 11 skipped / 139 deselected; full skills suite 7145 passed / 24 skipped / 24 failed in exactly the seven known environmental groups (same 7193 collected as the report's 7133/36/24; 12 environment-dependent skips passed here); check_owners --codeowners --strict --json mode solo, exit 0, no findings; reconcile 0 disagreements, fresh; solo-mode smoke in a scratch copy without the map (check clean, emit fails closed with no_ownership_map, CODEOWNERS untouched); openspec validate --strict valid; ruff clean; install.sh --check prints the portability pass line; every test id cited in the report exists. Corrections: the specs hold 47 scenarios, not 37 (the trace listed all 47); the human-projection invariant test lives in test_registry_projection.py; two ellipsized coordinator-independence test names; the "Existing suites unchanged with the map absent" trace now states that the suites ran with the map present and why that is sufficient; the base comparison now records the orchestrator's verification against 0a4659f. Skipped phases (Deploy, Smoke, E2E, scanners) are legitimately skipped: deployable: false and no docker daemon.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D3)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Plan Review
+
+**Four findings citing files outside change ownership-map were parked out_of_scope by the conductor after convergence** — Ledger items 1 (openspec/changes/reviewer-shaped-prs scaffold 'pRs' casing), 3 (TRUST_POSTURE.md header comment vs replan_required=auto), 4 (19 tautological roadmap scaffold scenarios) and 5 (launch_token/owner_nonce committed in roadmap checkpoint.json) are real but belong to the roadmap branch, not to this change's plan artifacts; parking keeps IMPL_REVIEW from inheriting unrelated open items. They are advisory for the branch owner. Items 2 (proposal Selected Approach says D1-D13; design has D14) and 6 (PathPattern regex admits embedded ** that only the loader rejects, by design D3) are in scope, low, and left open as advisories; item 2 is a one-token fix for the implementer's first commit.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D4)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Implementation Review
+
+**IMPL_FIX not entered by the inner loop: round 1 had zero blocking items, so converge() returned converged without calling fix_callback** — A real IMPL_FIX applicator was wired (phase_fixer.apply_phase_fixes persisting .review-ledger/pending-fixes.json, then a conductor dispatch_fn that blocks until the lead vendor claude_code — the conductor, package_authors being empty — applies the scoped edits, with converge()'s own out-of-scope rejection afterwards). Under ledger rule D3 a single-vendor review can never produce a 'confirmed' finding, so only deterministic findings can block; all 9 were judgment-class and the medium one therefore did not block. Loop-state phase_history is orchestrator-owned and was not edited; this entry is the sub-step record.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D4)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Validation Review
+
+**Conductor VAL_FIX after convergence: ledger 16 fixed test-first, 17 and 18 fixed in the spec; 19–21 left as advisories; 22 retired** — Item 16 is a real contract defect: collect_problems() documents "report, never raise" but raised OwnershipConfigError when owners.schema.json is not installed, and read_codeowners() decoded CODEOWNERS unguarded, so a non-UTF-8 file turned `check_owners --codeowners --json`, `reconcile` and `emit --write` into tracebacks (no JSON for CI consumers). Fix: _schema_problems returns the install problem as an invalid_map Problem; read_codeowners raises a new D9 error code codeowners_unreadable that reconcile and emit --write surface as a finding / fail-closed exit (nothing written). The code was added to CODES, the design D9 table and SKILL.md, and the CODES-equality test was extended; four new tests (test_missing_schema_is_reported_not_raised, TestUnreadableCodeowners in the reconcile and emit suites). Item 17: the spec stated SHALL behaviour for unowned_roadmap_item and sentinel_principal without scenarios; two scenarios mirroring the existing tests were added and traced in the report. Item 18: the spec omitted the git config user.name fallback that design D5 and derive_solo_principal implement; stated. Items 19 (corrupt roadmap.yaml folded into unknown_roadmap_item), 20 (two literal-prefix definitions) and 21 (collect_problems evaluated twice) stay open as low advisories with notes. Item 22 duplicated open item 12 and was retired, as 14/15 were in IMPL_REVIEW. These edits ran outside converge()'s fix_callback because nothing blocked (same reasoning as IMPL_REVIEW decision 5).
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D4)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Plan Review
+
+**Conductor's independent read found two medium plan defects the single lane did not report; recorded as open questions, not ledgered** — Because the claude_code CLI lane did dispatch, the vendor result is that lane's cold review and the conductor's own findings were not injected as a second claude_code result. (a) design.md D3 matching table says any `/` anchors a pattern at the repository root, but gitignore/GitHub CODEOWNERS leave a single segment with only a trailing `/` (e.g. `schemas/`) unanchored, matching that directory at any depth; the resolver and GitHub would disagree on openspec/schemas/x for such a rule. Fix: implement the gitignore rule or, consistent with the embedded-`**` precedent, have the loader reject a paths key whose only `/` is trailing (pointing at `/x/` or `**/x/`). D8's 'inverse of D4's rule order' is also the same order, not the inverse. (b) tasks.md 5.7 asks the checkpoint to record 'no pre-existing test file was modified', but tasks 2.5 and 5.4 edit pre-existing test files additively; the proposal NFR 'pass with no test edits' has the same contradiction. Both are deterministic consistency defects a PLAN_FIX could close in design.md/spec, tasks.md and proposal.md.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D5)
+
+---
+
+## 2026-10-09 — 2026-10-10-ownership-map
+
+### Phase: Implementation Review
+
+**Conductor applied the medium finding and four deterministic lows after convergence, test-first, scoped to cited files; ledgered as addressed** — Item 9 (medium, principals.py) is real: read_registry validated each humans: entry but not its key, so an id such as Jan_N that the coordinator rejects via AGENTS_SCHEMA propertyNames was accepted and counted toward mode derivation. Fix: validate the key against owners.schema.json $defs.PrincipalId (shipped with the skill; same slug pattern and 64-char limit) and raise invalid_registry naming the id; two new tests in test_principals.py; a coordinator test pins PRINCIPAL_ID_PATTERN and propertyNames.maxLength to that schema so the two readers cannot drift. Item 10: codeowners.tracked_files now catches OSError/SubprocessError like principals._git (TestTrackedFiles, timeout and missing-binary cases). Item 7: design D9 table lists invalid_registry and registry_not_found; test_codes_table_has_the_documented_codes tightened from subset to equality. Item 8: tasks.md 5.2 names the delivered capabilities. Item 11: SKILL.md documents mode null. Item 2 closed (fixed by PLAN_FIX 0a4659f, re-verified by the lane); items 14/15 retired as duplicate re-verification notes; item 6 (PathPattern two-layer validation) stays open as a low by-design advisory. Items 12 (projection-invariant checker uses exact string equality) and 13 (vacuous second assertion in test_repository_invariant) are test-style observations left open as advisories: tightening 12 to substring matching would make the invariant fire on legitimate strings containing 'jan', and 13 cannot be made independently meaningful without removing the stronger findings == [] assertion. These edits ran outside converge()'s fix_callback because nothing was blocking; the plan-review rejection of out-of-loop edits concerned plan artifacts needing PLAN_FIX, whereas here the write-capable reviewer is the lead vendor and the alternative was leaving a real medium defect open under a degraded quorum. All gates re-run green.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D5)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan Iteration 1
+
+**Capability assignments imply openspec/specs/<cap>/ and openspec/contracts/<cap>/ path rules ranked with explicit paths rules; explicit wins ties** — D8 emits CODEOWNERS lines from capability assignments and reconcile compares them with resolve_path(); without implied rules a capability-only map produced a false disagreement on every spec file. Implied-before-explicit rule order is the only way an author can override a capability's ownership of its own directory.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D1)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan Iteration 2
+
+**Acceptance outcome 2 ('a check reports capabilities with no owner') is satisfied in team mode and proven by fixture tests; the solo repository exercises the error-class findings and CODEOWNERS reconcile** — D14 makes the unowned_* findings vacuous in solo mode, so the proposal's outcome mapping now says so explicitly; otherwise a reviewer validating ri-02 against this repository would look for a report that correctly does not appear.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D1)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan
+
+**openspec/owners.yaml assigns owners, decision_rights and acceptance_rights to capabilities, roadmap items and restricted-glob paths with a mandatory default_owner** — Git-native, lives next to the specs it governs, fail-closed on invalid or unregistered owners; agents may never be owners.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D3)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan Iteration 1
+
+**unowned_capability and unowned_roadmap_item are team-mode-only warnings (D14)** — With one human every subject is owned by construction; demanding explicit assignments for 40 capabilities and ~190 roadmap items would break CI on every later /plan-feature or /plan-roadmap run, violating the solo-mode constraint. Task 5.2 now authors a representative, not exhaustive, map.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D3)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan
+
+**Solo principal derivation: single registry human, else git-config identity (matched to a declared human by email), else sentinel; two or more humans without a map is an error** — Returning 'whoever runs this' in a multi-human repo is the single-principal assumption the epic removes.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D4)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan Iteration 1
+
+**Finding codes are the --json machine contract and are enumerated in D9; new codes cover dangling keys, no-map and orphaned-block cases, registry escape and non-git checkouts** — tasks.md and the spec named codes the design never listed; later items consume codes, not messages, so the enumeration belongs in the design and the spec requires it.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D4)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan
+
+**mode (solo|team) derives from the number of human principals, not from owners.yaml presence** — Lets a one-maintainer repository dogfood the map and CODEOWNERS without flipping later roadmap items into team behavior; downstream items branch on ctx.mode.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D5)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan Iteration 1
+
+**registry: in owners.yaml is confined to the repository (schema rejects `..`, loader rejects escape); OWNERSHIP_REGISTRY_PATH stays unconfined** — A reviewed-but-careless map could otherwise make the reader parse an arbitrary file; the env var is operator-controlled so confinement there would only hinder consumer repositories.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D5)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan
+
+**Resolver ships as the infrastructure skill skills/ownership-runtime with install_assets schemas, importing nothing from agent-coordinator** — Mirrors roadmap-runtime; portable through install.sh; pyyaml + jsonschema only.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D6)
+
+---
+
+## 2026-10-05 — 2026-10-10-ownership-map
+
+### Phase: Plan
+
+**CODEOWNERS is a derived managed block emitted in ascending specificity so GitHub last-match-wins agrees with the resolver's most-specific-wins; reconcile probes real tracked paths and never feeds back** — Keeps GitHub review routing and the ownership map from silently disagreeing while restricting the glob subset both matchers interpret identically.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-ownership-map/session-log.md](/openspec/changes/archive/2026-10-10-ownership-map/session-log.md) (D7)
diff --git a/docs/decisions/parallel-infrastructure.md b/docs/decisions/parallel-infrastructure.md
new file mode 100644
index 00000000..28c3425f
--- /dev/null
+++ b/docs/decisions/parallel-infrastructure.md
@@ -0,0 +1,48 @@
+# Architectural Decisions — parallel-infrastructure
+
+> Reverse-chronological timeline of decisions tagged `architectural: parallel-infrastructure` in session-log Phase Entries.
+> Generated by `make decisions` — do not edit manually.
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**A lane is an endpoint-only agents.yaml agent (openrouter-review, type openrouter), with its model in an archetypes.yaml provider** — This reuses tier-2.5 discovery and the coordinator's dispatch-configs without a second roster. Lane id = type, because converge keys results by vendor.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D1)
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**Model-family diversity rule: reject anthropic-publisher lanes and skip duplicate families via vendor_families data** — Quorum is meant to measure independent model opinions. An OpenRouter lane in the claude_code or codex family would inflate it.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D2)
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**API lanes verify through an authenticated zero-cost probe (GET /key or GET /models) that also checks the spend budget** — The existing Dispatchable Vendor Verification requirement already names this; today every API lane is probe_unsupported.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D3)
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**Metered lanes fill quorum only (fill_target defaults to default_min_quorum)** — Prevents every host review from paying OpenRouter. The operator can tune it as data.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D5)
diff --git a/docs/decisions/roadmap-orchestration.md b/docs/decisions/roadmap-orchestration.md
index 970c1cc9..a2ab0b04 100644
--- a/docs/decisions/roadmap-orchestration.md
+++ b/docs/decisions/roadmap-orchestration.md
@@ -5,69 +5,69 @@
 
 ---
 
-## 2026-10-09 — dispatch-contract
+## 2026-10-09 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Review
 
 **Existing v1 contract schemas are given one role each instead of being duplicated** — `openspec/contracts/roadmap-orchestration/schemas/` already published request/result/attempt/context schemas; request/result are frozen as v1 reader schemas, the attempt schema becomes the single attempt definition `$ref`'d by `checkpoint.schema.json`, and the context schema is `$ref`'d by the v2 request.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D1)
 
 ---
 
-## 2026-10-09 — dispatch-contract
+## 2026-10-09 — 2026-10-10-dispatch-contract
 
 ### Phase: Implementation
 
 **Commit order keeps every commit green rather than following package boundaries literally** — The checkpoint/attempt schema $ref switch, models, orchestrator and execution must change together; schemas 2.3-2.4 landed in the ledger commit.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D1)
 
 ---
 
-## 2026-10-09 — dispatch-contract
+## 2026-10-09 — 2026-10-10-dispatch-contract
 
 ### Phase: Implementation
 
 **Cross-host reinitialize keeps a parked attempt's generation** — Its escalate_resume approval is bound to the generation (advisory finding 13).
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D3)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D3)
 
 ---
 
-## 2026-10-06 — dispatch-contract
+## 2026-10-06 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Iteration 1
 
 **Spec deltas target existing capabilities, not the placeholder** — multiplayer-collaboration is a roadmap, not a capability; the touched behaviour is owned by roadmap-orchestration, supervise, skill-workflow, trust-posture and parallel-infrastructure.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D1)
 
 ---
 
-## 2026-10-06 — dispatch-contract
+## 2026-10-06 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Iteration 3
 
 **Attempts persist the verified roadmap_approval_ref** — It is a non-secret gate-decision reference; persisting it lets child_start write it into every generation's marker and lets the supervisor apply the same scope rule from the same fact.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D1)
 
 ---
 
-## 2026-10-06 — dispatch-contract
+## 2026-10-06 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Iteration 1
 
 **Launch tokens are minted per generation and stored only as sha256 digests** — A digest-only checkpoint cannot re-emit the same token on resume, so the Durable Delegated Attempt Ledger requirement is MODIFIED; reissue is limited to states where takeover is already safe.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D2)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D2)
 
 ---
 
diff --git a/docs/decisions/skill-workflow.md b/docs/decisions/skill-workflow.md
index 5a9f3bb5..9888ce70 100644
--- a/docs/decisions/skill-workflow.md
+++ b/docs/decisions/skill-workflow.md
@@ -5,14 +5,36 @@
 
 ---
 
-## 2026-10-09 — dispatch-contract
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**agent_lane gains a CompositeOrchestrator (claude_code handshake plus include_lanes HTTP dispatch), and converge maps a mid-run vendor_unavailable/auth_required quorum loss to capability_unavailable** — This is the only path by which a cloud worker reaches quorum 2, and it makes 'exceeding the ceiling parks' true mid-run as well as at the probe.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D6)
+
+---
+
+## 2026-10-11 — openrouter-review-lane
+
+### Phase: Plan Iteration 1
+
+**Retiring TRUST_POSTURE's cloud section and the policy entry is the last task, gated by an evidence file and a guard test** — The roadmap says the policy is removed once the lane passes in cloud. Live cloud evidence cannot run in CI, so it is an operator-run step with a recorded artifact.
+
+- Status: `active`
+- Source: [openspec/changes/openrouter-review-lane/session-log.md](/openspec/changes/openrouter-review-lane/session-log.md) (D7)
+
+---
+
+## 2026-10-09 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Review
 
 **Quorum park happens in the worker protocol, not convergence_loop** — below quorum the SKILL.md probe skips review entirely, so convergence_loop never runs; `runner.py park` stays the only writer.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D4)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D4)
 
 ---
 
diff --git a/docs/decisions/supervise.md b/docs/decisions/supervise.md
index a7967b72..1dfad031 100644
--- a/docs/decisions/supervise.md
+++ b/docs/decisions/supervise.md
@@ -5,69 +5,69 @@
 
 ---
 
-## 2026-10-09 — dispatch-contract
+## 2026-10-09 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Review
 
 **Capability-park fan-out writes one escalate_resume record per dispatch** — keeps `require_approval_ref`'s per-dispatch and per-generation checks unchanged.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D2)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D2)
 
 ---
 
-## 2026-10-09 — dispatch-contract
+## 2026-10-09 — 2026-10-10-dispatch-contract
 
 ### Phase: Implementation
 
 **Review quorum per environment is data (review_quorum_policy.json) carried as review_requirements.quorum_policy** — Supervisor follow-up 1: a worker gets min_quorum 1 only through data with an explicit sunset; single-lane is detected by failed dispatch.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D2)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D2)
 
 ---
 
-## 2026-10-09 — dispatch-contract
+## 2026-10-09 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Review
 
 **counting_lanes includes unverified roster lanes** — otherwise `missing_lanes` is always empty and distinct capability gaps share one fingerprint.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D3)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D3)
 
 ---
 
-## 2026-10-06 — dispatch-contract
+## 2026-10-06 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Iteration 2
 
 **Review quorum defaults to 2 per review phase with a router-context override** — routing.yaml defines a cost ladder but no quorum; 2 is today's --min-vendors and the ladder orders lanes without excluding tiers. Recorded as a decision because this phase cannot ask the operator.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D2)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D2)
 
 ---
 
-## 2026-10-06 — dispatch-contract
+## 2026-10-06 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Iteration 1
 
 **Dispatched children defer gate authority to the supervisor** — Issue 1 arose because child and supervisor postures differed; the marker carries the supervisor posture digest and drift disables auto, so one holder is authoritative.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D3)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D3)
 
 ---
 
-## 2026-10-06 — dispatch-contract
+## 2026-10-06 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Iteration 2
 
 **Below-quorum availability still launches** — check-vendors exits 2 for both below-quorum and roster failure; only an error field or unparseable JSON blocks prepare, and the child parks capability_unavailable honestly at review.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D3)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D3)
 
 ---
 
diff --git a/docs/decisions/toolkit-distribution.md b/docs/decisions/toolkit-distribution.md
new file mode 100644
index 00000000..192bc6dd
--- /dev/null
+++ b/docs/decisions/toolkit-distribution.md
@@ -0,0 +1,59 @@
+# Architectural Decisions — toolkit-distribution
+
+> Reverse-chronological timeline of decisions tagged `architectural: toolkit-distribution` in session-log Phase Entries.
+> Generated by `make decisions` — do not edit manually.
+
+---
+
+## 2026-10-05 — 2026-10-10-toolkit-consistency
+
+### Phase: Plan Iteration 1
+
+**New capability toolkit-distribution owns stamp, drift check and shared learnings** — skill-workflow already holds Cross-Repo Portability and Canonical Skill Distribution but is a 7,000-line accretion spec; the install-to-consumer surface is coherent on its own and the existing requirements are referenced as constraints rather than modified.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md](/openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md) (D1)
+
+---
+
+## 2026-10-05 — 2026-10-10-toolkit-consistency
+
+### Phase: Plan Iteration 1
+
+**The install stamp is the pin and lives at .agentic-toolkit/stamp.json** — Mirror directories are often gitignored in consumer repos, so a per-agent stamp would not be tracked; a hand-edited pin would drift from the installed payload and carry no hash.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md](/openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md) (D2)
+
+---
+
+## 2026-10-05 — 2026-10-10-toolkit-consistency
+
+### Phase: Plan Iteration 1
+
+**Drift check is additive to the existing --check; unpinned is advisory, invalid stamp fails loud** — install.sh --check already does mirror parity; the roadmap's constraint is that advisory signals fail open, while docs/guides/state-artifacts.md forbids silently repairing an invalid tracked artifact.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md](/openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md) (D3)
+
+---
+
+## 2026-10-05 — 2026-10-10-toolkit-consistency
+
+### Phase: Plan Iteration 1
+
+**Self-install writes no stamp** — In this repository the source tree is the pin; stamping would churn a tracked file on every skill edit and in the CI install/--check step.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md](/openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md) (D4)
+
+---
+
+## 2026-10-05 — 2026-10-10-toolkit-consistency
+
+### Phase: Plan Iteration 1
+
+**Shared learnings are a one-way, allowlisted JSONL projection gated by a human-owned config.json** — The epic forbids a parallel learning store; projecting from episodic memory with a field allowlist, transcript-mined exclusion and the session-log sanitizer meets 'never include private transcript content' without a consent model this item does not own.
+
+- Status: `active`
+- Source: [openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md](/openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md) (D5)
diff --git a/docs/decisions/trust-posture.md b/docs/decisions/trust-posture.md
index 9667a54c..5f352415 100644
--- a/docs/decisions/trust-posture.md
+++ b/docs/decisions/trust-posture.md
@@ -5,25 +5,25 @@
 
 ---
 
-## 2026-10-06 — dispatch-contract
+## 2026-10-06 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Iteration 2
 
 **ApprovalGate reads the launch marker through an injected seam and ignores context refs** — A context value can be set by any caller; the marker is written by child_start after supervisor verification. The seam also keeps wp-posture independent of wp-contract-lib.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D1)
 
 ---
 
-## 2026-10-06 — dispatch-contract
+## 2026-10-06 — 2026-10-10-dispatch-contract
 
 ### Phase: Plan Iteration 1
 
 **Non-auto fallback is an optional `unscoped` posture sub-config defaulting to block** — The outcome names a fallback but the posture schema has none; a declared field keeps operators able to choose notify_with_timeout while failing closed by default. Recorded as a decision rather than asked: this phase sub-agent has no interactive channel to the operator.
 
 - Status: `active`
-- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D4)
+- Source: [openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md](/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md) (D4)
 
 ---
 
diff --git a/docs/guides/skills.md b/docs/guides/skills.md
index 86c54b17..4a35fd13 100644
--- a/docs/guides/skills.md
+++ b/docs/guides/skills.md
@@ -26,3 +26,6 @@
   `agent-coordinator/archetypes.yaml` changes — the report carries that
   file's content hash, `--check-freshness` exits `1` once they diverge, and
   the non-blocking `skill-audit-freshness` CI job annotates when they do.
+- **Install stamp and drift check**: a successful `install.sh` into a consumer repository writes `.agentic-toolkit/stamp.json` (`schema_version`, `toolkit_version`, `source_commit`, `payload_hash`, `installed_at`, `agents`, `mode`) after every sync step succeeds. Commit it: it is the pin for the toolkit payload the repository expects. A self-install (target is this repository) writes no stamp, and `--check` never writes one. `payload_hash` comes from `skills/shared/payload_hash.py` (portable skill dirs, shared libraries and `install-manifest.json`, excluding `tests/`, `__pycache__/`, `node_modules/`) and is identical for the source tree and a synced mirror. To move the pin, run `install.sh` from the new toolkit checkout and commit the changed stamp.
+- **Extended `--check`**: `bash skills/install.sh --target <consumer> --check` keeps its mirror-parity check and, when a stamp exists, adds *checkout drift* (this toolkit checkout is not the pinned payload) and *runtime drift* (an installed `.claude/skills/` or `.agents/skills/` mirror is not the pinned payload) with distinct messages; either exits `1`. No stamp is reported as "unpinned" and does not change the exit code; an invalid stamp (bad JSON, not an object, `schema_version` other than `1`) exits `1` and is never rewritten. `--check` runs from the toolkit checkout and does not auto-update anything.
+- **Opt-in shared learnings**: a repository shares capability-gap learnings only when a human sets `{"schema_version": 1, "shared_learnings": {"enabled": true}}` in `.agentic-toolkit/config.json` (the installer never writes it). `improve-harness` `export_shared_learnings.py` then projects allowlisted, sanitized, non-transcript entries into the tracked `.agentic-toolkit/learnings.jsonl`, and `analyze_failures.py` merges it read-only as `origin:shared-repo`. See [state artifacts](state-artifacts.md) for ownership and missing/stale behavior.
diff --git a/docs/guides/state-artifacts.md b/docs/guides/state-artifacts.md
index 2ec2317a..3c9dabc1 100644
--- a/docs/guides/state-artifacts.md
+++ b/docs/guides/state-artifacts.md
@@ -11,6 +11,10 @@ This guide is the canonical inventory and rehydration order for durable orchestr
 | **Roadmap learning entry** | `openspec/roadmaps/<roadmap-id>/learnings/<item-id>.md`, held beside the roadmap; `learning-log.md` is its index | `roadmap-runtime` learning writer after an item reaches a terminal phase | Advisory history: decisions, blockers, deviations, recommendations, and vendor evidence; never resumable execution state | Later item planning, roadmap retrospection, and supervisor context assembly | Missing learning reduces context but does not change readiness. A stale or conflicting learning is reported and ignored for execution decisions; checkpoint and loop state win. |
 | **Phase record** | Phase entries in `openspec/changes/<change-id>/session-log.md`, held on the change branch | `session-log` `PhaseRecord.write_both()` appends and sanitizes the tracked record | Durable historical rationale and evidence for a completed workflow phase; not current phase or roadmap position | Later phase context, decision-index generation, validation, and reviewers | Missing records are a context/evidence gap, not permission to infer execution state. Conflicts with checkpoint or loop state are reported; canonical execution state wins. |
 | **Handoff document** | Coordinator `handoff_documents`; local fallback `openspec/changes/<change-id>/handoffs/<phase>-<N>.json`; supervisor mirror `openspec/supervise/supervisor-record.json` | `PhaseRecord.write_both()` through the coordination bridge, or supervise's deterministic record writer and bridge call | Bootstrap locator and bounded cross-session context only; not execution authority | Fresh sessions, downstream phases, and supervisor bootstrap | Coordinator loss uses the tracked fallback or mirror and is reported as degraded. Stale handoffs may be ignored. A newer advisory timestamp never overrides canonical state. |
+| **Ownership map** | `openspec/owners.yaml`, tracked on the default branch of the repository it governs | Humans, by reviewed PR. No skill writes it; `codeowners.py` writes only the derived `.github/CODEOWNERS` managed block | Authoritative for owner, decision-right and acceptance-right sets over capabilities, roadmap items and paths; the repository default owner is the fail-closed fallback. `CODEOWNERS` is a derived projection | `ownership-runtime` resolver and check; later multiplayer-collaboration roadmap items (`ri-03`, `ri-08`, `ri-09`, `ri-12`, `ri-14`, `ri-17`) | Absence is valid and means solo mode (every call resolves to the sole repository principal). Present-but-invalid, or naming an unregistered owner, fails closed: the resolver raises and the check exits 1; it is never repaired from `CODEOWNERS`, git history or the coordinator. A stale `CODEOWNERS` is reported by reconcile and regenerated from `owners.yaml`, never the reverse. |
+| **Toolkit install stamp** | `<consumer-root>/.agentic-toolkit/stamp.json`, tracked in the consumer repository (never written in this repository: a self-install's source tree is the pin) | `skills/install.sh`, written last, only after every mirror, shared-library, manifest and asset step succeeded; never by `--check` | Authoritative pin of the toolkit payload the repository expects: `toolkit_version`, `source_commit`, `payload_hash`, `agents`, `mode` | `install.sh --check` (checkout drift: pinned hash vs source checkout; runtime drift: pinned hash vs each installed mirror) and teammates reviewing the pin in a PR | Absent stamp = unpinned: reported, exit code unaffected. Unreadable, non-object or `schema_version` other than `1` fails loud (`--check` exits `1`) and is never repaired or rewritten; an aborted install leaves the prior stamp byte-identical. Pin moves only by re-running `install.sh` and committing. |
+| **Toolkit config** | `<consumer-root>/.agentic-toolkit/config.json`, tracked in the consumer repository | The repository's humans (hand-edited); `install.sh` never creates or modifies it | Sole opt-in switch for repository-scoped learning sharing (`shared_learnings.enabled`) | `export_shared_learnings.py` and `analyze_failures.py` | Absent, unreadable, `schema_version` other than `1` or `enabled` other than `true` means sharing is disabled: the exporter exits `2` and writes nothing, and the analysis ignores `learnings.jsonl`. Never inferred from the stamp or from the presence of the learnings file. |
+| **Shared learnings projection** | `<consumer-root>/.agentic-toolkit/learnings.jsonl`, tracked in the consumer repository | `improve-harness` `export_shared_learnings.py` (allowlisted, sanitized, deterministic, one-way projection of episodic memory; `source:transcript-mined` entries excluded) | Advisory history only; episodic memory stays the learning store and this file is never a second store | `analyze_failures.py` (merges records tagged `origin:shared-repo`, never writes them back to memory) | Absent or stale file = reduced context, never execution state. Disabled sharing ignores it. Never derive loop state, checkpoint state or trust posture from it; canonical state wins. An export that receives no memory entries leaves the file unchanged. |
 
 The coordinator work queue is a derived projection, not a sixth authority class. Its one-way contract is documented in [Work-Queue Truth / Projection](work-queue-truth-projection.md).
 
diff --git a/docs/skills-catalogue.md b/docs/skills-catalogue.md
index 1647b0db..8f0b939d 100644
--- a/docs/skills-catalogue.md
+++ b/docs/skills-catalogue.md
@@ -150,6 +150,7 @@ Internal machinery used by workflow and methodology skills. Most are `user_invoc
 | ★ `session-bootstrap` | Cloud environment bootstrap (setup script + verify hook) and coordinator lifecycle hooks | `/session-bootstrap` |
 | ★ `session-log` | Structured decision records for session logs and merge logs at phase boundaries | `/session-log` |
 | ★ `roadmap-runtime` | Shared roadmap library: artifact models, checkpoint management, learning-log helpers, sanitization | `/roadmap-runtime` |
+| · `ownership-runtime` | Git-native ownership map resolver, check and `CODEOWNERS` projection (`openspec/owners.yaml`); infrastructure library, not user-invocable | Internal |
 
 ### Removed / deprecated skills
 
diff --git a/openspec/changes/dispatch-contract/.review-ledger/ledger.json b/openspec/changes/archive/2026-10-10-dispatch-contract/.review-ledger/ledger.json
similarity index 75%
rename from openspec/changes/dispatch-contract/.review-ledger/ledger.json
rename to openspec/changes/archive/2026-10-10-dispatch-contract/.review-ledger/ledger.json
index d6b19d53..2511ed73 100644
--- a/openspec/changes/dispatch-contract/.review-ledger/ledger.json
+++ b/openspec/changes/archive/2026-10-10-dispatch-contract/.review-ledger/ledger.json
@@ -518,7 +518,129 @@
       "description": "Citations omit or misplace evidence. Outcome 4 omits the IMPL_ITERATE/IMPL_REVIEW regression tests for the fingerprint path (test_a_human_rejected_escalation_is_not_cleared_when_its_membership_changes, test_an_operator_approval_ends_a_human_rejected_escalation, test_an_approval_resumes_a_member_that_joined_after_the_rejection, supervise test_execution posture tests) and the dispatched-child path (test_a_dispatched_child_does_not_self_re_evaluate, test_posture_drift_between_child_and_supervisor_blocks_auto, test_a_posture_derived_resume_does_not_end_a_human_rejection, test_a_matching_reference_does_not_authorize_another_gate_or_decision). Outcome 3 omits the apply-time refusal test test_supervised_dispatch::test_unroutable_parked_result_is_refused_before_any_callback and the non-enumerable-gate test. Outcome 6 cites test_delegated_checkpoint for child_start digest verification, but the wrong-token refusal is supervise/test_execution.py::test_child_start_rejects_a_wrong_token_without_touching_the_checkpoint.",
       "resolution": "compact: claimed fix did not take",
       "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 30,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/dispatch-contract/validation-report.md",
+      "fingerprint": "722edcc42b23fd2a",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Outcome 6 describes as future a scan that had already passed when the report was regenerated. PR #662 (roadmap branch to main) merged at 2026-10-10T03:07:43Z as 731557bc (gh api repos/.../pulls/662). The Security workflow's secret-scan job (gitleaks/gitleaks-action@v3, default ruleset via .gitleaks.toml useDefault=true) concluded success on PR #662 heads 0d078ff (the PR #667 merge), 4955e24 (the live multiplayer-collaboration checkpoint migrated to digest-only launch tokens with live attempts), c04a1a8 and 789705a, and on the push to main 731557bc (run 38019470729: secret-scan success). The report was written at 1560d08 (2026-10-10T10:06Z), seven hours later. The .gitleaks.toml commit allowlist exempts only the three raw-token-introducing commits (ddd2c4a8, c6424d74, 3c06430a), not 4955e24, so these runs are real default-ruleset evidence that a committed checkpoint with live attempts passes with no allowlist entry. The same stale statement appears in the Security section (line 155) and the Result line (line 172: 'first runs in PR #662's Security job and must pass there'). The report understates outcome 6 and leaves a confirmation condition open that is already met. \u2014 re-verified resolved in 794b4281",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 31,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/dispatch-contract/validation-report.md",
+      "fingerprint": "3918054b5bd61d53",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Outcome 4 (capability-fingerprint path) cites a test that no longer exists. 765f9d8 renamed it to test_an_approval_resumes_a_member_that_joined_after_the_rejection_only_once_re_projected (skills/tests/autopilot-roadmap/test_dispatch_contract_e2e.py:376) and changed what it asserts: an approval given before re-projection resumes nothing ('early[\"resumed\"] == []'). The report's header says 765f9d8 is in the code under test, but this citation uses the pre-fix name and so describes the pre-fix semantics. The renamed test passes. \u2014 re-verified resolved in 794b4281",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 32,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/dispatch-contract/validation-report.md",
+      "fingerprint": "36f8fd22e4a93864",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The header names the PR #667 review fixes and the post-merge commits as code under test, but the outcome-to-test mapping cites none of the tests they added. Each one bears on a claimed outcome. (a) Outcome 4: 765f9d8's supervise/test_execution.py tests test_a_member_that_parks_after_the_subject_is_not_resumed_by_its_answer, test_a_member_joining_a_human_rejection_is_persisted_before_it_can_be_approved and test_a_human_rejection_answered_before_re_projection_leaves_the_late_member_parked show that a human rejection survives a member joining. (b) Outcome 5: 43a9b11's test_concurrent_resolvers_on_one_fingerprint_are_single_flight (block/auto) shows racing resolvers still yield a single escalation. (c) Outcome 7: b35e544's test_a_cloud_worker_at_the_repo_root_prepares_and_starts, shared/test_dispatch_contract.py::test_harness_provided_isolation_at_the_repo_root_round_trips_as_dot and ::test_a_v1_request_at_the_repo_root_upgrades_to_a_schema_valid_dot_ref cover the portable repo-root isolation ref. (d) Outcome 1 and the gate-answer path: 3a29785 changed dispatch-request.schema.json and the escalate_resume answer, with tests in supervise/test_execution_contract.py, supervise/test_gate_router.py (test_escalate_resume_answer_records_resume_at_validate, test_resume_at_is_refused_unless_an_approved_validate_resume) and autopilot/test_console_interviewer.py. (e) f44bbd6's autopilot/test_goal_gate.py tests are not mentioned. These tests ran inside the whole-suite totals, so the evidence exists, but a reader cannot see from the mapping that the review fixes are proven. \u2014 re-verified resolved in 794b4281",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 33,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/dispatch-contract/validation-report.md",
+      "fingerprint": "af5843e6f87a76c3",
+      "first_seen_round": 2,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The parenthetical run id sits next to head 4955e24, so it reads as the run for that head. Run 37976320517 ran on PR #662 head 789705a. 4955e24 is in that run's PR commit range, so the claim holds, but 4955e24's own Security run is 37974967529 (secret-scan success). A reader checking the run id will see a different head SHA than the sentence implies. The Security section (line 182) repeats 37976320517 without a head.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 34,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/dispatch-contract/validation-report.md",
+      "fingerprint": "3116d20da831bddf",
+      "first_seen_round": 2,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The 'Tests added after IMPL review' block (added in 794b4281) is indented inside item 6 (the secret-scan outcome), yet its bullets cite tests for outcomes 4, 5, 7, 1 and the goal gate, none for outcome 6. A reader of the numbered outcome list attributes those tests to outcome 6.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 35,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/dispatch-contract/validation-report.md",
+      "fingerprint": "e306b2324a21e1bc",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Proposal outcome 5 requires both permission_blocked and capability_unavailable parks to be routed to the operator as single escalations. The report's outcome 5 says only 'capability parks'. The cited tests do cover permission_blocked (supervise/test_execution.py::test_three_workers_blocked_on_one_rule_produce_one_escalation uses _BLOCKED, kind permission_blocked, line 2247; test_concurrent_resolvers_on_one_fingerprint_are_single_flight likewise), and capability_unavailable (test_different_missing_lanes_are_separate_escalations, the e2e capability-park test), but the report never says which test proves which kind, so the permission_blocked half of the outcome is not visibly proved.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 36,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/dispatch-contract/validation-report.md",
+      "fingerprint": "1ac9e5ef7f170064",
+      "first_seen_round": 2,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The kind label added in 0466eab9 under-reports the end-to-end capability-park test. autopilot-roadmap/test_dispatch_contract_e2e.py::test_a_capability_park_is_one_operator_escalation_that_resumes_the_child is parametrized over `park` with ids [\"permission_blocked\", \"capability_unavailable\"] (lines 519-528), so it is the end-to-end proof for both kinds. Labelling it '(capability_unavailable)' only leaves permission_blocked with unit-level citations alone. A reader would conclude it has no end-to-end coverage, but it does.",
+      "consensus_status": "unconfirmed"
     }
   ],
-  "compacted_at": "2026-10-09T14:06:08Z"
+  "compacted_at": "2026-10-10T10:39:43Z"
 }
diff --git a/openspec/changes/dispatch-contract/design.md b/openspec/changes/archive/2026-10-10-dispatch-contract/design.md
similarity index 100%
rename from openspec/changes/dispatch-contract/design.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/design.md
diff --git a/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g2.json b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g2.json
similarity index 100%
rename from openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g2.json
rename to openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g2.json
diff --git a/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g3.json b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g3.json
new file mode 100644
index 00000000..b11c55f7
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g3.json
@@ -0,0 +1,50 @@
+{
+  "attempt": 1,
+  "branch": "openspec/dispatch-contract",
+  "change_id": "dispatch-contract",
+  "degradations": [
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
+    }
+  ],
+  "dispatch_id": "batch-1199bf07b6cb5035d4c22472:ri-21:attempt-1",
+  "evidence": {
+    "commit": "45f9195322bc3f52fc4c18bbb5ce5c98e7a011fd",
+    "loop_state_digest": "b55ce362b3fcfcaf304c6770f1708b4946aed1e852a38c1ae8853a4ab893fb35",
+    "loop_state_path": "openspec/changes/dispatch-contract/loop-state.json"
+  },
+  "host_id": "machine-801452e4fd3b9a26",
+  "lease_generation": 3,
+  "outcome": "parked",
+  "parked": {
+    "deadline": null,
+    "gate": null,
+    "kind": "policy_pause",
+    "reason": "goal gate refused: validate record predates report",
+    "resume_hint": "previous_phase=SUBMIT_PR; answer escalate_resume to resume"
+  },
+  "schema_version": 2,
+  "worktree_ref": null
+}
diff --git a/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g4.json b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g4.json
new file mode 100644
index 00000000..292e7ff3
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g4.json
@@ -0,0 +1,50 @@
+{
+  "attempt": 1,
+  "branch": "openspec/dispatch-contract",
+  "change_id": "dispatch-contract",
+  "degradations": [
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
+    }
+  ],
+  "dispatch_id": "batch-1199bf07b6cb5035d4c22472:ri-21:attempt-1",
+  "evidence": {
+    "commit": "bf613c97b74333336b11927489a1fe51c2d2f136",
+    "loop_state_digest": "20e8fa624f44682cf4064082a5b09393f6b7d09d6f25723024135295a645a2ee",
+    "loop_state_path": "openspec/changes/dispatch-contract/loop-state.json"
+  },
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 4,
+  "outcome": "parked",
+  "parked": {
+    "deadline": null,
+    "gate": null,
+    "kind": "policy_pause",
+    "reason": "goal gate refused: required section not passed: Validation Review (missing)",
+    "resume_hint": "previous_phase=SUBMIT_PR; answer escalate_resume to resume"
+  },
+  "schema_version": 2,
+  "worktree_ref": "dispatch-contract"
+}
diff --git a/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g5.json b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g5.json
new file mode 100644
index 00000000..2b3f4abe
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g5.json
@@ -0,0 +1,54 @@
+{
+  "attempt": 1,
+  "branch": "openspec/dispatch-contract",
+  "change_id": "dispatch-contract",
+  "degradations": [
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
+    }
+  ],
+  "dispatch_id": "batch-1199bf07b6cb5035d4c22472:ri-21:attempt-1",
+  "evidence": {
+    "commit": "ce23762b97c16ef4c1a6847584853e3794af2630",
+    "loop_state_digest": "bbede1b04fad897db34a3e1c77ade71745a334c50e83cf499ba60e86c6310b12",
+    "loop_state_path": "openspec/changes/dispatch-contract/loop-state.json"
+  },
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 5,
+  "outcome": "parked",
+  "parked": {
+    "classifier_reason": "auto-mode classifier denied running the scratchpad converge() driver for VAL_REVIEW (Code from External)",
+    "command": "skills/.venv/bin/python <scratchpad>/vr5d/run_converge.py <worktree> <scratchpad>/vr5d/proto",
+    "deadline": null,
+    "gate": null,
+    "kind": "permission_blocked",
+    "reason": "permission denied for Bash under rule auto-mode-classifier:Code from External",
+    "resume_hint": null,
+    "rule": "auto-mode-classifier:Code from External",
+    "tool": "Bash"
+  },
+  "schema_version": 2,
+  "worktree_ref": "dispatch-contract"
+}
diff --git a/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g6.json b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g6.json
new file mode 100644
index 00000000..5451b0f3
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g6.json
@@ -0,0 +1,50 @@
+{
+  "attempt": 1,
+  "branch": "openspec/dispatch-contract",
+  "change_id": "dispatch-contract",
+  "degradations": [
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
+    }
+  ],
+  "dispatch_id": "batch-1199bf07b6cb5035d4c22472:ri-21:attempt-1",
+  "evidence": {
+    "commit": "38ca63a77d3fa487c6ba00fe84bc4e9a4d23c643",
+    "loop_state_digest": "593d819fa63b21657409442357232f8ee183f931c297bb18ba864a913facff66",
+    "loop_state_path": "openspec/changes/dispatch-contract/loop-state.json"
+  },
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 6,
+  "outcome": "parked",
+  "parked": {
+    "deadline": null,
+    "gate": null,
+    "kind": "policy_pause",
+    "reason": "VAL_REVIEW transitioned to ESCALATE via outcome 'max_iter'",
+    "resume_hint": "previous_phase=VAL_REVIEW; answer escalate_resume to resume"
+  },
+  "schema_version": 2,
+  "worktree_ref": "dispatch-contract"
+}
diff --git a/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g7.json b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g7.json
new file mode 100644
index 00000000..887eb7ea
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g7.json
@@ -0,0 +1,44 @@
+{
+  "attempt": 1,
+  "branch": "openspec/dispatch-contract",
+  "change_id": "dispatch-contract",
+  "degradations": [
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
+    }
+  ],
+  "dispatch_id": "batch-1199bf07b6cb5035d4c22472:ri-21:attempt-1",
+  "evidence": {
+    "commit": "efed26dc52357e73bac37d30ac4f08f035702f0c",
+    "loop_state_digest": "92a866516e214e866ee0e65df42d9b6781ce3011bfbb802201686f85ea6e5ed3",
+    "loop_state_path": "openspec/changes/dispatch-contract/loop-state.json"
+  },
+  "handoff_id": "3913b110-b178-4694-922e-3986082c81aa",
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 7,
+  "outcome": "success",
+  "schema_version": 2,
+  "worktree_ref": "dispatch-contract"
+}
diff --git a/openspec/changes/dispatch-contract/handoffs/eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5.json b/openspec/changes/archive/2026-10-10-dispatch-contract/handoffs/eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5.json
similarity index 100%
rename from openspec/changes/dispatch-contract/handoffs/eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5.json
rename to openspec/changes/archive/2026-10-10-dispatch-contract/handoffs/eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5.json
diff --git a/openspec/changes/dispatch-contract/impl-findings.md b/openspec/changes/archive/2026-10-10-dispatch-contract/impl-findings.md
similarity index 100%
rename from openspec/changes/dispatch-contract/impl-findings.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/impl-findings.md
diff --git a/openspec/changes/archive/2026-10-10-dispatch-contract/loop-state.json b/openspec/changes/archive/2026-10-10-dispatch-contract/loop-state.json
new file mode 100644
index 00000000..01edf4d6
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-dispatch-contract/loop-state.json
@@ -0,0 +1,412 @@
+{
+  "schema_version": 6,
+  "change_id": "dispatch-contract",
+  "current_phase": "DONE",
+  "iteration": 0,
+  "total_iterations": 21,
+  "max_phase_iterations": 3,
+  "findings_trend": [],
+  "blocking_findings": [],
+  "vendor_availability": {},
+  "packages_status": {},
+  "package_authors": {},
+  "implementation_strategy": {},
+  "memory_ids": [],
+  "handoff_ids": [
+    "6166f2e8-de8e-4375-8750-316e09fd34f6",
+    "63b11a2c-616f-4b7a-91a1-c6d1278bde31",
+    "9b138f6d-f5f3-4a7f-99bb-0d3bb6a5e86e",
+    "eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5",
+    "8b3b7d01-452a-498f-9e34-46fdd6ca5e94",
+    "8d309935-3b68-44db-be5c-d6b327ec8c61",
+    "13e77665-feba-4ef3-b28a-a9b61d278135",
+    "8ebe1a5a-c868-49cc-b72d-f6bff31d85e9",
+    "c832cb1d-c7ab-48cb-9285-4f4b037d029a",
+    "c44fffaa-5096-400f-826a-c499391bb89e",
+    "b10c5945-2520-4d5f-8de2-8f76c41ed290",
+    "3913b110-b178-4694-922e-3986082c81aa"
+  ],
+  "phase_history": [
+    {
+      "at": "2026-10-06T09:10:51.641130+00:00",
+      "outcome": "proceed_with_review",
+      "phase": "GATEKEEPER"
+    },
+    {
+      "at": "2026-10-06T09:30:38.405916+00:00",
+      "outcome": "complete",
+      "phase": "PLAN_ITERATE"
+    },
+    {
+      "at": "2026-10-06T11:08:14.058241+00:00",
+      "outcome": "max_iter",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-06T11:08:14.233483+00:00",
+      "note": "capability_unavailable: PLAN_REVIEW requires min_quorum=2; only claude_code is dispatchable (codex listed by --check-vendors but no codex CLI/credential). Quorum not lowered; awaiting operator decision on cloud review lane (GX10/policy/credential). handoff 9b138f6d-f5f3-4a7f-99bb-0d3bb6a5e86e",
+      "outcome": "host_escalate",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-09T07:24:26.295968+00:00",
+      "outcome": "converged",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-09T12:52:59.405442+00:00",
+      "outcome": "complete",
+      "phase": "IMPLEMENT"
+    },
+    {
+      "at": "2026-10-09T13:26:34.431681+00:00",
+      "outcome": "complete",
+      "phase": "IMPL_ITERATE"
+    },
+    {
+      "at": "2026-10-09T13:47:51.835672+00:00",
+      "outcome": "converged",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "at": "2026-10-09T13:55:05.532741+00:00",
+      "outcome": "passed",
+      "phase": "VALIDATE"
+    },
+    {
+      "at": "2026-10-09T14:08:06.250432+00:00",
+      "outcome": "converged",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "at": "2026-10-10T09:52:41.398847+00:00",
+      "note": "Invalid outcome 'created' for phase 'ESCALATE'",
+      "outcome": "transition_failed",
+      "phase": "ESCALATE"
+    },
+    {
+      "at": "2026-10-10T10:06:25.827106+00:00",
+      "outcome": "passed",
+      "phase": "VALIDATE"
+    },
+    {
+      "at": "2026-10-10T10:28:53.285299+00:00",
+      "outcome": "max_iter",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "at": "2026-10-10T10:40:39.663017+00:00",
+      "outcome": "converged",
+      "phase": "VAL_REVIEW"
+    }
+  ],
+  "last_handoff_id": "3913b110-b178-4694-922e-3986082c81aa",
+  "started_at": "2026-10-06T09:08:58.470413+00:00",
+  "phase_started_at": "2026-10-10T10:40:51.107654+00:00",
+  "previous_phase": "VAL_REVIEW",
+  "escalation_reason": "VAL_REVIEW transitioned to ESCALATE via outcome 'max_iter'",
+  "val_review_enabled": true,
+  "cli_review_enabled": true,
+  "error": null,
+  "phase_archetype": null,
+  "force": false,
+  "gate_signals": {},
+  "gate_verdict": "proceed_with_review",
+  "gate_decisions": [
+    {
+      "approval_id": null,
+      "authorizing_disposition": "auto",
+      "default_action": null,
+      "disposition": "auto",
+      "gate": "proposal_approval",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "PLAN",
+      "posture_present": true,
+      "reason": "gate 'proposal_approval' auto-approved by trust posture",
+      "recorded_at": "2026-10-06T09:11:03.554035+00:00",
+      "resolution": "auto",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-09T07:09:02.414788+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator (in-session, 2026-10-09): allowlist launch-nonce commits by SHA, then continue. Review proceeds single-vendor (claude_code) under the dispatch's accepted single_vendor_review degradation.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator (in-session, 2026-10-09): allowlist launch-nonce commits by SHA, then continue. Review proceeds single-vendor (claude_code) under the dispatch's accepted single_vendor_review degradation.",
+      "recorded_at": "2026-10-09T07:09:10.123228+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "auto",
+      "default_action": null,
+      "disposition": "auto",
+      "gate": "pr_creation",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "SUBMIT_PR",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'pr_creation' auto-approved by trust posture",
+      "recorded_at": "2026-10-09T14:08:17.017603+00:00",
+      "resolution": "auto",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "merge",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "SUBMIT_PR",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'merge' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-09T14:09:04.031160+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "merge",
+      "note": "Operator approved merge in supervisor session 2026-10-09 ('merge both 662, 667, 666'); PR #667 merged as 0d078ff by the operator.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "SUBMIT_PR",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": "gate-decision:d2c8df05-dcfb-4133-a9d4-239e812c5620",
+        "source": "human"
+      },
+      "reason": "gate 'merge' approved by the operator \u2014 Operator approved merge in supervisor session 2026-10-09 ('merge both 662, 667, 666'); PR #667 merged as 0d078ff by the operator.",
+      "recorded_at": "2026-10-10T03:10:34.221320+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-10T09:52:54.591188+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator resumed merged item ri-21 in supervisor session 2026-10-10 (decision fb5a1364, a4948ea); goal gate fixed in 1d79737 (VAL_REVIEW binds after VALIDATE).",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": "gate-decision:fb5a1364-f4d7-41ce-b1fb-f385d2261d4d",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator resumed merged item ri-21 in supervisor session 2026-10-10 (decision fb5a1364, a4948ea); goal gate fixed in 1d79737 (VAL_REVIEW binds after VALIDATE).",
+      "recorded_at": "2026-10-10T09:52:57.428960+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-10T10:03:19.475199+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator re-validate decision 724eaee2 (supervisor, 2026-10-10): resume at VALIDATE so VALIDATE + VAL_REVIEW regenerate the report and its Validation Review section.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": "gate-decision:724eaee2-ea65-4edc-a891-f9ece3964707",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator re-validate decision 724eaee2 (supervisor, 2026-10-10): resume at VALIDATE so VALIDATE + VAL_REVIEW regenerate the report and its Validation Review section.",
+      "recorded_at": "2026-10-10T10:03:22.135499+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator chose 'Both' (supervisor 2026-10-10): unblock now; committed converge driver to follow.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "VAL_REVIEW",
+      "posture_present": false,
+      "provenance": {
+        "approval_ref": "gate-decision:1469b3d5-5478-4ab7-9bbd-dd6993bb998e",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator chose 'Both' (supervisor 2026-10-10): unblock now; committed converge driver to follow.",
+      "recorded_at": "2026-10-10T10:19:22.012039+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-10T10:35:34.289707+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator resume after ledger fix 53d94ef (supervisor 2026-10-10, gen 7): re-run VAL_REVIEW with committed agent_lane.py.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": "gate-decision:8afdd0a6-e757-4c12-b9b4-997951ce6463",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator resume after ledger fix 53d94ef (supervisor 2026-10-10, gen 7): re-run VAL_REVIEW with committed agent_lane.py.",
+      "recorded_at": "2026-10-10T10:35:37.210927+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    }
+  ],
+  "pending_gate": null,
+  "goal_gate": {
+    "verdict": "passed",
+    "reason": "all required evidence present",
+    "evidence": {
+      "bound_by": "VAL_REVIEW",
+      "checked_at": "2026-10-10T10:40:51.062457+00:00",
+      "merge_authorized": true,
+      "phase_statuses": {
+        "Spec Compliance": "pass",
+        "Validation Review": "pass"
+      },
+      "pr_url": "https://github.com/jankneumann/agentic-coding-tools/pull/667",
+      "report_mtime": "2026-10-09T14:08:04.183909+00:00",
+      "report_path": "openspec/changes/dispatch-contract/validation-report.md",
+      "report_time": "2026-10-10T10:40:36+00:00",
+      "report_time_source": "commit",
+      "required_sections": [
+        "Spec Compliance",
+        "Validation Review"
+      ],
+      "val_review_at": "2026-10-10T10:40:39.663017+00:00",
+      "validate_at": "2026-10-10T10:06:25.827106+00:00",
+      "validate_outcome": "passed"
+    }
+  },
+  "park": null,
+  "degradations": [
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
+    }
+  ]
+}
diff --git a/openspec/changes/dispatch-contract/plan-findings.md b/openspec/changes/archive/2026-10-10-dispatch-contract/plan-findings.md
similarity index 100%
rename from openspec/changes/dispatch-contract/plan-findings.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/plan-findings.md
diff --git a/openspec/changes/dispatch-contract/proposal.md b/openspec/changes/archive/2026-10-10-dispatch-contract/proposal.md
similarity index 100%
rename from openspec/changes/dispatch-contract/proposal.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/proposal.md
diff --git a/openspec/changes/dispatch-contract/session-log.md b/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md
similarity index 85%
rename from openspec/changes/dispatch-contract/session-log.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md
index c14fcc12..7ea62153 100644
--- a/openspec/changes/dispatch-contract/session-log.md
+++ b/openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md
@@ -299,3 +299,76 @@ VALIDATE passed: spec compliance pass, 0 open tasks, openspec strict valid, ruff
 ### Context
 converge() ran VAL_REVIEW (review_type=implementation, fix_mode=targeted, min_quorum=1 from resolve_quorum_policy, base_ref=origin/openspec/roadmap-multiplayer-collaboration) and converged in round 2 with blocking trend [5, 0]. The critique checked whether validation-report.md proves each ri-21 outcome. Four medium gaps: outcome 6 overstated CI coverage (security.yml runs gitleaks only for main, so this change's PR never triggers it); outcome 4 had no test clearing a posture-derived capability-fingerprint block after a posture flip; outcome 7's cross-host tests shared one repo root; outcome 5 was proven only piecewise. VAL_FIX (inline, claude_code) added three tests and corrected the report. No production code changed. The closure test (outcome 3) was confirmed to enumerate every schema-permitted kind/gate from the schema, independently of ANSWER_PATHS, which is built from the Gate enum.
 
+---
+
+## Phase: Validate (re-validation) (2026-10-10)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Report regenerated, no Validation Review section** `architectural: validation` — VAL_REVIEW writes it next; goal gate binds after VALIDATE
+
+### Completed Work
+- Ran 8 suites in separate processes
+- ruff on 51 changed files
+- openspec validate --strict
+- regenerated validation-report.md
+
+### Next Steps
+- VAL_REVIEW appends ## Validation Review
+
+### Relevant Files
+- `openspec/changes/dispatch-contract/validation-report.md` — regenerated report
+
+### Context
+Re-validation at c83cf40 (gate-decision 724eaee2, gen 5): passed. Spec Compliance pass; 1,747 passed/24 skipped/1 known env-only failure; ruff clean; openspec strict valid; gate_logic action=continue. Outcome 6 caveat stands: only a Python port of gitleaks generic-api-key ran; first real full-ruleset scan is PR #662 Security job. CI DEGRADED (no run for head).
+
+---
+
+## Phase: Validation Review (gen 6) (2026-10-10)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Next Steps
+- Fix review_ledger.compact false-reopen for additive (doc) fixes or let re-verified accept supersede it
+- Fix the two low readability findings
+- Operator decides resume (re-run VAL_REVIEW with committed agent_lane.py after the ledger fix)
+
+### Context
+VAL_REVIEW (operator-approved scratch driver, single_vendor_review) did not converge: stalled after 2 rounds, findings trend [3,4]. Round 1 raised 3 report-only findings (30 medium: outcome 6 now confirmed by real CI secret-scan on PR #662 runs 37976320517/37974967529 and main run 38019470729; 31/32 low citation gaps); all fixed in 794b4281 and re-verified by the reviewer in round 2. Round 2 added 2 low readability findings (run-id attribution next to 4955e24; added-tests block nested under outcome 6). Stall cause: review_ledger.compact() reopens an addressed item whose description tokens are still present in the cited file ('compact: claimed fix did not take'); additive documentation fixes always keep those tokens, so deterministic doc findings can never close. No Validation Review section written; outcome max_iter.
+
+---
+
+## Phase: Validation Review (gen 7) (2026-10-10)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Next Steps
+- SUBMIT_PR (merge already authorized, d2c8df05) -> DONE
+- emit-result gen 7, archive, close-out PR
+
+### Context
+VAL_REVIEW converged in 3 rounds via committed agent_lane.py (ebc08d6) with the ledger fix (53d94ef); claude_code lane only, min_quorum=1 under cloud-container-single-vendor-2026-10-09 (single_vendor_review). Round 1: 3 low report fixes (CI run/head attribution 37974967529@4955e24, 37976320517@789705a, 38019470729@731557b; added-tests block moved out of outcome 6; outcome 5 names permission_blocked and capability_unavailable) in 0466eab9. Round 2: 1 low fix (e2e park test covers both kinds) in 3b7be179. Round 3: no findings. Driver wrote ## Validation Review **Status**: pass; Spec Compliance pass.
+
+---
+
+## Phase: Cleanup (2026-10-10)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Archive on the feature branch, not main** — Supervisor-directed: the archive commit goes to openspec/dispatch-contract with a close-out PR against the roadmap branch, which later lands on main via the roadmap PR.
+2. **No open-task migration** — tasks.md has 0 unchecked items (41 checked).
+
+### Completed Work
+- task-check
+- archive
+- decision-index-regen
+- validate-strict
+
+### Next Steps
+- Close-out PR against openspec/roadmap-multiplayer-collaboration; operator merges
+
+### Context
+Post-merge cleanup for dispatch-contract (ri-21): PR #667 was merged by the operator into openspec/roadmap-multiplayer-collaboration as 0d078ff (rebase/merge chosen by the operator; autopilot never merges). All 41 tasks checked, so no open-task migration; no choices ledger. Loop reached DONE at gen 7 after operator-authorized re-validation (VALIDATE + VAL_REVIEW converged via committed agent_lane.py). Archived the change, regenerated docs/decisions in the same commit; staged rollout N/A (non-deployable skills/schemas change, no feature flag).
+
diff --git a/openspec/changes/dispatch-contract/specs/parallel-infrastructure/spec.md b/openspec/changes/archive/2026-10-10-dispatch-contract/specs/parallel-infrastructure/spec.md
similarity index 100%
rename from openspec/changes/dispatch-contract/specs/parallel-infrastructure/spec.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/specs/parallel-infrastructure/spec.md
diff --git a/openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md b/openspec/changes/archive/2026-10-10-dispatch-contract/specs/roadmap-orchestration/spec.md
similarity index 100%
rename from openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/specs/roadmap-orchestration/spec.md
diff --git a/openspec/changes/dispatch-contract/specs/skill-workflow/spec.md b/openspec/changes/archive/2026-10-10-dispatch-contract/specs/skill-workflow/spec.md
similarity index 100%
rename from openspec/changes/dispatch-contract/specs/skill-workflow/spec.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/specs/skill-workflow/spec.md
diff --git a/openspec/changes/dispatch-contract/specs/supervise/spec.md b/openspec/changes/archive/2026-10-10-dispatch-contract/specs/supervise/spec.md
similarity index 100%
rename from openspec/changes/dispatch-contract/specs/supervise/spec.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/specs/supervise/spec.md
diff --git a/openspec/changes/dispatch-contract/specs/trust-posture/spec.md b/openspec/changes/archive/2026-10-10-dispatch-contract/specs/trust-posture/spec.md
similarity index 100%
rename from openspec/changes/dispatch-contract/specs/trust-posture/spec.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/specs/trust-posture/spec.md
diff --git a/openspec/changes/dispatch-contract/tasks.md b/openspec/changes/archive/2026-10-10-dispatch-contract/tasks.md
similarity index 100%
rename from openspec/changes/dispatch-contract/tasks.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/tasks.md
diff --git a/openspec/changes/dispatch-contract/validation-report.md b/openspec/changes/archive/2026-10-10-dispatch-contract/validation-report.md
similarity index 55%
rename from openspec/changes/dispatch-contract/validation-report.md
rename to openspec/changes/archive/2026-10-10-dispatch-contract/validation-report.md
index 8e6e5433..8b10fd3f 100644
--- a/openspec/changes/dispatch-contract/validation-report.md
+++ b/openspec/changes/archive/2026-10-10-dispatch-contract/validation-report.md
@@ -1,8 +1,17 @@
 # Validation Report: dispatch-contract
 
-**Date**: 2026-10-09
-**Commit**: 7cc9180c3ea49a0a9b08618d376bf0c2793bdccc (VALIDATE); counts and evidence refreshed in VAL_REVIEW at df3b98e
-**Branch**: openspec/dispatch-contract
+**Date**: 2026-10-10
+**Commit**: c83cf40 (branch head on origin; re-validation, operator gate-decision 724eaee2, lease generation 5)
+**Branch**: openspec/dispatch-contract (merged via PR #667 as 0d078ff)
+
+This report was regenerated against the current head. It supersedes the 2026-10-09 report (VALIDATE at 7cc9180,
+VAL_REVIEW at df3b98e). Code under test now includes the PR #667 review fixes (765f9d8 resume only the recorded
+escalation subject's dispatches; b35e544 keep a repo-root harness isolation as the portable ref "."; 43a9b11
+single-flight capability/permission park resolution; 6a0a096 records them), the post-merge fixes 4955e24
+(digest-only launch tokens in the live checkpoint), c04a1a8 (accept an already-migrated live checkpoint),
+789705a (verified isolation mode in the attempt profile), and the cherry-picked goal-gate fix f44bbd6 (goal gate binds
+to the report's last writer and commit time, so VAL_REVIEW binds after VALIDATE) and resume-at-VALIDATE commits
+(3a29785, c83cf40).
 
 Scope: skills scripts, shared libraries, and JSON schemas only. There is no deployable
 service (no docker-compose, agent-coordinator/, packages/ or apps/ path changed; the only
@@ -19,9 +28,9 @@ phases are therefore not applicable, not skipped.
 - Architecture: not run (advisory; no service/graph consumer touched)
 - Task drift: pass (0 unchecked boxes in tasks.md)
 - OpenSpec: pass (`openspec validate dispatch-contract --strict`: valid)
-- Lint: pass (`ruff check` on every changed Python file/dir: all checks passed)
-- Test suites: pass except the known environment-only failure (see Spec Compliance)
-- CI/CD: DEGRADED (not checked; GitHub MCP lists zero workflow runs for branch openspec/dispatch-contract and no PR exists yet)
+- Lint: pass (`ruff check` on all 51 Python files changed since base bdb0048: all checks passed)
+- Test suites: pass except the known environment-only failure (see Spec Compliance); worktree, cleanup-feature and validate-feature suites not run (not touched; environment-only failures identical at base)
+- CI/CD: DEGRADED (not applicable to this head: GitHub lists exactly one run for branch openspec/dispatch-contract, CI #2056 on 2e45ea7, the pre-merge PR head, conclusion success; no run exists for c83cf40)
 - Choices: no ledger
 
 ## Spec Compliance
@@ -32,18 +41,21 @@ Per-directory results (each `skills/tests/<dir>` run in its own process, base-in
 
 | Suite | Result |
 |---|---|
-| skills/tests/autopilot | 533 passed, 6 skipped |
-| skills/tests/autopilot-roadmap | 146 passed |
+| skills/tests/autopilot | 544 passed, 6 skipped |
+| skills/tests/autopilot-roadmap | 147 passed |
 | skills/tests/install_sh | 18 passed, 14 skipped |
 | skills/tests/parallel-infrastructure | 292 passed, 2 skipped |
 | skills/tests/roadmap-runtime | 182 passed, 1 skipped |
-| skills/tests/shared | 134 passed, 1 skipped |
-| skills/tests/supervise | 459 passed, 1 failed (known) |
-| skills/autopilot/scripts/tests/test_autopilot.py | 48 passed |
+| skills/tests/shared | 136 passed, 1 skipped |
+| skills/tests/supervise | 469 passed, 1 failed (known) |
+| skills/autopilot/scripts/tests | 227 passed |
+
+Totals: 1,747 passed, 24 skipped, 1 failed (known environment-only). The two project-context-refresh
+shared-checkout tests are outside the touched suites and were not run. `openspec validate dispatch-contract --strict`: valid.
 
 The single failure is the documented environment-only
 `test_workflow_contract.py::test_contract_inspects_the_canonical_source_contribution`
-(fails identically at base bdb0048 when run under a `.claude/` path). No other failures.
+(fails identically at base bdb0048 when run under a `.claude/` path; this run is under `.claude/worktrees/`). No other failures.
 
 ### Acceptance outcome to test mapping (proposal.md, ri-21)
 
@@ -82,18 +94,20 @@ The single failure is the documented environment-only
    - Capability fingerprint (escalate_resume): `autopilot-roadmap/test_dispatch_contract_e2e.py`
      (`test_a_posture_derived_capability_block_clears_after_a_posture_flip`, added in VAL_REVIEW;
      `test_a_human_rejected_escalation_is_not_cleared_when_its_membership_changes`,
-     `test_an_operator_approval_ends_a_human_rejected_escalation`, `test_an_approval_resumes_a_member_that_joined_after_the_rejection`).
-5. execution_profile, review_requirements, degradations[] carried end to end; capability parks routed as single escalations: pass.
+     `test_an_operator_approval_ends_a_human_rejected_escalation`, `test_an_approval_resumes_a_member_that_joined_after_the_rejection_only_once_re_projected`, renamed in 765f9d8: an approval given before re-projection resumes nothing).
+5. execution_profile, review_requirements, degradations[] carried end to end; permission_blocked and capability_unavailable
+   parks each routed to the operator as a single escalation: pass.
    End to end: `autopilot-roadmap/test_dispatch_contract_e2e.py::test_profile_and_degradations_travel_the_whole_chain`
-   (added in VAL_REVIEW: request, launch marker, `runner.py record-degradation`, emit-result, apply, attempt record and
-   apply return value) and `::test_a_capability_park_is_one_operator_escalation_that_resumes_the_child`.
+   (request, launch marker, `runner.py record-degradation`, emit-result, apply, attempt record and
+   apply return value) and `::test_a_capability_park_is_one_operator_escalation_that_resumes_the_child` (parametrized over both kinds: permission_blocked and capability_unavailable).
    Units: `autopilot/test_emit_result.py::test_degradations_travel_into_the_result`,
    `supervise/test_execution.py` (`test_a_marker_carries_the_supervisor_view_but_no_token`, `test_apply_persists_degradations_on_the_attempt`,
-   `test_three_workers_blocked_on_one_rule_produce_one_escalation`, `test_different_missing_lanes_are_separate_escalations`),
+   `test_three_workers_blocked_on_one_rule_produce_one_escalation` (permission_blocked: one escalation per rule),
+   `test_different_missing_lanes_are_separate_escalations` (capability_unavailable: one escalation per missing-lane set)),
    `autopilot/test_quorum_park.py`, `autopilot/test_convergence_loop.py`,
    `parallel-infrastructure/test_check_vendors_dispatchable.py`, `parallel-infrastructure/test_review_packet.py`.
-6. checkpoint.json stores no raw launch token; default secret scan passes with no allowlist entry: pass locally by a
-   one-rule proxy; the real default-ruleset scan has not run.
+6. checkpoint.json stores no raw launch token; default secret scan passes with no allowlist entry: pass, confirmed by
+   the real default-ruleset gitleaks scan in CI (see the CI confirmation below), plus the local one-rule proxy.
    `roadmap-runtime/test_landable_checkpoint.py`: `test_the_fixture_has_live_attempts_and_no_raw_token`,
    `test_the_default_generic_api_key_rule_finds_nothing` (Python port of the default gitleaks
    generic-api-key rule: keyword prefilter, regex, entropy > 3.5, applied to the committed-shape
@@ -107,11 +121,16 @@ The single failure is the documented environment-only
    Limits of this evidence: only gitleaks' `generic-api-key` rule is ported (the rule that flagged the raw
    tokens on PR #662); the other default rules were not applied locally.
    NOT RUN: `test_gitleaks_scan_of_the_fixture_directory_is_clean` (skipped: gitleaks binary not
-   installed; binaries must not be downloaded). No CI run covers it yet either: `.github/workflows/security.yml`
+   installed; binaries must not be downloaded). This change's own PR did not run it: `.github/workflows/security.yml`
    runs gitleaks only on pushes to `main` and on pull requests / merge groups targeting `main`. This change's PR
    targets `openspec/roadmap-multiplayer-collaboration`, so it does not trigger that job. The first real
-   default-ruleset scan of these commits is the Security workflow on PR #662 (roadmap branch to `main`). Treat
-   outcome 6 as confirmed only once that job passes.
+   default-ruleset scan of these commits is the Security workflow on PR #662 (roadmap branch to `main`).
+   CI confirmation (verified in VAL_REVIEW, generation 6): the Security workflow's `secret-scan` job (full default
+   gitleaks ruleset) passed on PR #662: at head 4955e24, where the live checkpoint was migrated to digest-only with live
+   attempts (run 37974967529, success), and at the final PR head 789705a (run 37976320517, success); and again on the push to `main` after PR #662 merged as
+   731557b (run 38019470729). `.gitleaks.toml` exempts only the three historical raw-token commits by SHA
+   (ddd2c4a, c6424d7, 3c06430); it has no entry for 4955e24, the digest-only checkpoint or the fixture, so the pass
+   needed no allowlist help.
 7. Checkpoint with live attempts committed on one host reconciles on another: pass.
    `roadmap-runtime/test_cross_host_reconcile.py` (8 tests: rebind of matching worktree, refusal on diverged worktree / digest mismatch,
    reinitialize of prepared attempt, unexpired vs expired pre-go claim, post-go unknown liveness quarantined, and
@@ -122,6 +141,40 @@ The single failure is the documented environment-only
    `autopilot-roadmap/test_dispatch_contract_e2e.py::test_a_dispatched_child_with_a_marker_ref_takes_scoped_auto`,
    `::test_a_standalone_run_blocks_with_scope_unscoped`.
 
+**Tests added after IMPL review** (PR #667 review fixes and post-merge commits; counted in the suite totals above, listed by the outcome they prove):
+
+- Outcome 4, late members never ride an earlier answer (765f9d8): `supervise/test_execution.py`
+  (`test_a_member_that_parks_after_the_subject_is_not_resumed_by_its_answer`,
+  `test_a_member_joining_a_human_rejection_is_persisted_before_it_can_be_approved`,
+  `test_a_human_rejection_answered_before_re_projection_leaves_the_late_member_parked`).
+- Outcome 5, one escalation per fingerprint under concurrency (43a9b11):
+  `supervise/test_execution.py::test_concurrent_resolvers_on_one_fingerprint_are_single_flight` (permission_blocked fingerprint, block and auto postures).
+- Outcome 7, repo-root harness isolation stays portable as `"."` (b35e544):
+  `shared/test_dispatch_contract.py` (`test_harness_provided_isolation_at_the_repo_root_round_trips_as_dot`,
+  `test_a_v1_request_at_the_repo_root_upgrades_to_a_schema_valid_dot_ref`),
+  `autopilot-roadmap/test_dispatch_contract_e2e.py::test_a_cloud_worker_at_the_repo_root_prepares_and_starts`.
+- Outcome 1, operator-approved resume at VALIDATE (3a29785): `supervise/test_execution_contract.py`
+  (`test_gate_answer_may_name_validate_as_the_resume_target`, `test_the_continuation_answer_carries_the_recorded_resume_target`),
+  `supervise/test_gate_router.py` (`test_escalate_resume_answer_records_resume_at_validate`,
+  `test_resume_at_is_refused_unless_an_approved_validate_resume`), `autopilot/test_console_interviewer.py`
+  (`test_resume_at_validate_reruns_validation_instead_of_the_parked_phase`, `test_without_resume_at_the_parked_phase_resumes`,
+  `test_resume_at_is_refused_outside_an_approved_escalate_resume`).
+- Goal gate bound to the report's last writer and commit time (f44bbd6): `autopilot/test_goal_gate.py`
+  (`test_converged_val_review_binds_a_report_it_appended_to`, `test_unconverged_val_review_does_not_bind`,
+  `test_val_review_before_the_latest_validate_does_not_bind`, `test_val_review_does_not_bind_when_disabled`,
+  `test_a_committed_unmodified_report_is_timed_by_its_commit`, `test_a_report_committed_after_validation_is_stale`,
+  `test_an_uncommitted_edit_falls_back_to_mtime`).
+
+## Deploy
+
+**Status**: N/A
+Reason: work-packages.yaml `feature.deployable: false`; no service to deploy.
+
+## CI/CD
+
+**Status**: DEGRADED
+Reason: no CI run exists for branch head c83cf40. The only run for the branch is CI #2056 on 2e45ea7 (success, pre-merge PR head). Local suites above are the evidence.
+
 ## Smoke Tests
 
 **Status**: not applicable
@@ -130,7 +183,7 @@ Reason: skills/schemas-only change, no running service to smoke test.
 ## Security
 
 **Status**: not applicable
-Reason: no deployable surface for ZAP/dependency-check. Secret-scan evidence for the changed checkpoint shape is in Spec Compliance outcome 6; the real gitleaks binary was not available locally, and the Security workflow runs only for `main` (push or PR), so the first real scan is PR #662's Security job.
+Reason: no deployable surface for ZAP/dependency-check. Secret-scan evidence for the changed checkpoint shape is in Spec Compliance outcome 6; the real gitleaks binary was not available locally; the Security workflow (which runs only for `main`, push or PR) has since passed its `secret-scan` job on PR #662 (run 37974967529 at head 4955e24, run 37976320517 at head 789705a) and on the push to `main` at 731557b (run 38019470729).
 
 ## E2E Tests
 
@@ -141,8 +194,19 @@ Reason: no browser or service surface.
 
 - single_vendor_review: PLAN_REVIEW, IMPL_REVIEW and VAL_REVIEW ran claude_code only (cloud-container policy, min_quorum=1).
 - coordinator_projection_forbidden: coordinator queue projection returned forbidden (expected in this environment).
+- audit_sink_failed: audit sink failed for the proposal_approval, escalate_resume, pr_creation and merge gate decisions (SUBMIT_PR).
 - GATEKEEPER ran via a real judge (no degradation).
+- Re-validation: no new reviewer was dispatched in this VALIDATE run; VAL_REVIEW runs next and appends its own section.
 
 ## Result
 
-**PASS** — All eight acceptance outcomes are covered by passing tests. Outcome 6's secret-scan claim rests on a one-rule port locally; the real default-ruleset gitleaks scan first runs in PR #662's Security job and must pass there before the claim is confirmed. Other not-run items are recorded above (CI status, live-service phases). Ready for `/cleanup-feature dispatch-contract`.
+**PASS** (re-validation at c83cf40) — All eight acceptance outcomes are covered by passing tests. Outcome 6 is confirmed by the real default-ruleset gitleaks `secret-scan` job, which passed on PR #662 and on `main` with no allowlist entry for the digest-only checkpoint; locally it rests on a one-rule port. Other not-run items are recorded above (CI status, live-service phases). The change is already merged (PR #667, 0d078ff); this report exists so the goal gate can bind VAL_REVIEW after VALIDATE.
+
+## Validation Review
+
+**Status**: pass
+
+- Result: converged in 3 round(s) via `agent_lane.py converge`.
+- Lanes: `claude_code` only (min_quorum=1).
+- Degradation: `single_vendor_review` under quorum policy `cloud-container-single-vendor-2026-10-09`.
+- Summary: {'total_unique_findings': 0, 'confirmed_count': 0, 'unconfirmed_count': 0, 'disagreement_count': 0, 'blocking_count': 0, 'advisory_count': 0}
diff --git a/openspec/changes/dispatch-contract/work-packages.yaml b/openspec/changes/archive/2026-10-10-dispatch-contract/work-packages.yaml
similarity index 100%
rename from openspec/changes/dispatch-contract/work-packages.yaml
rename to openspec/changes/archive/2026-10-10-dispatch-contract/work-packages.yaml
diff --git a/openspec/changes/multiplayer-principles-guide/.review-ledger/ledger.json b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/.review-ledger/ledger.json
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/.review-ledger/ledger.json
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/.review-ledger/ledger.json
diff --git a/openspec/changes/multiplayer-principles-guide/design.md b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/design.md
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/design.md
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/design.md
diff --git a/openspec/changes/multiplayer-principles-guide/loop-state.json b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/loop-state.json
similarity index 69%
rename from openspec/changes/multiplayer-principles-guide/loop-state.json
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/loop-state.json
index 6ced0475..6e233a3c 100644
--- a/openspec/changes/multiplayer-principles-guide/loop-state.json
+++ b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/loop-state.json
@@ -1,9 +1,9 @@
 {
-  "schema_version": 5,
+  "schema_version": 6,
   "change_id": "multiplayer-principles-guide",
-  "current_phase": "SUBMIT_PR",
+  "current_phase": "DONE",
   "iteration": 0,
-  "total_iterations": 15,
+  "total_iterations": 18,
   "max_phase_iterations": 3,
   "findings_trend": [],
   "blocking_findings": [],
@@ -20,7 +20,8 @@
     "0d93042b-2da5-42ce-99ec-50e7880ce78d",
     "ff647b09-6f37-4515-beaf-edee4599dcba",
     "323b6f25-0e3d-48b8-b5aa-919b8fa7957c",
-    "b78e5326-fe14-4111-80f9-ac7c4466123a"
+    "b78e5326-fe14-4111-80f9-ac7c4466123a",
+    "0b4dc20a-e3d6-468b-8d9f-d3c3f9752725"
   ],
   "phase_history": [
     {
@@ -68,17 +69,22 @@
       "at": "2026-10-09T08:30:21.741688+00:00",
       "outcome": "passed",
       "phase": "VALIDATE"
+    },
+    {
+      "at": "2026-10-10T09:58:22.377550+00:00",
+      "outcome": "passed",
+      "phase": "VALIDATE"
     }
   ],
-  "last_handoff_id": "b78e5326-fe14-4111-80f9-ac7c4466123a",
+  "last_handoff_id": "0b4dc20a-e3d6-468b-8d9f-d3c3f9752725",
   "started_at": "2026-10-05T07:03:40.733622+00:00",
-  "phase_started_at": "2026-10-09T12:16:46.494024+00:00",
+  "phase_started_at": "2026-10-10T09:58:22.637839+00:00",
   "previous_phase": "SUBMIT_PR",
-  "escalation_reason": "pr_creation: coordinator_unreachable \u2014 gate 'pr_creation' parked: coordinator unreachable (request_approval failed: coordinator unauthorized (status=403))",
+  "escalation_reason": "goal gate refused: required section not passed: Spec Compliance (missing)",
   "val_review_enabled": false,
   "cli_review_enabled": true,
   "error": null,
-  "phase_archetype": "runner",
+  "phase_archetype": "validator",
   "force": false,
   "gate_signals": {
     "external_dep_count": 0,
@@ -188,83 +194,145 @@
       "timeout_seconds": null
     },
     {
-      "gate": "pr_creation",
-      "outcome": "blocked",
-      "resolution": "coordinator_unreachable",
+      "approval_id": null,
       "authorizing_disposition": "notify_with_timeout",
-      "reason": "gate 'pr_creation' parked: coordinator unreachable (request_approval failed: coordinator unauthorized (status=403))",
-      "approval_id": null,
       "default_action": null,
-      "posture_present": true,
-      "notified": null,
-      "timeout_seconds": null,
       "disposition": "notify_with_timeout",
+      "gate": "pr_creation",
+      "notified": null,
+      "outcome": "blocked",
       "phase": "SUBMIT_PR",
-      "recorded_at": "2026-10-09T12:16:18.411838+00:00"
+      "posture_present": true,
+      "reason": "gate 'pr_creation' parked: coordinator unreachable (request_approval failed: coordinator unauthorized (status=403))",
+      "recorded_at": "2026-10-09T12:16:18.411838+00:00",
+      "resolution": "coordinator_unreachable",
+      "timeout_seconds": null
     },
     {
-      "gate": "escalate_resume",
-      "outcome": "blocked",
-      "resolution": "posture_block",
+      "approval_id": null,
       "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
       "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
-      "approval_id": null,
-      "default_action": null,
-      "posture_present": true,
-      "notified": null,
-      "timeout_seconds": null,
-      "disposition": "block",
-      "phase": "ESCALATE",
-      "recorded_at": "2026-10-09T12:16:46.292366+00:00"
-    },
-    {
-      "gate": "escalate_resume",
-      "outcome": "proceed",
-      "resolution": "console_approved",
-      "authorizing_disposition": "block",
-      "reason": "gate 'escalate_resume' approved by the operator \u2014 User (session owner) 2026-10-09 answered 'Approve PR now' to the pr_creation gate question. The pr_creation gate cannot record through the coordinator in this container (request_approval 403 forbidden); this console decision is the recorded authorization for opening the stacked PR. Merge stays block.",
-      "approval_id": null,
-      "default_action": null,
-      "posture_present": true,
-      "notified": null,
-      "timeout_seconds": null,
-      "disposition": "block",
-      "phase": "ESCALATE",
-      "recorded_at": "2026-10-09T12:16:46.493945+00:00",
-      "note": "User (session owner) 2026-10-09 answered 'Approve PR now' to the pr_creation gate question. The pr_creation gate cannot record through the coordinator in this container (request_approval 403 forbidden); this console decision is the recorded authorization for opening the stacked PR. Merge stays block."
-    },
-    {
-      "gate": "merge",
-      "outcome": "blocked",
+      "recorded_at": "2026-10-09T12:16:46.292366+00:00",
       "resolution": "posture_block",
-      "authorizing_disposition": "block",
-      "reason": "gate 'merge' parked: trust posture disposition is block",
+      "timeout_seconds": null
+    },
+    {
       "approval_id": null,
+      "authorizing_disposition": "block",
       "default_action": null,
-      "posture_present": true,
-      "notified": null,
-      "timeout_seconds": null,
       "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "User (session owner) 2026-10-09 answered 'Approve PR now' to the pr_creation gate question. The pr_creation gate cannot record through the coordinator in this container (request_approval 403 forbidden); this console decision is the recorded authorization for opening the stacked PR. Merge stays block.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 User (session owner) 2026-10-09 answered 'Approve PR now' to the pr_creation gate question. The pr_creation gate cannot record through the coordinator in this container (request_approval 403 forbidden); this console decision is the recorded authorization for opening the stacked PR. Merge stays block.",
+      "recorded_at": "2026-10-09T12:16:46.493945+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "merge",
+      "notified": null,
+      "outcome": "blocked",
       "phase": "SUBMIT_PR",
-      "recorded_at": "2026-10-09T12:17:28.246464+00:00"
+      "posture_present": true,
+      "reason": "gate 'merge' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-09T12:17:28.246464+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "merge",
+      "note": "User (session owner) 2026-10-10: 'Approving merge'. PR #666 was already merged by jankneumann at 2026-10-09T18:39:50Z (head 9dcc24f, 24/24 checks green).",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "SUBMIT_PR",
+      "posture_present": true,
+      "reason": "gate 'merge' approved by the operator \u2014 User (session owner) 2026-10-10: 'Approving merge'. PR #666 was already merged by jankneumann at 2026-10-09T18:39:50Z (head 9dcc24f, 24/24 checks green).",
+      "recorded_at": "2026-10-10T03:07:07.019853+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-10T09:52:19.441066+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "User (session owner) 2026-10-10 chose 'Follow up': regenerate validation-report.md in validate-feature section format, declare deployable: false (docs-only), record a fresh VALIDATE, then DONE + archive. Branch restarted from openspec/roadmap-multiplayer-collaboration (PR #666 merged as f5557f4).",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": null,
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 User (session owner) 2026-10-10 chose 'Follow up': regenerate validation-report.md in validate-feature section format, declare deployable: false (docs-only), record a fresh VALIDATE, then DONE + archive. Branch restarted from openspec/roadmap-multiplayer-collaboration (PR #666 merged as f5557f4).",
+      "recorded_at": "2026-10-10T09:52:19.684134+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
     }
   ],
-  "pending_gate": {
-    "schema_version": 1,
-    "change_id": "multiplayer-principles-guide",
-    "gate": "merge",
-    "phase": "SUBMIT_PR",
-    "requested_at": "2026-10-09T12:17:28.247738+00:00",
-    "prompt": "Authorize merging this pull request? (autopilot records the authorization only; /cleanup-feature merges)",
-    "context": {
+  "pending_gate": null,
+  "goal_gate": {
+    "verdict": "passed",
+    "reason": "all required evidence present",
+    "evidence": {
+      "checked_at": "2026-10-10T09:58:22.612560+00:00",
+      "merge_authorized": true,
+      "phase_statuses": {
+        "Spec Compliance": "pass"
+      },
       "pr_url": "https://github.com/jankneumann/agentic-coding-tools/pull/666",
-      "branch": "openspec/multiplayer-principles-guide",
-      "change_id": "multiplayer-principles-guide"
-    },
-    "posture": {
-      "disposition": "block",
-      "posture_present": true
+      "report_mtime": "2026-10-09T08:30:13.420114+00:00",
+      "report_path": "openspec/changes/multiplayer-principles-guide/validation-report.md",
+      "required_sections": [
+        "Spec Compliance"
+      ],
+      "validate_at": "2026-10-10T09:58:22.377550+00:00",
+      "validate_outcome": "passed",
+      "report_time": "2026-10-10T09:58:07+00:00",
+      "report_time_source": "commit",
+      "bound_by": "VALIDATE"
     }
   },
-  "goal_gate": null
+  "park": null,
+  "degradations": []
 }
diff --git a/openspec/changes/multiplayer-principles-guide/plan-findings.md b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/plan-findings.md
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/plan-findings.md
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/plan-findings.md
diff --git a/openspec/changes/multiplayer-principles-guide/proposal.md b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/proposal.md
similarity index 99%
rename from openspec/changes/multiplayer-principles-guide/proposal.md
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/proposal.md
index adee477d..9646173b 100644
--- a/openspec/changes/multiplayer-principles-guide/proposal.md
+++ b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/proposal.md
@@ -1,3 +1,7 @@
+---
+deployable: false
+---
+
 # Publish the multiplayer collaboration principles guide
 
 > Parent roadmap: `multiplayer-collaboration` (item `ri-01`)
diff --git a/openspec/changes/multiplayer-principles-guide/review-findings-plan.json b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/review-findings-plan.json
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/review-findings-plan.json
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/review-findings-plan.json
diff --git a/openspec/changes/multiplayer-principles-guide/reviews/consensus-plan.json b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/consensus-plan.json
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/reviews/consensus-plan.json
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/consensus-plan.json
diff --git a/openspec/changes/multiplayer-principles-guide/reviews/raw-codex-plan.meta.json b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/raw-codex-plan.meta.json
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/reviews/raw-codex-plan.meta.json
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/raw-codex-plan.meta.json
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/raw-codex-plan.txt b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/raw-codex-plan.txt
new file mode 100644
index 00000000..e69de29b
diff --git a/openspec/changes/multiplayer-principles-guide/reviews/review-manifest.json b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/review-manifest.json
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/reviews/review-manifest.json
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/review-manifest.json
diff --git a/openspec/changes/multiplayer-principles-guide/reviews/review-prompt.md b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/review-prompt.md
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/reviews/review-prompt.md
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/review-prompt.md
diff --git a/openspec/changes/multiplayer-principles-guide/session-log.md b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md
similarity index 87%
rename from openspec/changes/multiplayer-principles-guide/session-log.md
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md
index 660012f2..dade1e50 100644
--- a/openspec/changes/multiplayer-principles-guide/session-log.md
+++ b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md
@@ -196,3 +196,47 @@ IMPL_REVIEW ran converge(review_type=implementation, max_rounds=3, min_quorum=1,
 ### Context
 VALIDATE PASS (docs-only): spec valid strict, 1706 tests pass, security clean; deploy/smoke/e2e skipped. DEGRADED: GATEKEEPER signal-only, PLAN_REVIEW and IMPL_REVIEW single_vendor_review (claude_code).
 
+---
+
+## Phase: Validate (2026-10-10)
+
+**Agent**: validator | **Session**: N/A
+
+### Completed Work
+- openspec validate --strict
+- pytest 1722 passed
+- diff secret scan
+- validation-report.md rewritten with Spec Compliance Status pass
+
+### Next Steps
+- DONE gate
+- archive
+
+### Context
+VALIDATE PASS (docs-only, deployable false): report rewritten in validate-feature section format; Spec Compliance pass; required phases resolve to Spec Compliance only; openspec strict valid; 1722 tests pass; diff secret scan clean. DEGRADED: GATEKEEPER signal-only, PLAN_REVIEW and IMPL_REVIEW single_vendor_review (claude_code).
+
+---
+
+## Phase: Cleanup (2026-10-10)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Post-merge mode; no merge executed** — The operator merged PR #666 on 2026-10-09 and approved the merge gate; autopilot and cleanup never merge.
+2. **No task migration** — tasks.md has 6/6 tasks checked; no open tasks to move to issues or a follow-up proposal.
+3. **Staged rollout and pre-launch checklist not applicable** — Docs-only change (proposal declares deployable: false): a guide, a guard test, two links, and a testpaths entry. There is no service, feature flag, or traffic to stage. CI was green on head 9dcc24f (24/24 checks).
+4. **Branch restarted from roadmap base for the follow-up** — The merged branch was restarted from openspec/roadmap-multiplayer-collaboration (a fast-forward of the merged head) to fix the validation-report format that the DONE goal gate refused; loop reached DONE at c0d2750.
+
+### Completed Work
+- task-migration (none needed)
+- archive
+- spec-sync
+- decision-index
+
+### Next Steps
+- Operator merges the archive PR into openspec/roadmap-multiplayer-collaboration
+- ri-02 ownership-map confirms or amends the solo-mode definition (design D2)
+
+### Context
+Post-merge cleanup: PR #666 was merged into openspec/roadmap-multiplayer-collaboration as f5557f4 by the operator, so no merge ran here. All 6 tasks were complete, so nothing was migrated. The change is archived with its spec delta merged, and the decision index regenerated in the same commit.
+
diff --git a/openspec/changes/multiplayer-principles-guide/specs/multiplayer-collaboration/spec.md b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/specs/multiplayer-collaboration/spec.md
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/specs/multiplayer-collaboration/spec.md
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/specs/multiplayer-collaboration/spec.md
diff --git a/openspec/changes/multiplayer-principles-guide/tasks.md b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/tasks.md
similarity index 100%
rename from openspec/changes/multiplayer-principles-guide/tasks.md
rename to openspec/changes/archive/2026-10-10-multiplayer-principles-guide/tasks.md
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/validation-report.md b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/validation-report.md
new file mode 100644
index 00000000..0cbc0b77
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-principles-guide/validation-report.md
@@ -0,0 +1,52 @@
+# Validation Report: multiplayer-principles-guide
+
+**Date**: 2026-10-10
+**Commit**: d565671 (origin/openspec/multiplayer-principles-guide)
+**Scope**: docs-only (guide, guard test, two inbound links, testpaths entry). `proposal.md` declares `deployable: false`.
+
+## Required Phases
+
+`gate_logic.resolve_required_phases(None, change_dir=<change dir>)` returns only `{'Spec Compliance': 'Spec compliance'}`. Smoke Tests, Security and E2E Tests are not required for a non-deployable change.
+
+## Degraded Status
+- GATEKEEPER: DEGRADED (signal-only fallback on attempt 0)
+- PLAN_REVIEW: DEGRADED `single_vendor_review` (claude_code only; codex auth_required)
+- IMPL_REVIEW: DEGRADED `single_vendor_review` (claude_code only)
+- Single-vendor policy approved by session owner (gate-decision:e49a71df-6e23-4937-816e-4e4f39d3eaff). Human merge gate remains block.
+
+## Spec Compliance
+
+**Status**: pass
+
+`openspec validate multiplayer-principles-guide --strict` reports the change valid. All 7 requirements and their scenarios map to guide sections and guard-test cases. Inbound links are present in AGENTS.md and docs/guides/documentation.md, and the testpaths entry is registered.
+
+## Evidence Completeness
+
+**Status**: pass
+
+`cd skills && uv run pytest tests/multiplayer-collaboration tests/docs tests/ci_coverage tests/openspec_paths`: 1722 passed.
+
+## Smoke Tests
+
+**Status**: skipped
+
+No service to deploy; docs-only change (`deployable: false`).
+
+## Security
+
+**Status**: skipped
+
+Not required for a non-deployable change. Informational diff scan for secrets and credentials (AWS keys, private keys, GitHub and API tokens) over the branch diff found none.
+
+## E2E Tests
+
+**Status**: skipped
+
+No service or UI; docs-only change (`deployable: false`).
+
+## Open Items (non-blocking)
+- session-log.md "Plan Iteration 1" Context paragraph contains a `[REDACTED:high-entropy]` sanitizer artifact and an orphaned list item (IMPL_REVIEW Medium #5). Not repaired: the redacted span is lost and not recoverable from the tree. Needs operator decision.
+- Other IMPL_REVIEW open questions (roadmap bootstrap on branch, TRUST_POSTURE citation, per-skill trailer attribution, spec wording clause) remain as logged.
+
+## Result
+**PASS**
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/.review-ledger/ledger.json b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/.review-ledger/ledger.json
new file mode 100644
index 00000000..8b05d5b5
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/.review-ledger/ledger.json
@@ -0,0 +1,534 @@
+{
+  "schema_version": 1,
+  "change_id": "multiplayer-simulation-harness",
+  "items": [
+    {
+      "id": 1,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "high",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "spec_file": "openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "325719d4e87ae6c4",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The memory-store scenario's readiness input is under-specified. D7 has every ScriptedAgent push to its own branch `refs/heads/sim/<principal>/<change>`, and D5 says each step's `set_status` edit to `roadmap.yaml` is committed and pushed by that principal. With two principals editing the same `roadmap.yaml` on two different branches, there is no single \"roadmap.yaml currently visible on the shared remote\" (spec wording) for `Roadmap.ready_items()` to evaluate: storage-owner's `completed` lives on `sim/storage-owner/sim-memory-store-core`, retrieval-owner's `approved` item on its own branch, and `main` still holds the seed. The scheduler must either (a) read the dependency item's status from the owner's branch and merge per-item statuses, or (b) have status transitions pushed to `main` (modelling a checkpoint commit). Each choice changes what task 5.2 implements, what the fixture must look like, and what ri-11's flip has to touch. State the chosen ref model in D5/D7 and in the Memory-Store requirement text, and reflect it in task 5.1/5.2.",
+      "resolution": "operator decision A1 (escalate_resume 2026-10-05) applied in PLAN_FIX fe0b333: D5/D7 integration ref = shared remote main, sim-supervisor status applier",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 2,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "spec_file": "openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "3b350cbf61af0726",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Group 2 check: several SHALL clauses have no scenario. (a) \"The harness SHALL NOT import agent-coordinator or coordination-bridge modules, SHALL NOT use HTTP or MCP transports\" (Offline requirement) has no WHEN/THEN; O.1/O.2 only test behaviour, not imports. (b) \"Every roadmap status change a simulated agent makes SHALL be declared as data in the fixture's step script, never in harness code\" (Memory-Store requirement) has no scenario; B.1 only implies it. (c) \"Registering a new probe SHALL NOT require editing any scenario definition other than its pinned expectations\" (Probe Seam) is only implicit in S.1. All three are cheap to pin with a static test (AST/grep over `mpsim/` for forbidden imports and for literal status strings; a test that registers a probe without touching `scenarios/`).",
+      "resolution": "PLAN_FIX fe0b333 (post-escalation, ledger items 1-4, 7, 8)",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 3,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "contract_mismatch",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/contracts/schemas/sim-report.schema.json",
+      "fingerprint": "fda86f78432b324e",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Error-path reports cannot validate against `sim-report.schema.json`. The contract (exit 1) and D8 say \"a report carrying a non-null `error` is printed when possible\", including when \"a git operation failed\", and the Deterministic requirement says any scenario report validates against the schema. But the schema requires `principals` with `minItems: 2` and non-nullable `timeline`; a failure during world build (before principals exist) cannot satisfy it. Either relax `principals` to allow an empty array/null when `error` is non-null, or state explicitly that exit-1 reports are best-effort and exempt from the schema (and from D.2's \"any scenario report\" assertion).",
+      "resolution": "PLAN_FIX fe0b333 (post-escalation, ledger items 1-4, 7, 8)",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 4,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "fingerprint": "1fe35a63f167a57d",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Stale cross-references in design.md after the iteration-2 renumbering: the Risks table says the 30 s budget is \"checked in task 6.2\" (it is 9.1) and that \"Task 4.2 documents the call site in the README\" (the README is 8.2 and the call site is in `scenarios/blocked.py`, task 5.2). D9 says \"the gen-eval pack test sets COORDINATION_API_URL\" and compares reports, but plan-findings iteration 2 #3 moved O.2 to task 6.1 against raw `mpsim run` stdout. D8's exit-code table omits code 2, which the contract and task 6.2 both declare.",
+      "resolution": "PLAN_FIX fe0b333 (post-escalation, ledger items 1-4, 7, 8)",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 5,
+      "status": "open",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/contracts/cli/mpsim.yaml",
+      "fingerprint": "bcfcca92b7417351",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger item 5: still present. The change-local header keeps the in-flight provenance note and a relative schema path that resolves correctly only from `openspec/changes/<id>/contracts/cli/`; from the promoted location `openspec/contracts/multiplayer-simulation/cli/` four `..` segments leave the repository. Task 1.1 still requires the promoted copy to be byte-identical, so the stale comment ships in the canonical file. Replace the relative path with a repo-root-relative one (`openspec/contracts/gen-eval-framework/schemas/cli-contract.schema.json`) and reword the provenance note so it is true at both locations.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 6,
+      "status": "open",
+      "axis": "resilience",
+      "type": "resilience",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/tasks.md",
+      "fingerprint": "af50ee0e20916b77",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Interpreter selection for the two subprocess entry points is unspecified. `bin/mpsim` \"runs `python -m mpsim`\"; `mpsim` imports `skills/roadmap-runtime/scripts` (needs pyyaml/jsonschema from the skills venv). Task 7.3 prepends only `bin/` to PATH and runs the `gen-eval` console script by name, so both resolutions depend on the skills venv already being first on PATH. Under `uv run --project skills pytest` that holds, but a developer running `pytest` from an activated other venv, or an IDE runner, gets a confusing ImportError or a `gen-eval: command not found`.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 7,
+      "status": "addressed",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "fingerprint": "34ddc4e5116d868d",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D5 asserts `Roadmap.ready_items()` \"decides from item statuses alone\" (dependency satisfied when `status: completed`, admitted when `approved`), but the architecture diagram in Context says readiness is evaluated \"over the remote's roadmap/checkpoint\", hinting that roadmap-runtime may also read checkpoint state. The pinned 10-tick baseline, B.4, and the ri-11 flip all depend on the exact admission semantic. The plan does not record where this was verified.",
+      "resolution": "PLAN_FIX fe0b333 (post-escalation, ledger items 1-4, 7, 8)",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 8,
+      "status": "addressed",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/contracts/cli/mpsim.yaml",
+      "fingerprint": "3b8f4ed8c776c544",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Exit-code 64 text lists \"missing --fixture-dir\" as a usage error, but the flag is optional; the intended meaning is a `--fixture-dir` value that points at a non-existent directory. Task 6.1 repeats the ambiguous phrase. A reader could conclude the flag is required.",
+      "resolution": "PLAN_FIX fe0b333 (post-escalation, ledger items 1-4, 7, 8)",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 9,
+      "status": "parked",
+      "axis": "observability",
+      "type": "observability",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/loop-state.json",
+      "fingerprint": "01a6dc52d58fde77",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "`loop-state.json` records `findings_trend: []` and `iteration: 0` although plan-findings.md documents three PLAN_ITERATE iterations with 16, 8 and 3 findings. The trend field exists to let PLAN_REVIEW and escalation logic see convergence; leaving it empty hides that history from the orchestrator.",
+      "resolution": "targets loop-state.json, which the orchestrator owns; PLAN_FIX must not edit it",
+      "parked_reason": "out_of_scope",
+      "consensus_status": "disagreement"
+    },
+    {
+      "id": 10,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "spec_file": "/home/user/agentic-coding-tools/.claude/worktrees/agent-a9b56ed97decb12c5/openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "3de285a3f765ab87",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The probe invocation point is stated two different ways. D4 says the driver calls every registered probe \"at each principal's plan step\" (which would include Alice's plan step and the plan steps of both memory-store principals), while the Same-Requirement requirement says probes are run and recorded \"at the second principal's plan step\". The difference is observable: under D4's wording a single stub probe would produce two `probes` entries in `same-requirement-collision` (one per principal's plan step), contradicting S.1's pin of \"one entry with the stub's probe_id\", and the blocked scenarios would carry non-null `probes`/`collision_detected`, contradicting D8's \"fields that do not apply are null\" and S.5's \"appears in probes of both collision scenarios\" (implying not in the other two). State in D4 and task 4.4 that probes run only at the planning (second) principal's plan step in the collision scenarios, and that the blocked scenarios report `probes: null`.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 11,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "spec_file": "/home/user/agentic-coding-tools/.claude/worktrees/agent-a9b56ed97decb12c5/openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "06dc27f7c92b6716",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D5 does not say whether the implement step of a principal with no dependency is also admitted through `Roadmap.ready_items()` or by harness logic. The sentence \"A principal with no dependency is ready at earliest_start_tick\" reads as a harness-local rule, which the Memory-Store requirement forbids (\"SHALL NOT use readiness logic of its own\"). The choice matters for B.4: that fixture seeds the dependency item (`ri-storage`) as `completed` at tick 0, and D5 states `ready_items()` admits only items whose status is `approved`. If every principal's implement step goes through `ready_items()`, storage-owner is never admitted in B.4 (its item is `completed`, not `approved`), so it finishes with `unblocked: false` and `blocked_ticks: 47` at the default budget, and the applier would also write `in_progress` over a `completed` item if it were admitted. B.4 and task 5.1 pin only retrieval-owner's value, so the storage-owner side of that report is unspecified and a reviewer of the pinned gen-eval YAML cannot tell which outcome is intended. Decide (recommended: every principal's implement admission goes through `ready_items()`, no exception) and pin storage-owner's expected `unblocked`/`blocked_ticks` in B.4, or make the B.4 fixture remove storage-owner's implement step.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 12,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "fingerprint": "df981a23294a5b61",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D7 declares the `Agent.act` protocol as returning `None`, but three lines later `ScriptedAgent` must \"return the step's declared status transitions to the scheduler\", and task 2.3 tests that it \"returns the step's declared status transitions\". Under operator decision A1 the return value is the only channel from agent to applier, so the protocol signature should return the transitions (for example a `StepResult` with `set_status: str | None`), not `None`.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 13,
+      "status": "open",
+      "axis": "readability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "spec_file": "/home/user/agentic-coding-tools/.git-worktrees/multiplayer-simulation-harness/impl/openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "af542f94c654364d",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of ledger item 13: partially addressed. D5 now states the applier is part of `mpsim`, 'operating on its own clone of the shared remote, not a principal's clone', which applier.py implements via `world.clone_for(root/'supervisor'/'clone', SUPERVISOR_IDENTITY)`. The diff does not touch D2's package inventory (so `applier.py`, and also `fixture.py`, `model.py`, `paths.py`, `runner.py`, `errors.py` as shipped, may still be missing from it) nor D6's determinism statement that supervisor commits use the same tick-derived dates and `GIT_CONFIG_GLOBAL=/dev/null` env as principal commits (which `commit_as` -> `_commit` does, and D.1 byte-identity depends on).",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 14,
+      "status": "open",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "fingerprint": "9bb1748c7ddb5fc0",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D5 says the ri-11 flip is \"three fixture edits plus one expectation edit\" and then lists three numbered items, of which only two are fixture edits and the third is the expectation edit. plan-findings iteration 2 describes it as \"three fixture edits plus a rule change\". Make the count match the list (two fixture edits, one expectation edit, plus ri-11's own rule and schema change).",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 15,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "spec_file": "openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "7d89a6ba9a702d9e",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Group 2 check on the Deterministic requirement: the SHALL clauses \"serialized with sorted keys\" and \"fields that do not apply SHALL be present with value null\" have no WHEN/THEN scenario. D.1 (byte-identical reruns) does not prove key ordering, and D.2 (schema validation) does not prove null-presence because the schema's `required` list would be satisfied by either null or a value. Task 2.5 does test both, so the gap is in the spec only; add a scenario (for example: WHEN any scenario report is parsed THEN its top-level keys are in sorted order AND every schema property is present, with null for inapplicable fields) and trace it to task 2.5. Every other SHALL in the delta has at least one scenario; no MODIFIED requirements exist, so nothing was dropped.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 16,
+      "status": "open",
+      "axis": "resilience",
+      "type": "resilience",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/tasks.md",
+      "fingerprint": "98c8d77b7927ceb1",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of open ledger item 6: still unaddressed. Task 1.4's `bin/mpsim` runs a bare `python`, and task 7.3 invokes the `gen-eval` console script by name with only `bin/` prepended to PATH, so both depend on the skills venv already being first on PATH. Cheapest fix: have `bin/mpsim` use `#!/usr/bin/env python3` and have the subprocess tests (6.1, 7.3) pass `sys.executable` explicitly (`[sys.executable, '-m', 'mpsim', ...]` and `[sys.executable, '-m', 'gen_eval', ...]` if gen-eval exposes a module entry point), with `bin/` on PATH only for gen-eval's own invocation of `mpsim`. Record the choice in D3 and the README task 8.2.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 17,
+      "status": "open",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/contracts/multiplayer-simulation/cli/mpsim.yaml",
+      "fingerprint": "1a3d5753cb5a64c3",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of ledger item 5: still present. The promoted openspec/contracts/multiplayer-simulation/cli/mpsim.yaml keeps the change-local header: 'Validates against ../../../../contracts/gen-eval-framework/schemas/cli-contract.schema.json (path relative to this file's change-local location)' and 'promoted ... by task 1.2'. From the promoted location four `..` segments land at the repo root, so `contracts/gen-eval-framework/...` does not resolve (the schema is under `openspec/contracts/`). test_contracts.py pins the promoted copy byte-identical to the change-local one, so the stale note ships in the canonical file. Use a repo-root-relative path and word the provenance so it is true at both locations.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 18,
+      "status": "open",
+      "axis": "readability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/multiplayer-simulation/test_gen_eval_pack.py",
+      "spec_file": "/home/user/agentic-coding-tools/.git-worktrees/multiplayer-simulation-harness/impl/openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "a5bfc403df741b99",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of ledger items 6/16: addressed in code, not in the design record. bin/mpsim now uses `#!/usr/bin/env python3`, test_cli.py runs the launcher with `sys.executable`, and test_gen_eval_pack.py resolves `gen-eval` from `Path(sys.executable).parent` and prepends that directory plus `bin/` to PATH so the launcher's `python3` resolves to the test interpreter. That is the cheapest fix the ledger asked for. The ledger also asked that the choice be recorded in D3 and in the README (task 8.2); the design.md diff does not touch D3 and the README's 'Running locally' section does not mention that the subprocess tests pin the interpreter.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 19,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "spec_file": "/home/user/agentic-coding-tools/.git-worktrees/multiplayer-simulation-harness/impl/openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "f58e801130eb80c1",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of ledger item 10: resolved. design.md D4 now says probes run 'At the second principal's plan step', collision.py runs the oracle and probes only when `index == 1`, and the blocked scenarios build their report without `probes`/`collision_*`, so those fields are null there (new_report defaults). test_probes.py S.1 pins exactly one entry per stub.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 20,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/multiplayer-simulation/test_blocked_scenarios.py",
+      "spec_file": "/home/user/agentic-coding-tools/.git-worktrees/multiplayer-simulation-harness/impl/openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "8cd2a437868022ed",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of ledger item 11: the design half is done (D5 now says 'A principal with no dependency is also admitted through Roadmap.ready_items(). The harness never short-circuits readiness', and blocked.py routes every waiting principal through ready_items()), but the pinning half is not. In B.4 (`test_a_dependency_that_starts_completed_unblocks_through_the_admission_rule`) the fixture seeds `ri-storage` as `completed`; with no short-circuit, storage-owner's implement step is never admitted (its item is not `approved`), so after retrieval-owner finishes at tick 5 the scheduler's fast-forward sets final_tick=20 and the report carries `unblocked.storage-owner: false`, `blocked_ticks.storage-owner: 17`. The test asserts only retrieval-owner, so this intended-by-design outcome is unpinned and a later change to admission could silently alter it. Pin storage-owner's values (or drop its implement step in that fixture copy) as the ledger asked.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 21,
+      "status": "open",
+      "axis": "architecture",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/multiplayer-simulation/mpsim/agents.py",
+      "fingerprint": "38d0e8597059121c",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of ledger item 12: resolved. D7 now declares `Agent.act(world, step, tick)` returning the step's declared transitions, agents.py's Protocol matches, and test_agents.py asserts the returned StatusTransition list and that `on_start` is read via `declared_transitions(step, 'start')`.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 22,
+      "status": "open",
+      "axis": "readability",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/design.md",
+      "spec_file": "/home/user/agentic-coding-tools/.git-worktrees/multiplayer-simulation-harness/impl/openspec/changes/multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md",
+      "fingerprint": "c52aaf09489d856a",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Re-verification of ledger item 14: no hunk in this diff touches the D5 sentence counting the ri-11 flip as 'three fixture edits plus one expectation edit', so the count/list mismatch is still open as far as this packet shows. The README's 'Where ri-11 must look' section lists the call site, the fixture dependency form, the fixture transitions, and the pinned blocked_ticks, which is the accurate enumeration D5 should mirror.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 23,
+      "status": "open",
+      "axis": "compatibility",
+      "type": "compatibility",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "skills/pyproject.toml",
+      "fingerprint": "a56b03dff8459661",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "skills/pyproject.toml adds `gen-eval` to the `test` extra and a `[tool.uv.sources]` path entry, and task 1.3 (ticked) says to run `uv lock` in skills/, but no `skills/uv.lock` hunk appears in this diff. If the lock was not committed, `uv sync --locked`/`--frozen` in CI either fails outright or installs without gen-eval, and the newly swept `tests/multiplayer-simulation` fails in test_gen_eval_pack.py with a FileNotFoundError on the console script. If lockfiles are simply filtered out of review packets, this is a non-issue; the packet gives no way to tell.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 24,
+      "status": "open",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/multiplayer-simulation/README.md",
+      "fingerprint": "e84b3cf06f5d3934",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "README 'Running locally' gives `PATH=tests/multiplayer-simulation/bin:$PATH uv run python -m mpsim list   # from the harness dir` after `cd skills`. Prepending `bin/` to PATH does nothing for `python -m mpsim`, and `python -m mpsim` from `skills/` cannot import `mpsim` (only the launcher puts the harness root on sys.path). The trailing comment contradicts the preceding `cd skills`. A reader following it gets `No module named mpsim`.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 25,
+      "status": "open",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/autopilot/scripts/convergence_loop.py",
+      "fingerprint": "5b4c60dccbc9abfa",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The `_BOOKKEEPING_DIRS` comment says converge writes the ledger/cache itself and that `save_ledger` 'runs before the pre-fix snapshot'. If that were the whole story the bookkeeping paths would already be in `pre_rev` and never show up in `_changed_paths`, and the filter (and the escalation that motivated it) would be unnecessary. Something writes under `.review-ledger/` or `.review-cache/` between the snapshot and the scope check; the comment should name that write so the next reader understands why the filter exists rather than concluding it is dead code.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 26,
+      "status": "open",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/multiplayer-simulation/mpsim/scenarios/collision.py",
+      "fingerprint": "c613fd5e51678478",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The agent id format `<name>-agent-1` is defined three times: world.py (`Principal(name, email, f\"{name}-agent-1\", clone)`), agents.py (`self.agent_id = f\"{spec.name}-agent-1\"`), and collision.py, which re-derives it as `f\"{p.name}-agent-1\"` for the report instead of reading `agent.agent_id` from the ScriptedAgent it just created. blocked.py does read `s.agent.agent_id`. A change to the format in one place silently diverges the report from the world/agent.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 27,
+      "status": "open",
+      "axis": "resilience",
+      "type": "resilience",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/multiplayer-simulation/mpsim/runner.py",
+      "fingerprint": "baa331bba62e6485",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "runner.run only catches ScenarioError around `scenario.run(ctx)`. `render()` runs outside that inner try, so a ScenarioError message that happens to contain a 40-hex commit id (git stderr often does) makes `render` raise ReportError, which escapes as an uncaught traceback with no report printed. Likewise a malformed `scenario.yaml` raises yaml.YAMLError out of `load_fixture` before any mapping to exit 64/1. Both end up as exit 1 via the interpreter, which matches the contract's code but not its 'A report carrying a non-null error is printed when possible' intent.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 28,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/multiplayer-simulation/test_probes.py",
+      "fingerprint": "896d0af43cee4288",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "test_no_probe_is_registered_at_import_time pops `mpsim.probes` from sys.modules and re-imports it. importlib then rebinds the package attribute `mpsim.probes` to the fresh module and the `finally` restores only sys.modules, so for the rest of the session `mpsim.probes` (attribute access) and `sys.modules['mpsim.probes']` are different objects with different `REGISTRY` and `ProbeResult` classes. Nothing currently breaks because every consumer bound the original at import, but any later `from mpsim import probes` evaluated at runtime sees the stale module. Separately, once ri-06 adds `from mpsim.probes import requirement_collision`, the re-import finds that submodule cached, its module-level `register()` does not re-run, and `fresh.REGISTRY == {}` passes trivially, so the test no longer tests what its name claims.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 29,
+      "status": "open",
+      "axis": "readability",
+      "type": "style",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/multiplayer-simulation/conftest.py",
+      "fingerprint": "ebb1a4a4c64b8068",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "In conftest.py `_blocked` ends with `raise AssertionError(\"non-inet connect is not expected in this harness\")`, but `_wrap` only calls `_blocked` when `self.family in _INET_FAMILIES`, so that branch is unreachable and the message is misleading (AF_UNIX connects are in fact passed through to the original).",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 30,
+      "status": "open",
+      "axis": "observability",
+      "type": "observability",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/multiplayer-simulation-harness/tasks.md",
+      "fingerprint": "1bf979087155d2f1",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The recorded wall time for the harness suite disagrees across the packet: tasks.md 9.1 says 34 s with ~8 s in the archive-stability guard, the Implementation Iteration session-log entry says ~37 s with ~11 s. Both exceed the 30 s budget the plan set (recorded, not asserted, per plan finding iteration 3). Not a defect, but the validation report should carry one number and name the environment it was measured in.",
+      "consensus_status": "unconfirmed"
+    }
+  ]
+}
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/contracts/cli/mpsim.yaml b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/contracts/cli/mpsim.yaml
new file mode 100644
index 00000000..d1981648
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/contracts/cli/mpsim.yaml
@@ -0,0 +1,105 @@
+# mpsim CLI contract: the multi-player simulation driver (design D8).
+#
+# Ground truth for the ToolDescriptor at
+# skills/tests/multiplayer-simulation/evaluation/descriptor.yaml, generated by
+# packages/gen-eval/scripts/generate_tool_descriptor.py. Authored here while the
+# change is in flight; promoted to
+# openspec/contracts/multiplayer-simulation/cli/mpsim.yaml by task 1.2 so the
+# harness never reads a path that moves on archival (design D10).
+#
+# Validates against ../../../../contracts/gen-eval-framework/schemas/cli-contract.schema.json
+# (path relative to this file's change-local location).
+#
+# `--help` is supplied by argparse and is deliberately not declared, matching
+# the gen-eval contract's convention.
+
+contract_version: "1"
+
+tool:
+  name: mpsim
+  executable: mpsim
+  description: >-
+    Deterministic, offline multi-player simulation driver. Builds a temporary
+    world of two or more simulated principals sharing a local bare git remote,
+    runs one named scenario on a logical tick clock, and prints a single JSON
+    report validating against
+    openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json.
+
+commands:
+  - name: list
+    description: Print the built-in scenario ids as a JSON array, sorted.
+    traceability:
+      requirements:
+        - multiplayer-simulation.scenario-pack-runs-through-gen-eval
+
+  - name: run
+    description: >-
+      Run one scenario and print its report on stdout. Exit 0 whenever the
+      scenario ran to completion, regardless of what was detected or how long
+      a principal was blocked; the scenario file, not the driver, decides what
+      is expected.
+    traceability:
+      requirements:
+        - multiplayer-simulation.simulated-principals-have-separate-identities-worktrees-and-agents
+        - multiplayer-simulation.scenarios-run-offline-without-a-shared-coordinator
+        - multiplayer-simulation.scenario-reports-are-deterministic
+    flags:
+      - name: --scenario
+        type: string
+        required: true
+        description: >-
+          Built-in scenario id (see `mpsim list`). An unknown id exits 64.
+        traceability:
+          requirements:
+            - multiplayer-simulation.same-requirement-collision-scenario-records-plan-time-detection
+            - multiplayer-simulation.memory-store-scenario-reports-time-blocked-on-dependency
+
+      - name: --probe
+        type: string
+        repeatable: true
+        description: >-
+          Restrict the run to the named registered collision probes. Omitted,
+          every registered probe runs. An unregistered id exits 64.
+        traceability:
+          requirements:
+            - multiplayer-simulation.plan-time-detectors-attach-through-a-probe-seam
+
+      - name: --tick-budget
+        type: integer
+        default: 50
+        description: >-
+          Maximum logical ticks before the scheduler stops. A principal still
+          blocked at the budget is reported with unblocked=false and
+          blocked_ticks equal to the budget minus its earliest start tick.
+          A value below 1 exits 64.
+        traceability:
+          requirements:
+            - multiplayer-simulation.memory-store-scenario-reports-time-blocked-on-dependency
+
+      - name: --fixture-dir
+        type: path
+        description: >-
+          Replace the scenario's built-in fixture directory. Used by tests to
+          supply altered fixtures without editing the shipped ones. A missing
+          directory, or a fixture declaring fewer than two principals, exits 64.
+        traceability:
+          requirements:
+            - multiplayer-simulation.simulated-principals-have-separate-identities-worktrees-and-agents
+            - multiplayer-simulation.same-requirement-collision-scenario-records-plan-time-detection
+
+exit_codes:
+  - code: 0
+    meaning: The scenario ran to completion and a report was printed.
+  - code: 1
+    meaning: >-
+      The scenario could not be established (for example the oracle found the
+      fixture's required collision absent, or a git operation failed). A report
+      carrying a non-null `error` is printed when possible.
+  - code: 2
+    meaning: Argparse usage error, e.g. missing subcommand or --scenario.
+  - code: 64
+    meaning: >-
+      Semantic usage error: unknown scenario, unknown probe, a --fixture-dir
+      that does not exist, --tick-budget below 1, or a fixture with fewer than two
+      principals.
+    sysexits_name: EX_USAGE
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/contracts/schemas/sim-report.schema.json b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/contracts/schemas/sim-report.schema.json
new file mode 100644
index 00000000..7380991f
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/contracts/schemas/sim-report.schema.json
@@ -0,0 +1,234 @@
+{
+  "$schema": "https://json-schema.org/draft/2020-12/schema",
+  "$id": "https://raw.githubusercontent.com/jankneumann/agentic-coding-tools/main/openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json",
+  "title": "mpsim scenario report",
+  "description": "One report per `mpsim run`. Ephemeral test output, not canonical state (design D8). Every property is always present; properties that do not apply to a scenario are null so gen-eval body assertions stay uniform across the pack. No absolute paths, temp directory names, commit SHAs, or wall-clock timestamps may appear (requirement: Scenario Reports Are Deterministic). An exit-1 error report (non-null `error`) may carry an empty `principals` array and a null `timeline`, because the failure can happen before the world exists; every other report must name at least two principals and carry a timeline.",
+  "type": "object",
+  "additionalProperties": false,
+  "required": [
+    "schema_version",
+    "scenario_id",
+    "principals",
+    "collision_present",
+    "collision_detected",
+    "probes",
+    "blocked_ticks",
+    "unblocked",
+    "final_tick",
+    "timeline",
+    "error"
+  ],
+  "properties": {
+    "schema_version": {
+      "const": "1"
+    },
+    "scenario_id": {
+      "type": "string",
+      "pattern": "^[a-z0-9][a-z0-9-]*$"
+    },
+    "principals": {
+      "type": "array",
+      "minItems": 0,
+      "items": {
+        "type": "object",
+        "additionalProperties": false,
+        "required": [
+          "name",
+          "agent_id",
+          "change_id"
+        ],
+        "properties": {
+          "name": {
+            "type": "string",
+            "pattern": "^[a-z0-9][a-z0-9-]*$"
+          },
+          "agent_id": {
+            "type": "string",
+            "minLength": 1
+          },
+          "change_id": {
+            "type": "string",
+            "pattern": "^sim-[a-z0-9-]+$"
+          }
+        }
+      }
+    },
+    "collision_present": {
+      "type": [
+        "boolean",
+        "null"
+      ],
+      "description": "Ground-truth oracle over fixture contents (design D4). Null for scenarios with no collision question."
+    },
+    "collision_detected": {
+      "type": [
+        "boolean",
+        "null"
+      ],
+      "description": "True only when a probe with status ok reported a requirement-level collision against the other principal's change. Null for scenarios with no collision question."
+    },
+    "probes": {
+      "type": [
+        "array",
+        "null"
+      ],
+      "items": {
+        "type": "object",
+        "additionalProperties": false,
+        "required": [
+          "probe_id",
+          "status",
+          "collisions",
+          "error"
+        ],
+        "properties": {
+          "probe_id": {
+            "type": "string",
+            "minLength": 1
+          },
+          "status": {
+            "enum": [
+              "ok",
+              "error"
+            ]
+          },
+          "collisions": {
+            "type": "array",
+            "items": {
+              "type": "object",
+              "additionalProperties": false,
+              "required": [
+                "level",
+                "other_change",
+                "requirement"
+              ],
+              "properties": {
+                "level": {
+                  "enum": [
+                    "intent",
+                    "requirement",
+                    "contract",
+                    "file"
+                  ]
+                },
+                "other_change": {
+                  "type": "string"
+                },
+                "requirement": {
+                  "type": [
+                    "string",
+                    "null"
+                  ]
+                }
+              }
+            }
+          },
+          "error": {
+            "type": [
+              "string",
+              "null"
+            ]
+          }
+        }
+      }
+    },
+    "blocked_ticks": {
+      "type": [
+        "object",
+        "null"
+      ],
+      "description": "Per principal: first tick its implement step is admitted by Roadmap.ready_items minus the tick its own preceding steps finished (design D5).",
+      "additionalProperties": {
+        "type": "integer",
+        "minimum": 0
+      }
+    },
+    "unblocked": {
+      "type": [
+        "object",
+        "null"
+      ],
+      "additionalProperties": {
+        "type": "boolean"
+      }
+    },
+    "final_tick": {
+      "type": [
+        "integer",
+        "null"
+      ],
+      "minimum": 0
+    },
+    "timeline": {
+      "type": [
+        "array",
+        "null"
+      ],
+      "items": {
+        "type": "object",
+        "additionalProperties": false,
+        "required": [
+          "tick",
+          "principal",
+          "step",
+          "event"
+        ],
+        "properties": {
+          "tick": {
+            "type": "integer",
+            "minimum": 0
+          },
+          "principal": {
+            "type": "string"
+          },
+          "step": {
+            "enum": [
+              "plan",
+              "contract",
+              "implement"
+            ]
+          },
+          "event": {
+            "enum": [
+              "started",
+              "finished",
+              "blocked",
+              "admitted",
+              "pushed",
+              "probed",
+              "status_applied"
+            ]
+          }
+        }
+      }
+    },
+    "error": {
+      "type": [
+        "string",
+        "null"
+      ],
+      "description": "Non-null only when the process exits 1. When non-null, `principals` may be empty and `timeline` may be null."
+    }
+  },
+  "allOf": [
+    {
+      "if": {
+        "properties": {
+          "error": {
+            "type": "null"
+          }
+        }
+      },
+      "then": {
+        "properties": {
+          "principals": {
+            "minItems": 2
+          },
+          "timeline": {
+            "type": "array"
+          }
+        }
+      }
+    }
+  ]
+}
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/design.md b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/design.md
new file mode 100644
index 00000000..93fa2573
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/design.md
@@ -0,0 +1,355 @@
+# Design: multiplayer-simulation-harness
+
+## Context
+
+`ri-06` and `ri-11` each have an acceptance outcome that only means something if a
+simulation already exists with a recorded baseline. This harness has to satisfy three
+conditions at once:
+
+1. **Faithful enough to flip.** When a real capability lands, the measured result has to
+   change, and that change has to come from the code under test, not from a harness edit.
+2. **Honest about today.** The baseline records what the system actually does now, and it
+   cannot pass vacuously.
+3. **Cheap and offline.** It runs in the skills CI sweep with no coordinator, no network and
+   no vendor CLI, and it is deterministic enough to pin exact values.
+
+The roadmap names gen-eval as the scenario surface. gen-eval already has a CLI transport and
+a contract-derived ToolDescriptor archetype, and its own dogfood pack
+(`packages/gen-eval/evaluation/`) is the model to follow.
+
+```
+gen-eval (CLI transport) ──► bin/mpsim run --scenario <id> ──► JSON report on stdout
+                                         │
+                       ┌─────────────────┴──────────────────┐
+                       ▼                                    ▼
+                World builder                         Tick scheduler
+    bare remote + N principals                    each tick: agents act, push;
+    (identity, clone/worktree, agent id)          applier writes statuses to main;
+                       │                          ready_items() over remote main
+                       ▼
+          plan step ──► CollisionProbe registry ──► probes[] + collision_detected
+                    └─► fixture oracle          ──► collision_present
+```
+
+## Decisions
+
+### D1: New capability `multiplayer-simulation`, not the scaffold's `multiplayer-collaboration`
+
+The scaffold put these requirements under `multiplayer-collaboration`. Every sibling item
+uses that placeholder too. Mixing test-harness requirements with collaboration behaviour in
+one capability spec would give the capability two kinds of content with different owners and
+lifecycles. It would also put this change's spec delta in the same file as about 19 sibling
+deltas, which is exactly the same-requirement collision the roadmap is trying to make visible.
+
+- **Chosen**: a narrow capability `multiplayer-simulation` covering the simulation harness,
+  its scenarios, its probe seam and its report contract.
+- **Rejected**: `gen-eval-framework`. That capability specifies the framework itself, and a
+  scenario pack is a consumer of gen-eval, not part of it.
+- **Rejected**: keeping `multiplayer-collaboration`, for the collision and ownership reasons
+  above.
+- **Consequence**: the spec deltas of `ri-06` and `ri-11` that mention "the simulation
+  harness's scenario" should reference `multiplayer-simulation` requirements. When those
+  changes iterate, they will see this as a cross-capability reference rather than a
+  duplicate.
+
+### D2: Harness lives at `skills/tests/multiplayer-simulation/`, driven by the skills venv
+
+The driver must import the systems it measures. The roadmap-runtime admission rule and the
+future plan-feature collision scanner both live in `skills/`. Packages under `packages/` have
+their own virtualenvs and no import path into `skills/`.
+
+- **Chosen**: `skills/tests/multiplayer-simulation/`, holding:
+  - `mpsim/`, the driver package: `world.py`, `agents.py`, `clock.py`, `oracle.py`,
+    `report.py`, `errors.py`, `__main__.py`, plus two subpackages:
+    - `probes/`, the collision probe seam (D4);
+    - `scenarios/`, one module per scenario family. These are discovered with `pkgutil`, so
+      adding a scenario never edits a shared list.
+  - `bin/mpsim`, a launcher that runs `python -m mpsim` with the harness directory on
+    `sys.path`
+  - `fixtures/`, the seed capability spec, the memory-store roadmap and the durations
+  - `evaluation/`, holding `descriptor.yaml` (generated) and `scenarios/*.yaml` (the gen-eval
+    pack)
+  - `test_*.py`
+- `skills/tests/` is excluded from `install.sh`, so no consumer repository receives the
+  harness. That also satisfies the roadmap constraint that installed payloads stay portable.
+- Imports of skill scripts follow the existing `sys.path` pattern in
+  `skills/tests/roadmap-runtime/conftest.py`.
+- **Rejected**: a new `packages/multiplayer-sim/`. It would need its own CI job, which
+  `test_every_package_suite_runs_in_ci` enforces, and it would have no way to import
+  `skills/roadmap-runtime` without vendoring that code.
+- **Rejected**: `agent-coordinator/evaluation/scenarios/`. The coordinator gen-eval job needs
+  Postgres and a live HTTP service, which contradicts the offline requirement.
+
+### D3: gen-eval runs in-process from pytest, with `gen-eval` added to the skills `test` extra
+
+- **Chosen**: add `gen-eval = { path = "../packages/gen-eval" }` to the
+  `[tool.uv.sources]` table in `skills/pyproject.toml`, and add `gen-eval` to the `test`
+  extra. This follows the existing path-dependency pattern for `system-one-decisions` and
+  `openbao-credentials`. A pytest test, `test_gen_eval_pack.py`, invokes the `gen-eval`
+  console script by subprocess with `--descriptor evaluation/descriptor.yaml
+  --fail-threshold 1.0`, with `bin/` prepended to `PATH` and the harness directory as the
+  working directory. The pack therefore runs wherever the harness tests run.
+- gen-eval's core dependencies are pydantic, pyyaml, jinja2, jsonpath-ng and httpx. The
+  skills `test` extra already pulls pyyaml, httpx and, through fastapi, pydantic, so the
+  added footprint is jinja2 and jsonpath-ng.
+- **Feasibility evidence**: during planning, a scratch copy of `skills/pyproject.toml` with
+  this dependency added resolved cleanly with `uv lock` (56 packages).
+- **Rejected**: running the pack from the `gen-eval-tests` CI job, with `mpsim` shelling into
+  the skills venv through `uv run --project ../../skills`. That is a cross-venv subprocess
+  chain, fragile under PATH differences, and it splits one feature's CI signal across two
+  jobs.
+- **Fallback**: if `uv lock` cannot resolve the added dependency, task 1.3 stops and records
+  the conflict. The fallback is the rejected option above, recorded as a design amendment
+  rather than taken silently.
+
+### D4: Collision detection is a probe seam, with a ground-truth oracle alongside it
+
+Plan-time requirement-collision detection does not exist yet. `feature_registry.py` overlap
+needs a coordinator and covers only locks and files. Asking "was a collision detected at plan
+time?" today has one honest answer: nothing ran.
+
+- **Chosen**: `mpsim.probes` (`mpsim/probes/__init__.py`) defines a `CollisionProbe` protocol and a module-level registry.
+  - Protocol: `probe_id: str`, plus
+    `detect(view: PrincipalView, change_id: str) -> ProbeResult`.
+  - `PrincipalView` exposes the principal's worktree path and the shared remote's URL, so a
+    probe can read git state but cannot mutate the world.
+  - `ProbeResult` fields: `probe_id`, `status ∈ {ok, error}`, `collisions: list[{level,
+    other_change, requirement}]`, `error: str | null`.
+- At the second principal's plan step, the driver calls every registered probe. It records
+  `probes` (one entry per probe that ran) and sets `collision_detected` to true when any probe
+  with status `ok` reported a collision at level `requirement` against the other principal's
+  change.
+- A probe that raises an exception, or runs longer than its per-probe timeout (default 10 s),
+  is recorded with `status: error`. The run still completes. A probe runs in a daemon thread,
+  so a hung probe is abandoned at its timeout rather than joined, and it cannot keep the
+  process alive. This mirrors the roadmap
+  constraint that advisory signals fail open.
+- `mpsim.oracle` computes `collision_present` from fixture contents. It is true when the two
+  simulated changes' spec deltas name the same `### Requirement:` heading of the same
+  capability. It is a string comparison over files the fixture wrote, with no git history and
+  no live scanning. It exists only so a broken fixture cannot make "not detected" trivially
+  true. It is not a detector, and it is never registered as a probe.
+- **Selection**: `mpsim run --probe <id>` restricts the run to the named probes. With no
+  `--probe`, every registered probe runs. Registration happens in
+  `mpsim/probes/__init__.py`. Adding a probe means adding one import line there, and the
+  scenario files stay untouched.
+- **Rejected**: making the harness invoke a predetermined scanner CLI path. That would fix
+  `ri-06`'s interface before `ri-06` designs it. The adapter belongs on the harness side, and
+  `ri-06` writes a thin probe that wraps whatever entry point it ships.
+- **Rejected**: pinning `collision_detected: false` without the oracle. A fixture regression
+  that stopped writing the shared requirement would pass the baseline and then also break
+  `ri-06`'s flip, with nothing to say why.
+
+### D5: Blocked time is measured in logical ticks with the real admission rule
+
+- **Clock**: a logical tick counter starting at 0. The fixture declares a duration in ticks
+  for each step: `plan`, `contract`, `implement`. Nothing reads wall-clock time, which is
+  what makes `blocked_ticks` reproducible enough to pin.
+- **Integration ref (operator decision A1, 2026-10-05).** `roadmap.yaml` has exactly one
+  authoritative copy: the one on the shared remote's `main`, the integration ref. Principals'
+  change branches never edit `roadmap.yaml`. Status transitions are written to `main` only by
+  a simulated supervisor step, the *status applier* (`mpsim/applier.py`), which commits as
+  `sim-supervisor <sim-supervisor@sim.invalid>`. This mirrors the real split, where workers
+  report results and only the supervisor writes roadmap state.
+- **Readiness**: on every tick, the scheduler fetches the shared remote's `main` into the
+  dependent principal's clone. It then loads `roadmap.yaml` from that fetched `main`
+  (`origin/main`), never from a principal's change branch, through roadmap-runtime's
+  `load_roadmap`. That call validates the file against the *real*
+  repository's roadmap schema, located from the real repo root and not the temporary world,
+  so a schema extension in `ri-11` is exercised too. Finally, the scheduler asks
+  `Roadmap.ready_items()` whether the dependent's item is admitted. `ready_items()` decides
+  from roadmap data alone: a dependency counts as satisfied when its item `status` is
+  `completed`, only items whose status is `approved` are admitted, and items with a
+  `superseded_by` edge or an unmet `external_depends_on` are withheld. It reads no checkpoint
+  state. This was verified against `skills/roadmap-runtime/scripts/models.py`
+  (`Roadmap.ready_items`) during PLAN_FIX, and the fixture uses neither `superseded_by` nor
+  `external_depends_on`.
+- **Status transitions are fixture data, not harness code.** Each step in a principal's
+  fixture script may declare `on_start.set_status` and `on_finish.set_status` for that
+  principal's own roadmap item. The agent does not apply them. It reports them as step
+  results. The status applier (part of the `mpsim` package, operating on its own clone of
+  the shared remote, not a principal's clone) commits each one to `roadmap.yaml` on `main` and pushes.
+  The applier holds no transition logic of its own: it writes exactly the status the fixture
+  declared, for the item of the principal that reported it. In the baseline fixture:
+  - `plan` and `contract` change no status, so the item stays `approved` and remains
+    admissible;
+  - `contract` pushes the contract files to the owner's change branch but declares no
+    status, because
+    today's roadmap schema has no contract-complete state. That absence is the baseline gap;
+  - `implement` sets `in_progress` when it starts and `completed` when it finishes.
+- **Intra-tick order.** The pinned value depends on it, so it is fixed. Within tick *t*:
+  1. Every step that finishes at *t* pushes its work to its change branch, taking
+     principals in fixture declaration order.
+  2. The status applier commits every `on_finish` transition reported at *t* to `main`, in
+     the same order, and pushes once.
+  3. Each waiting principal fetches `main` and evaluates `ready_items()`.
+  4. For each admitted principal, the applier commits its implement step's `on_start`
+     transition to `main` at the same tick *t*.
+
+  A dependency completed at tick 11 therefore admits its dependent at tick 11, not tick 12.
+- **Metric**: for each principal,
+  `blocked_ticks = ready_tick − earliest_start_tick`.
+  - `earliest_start_tick` is the tick at which that principal's own preceding steps finished
+    (its plan).
+  - `ready_tick` is the first tick at which `ready_items()` admits its implement step.
+  - A principal with no dependency is also admitted through `Roadmap.ready_items()`. The
+    harness never short-circuits readiness. Such a principal is admitted at
+    `earliest_start_tick`, so its value is 0.
+- **Baseline fixture durations**:
+  - `storage-owner`: plan 1, contract 2, implement 8. Its implementation completes at tick
+    11.
+  - `retrieval-owner`: plan 1, implement 4. Its earliest start is tick 1.
+  - Today's bare `depends_on` keeps it blocked until tick 11, so the pinned baseline is
+    `blocked_ticks: {retrieval-owner: 10, storage-owner: 0}`.
+- **Termination**: `--tick-budget` (default 50) bounds the loop. If the dependency is not
+  complete when the budget runs out, the run stops with that principal marked
+  `unblocked: false` and `blocked_ticks = tick_budget − earliest_start_tick`. It never loops
+  forever. A budget below 1 is a usage error and exits 64.
+- **What `ri-11` changes**: `ri-11` extends the roadmap schema and the admission rule. Its
+  flip is three fixture edits plus one expectation edit, and the harness code itself does not
+  change. The fixture edits:
+  1. the dependency becomes `{item: ri-storage, on: contract}`;
+  2. the `contract` step gains `on_finish.set_status: contract_complete`, or whatever state
+     name `ri-11` defines;
+  3. the expectation in the scenario file changes to the new, lower `blocked_ticks`. Under
+     the baseline durations that is 2.
+
+  `ri-11` ships its own rule change alongside these.
+- **Rejected**: a harness-local readiness function. It would freeze the measured behaviour at
+  whatever the harness author wrote and never move when `ri-11` lands.
+- **Rejected**: hard-coding status transitions in `ScriptedAgent`. `ri-11` would then
+  have to edit harness code to emit its new state, which breaks the condition that the
+  harness does not change when a capability lands.
+- **Rejected**: wall-clock timing of real agent runs. It is non-deterministic, slow, and
+  needs vendor access.
+
+### D6: Principals are harness-local identities with real git isolation
+
+- Each principal has:
+  - a `name`, used as the git `user.name`;
+  - an email in the form `<name>@sim.invalid`. The `.invalid` TLD is reserved, so the address
+    can never route anywhere;
+  - an `agent_id` (`<name>-agent-1`);
+  - its own clone of the shared bare remote under `<world>/principals/<name>/clone`, with its
+    work in a `git worktree` at `<world>/principals/<name>/wt-<change>`.
+- **Visibility**: principals see each other's work only through `git fetch` from the shared
+  remote. Unpushed commits are invisible to everyone else. That models the roadmap
+  constraint that planning-time capabilities must work with the git remote alone.
+- **Determinism**: commits use fixed `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` values
+  derived from the tick, `-c init.defaultBranch=main`, and no global git config
+  (`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`). Ignoring global config also
+  keeps a developer's hooks, commit signing (`commit.gpgsign`) and credential helpers out of
+  the simulated world.
+- **Seed commit**: the world builder makes one seed commit on `main`, authored by
+  `sim-seed <sim-seed@sim.invalid>`, containing the fixture's seeded `openspec/specs/` and
+  `roadmap.yaml`. Identity assertions apply to commits reachable from a principal's change
+  branch but not from `main`.
+- **Size**: the world supports N ≥ 2 principals. Fewer than 2 is a usage error with exit
+  code 64.
+- **Rejected**: registering the simulated principals in the
+  `principal-credential-architecture` registry. That registry belongs to `ri-02` and is out
+  of scope. The harness would also be coupled to a schema that does not exist yet.
+
+### D7: Scripted agents behind an `Agent` protocol
+
+- `Agent.act(world, step, tick)` performs one step's file edits and git operations and
+  returns the step's declared status transitions (it never applies them).
+- `ScriptedAgent` replays the fixture's step script deterministically:
+  - write the OpenSpec change files under a synthetic change id;
+  - commit;
+  - push to `refs/heads/sim/<principal>/<change>`, which models an open PR branch;
+  - return the step's declared status transitions to the scheduler. `on_start` data is read
+    through `declared_transitions(step, "start")`, since it applies before the step runs.
+- Agents never write `roadmap.yaml` and never push to `main`. A test asserts that no commit
+  on any `sim/*` branch touches `roadmap.yaml`, and that every commit on `main` after the
+  seed is authored by `sim-supervisor` (D5, operator decision A1).
+- **Rejected**: live vendor agents. They are non-deterministic and need network access, so
+  they are a non-goal here. The protocol leaves room for a later `ExecutorAgent` that adapts
+  `packages/agent-scenarios`' `ScenarioExecutor`.
+
+### D8: CLI surface, report contract and determinism
+
+The CLI surface is contracted in `contracts/cli/mpsim.yaml`. It validates against
+`gen-eval-framework/schemas/cli-contract.schema.json` and cites `multiplayer-simulation.*`
+requirements in `traceability:` blocks.
+
+| Command | Flags | Purpose |
+|---|---|---|
+| `mpsim list` | (none) | Print the built-in scenario ids as a JSON array. |
+| `mpsim run` | `--scenario <id>` (required), `--probe <id>` (repeatable), `--tick-budget <int>` (default 50), `--fixture-dir <path>` | Run one scenario and print its report. `--fixture-dir` replaces the scenario's built-in fixture directory. Tests use it to supply altered fixtures, such as a lost shared requirement, an already-completed dependency, or one principal, without touching the shipped fixtures. |
+
+- `mpsim run` prints one JSON object to stdout. It validates against
+  `sim-report.schema.json` and is written with sorted keys and no trailing whitespace.
+- Fields:
+  - `schema_version`, `scenario_id`, `principals[]` (name, agent_id, change_id)
+  - `collision_present`, `collision_detected`, `probes[]`
+  - `blocked_ticks{principal: int}`, `unblocked{principal: bool}`, `final_tick`
+  - `timeline[]` of `{tick, principal, step, event}`
+- Fields that do not apply to a scenario are `null`, not omitted, so gen-eval `body`
+  assertions stay uniform across the pack.
+- The report never contains absolute paths, temp directory names or commit SHAs. Only
+  ref names, change ids and ticks appear. That keeps two runs byte-identical, and the
+  determinism test asserts it.
+
+**Exit codes**:
+
+| Code | Meaning |
+|---|---|
+| 0 | The scenario ran to completion and a report was emitted. This holds whatever was or was not detected, and whatever the blocked time was. |
+| 1 | The harness could not establish the scenario, for example when the oracle finds that the fixture's required collision is missing, or a git operation failed. A report with an `error` field is still printed when possible. |
+| 2 | Argparse usage error, such as a missing subcommand or a missing `--scenario`. |
+| 64 | Usage error: an unknown scenario, an unknown probe, a `--fixture-dir` that does not exist, a `--tick-budget` below 1, or a fixture declaring fewer than 2 principals (`EX_USAGE`). |
+
+Pinned expectations live in the gen-eval scenario YAML, not in the driver. The driver
+measures and the scenario decides what is expected.
+
+### D9: Offline enforcement is tested, not assumed
+
+- The driver imports nothing from `agent-coordinator` and nothing from
+  `coordination_bridge`. It has no HTTP or MCP transport.
+- An autouse fixture in the harness `conftest.py` replaces `socket.socket.connect` (and
+  `connect_ex`) so that any `AF_INET` or `AF_INET6` connection raises. That turns an
+  accidental network call into an immediate test failure instead of a CI-only hang.
+- Subprocesses such as `git` and `bin/mpsim` do not inherit that patch. For them:
+  - the shared remote is a `file://` path, so git never opens a socket;
+  - the CLI test (task 6.1) runs `mpsim run` with `COORDINATION_API_URL=http://127.0.0.1:9`,
+    a discard port that would fail fast, and asserts stdout is byte-identical to a run
+    without that variable.
+- **Rejected**: relying on the CI runner having no coordinator. The runner does have network
+  access, so the absence of a coordinator proves nothing about the harness.
+
+### D10: Archive stability
+
+- Fixture worlds use synthetic change ids prefixed `sim-`, for example
+  `sim-memory-store-core` and `sim-retrieval-api`.
+- A test asserts that no fixture change id is a real repository change id. It reads the ids
+  the same way the path-stability guard does, through `openspec_paths`, so a future real
+  change named `sim-…` cannot quietly turn a fixture into a guard violation.
+- Any test that reads this change's own artifacts goes through
+  `change_dir(repo_root_from(__file__, 3), ...)`. The CLI contract is read from its promoted
+  path under `openspec/contracts/multiplayer-simulation/`, never from the change directory.
+- Requirement headings that contract citations resolve against come from the canonical
+  `openspec/specs/multiplayer-simulation/spec.md` once this change is archived, and from the
+  change's own delta only while it is in flight. The promoted-vs-change-local identity check
+  likewise applies only in flight; after archive it instead asserts the canonical spec exists.
+  The traceability gate follows the same rule: it accepts a capability spec ADDED by the
+  resolving change's delta until archive, then reads the archived spec.
+
+## Risks and Trade-offs
+
+| Risk | Mitigation |
+|---|---|
+| Adding `gen-eval` to the skills venv conflicts with existing pins | D3 fallback, plus task 1.3 runs `uv lock` first and stops if it fails |
+| Git-heavy scenarios make the skills sweep slower | Four scenarios, each creating only a handful of commits. Budget is under 30 s for the whole harness directory, recorded in task 9.1. |
+| `Roadmap.ready_items` signature changes under `ri-11` | That is the intended coupling: the harness should move with the rule. The call site is in `scenarios/blocked.py` (task 5.2); the README (task 8.2) names it as the place `ri-11` must look. |
+| Pinned baselines read as asserting that the bug should exist | Each pinned value carries a YAML comment naming the roadmap item that flips it. The README states that baselines are characterisations. |
+| The oracle and a future probe diverge in what they call a "collision" | The oracle is deliberately narrow: same capability and same requirement heading. `ri-06` may detect more levels. The flip assertion is only `collision_detected`, not equality with the oracle. |
+
+## Open Questions
+
+None block implementation. These are recorded for downstream items:
+
+- Should `ri-06`'s probe also be exercised at the coordinator level by `ri-07`? Out of scope
+  here, and the probe seam allows either.
+- Once `ri-02` lands, should the fixture seed an `owners.yaml` so reports can name owners?
+  That is deferred to `ri-06`, which needs owners in its collision report.
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/dispatch-results/batch-5f656e42c1f7d13a649f095a-ri-05-attempt-1-g5.json b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/dispatch-results/batch-5f656e42c1f7d13a649f095a-ri-05-attempt-1-g5.json
new file mode 100644
index 00000000..7afff094
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/dispatch-results/batch-5f656e42c1f7d13a649f095a-ri-05-attempt-1-g5.json
@@ -0,0 +1,18 @@
+{
+  "attempt": 1,
+  "branch": "openspec/multiplayer-simulation-harness",
+  "change_id": "multiplayer-simulation-harness",
+  "degradations": [],
+  "dispatch_id": "batch-5f656e42c1f7d13a649f095a:ri-05:attempt-1",
+  "evidence": {
+    "commit": "3b6c2ce26bcda9a9e14f2e2eb5639f96858955e4",
+    "loop_state_digest": "f24cb17df8cf0f43ace6cca58c7dbd562a73d2845644a4659c79876df6123219",
+    "loop_state_path": "openspec/changes/multiplayer-simulation-harness/loop-state.json"
+  },
+  "handoff_id": "6a9dccf9-2520-4025-b2c5-9c80ad34b3e7",
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 5,
+  "outcome": "success",
+  "schema_version": 2,
+  "worktree_ref": "multiplayer-simulation-harness"
+}
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/loop-state.json b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/loop-state.json
new file mode 100644
index 00000000..a7c2272a
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/loop-state.json
@@ -0,0 +1,356 @@
+{
+  "schema_version": 6,
+  "change_id": "multiplayer-simulation-harness",
+  "current_phase": "DONE",
+  "iteration": 0,
+  "total_iterations": 20,
+  "max_phase_iterations": 3,
+  "findings_trend": [],
+  "blocking_findings": [],
+  "vendor_availability": {},
+  "packages_status": {},
+  "package_authors": {},
+  "implementation_strategy": {},
+  "memory_ids": [],
+  "handoff_ids": [
+    "fd37041f-3151-464f-b6b5-918c1295fc67",
+    "9403b68a-7911-4949-a775-3b689b8ecb54",
+    "44759acd-c2f6-4d02-8dfd-278037b64a61",
+    "11f32d63-4f2f-4bf4-a4d0-deebdea265f9",
+    "ab3b1133-8595-4fe0-92b6-909f7872b6f3",
+    "fa6e1d35-520b-42bd-932c-644b008829cf",
+    "cc44baf6-dd8c-4ae4-931c-2203d6928c33",
+    "164aa1f5-f41a-4f7f-bb02-dc3be93baeda",
+    "6a9dccf9-2520-4025-b2c5-9c80ad34b3e7"
+  ],
+  "phase_history": [
+    {
+      "at": "2026-10-05T07:14:09.249458+00:00",
+      "outcome": "proceed",
+      "phase": "GATEKEEPER"
+    },
+    {
+      "at": "2026-10-05T07:33:31.584300+00:00",
+      "outcome": "complete",
+      "phase": "PLAN_ITERATE"
+    },
+    {
+      "at": "2026-10-05T08:59:55.769068+00:00",
+      "outcome": "max_iter",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-09T08:08:36.154426+00:00",
+      "outcome": "converged",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-09T08:10:30.617950+00:00",
+      "outcome": "failed",
+      "phase": "IMPLEMENT"
+    },
+    {
+      "at": "2026-10-09T08:34:06.664816+00:00",
+      "outcome": "complete",
+      "phase": "IMPLEMENT"
+    },
+    {
+      "at": "2026-10-09T12:18:38.221344+00:00",
+      "outcome": "complete",
+      "phase": "IMPL_ITERATE"
+    },
+    {
+      "at": "2026-10-09T12:22:27.260061+00:00",
+      "note": "IMPL_REVIEW blocked before any review ran: the auto-mode classifier denied the converge() driver run as [CI Bypass] (driver shims base_ref=d22417e, excludes .review-ledger/.review-cache from the post-fix scope check, and drops to min_quorum=1). Needs an operator decision on how implementation review may run in cloud containers.",
+      "outcome": "host_escalate",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "at": "2026-10-10T03:14:50.052251+00:00",
+      "outcome": "converged",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "at": "2026-10-10T03:18:09.228272+00:00",
+      "outcome": "passed",
+      "phase": "VALIDATE"
+    }
+  ],
+  "last_handoff_id": "6a9dccf9-2520-4025-b2c5-9c80ad34b3e7",
+  "started_at": "2026-10-05T07:12:02.399401+00:00",
+  "phase_started_at": "2026-10-10T10:44:02.441949+00:00",
+  "previous_phase": "SUBMIT_PR",
+  "escalation_reason": "goal gate refused: required section not passed: Smoke Tests (not_applicable)",
+  "val_review_enabled": false,
+  "cli_review_enabled": true,
+  "error": null,
+  "phase_archetype": "runner",
+  "force": false,
+  "gate_signals": {
+    "external_dep_count": 0,
+    "has_broad_write_scope": false,
+    "has_db_migration": false,
+    "has_proposal": true,
+    "has_security_signal": false,
+    "has_specs": true,
+    "has_tasks": true,
+    "has_work_packages": false,
+    "package_count": 0,
+    "total_loc_estimate": null
+  },
+  "gate_verdict": null,
+  "gate_decisions": [
+    {
+      "approval_id": null,
+      "authorizing_disposition": "auto",
+      "default_action": null,
+      "disposition": "auto",
+      "gate": "proposal_approval",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "PLAN",
+      "posture_present": true,
+      "reason": "gate 'proposal_approval' auto-approved by trust posture",
+      "recorded_at": "2026-10-05T07:14:15.969805+00:00",
+      "resolution": "auto",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-05T09:00:11.451005+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator decision A1 (2026-10-05, supervisor session_01J39bSygVy2r68wyPyHN5VA): Roadmap.ready_items() reads roadmap.yaml from the shared integration ref; status transitions are written only there by a simulated supervisor/applier step; principals' own branches never edit roadmap.yaml (mirrors the real supervisor/worker split). Apply via PLAN_FIX to design D5/D7 plus ledger items 1-3.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator decision A1 (2026-10-05, supervisor session_01J39bSygVy2r68wyPyHN5VA): Roadmap.ready_items() reads roadmap.yaml from the shared integration ref; status transitions are written only there by a simulated supervisor/applier step; principals' own branches never edit roadmap.yaml (mirrors the real supervisor/worker split). Apply via PLAN_FIX to design D5/D7 plus ledger items 1-3.",
+      "recorded_at": "2026-10-05T13:44:40.103541+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-09T08:10:36.683211+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator (user, 2026-10-09) approved fast-forwarding the IMPLEMENT sub-agent worktree to origin/openspec/multiplayer-simulation-harness (git reset --hard / merge --ff-only) to resolve the IMPLEMENT branch-adoption failure.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator (user, 2026-10-09) approved fast-forwarding the IMPLEMENT sub-agent worktree to origin/openspec/multiplayer-simulation-harness (git reset --hard / merge --ff-only) to resolve the IMPLEMENT branch-adoption failure.",
+      "recorded_at": "2026-10-09T08:15:43.361558+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-09T12:22:33.881025+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator (user, 2026-10-10) chose option 2: port converge() base_ref + bookkeeping-path scope fix from the PR base (commit above) and run IMPL_REVIEW via converge() without driver shims.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator (user, 2026-10-10) chose option 2: port converge() base_ref + bookkeeping-path scope fix from the PR base (commit above) and run IMPL_REVIEW via converge() without driver shims.",
+      "recorded_at": "2026-10-10T03:04:37.519036+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "gate": "pr_creation",
+      "outcome": "blocked",
+      "resolution": "coordinator_unreachable",
+      "authorizing_disposition": "notify_with_timeout",
+      "reason": "gate 'pr_creation' parked: coordinator unreachable (request_approval failed: coordinator unauthorized (status=403))",
+      "approval_id": null,
+      "default_action": null,
+      "posture_present": true,
+      "notified": null,
+      "timeout_seconds": null,
+      "disposition": "notify_with_timeout",
+      "phase": "SUBMIT_PR",
+      "recorded_at": "2026-10-10T03:18:25.700615+00:00"
+    },
+    {
+      "gate": "escalate_resume",
+      "outcome": "blocked",
+      "resolution": "posture_block",
+      "authorizing_disposition": "block",
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "approval_id": null,
+      "default_action": null,
+      "posture_present": true,
+      "notified": null,
+      "timeout_seconds": null,
+      "disposition": "block",
+      "phase": "ESCALATE",
+      "recorded_at": "2026-10-10T09:48:18.467093+00:00"
+    },
+    {
+      "gate": "escalate_resume",
+      "outcome": "proceed",
+      "resolution": "console_approved",
+      "authorizing_disposition": "block",
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator (user, 2026-10-10) approved opening the PR against openspec/roadmap-multiplayer-collaboration: the pr_creation gate could not notify (coordinator 403); the PR base's TRUST_POSTURE.md already sets pr_creation to auto (7fea1cd). Console approval stands in for the undeliverable notification.",
+      "approval_id": null,
+      "default_action": null,
+      "posture_present": true,
+      "notified": null,
+      "timeout_seconds": null,
+      "disposition": "block",
+      "phase": "ESCALATE",
+      "recorded_at": "2026-10-10T09:48:18.635059+00:00",
+      "note": "Operator (user, 2026-10-10) approved opening the PR against openspec/roadmap-multiplayer-collaboration: the pr_creation gate could not notify (coordinator 403); the PR base's TRUST_POSTURE.md already sets pr_creation to auto (7fea1cd). Console approval stands in for the undeliverable notification."
+    },
+    {
+      "gate": "merge",
+      "outcome": "blocked",
+      "resolution": "posture_block",
+      "authorizing_disposition": "block",
+      "reason": "gate 'merge' parked: trust posture disposition is block",
+      "approval_id": null,
+      "default_action": null,
+      "posture_present": true,
+      "notified": null,
+      "timeout_seconds": null,
+      "disposition": "block",
+      "phase": "SUBMIT_PR",
+      "recorded_at": "2026-10-10T09:49:12.385406+00:00"
+    },
+    {
+      "gate": "merge",
+      "outcome": "proceed",
+      "resolution": "console_approved",
+      "authorizing_disposition": "block",
+      "reason": "gate 'merge' approved by the operator \u2014 Operator merged PR #669 ('merge 669') as a953b92 into openspec/roadmap-multiplayer-collaboration.",
+      "approval_id": null,
+      "default_action": null,
+      "posture_present": true,
+      "notified": null,
+      "timeout_seconds": null,
+      "provenance": {
+        "source": "human",
+        "approval_ref": "gate-decision:ba667a32-e0e7-4034-bbd1-0fe249f597aa"
+      },
+      "disposition": "block",
+      "phase": "SUBMIT_PR",
+      "recorded_at": "2026-10-10T10:35:29.524437+00:00",
+      "note": "Operator merged PR #669 ('merge 669') as a953b92 into openspec/roadmap-multiplayer-collaboration."
+    },
+    {
+      "gate": "escalate_resume",
+      "outcome": "blocked",
+      "resolution": "posture_block",
+      "authorizing_disposition": "block",
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "approval_id": null,
+      "default_action": null,
+      "posture_present": true,
+      "notified": null,
+      "timeout_seconds": null,
+      "provenance": {
+        "source": "posture",
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24"
+      },
+      "disposition": "block",
+      "phase": "ESCALATE",
+      "recorded_at": "2026-10-10T10:37:31.871689+00:00"
+    },
+    {
+      "gate": "escalate_resume",
+      "outcome": "proceed",
+      "resolution": "console_approved",
+      "authorizing_disposition": "block",
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator (user, 2026-10-10) approved resuming after the DONE goal gate refusal: proposal.md now declares deployable: false (ad747240), matching validation's measured surface; only Spec Compliance is required and it passes.",
+      "approval_id": null,
+      "default_action": null,
+      "posture_present": true,
+      "notified": null,
+      "timeout_seconds": null,
+      "provenance": {
+        "source": "human",
+        "approval_ref": null
+      },
+      "disposition": "block",
+      "phase": "ESCALATE",
+      "recorded_at": "2026-10-10T10:44:02.162212+00:00",
+      "note": "Operator (user, 2026-10-10) approved resuming after the DONE goal gate refusal: proposal.md now declares deployable: false (ad747240), matching validation's measured surface; only Spec Compliance is required and it passes."
+    }
+  ],
+  "pending_gate": null,
+  "goal_gate": {
+    "verdict": "passed",
+    "reason": "all required evidence present",
+    "evidence": {
+      "merge_authorized": true,
+      "pr_url": "https://github.com/jankneumann/agentic-coding-tools/pull/669",
+      "report_path": "openspec/changes/multiplayer-simulation-harness/validation-report.md",
+      "checked_at": "2026-10-10T10:44:02.415919+00:00",
+      "validate_outcome": "passed",
+      "validate_at": "2026-10-10T03:18:09.228272+00:00",
+      "report_time": "2026-10-10T03:17:49+00:00",
+      "report_time_source": "commit",
+      "bound_by": "VALIDATE",
+      "required_sections": [
+        "Spec Compliance"
+      ],
+      "phase_statuses": {
+        "Spec Compliance": "pass"
+      }
+    }
+  },
+  "park": null,
+  "degradations": []
+}
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/plan-findings.md b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/plan-findings.md
new file mode 100644
index 00000000..5a9adedc
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/plan-findings.md
@@ -0,0 +1,67 @@
+# Plan Findings: multiplayer-simulation-harness
+
+## Iteration 1 (2026-10-05)
+
+Baseline: `openspec validate --strict` passed on the scaffold, which is a structural pass
+only. GATEKEEPER set four conditions for PLAN:
+
+- replace the circular WHEN/THEN scaffolds;
+- record baselines without asserting later capabilities;
+- decide the capability, the non-goals and the offline strategy;
+- use `change_dir()`.
+
+| # | Type | Criticality | Description | Resolution |
+|---|------|-------------|-------------|------------|
+| 1 | testability | critical | Every scenario was circular ("WHEN implemented THEN <requirement restated>"), so nothing was verifiable | Rewrote the spec as 8 requirements with 26 concrete WHEN/THEN scenarios, each naming the command, the inputs and the exact report fields or exit codes |
+| 2 | completeness | critical | proposal.md lacked Why, What Changes and Impact sections | Rewrote the proposal with Why (ri-06 and ri-11 depend on this baseline), What Changes, Non-Goals, Impact, and a table mapping outcomes to requirements |
+| 3 | completeness | high | design.md was a stub that only listed open questions | Wrote design D1–D10, each decision with rejected alternatives, plus risks |
+| 4 | feasibility | high | tasks.md had 5 generic tasks, none traceable to a requirement and none single-commit | Replaced them with 26 TDD-ordered tasks carrying scenario IDs, design references, dependencies and sizes |
+| 5 | assumptions | high | The capability placeholder `multiplayer-collaboration` was shared by about 19 sibling deltas | Chose a new `multiplayer-simulation` capability (D1). This was a recorded autonomous decision; see the session log |
+| 6 | assumptions | high | Where the harness lives and which venv runs gen-eval were unstated | D2 puts it at `skills/tests/multiplayer-simulation/`. D3 adds gen-eval to the skills `test` extra; a scratch `uv lock` resolved |
+| 7 | assumptions | high | "Collision detected at plan time" has no detector today, so the baseline would pass vacuously | D4 adds a probe seam plus a ground-truth oracle. A broken fixture now exits 1 instead of reading as "not detected" |
+| 8 | assumptions | high | How time-blocked is measured was undefined, and a wall-clock measure would be nondeterministic | D5 uses logical ticks and the real admission rule `Roadmap.ready_items`, with a pinned baseline of 10 ticks under fixture durations |
+| 9 | testability | high | "Runs without network access" was not enforced | D9 adds an autouse socket-blocking fixture, a `file://` remote, and a byte-identity check with `COORDINATION_API_URL` set |
+| 10 | consistency | high | Downstream ri-06 and ri-11 need to flip this harness, but no flip mechanism was defined | Flips happen by registering a probe (one import line) or by a fixture edit plus a rule change, followed by a reviewed edit to the pinned expectation |
+| 11 | completeness | medium | Requirements covered only success paths | Added failure and edge scenarios: broken fixture, probe error, probe timeout, unknown probe, tick-budget exhaustion, fewer than two principals |
+| 12 | scope | medium | Non-goals were absent, and the incident has two halves | Non-goals now exclude the competing-spec half (ri-16), live LLM agents, owners.yaml (ri-02), coordinator variants (ri-07/08), durable state, and editing ri-01's guide |
+| 13 | completeness | medium | No CLI contract or report schema existed | Authored `contracts/cli/mpsim.yaml`, which validates against `cli-contract.schema.json` and cites 7 of 8 requirements, and `contracts/schemas/sim-report.schema.json`. Task 1.2 promotes both |
+| 14 | parallelizability | medium | No dependency graph existed, and scenario registration was a shared-file hotspot | Added a dependency graph (max width 3) and switched to `pkgutil` scenario discovery, so 4.4 and 5.2 never edit the same file |
+| 15 | testability | medium | Determinism was implicit, yet exact pinned values depend on it | Added the "Scenario Reports Are Deterministic" requirement: sorted keys, no paths or SHAs, byte-identical reruns |
+| 16 | consistency | low | CI coverage guard and path guard interplay | O.3 and A.1 cover both explicitly |
+
+Remaining below threshold: none.
+
+## Iteration 2 (2026-10-05)
+
+A cold re-read of the iteration-1 plan found 2 high, 4 medium and 2 low findings.
+
+| # | Type | Criticality | Description | Resolution |
+|---|------|-------------|-------------|------------|
+| 1 | clarity | high | The order of events within a tick was unspecified. A dependency finishing at tick 11 could admit its dependent at 11 or 12, which changes the pinned baseline (10 vs 11) | D5 now fixes the order: finishing steps push in declaration order, then waiting principals fetch and evaluate `ready_items()`, then admitted principals start |
+| 2 | consistency | high | D5 said ri-11 changes no harness code, yet `ScriptedAgent` hard-coded status transitions, so emitting `contract_complete` would have needed a code edit | Status transitions are now fixture data (`on_start` / `on_finish` `set_status`). The ri-11 flip is three fixture edits plus a rule change, worth 2 ticks under baseline durations. The hard-coded alternative is recorded as rejected |
+| 3 | testability | medium | O.2 compared "reports" from gen-eval runs, but gen-eval parses stdout into a body and adds timings, so byte identity was unobservable there | O.2 now compares `mpsim run` stdout directly, and moved from task 7.3 to task 6.1 |
+| 4 | clarity | medium | P.1's "every commit on alice's branch" included the seed commit | D6 defines a `sim-seed` identity for the seed commit. P.1 now scopes to commits reachable from the change branch but not from `main` |
+| 5 | clarity | medium | The pinned-baseline comment rule had no verifying scenario | Added scenario G.3, which scans the pack for `ri-06` / `ri-11` comments. The drift scenario became G.4, and tasks were renumbered |
+| 6 | clarity | medium | D.1's "separate temporary directories" did not say how a test controls them | D.1 now runs with different `TMPDIR` values |
+| 7 | completeness | low | `--tick-budget 0` or a negative budget was unhandled | Added exit 64 to D5, D8, the contract and task 6.1 |
+| 8 | feasibility | low | A hung probe thread could keep the process alive | D4 runs probes in a daemon thread that is abandoned at timeout |
+
+Quality checks after the fixes:
+
+- `openspec validate --strict` passes.
+- Scenario coverage is 27/27 IDs traced to tasks, with no orphans either way.
+- The CLI contract validates, and all traceability citations resolve.
+- The single uncited requirement, Archive-Stable, has no CLI surface. That is acceptable
+  because reverse traceability is not opted in.
+
+Remaining below threshold: none at medium or above.
+
+## Iteration 3 (2026-10-05): convergence
+
+| # | Type | Criticality | Description | Resolution |
+|---|------|-------------|-------------|------------|
+| 1 | consistency | medium | Fixture-declared status transitions and the intra-tick order were stated only in design D5, although the pinned baseline and ri-11's flip both depend on them | Added both as normative SHALL clauses in "Memory-Store Scenario Reports Time Blocked On Dependency" |
+| 2 | testability | low | The 30-second suite budget is recorded at task 9.1, not asserted | Accepted. A wall-clock assertion would be flaky in CI |
+| 3 | consistency | low | ri-06 and ri-11 deltas still reference the `multiplayer-collaboration` placeholder | Out of scope for this change. Recorded as an open question for those changes' own iteration |
+
+Termination: all findings are below the medium threshold. `openspec validate --strict` passes.
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/proposal.md b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/proposal.md
new file mode 100644
index 00000000..32e4bf0a
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/proposal.md
@@ -0,0 +1,128 @@
+---
+# Offline test harness under skills/tests/ plus a gen-eval gate fix; no service surface.
+deployable: false
+---
+
+# Change: multiplayer-simulation-harness
+
+> Parent roadmap: `multiplayer-collaboration` (item `ri-05`, Phase 1)
+> Change ID: `multiplayer-simulation-harness`
+> Effort: M
+> Priority: 2
+> Capability: `multiplayer-simulation` (new)
+
+## Why
+
+This toolkit is built by one developer and installed into team repositories. The
+`multiplayer-collaboration` roadmap exists because single-principal assumptions break in
+team use. Its motivating incident was a memory store planned by a small team: two
+developers' specs collided, and one developer sat blocked waiting for another's
+implementation when only the contract was needed.
+
+None of that can be observed in this repository today. There is one principal, one
+coordinator (or none), and one person planning at a time, so team failure modes never
+happen here. Later roadmap items need a measurable before/after to prove they work:
+
+- `ri-06` (`plan-time-collision-detection`) says "the simulation harness's same-requirement
+  scenario flips from not-detected to detected".
+- `ri-11` (`contract-dependencies`) says "the memory-store simulation scenario shows reduced
+  time-blocked-on-dependency compared with its baseline".
+
+Both outcomes need a harness that already exists, records an honest baseline, and changes its
+measured result when the real capability lands, without the scenario itself being rewritten.
+This change builds that harness. It does not build either capability.
+
+## What Changes
+
+- **A deterministic, offline simulation driver, `mpsim`**, at
+  `skills/tests/multiplayer-simulation/`. It builds a temporary world: one local bare git
+  repository acting as the shared remote, plus two or more simulated principals. Each
+  principal has its own git identity, its own clone and worktree, and its own scripted agent.
+  Principals see each other's work only through pushes to that remote. Time is a logical tick
+  clock rather than wall-clock time. The driver writes one JSON report per scenario run.
+- **A plan-time collision probe seam.** At each principal's plan step the driver calls every
+  registered `CollisionProbe` and records which probes ran and what they reported. No probe
+  is registered today, so the baseline result is "not detected". `ri-06` registers its scanner
+  as a probe. A ground-truth oracle, computed from fixture contents, also records whether a
+  collision actually exists, so a "not detected" baseline cannot pass because of a broken
+  fixture.
+- **Readiness from the real admission rule.** The driver decides when a dependent principal
+  becomes unblocked by calling the roadmap-runtime admission rule (`Roadmap.ready_items`) on
+  the `roadmap.yaml` visible on the shared remote. It does not carry its own readiness
+  logic. When `ri-11` changes that rule, the metric moves with it.
+- **Two scenarios, each with a control case:**
+  - `same-requirement-collision`: principal A pushes a change that modifies requirement R.
+    Principal B then plans a change that modifies R. The control case
+    `different-requirement-control` has B modify a different requirement.
+  - `memory-store-blocked-dependency`: reproduces the dependency half of the incident.
+    `retrieval-owner` depends on a memory-store API owned by `storage-owner`. The driver
+    reports `blocked_ticks` per principal. The control case `independent-principals-control`
+    has no dependency between them.
+- **A gen-eval scenario pack.** The four scenarios above are gen-eval CLI-transport
+  scenarios. They run against a ToolDescriptor derived from a new CLI contract for `mpsim`,
+  promoted to `openspec/contracts/multiplayer-simulation/cli/mpsim.yaml`. Each scenario pins
+  its baseline values. A later change that flips a baseline does so with a visible,
+  reviewed edit to the scenario's expectation.
+- **CI wiring.** The harness test directory joins the skills in-skill sweep in
+  `.github/workflows/ci.yml`. It runs with no services, no coordinator, and network sockets
+  blocked inside the test process.
+- **A small README** in the harness directory. It explains how a downstream change registers
+  a probe, flips a pinned baseline, or adds a scenario.
+
+## Non-Goals
+
+- **Building collision detection or contract-level dependencies.** Those belong to `ri-06`,
+  `ri-07` and `ri-11`. This change only records today's behaviour.
+- **The competing-spec half of the incident.** Reconciling two divergent specs is
+  `ri-16` (`reconcile-skill`), which can add its own scenario to this pack.
+- **Live LLM agents.** The agents here are scripted and deterministic, because CI must be
+  reproducible and offline. Running a live agent per principal (for example through
+  `packages/agent-scenarios`' `CLIVendorExecutor`) is a possible later extension, not part of
+  this change.
+- **Registered human principals and `owners.yaml`.** Simulated identities are local to the
+  harness. Once `ri-02` (`ownership-map`) lands, a scenario may seed an `owners.yaml`. This
+  change does not anticipate its schema.
+- **Coordinator-backed scenarios.** Coordinator claims, locks and queue entries are not
+  simulated. `ri-07` and `ri-08` may add a coordinator-backed variant, but the offline pack
+  stays the CI baseline.
+- **Durable state.** Reports are ephemeral test output written under a temp or `.reports/`
+  directory. They are not canonical state, so they are not registered in
+  `docs/guides/state-artifacts.md`.
+- **Editing the principles guide.** `docs/guides/multiplayer-collaboration.md` belongs to
+  `ri-01` (`multiplayer-principles-guide`), which is in flight. Linking the harness from that
+  guide is left to whichever change lands second.
+
+## Impact
+
+- **New capability spec delta**: `specs/multiplayer-simulation/spec.md` (ADDED requirements
+  only). The scaffold's placeholder capability `multiplayer-collaboration` is not used. See
+  design D1.
+- **New code**: `skills/tests/multiplayer-simulation/`, which holds the `mpsim` driver
+  package, its `bin/mpsim` launcher, fixtures, the gen-eval `evaluation/` pack and tests.
+  It sits under `skills/tests/`, which `install.sh` does not ship, so consumer repositories
+  receive nothing.
+- **New contract**: `openspec/contracts/multiplayer-simulation/cli/mpsim.yaml` (authored in
+  `contracts/cli/mpsim.yaml` in this change, then promoted), plus
+  `openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json`.
+- **Modified**: `skills/pyproject.toml` adds `gen-eval` as a path dependency of the `test`
+  extra, which also updates `skills/uv.lock`. `.github/workflows/ci.yml` adds
+  `tests/multiplayer-simulation` to the in-skill sweep list.
+  `openspec/contracts/README.md` gains a row in its contents table.
+- **Read-only dependencies (systems under test)**:
+  `skills/roadmap-runtime/scripts/models.py` (`Roadmap.ready_items`, `load_roadmap`, and
+  the roadmap schema it validates against), `packages/gen-eval` (ToolDescriptor, CLI transport,
+  `scripts/generate_tool_descriptor.py`), and `skills/tests/_shared/openspec_paths.py`.
+- **Downstream contract**: `ri-06` and `ri-11` consume the probe seam, the pinned baselines,
+  and the report fields `collision_detected` and `blocked_ticks`. Their spec deltas should
+  cite `multiplayer-simulation` requirements instead of restating them.
+
+## Acceptance Outcomes
+
+Each outcome from the roadmap item maps to a requirement in the spec delta:
+
+| Roadmap acceptance outcome | Requirement |
+|---|---|
+| Two principals modifying the same requirement; records whether a collision was detected at plan time (baseline: not detected) | Same-Requirement Collision Scenario Records Plan-Time Detection; Plan-Time Detectors Attach Through A Probe Seam |
+| Memory-store scenario reports time-blocked-on-dependency for the dependent principal | Memory-Store Scenario Reports Time Blocked On Dependency |
+| Scenarios run in CI without network access to a shared coordinator | Scenarios Run Offline Without A Shared Coordinator |
+| Scenario tests resolve change paths with `change_dir()` and pass the path-stability guard | Scenario Tests Are Archive-Stable |
diff --git a/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md
new file mode 100644
index 00000000..85da1870
--- /dev/null
+++ b/openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md
@@ -0,0 +1,332 @@
+# Session Log: multiplayer-simulation-harness
+
+> Decision rationale, trade-offs, and alternatives recorded at each workflow phase.
+> Auto-generated by workflow skills. Sanitized before commit.
+
+## Phase: Gatekeeper (2026-10-05)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Proceed without VAL_REVIEW** — No db/security/external-dep signals; additive and reversible
+
+### Context
+GATEKEEPER verdict: proceed. Outcomes verifiable (4 testable acceptance outcomes); risk low (additive gen-eval pack, offline). Conditions for PLAN: replace circular WHEN/THEN scaffolds with concrete scenarios; record baselines (collision not detected, non-zero blocked time) without asserting later capabilities; decide capability/non-goals/offline coordinator strategy; tests use change_dir().
+
+---
+
+## Phase: Plan Iteration 1 (2026-10-05)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **New capability multiplayer-simulation instead of the multiplayer-collaboration placeholder** `architectural: multiplayer-simulation` — About 19 sibling deltas target the multiplayer-collaboration placeholder. Putting harness requirements there would mix test-harness content with collaboration behaviour, and would itself create the same-requirement collision the roadmap is trying to surface. This was an autonomous resolution of an assumptions finding.
+2. **Harness at skills/tests/multiplayer-simulation, with gen-eval added to the skills test extra** `architectural: multiplayer-simulation` — The systems under test (roadmap-runtime, and later the plan-feature scanner) live in skills/. skills/tests is not shipped by install.sh. A scratch uv lock with gen-eval as a path dependency resolved 56 packages.
+3. **Collision detection via a CollisionProbe seam plus a ground-truth fixture oracle** `architectural: multiplayer-simulation` — No plan-time requirement-collision detector exists. The seam lets ri-06 attach its scanner without the harness fixing ri-06's interface. The oracle stops a broken fixture from making 'not detected' vacuously true.
+4. **Blocked time measured in logical ticks with the real Roadmap.ready_items admission rule** `architectural: multiplayer-simulation` — Ticks are deterministic, so exact baselines can be pinned. Using the real rule means ri-11's rule and schema change moves the metric without any edit to the harness code.
+5. **Pinned baselines live in gen-eval scenario YAML, and flips are reviewed expectation edits** `architectural: multiplayer-simulation` — The driver measures and the scenario decides what is expected. ri-06 and ri-11 flip a value in their own PRs, which keeps the before/after visible in review.
+6. **Assumption findings resolved autonomously, not through AskUserQuestion** `architectural: skill-procedure-deviation` — The skill directs assumption findings to AskUserQuestion. This run is an autopilot PLAN_ITERATE sub-agent that returns (outcome, handoff_id) with no interactive channel, and the proposal_approval gate was auto-approved by trust posture. Each assumption (capability, location, venv, detection seam, metric unit) became an explicit design decision with rejected alternatives, which PLAN_REVIEW and the human approver can overturn.
+7. **Analysis run inline, not through parallel Explore sub-agents** `architectural: skill-procedure-deviation` — This sub-agent harness exposes no Agent or Task tool, so the five-way parallel analysis could not be dispatched. The completeness, clarity, consistency, feasibility, parallelizability, testability and security/performance axes were analysed inline. This is reported as a fallback because the adapter was genuinely unavailable, not chosen to avoid dispatching.
+
+### Alternatives Considered
+- packages/multiplayer-sim as a new package: rejected because Needs its own CI job and cannot import skills/roadmap-runtime
+- agent-coordinator/evaluation scenarios: rejected because That gen-eval job needs Postgres and live HTTP, which contradicts the offline requirement
+- Harness-local readiness function: rejected because It would freeze the measured behaviour, and ri-11 could never move the metric
+- Invoke a predetermined scanner CLI: rejected because It would fix ri-06's interface before ri-06 designs it
+- Live LLM agents per principal: rejected because Nondeterministic and needs network and vendor access; left as a future ExecutorAgent
+
+### Trade-offs
+- Accepted Pinned exact baselines that downstream changes must edit over Field-presence-only assertions because An edit makes the flip visible in review; presence-only assertions could never detect a regression
+- Accepted Scripted deterministic agents over Realistic agent behaviour because CI reproducibility and offline execution are acceptance outcomes
+
+### Open Questions
+- [ ] ri-06 and ri-11 spec deltas should cite multiplayer-simulation requirements when they iterate (cross-capability reference)
+- [ ] Should the fixture seed owners.yaml once ri-02 lands? Deferred to ri-06
+
+### Completed Work
+- proposal.md rewritten with Why, What Changes, Non-Goals, Impact and an outcome-to-requirement map
+- design.md D1-D10 with alternatives and risks
+- spec delta moved to specs/multiplayer-simulation with 8 requirements and 26 scenarios
+- contracts/cli/mpsim.yaml (schema-valid, traceability resolves) and contracts/schemas/sim-report.schema.json
+- tasks.md with 26 tasks, scenario IDs, dependencies and graph
+- plan-findings.md iteration 1
+
+### Context
+Replaced the plan-roadmap scaffold with a full plan. Ten design decisions cover where the harness lives, how gen-eval runs it, the probe seam and oracle, logical-tick readiness through Roadmap.ready_items, offline enforcement and archive stability. The spec now has 8 requirements and 26 concrete scenarios, plus a CLI contract, a report schema and 26 TDD-ordered tasks with a dependency graph. All 16 findings were addressed, including 2 critical and 8 high.
+
+---
+
+## Phase: Plan Iteration 2 (2026-10-05)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Roadmap status transitions are fixture data (on_start/on_finish set_status)** `architectural: multiplayer-simulation` — Keeps the promise that ri-11 flips the blocked-time metric with fixture and rule changes only. Emitting contract_complete would otherwise need an edit to the harness agent.
+2. **Fixed intra-tick order: finishers push, then waiters evaluate readiness, then admitted principals start** `architectural: multiplayer-simulation` — The pinned blocked_ticks value depends on the order. Under this order, a dependency completed at tick t admits its dependent at tick t.
+3. **Vendor review (skill step 10) deferred to autopilot PLAN_REVIEW** `architectural: skill-procedure-deviation` — Under autopilot with cli_review_enabled, multi-vendor plan review is the dedicated PLAN_REVIEW phase that follows PLAN_ITERATE. Running it here would duplicate that phase, and the orchestrator owns its convergence loop.
+
+### Alternatives Considered
+- Hard-coded status transitions in ScriptedAgent: rejected because ri-11 would have to edit harness code
+
+### Trade-offs
+- Accepted Fixture schema carries per-step status data over Simpler fixtures because It decouples harness code from roadmap-state vocabulary that ri-11 will extend
+
+### Completed Work
+- D5 intra-tick order and data-driven status transitions
+- P.1, B.3, D.1 and O.2 sharpened; G.3 added
+- tick-budget below 1 exits 64; daemon-thread probe timeout
+- tasks renumbered; 27/27 scenario IDs traced
+
+### Context
+A cold re-review found 8 findings: 2 high, 4 medium and 2 low. All were fixed. The intra-tick event order is now fixed, so the pinned 10-tick baseline is unambiguous. Roadmap status transitions moved from agent code to fixture data, so ri-11 can flip the metric without editing the harness. Several scenarios were sharpened, and every one of the 27 scenario IDs traces to a task.
+
+---
+
+## Phase: Plan Iteration 3 (2026-10-05)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Lift D5's fixture-data transitions and intra-tick ordering into the requirement text** `architectural: multiplayer-simulation` — The pinned blocked_ticks baseline and ri-11's no-harness-edit flip both depend on these rules. As design-only notes they were not part of the contract that downstream changes and validators read.
+
+### Open Questions
+- [ ] Low: the 30-second suite budget is recorded at task 9.1 rather than asserted, to avoid a flaky timing test
+- [ ] Low: the ri-06 and ri-11 deltas still name multiplayer-collaboration; they should cite multiplayer-simulation when they iterate
+
+### Completed Work
+- spec: Memory-Store requirement states fixture-declared transitions and intra-tick order
+- openspec validate --strict passes; 27/27 scenarios traced; CLI contract valid
+
+### Context
+Convergence pass. One medium consistency finding was fixed: the Memory-Store requirement now states normatively that status transitions are fixture data and that within a tick, finishing steps push before readiness is evaluated. Both were previously only in design D5. No findings at medium or above remain, and the plan is ready for PLAN_REVIEW.
+
+---
+
+## Phase: Plan Review (2026-10-05)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Pin the review-packet base ref to 4a9e81b^ (driver shim, not a code edit)** `architectural: skill-procedure-deviation` — This checkout has no local `main` ref, so build_review_packet's default `git diff main...HEAD` was empty. The first attempt therefore reviewed only a truncated spec excerpt and produced a false 'no implementation' high finding. That attempt was discarded and archived outside the repo, and converge() was re-run with base_ref bound to the parent of the change's first commit.
+2. **min_quorum=1: single-vendor review** `architectural: skill-procedure-deviation` — Only claude-local was dispatchable. codex, antigravity, grok, pi and ocr had no CLI, and the SDK and OpenAI tiers had no keys. With quorum 2 the loop would end immediately with quorum_lost.
+3. **Return max_iter rather than converged on adjudication_required** — The ledger has zero D3-blocking items, but ledger item 1 is a high-impact judgment gap that one vendor cannot confirm. Reporting 'converged' would hide an unresolved high gap. The reviewer independently checked the finding and agrees it is valid: D5/D7 never name the ref that ready_items() reads.
+
+### Capability Gaps Observed
+- **convergence_failed**: review_packet defaults base_ref to a local 'main' ref that cloud worktrees may lack, so the diff silently comes out empty. converge() exposes no base_ref parameter. (skill: parallel-infrastructure, severity: high)
+- **convergence_failed**: With a single vendor, any high judgment finding is permanently unconfirmed, so converge() always exits adjudication_required before fix dispatch (skill: autopilot, severity: medium)
+
+### Open Questions
+- [ ] Adjudicate ledger item 1 (high): choose the roadmap ref model for memory-store readiness. Option (a): read the dependency status from the owner's branch. Option (b): push status transitions to main. Then update D5/D7, the Memory-Store requirement, and tasks 5.1/5.2.
+
+### Completed Work
+- converge(review_type=plan) round 1: 9 findings, all unconfirmed single-vendor: 1 high, 2 medium, 6 low
+- Ledger: .review-ledger/ledger.json; checkpoint: .review-cache/round-1/
+- PLAN_FIX sub-step: 0 invocations, because the loop exited at step 2g (adjudication) before step 2k
+
+### Next Steps
+- Adjudicate item 1, then run PLAN_FIX for items 1-3 (design.md, spec.md, sim-report.schema.json)
+- Medium items: #2 SHALL clauses lacking scenarios (no-coordinator-imports, fixture-only status transitions, probe registration without scenario edits); #3 the error-path report cannot satisfy the schema (principals minItems 2, non-null timeline)
+- Low items #4-#8 cover stale task cross-references in design.md, exit code 2 missing from the D8 table, wording in the promoted contract header, the interpreter for bin/mpsim and gen-eval, a ready_items/checkpoint verification note, and the wording of 'missing --fixture-dir'
+- Item #9 targets loop-state.json, which the orchestrator owns. PLAN_FIX must not edit it.
+- Provision a second review vendor, or add a base_ref parameter to converge(), so later rounds can reach consensus
+
+### Relevant Files
+- `openspec/changes/multi

[diff truncated to fit packet budget; use Read/Grep for the remainder]

```

### Rule groups

#### Group 1 (default: `(default)`)
Applies to:
- .github/CODEOWNERS
- .github/workflows/ci.yml
- TRUST_POSTURE.md
- docs/architecture-analysis/contracts-inventory.md
- docs/architecture-analysis/skills-inventory.md
- docs/decisions/README.md
- docs/decisions/agent-identity.md
- docs/decisions/model-routing.md
- docs/decisions/multiplayer-collaboration.md
- docs/decisions/multiplayer-simulation.md
- docs/decisions/ownership-map.md
- docs/decisions/parallel-infrastructure.md
- docs/decisions/roadmap-orchestration.md
- docs/decisions/skill-workflow.md
- docs/decisions/supervise.md
- docs/decisions/toolkit-distribution.md
- docs/decisions/trust-posture.md
- docs/guides/skills.md
- docs/guides/state-artifacts.md
- docs/skills-catalogue.md
- openspec/changes/archive/2026-10-10-dispatch-contract/.review-ledger/ledger.json
- openspec/changes/archive/2026-10-10-dispatch-contract/design.md
- openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g2.json
- openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g3.json
- openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g4.json
- openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g5.json
- openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g6.json
- openspec/changes/archive/2026-10-10-dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g7.json
- openspec/changes/archive/2026-10-10-dispatch-contract/handoffs/eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5.json
- openspec/changes/archive/2026-10-10-dispatch-contract/impl-findings.md
- openspec/changes/archive/2026-10-10-dispatch-contract/loop-state.json
- openspec/changes/archive/2026-10-10-dispatch-contract/plan-findings.md
- openspec/changes/archive/2026-10-10-dispatch-contract/proposal.md
- openspec/changes/archive/2026-10-10-dispatch-contract/session-log.md
- openspec/changes/archive/2026-10-10-dispatch-contract/tasks.md
- openspec/changes/archive/2026-10-10-dispatch-contract/validation-report.md
- openspec/changes/archive/2026-10-10-dispatch-contract/work-packages.yaml
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/.review-ledger/ledger.json
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/design.md
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/loop-state.json
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/plan-findings.md
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/proposal.md
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/review-findings-plan.json
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/consensus-plan.json
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/raw-codex-plan.meta.json
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/raw-codex-plan.txt
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/review-manifest.json
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/reviews/review-prompt.md
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/session-log.md
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/tasks.md
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/validation-report.md
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/.review-ledger/ledger.json
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/contracts/cli/mpsim.yaml
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/contracts/schemas/sim-report.schema.json
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/design.md
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/dispatch-results/batch-5f656e42c1f7d13a649f095a-ri-05-attempt-1-g5.json
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/loop-state.json
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/plan-findings.md
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/proposal.md
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/session-log.md
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/tasks.md
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/validation-report.md
- openspec/changes/archive/2026-10-10-ownership-map/.review-ledger/ledger.json
- openspec/changes/archive/2026-10-10-ownership-map/contracts/README.md
- openspec/changes/archive/2026-10-10-ownership-map/contracts/schemas/human-principals.schema.json
- openspec/changes/archive/2026-10-10-ownership-map/contracts/schemas/owners.schema.json
- openspec/changes/archive/2026-10-10-ownership-map/design.md
- openspec/changes/archive/2026-10-10-ownership-map/loop-state.json
- openspec/changes/archive/2026-10-10-ownership-map/plan-findings.md
- openspec/changes/archive/2026-10-10-ownership-map/proposal.md
- openspec/changes/archive/2026-10-10-ownership-map/review-findings-plan.json
- openspec/changes/archive/2026-10-10-ownership-map/reviews/consensus-plan.json
- openspec/changes/archive/2026-10-10-ownership-map/reviews/findings-claude_code-plan.json
- openspec/changes/archive/2026-10-10-ownership-map/session-log.md
- openspec/changes/archive/2026-10-10-ownership-map/tasks.md
- openspec/changes/archive/2026-10-10-ownership-map/validation-report.md
- openspec/changes/archive/2026-10-10-ownership-map/work-packages.yaml
- openspec/changes/archive/2026-10-10-toolkit-consistency/.review-ledger/ledger.json
- openspec/changes/archive/2026-10-10-toolkit-consistency/design.md
- openspec/changes/archive/2026-10-10-toolkit-consistency/dispatch-results/batch-70e0f5a2192d3fc876eb9732-ri-20-attempt-1-g7.json
- openspec/changes/archive/2026-10-10-toolkit-consistency/dispatch-results/batch-70e0f5a2192d3fc876eb9732-ri-20-attempt-1-g8.json
- openspec/changes/archive/2026-10-10-toolkit-consistency/dispatch-results/batch-70e0f5a2192d3fc876eb9732-ri-20-attempt-1-g9.json
- openspec/changes/archive/2026-10-10-toolkit-consistency/loop-state.json
- openspec/changes/archive/2026-10-10-toolkit-consistency/plan-findings.md
- openspec/changes/archive/2026-10-10-toolkit-consistency/proposal.md
- openspec/changes/archive/2026-10-10-toolkit-consistency/session-log.md
- openspec/changes/archive/2026-10-10-toolkit-consistency/tasks.md
- openspec/changes/archive/2026-10-10-toolkit-consistency/validation-report.md
- openspec/changes/openrouter-review-lane/.review-ledger/ledger.json
- openspec/changes/openrouter-review-lane/design.md
- openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g1.json
- openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g2.json
- openspec/changes/openrouter-review-lane/dispatch-results/batch-d8913c4d8e973cd7940e2d09-ri-22-attempt-1-g3.json
- openspec/changes/openrouter-review-lane/loop-state.json
- openspec/changes/openrouter-review-lane/plan-findings.md
- openspec/changes/openrouter-review-lane/proposal.md
- openspec/changes/openrouter-review-lane/session-log.md
- openspec/changes/openrouter-review-lane/tasks.md
- openspec/contracts/README.md
- openspec/contracts/multiplayer-simulation/cli/mpsim.yaml
- openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json
- openspec/owners.yaml
- openspec/roadmaps/multiplayer-collaboration/checkpoint.json
- openspec/roadmaps/multiplayer-collaboration/learning-log.md
- openspec/roadmaps/multiplayer-collaboration/learnings/_supervisor.md
- openspec/roadmaps/multiplayer-collaboration/learnings/ri-01.md
- openspec/roadmaps/multiplayer-collaboration/learnings/ri-02.md
- openspec/roadmaps/multiplayer-collaboration/learnings/ri-05.md
- openspec/roadmaps/multiplayer-collaboration/learnings/ri-20.md
- openspec/roadmaps/multiplayer-collaboration/learnings/ri-21.md
- openspec/roadmaps/multiplayer-collaboration/roadmap.yaml
- openspec/specs/agent-identity/spec.md
- openspec/specs/multiplayer-collaboration/spec.md
- openspec/specs/multiplayer-simulation/spec.md
- openspec/specs/ownership-map/spec.md
- openspec/specs/parallel-infrastructure/spec.md
- openspec/specs/roadmap-orchestration/spec.md
- openspec/specs/skill-workflow/spec.md
- openspec/specs/supervise/spec.md
- openspec/specs/toolkit-distribution/spec.md
- openspec/specs/trust-posture/spec.md
- openspec/supervise/supervisor-record.json
- skills/install-manifest.json
- skills/install.sh
- skills/ownership-runtime/install_assets/openspec/schemas/human-principals.schema.json
- skills/ownership-runtime/install_assets/openspec/schemas/owners.schema.json
- skills/pyproject.toml
- skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-request.schema.json

Review for correctness, security, and adherence to this repository's conventions.

#### Group 2 (default: `agent-coordinator/agents.yaml`)
Applies to:
- agent-coordinator/agents.yaml

Verify a new or changed CLI/SDK block's flags match what that vendor's CLI actually accepts (cross-check against any comment citing a verified version). Check that trust_level, capabilities, and archetypes are consistent with what the agent is actually granted.

#### Group 3 (default: `**/*.py`)
Applies to:
- agent-coordinator/src/agents_config.py
- agent-coordinator/tests/test_human_principals.py
- agent-coordinator/tests/test_registry_projection.py
- packages/gen-eval/scripts/check_traceability.py
- packages/gen-eval/tests/test_traceability_gate.py
- skills/shared/approval_gate.py
- skills/shared/dispatch_contract.py
- skills/shared/payload_hash.py

Check for unhandled exceptions, resource leaks (files/sockets/locks not in a context manager), and mutable default arguments. Flag a docstring claim ("never raises", "pure function") the code does not actually satisfy.

#### Group 4 (default: `openspec/changes/*/specs/**/spec.md`)
Applies to:
- openspec/changes/archive/2026-10-10-dispatch-contract/specs/parallel-infrastructure/spec.md
- openspec/changes/archive/2026-10-10-dispatch-contract/specs/roadmap-orchestration/spec.md
- openspec/changes/archive/2026-10-10-dispatch-contract/specs/skill-workflow/spec.md
- openspec/changes/archive/2026-10-10-dispatch-contract/specs/supervise/spec.md
- openspec/changes/archive/2026-10-10-dispatch-contract/specs/trust-posture/spec.md
- openspec/changes/archive/2026-10-10-multiplayer-principles-guide/specs/multiplayer-collaboration/spec.md
- openspec/changes/archive/2026-10-10-multiplayer-simulation-harness/specs/multiplayer-simulation/spec.md
- openspec/changes/archive/2026-10-10-ownership-map/specs/agent-identity/spec.md
- openspec/changes/archive/2026-10-10-ownership-map/specs/ownership-map/spec.md
- openspec/changes/archive/2026-10-10-toolkit-consistency/specs/toolkit-distribution/spec.md
- openspec/changes/openrouter-review-lane/specs/model-routing/spec.md
- openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
- openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md
- openspec/changes/openrouter-review-lane/specs/supervise/spec.md

Verify every SHALL/MUST has at least one Scenario with WHEN/THEN. Check that a MODIFIED requirement's unchanged scenarios were preserved, not silently dropped.

#### Group 5 (default: `openspec/schemas/*.schema.json`)
Applies to:
- openspec/schemas/dispatch-request.schema.json
- openspec/schemas/human-principals.schema.json
- openspec/schemas/owners.schema.json

Verify the schema is valid Draft 2020-12, that required fields were not silently dropped, and that any mirrored copy (install_assets, sentinel-injected) is checked for the same change.

#### Group 6 (default: `skills/*/scripts/*.py`)
Applies to:
- skills/autopilot/scripts/agent_lane.py
- skills/autopilot/scripts/autopilot.py
- skills/autopilot/scripts/convergence_loop.py
- skills/autopilot/scripts/goal_gate.py
- skills/autopilot/scripts/phase_agent.py
- skills/autopilot/scripts/runner.py
- skills/improve-harness/scripts/analyze_failures.py
- skills/improve-harness/scripts/export_shared_learnings.py
- skills/ownership-runtime/scripts/__init__.py
- skills/ownership-runtime/scripts/check_owners.py
- skills/ownership-runtime/scripts/codeowners.py
- skills/ownership-runtime/scripts/owners.py
- skills/ownership-runtime/scripts/principals.py
- skills/parallel-infrastructure/scripts/review_ledger.py
- skills/supervise/scripts/cycle_state.py
- skills/supervise/scripts/execution.py
- skills/supervise/scripts/gate_router.py

Check for unhandled exceptions on the failure paths this module is meant to guard (network, subprocess, file I/O). Verify a function documented as "never raises" actually catches every exception class it claims to. Flag silent behavior changes to existing callers.

#### Group 7 (default: `skills/*/SKILL.md`)
Applies to:
- skills/improve-harness/SKILL.md
- skills/ownership-runtime/SKILL.md

Check that the workflow steps match what the referenced scripts actually accept (flags, return shapes). Verify examples are runnable as written. Flag instructions that silently assume coordinator, tier, or environment state without stating the fallback.

#### Group 8 (default: `skills/tests/**`)
Applies to:
- skills/tests/autopilot/test_agent_lane.py
- skills/tests/autopilot/test_console_interviewer.py
- skills/tests/autopilot/test_gate_check_reeval.py
- skills/tests/autopilot/test_goal_gate.py
- skills/tests/autopilot/test_runner_archived_change.py
- skills/tests/improve-harness/test_export_shared_learnings.py
- skills/tests/improve-harness/test_shared_learnings_merge.py
- skills/tests/install_sh/test_install_check_drift.py
- skills/tests/install_sh/test_install_stamp.py
- skills/tests/install_sh/test_openspec_assets.py
- skills/tests/install_sh/test_payload_hash.py
- skills/tests/install_sh/test_related_validation.py
- skills/tests/install_sh/test_state_artifacts_registration.py
- skills/tests/multiplayer-simulation/README.md
- skills/tests/multiplayer-simulation/bin/mpsim
- skills/tests/multiplayer-simulation/conftest.py
- skills/tests/multiplayer-simulation/evaluation/descriptor.yaml
- skills/tests/multiplayer-simulation/evaluation/scenarios/blocked.yaml
- skills/tests/multiplayer-simulation/evaluation/scenarios/collision.yaml
- skills/tests/multiplayer-simulation/evaluation/scenarios/usage.yaml
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/scenario.yaml
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/seed/openspec/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/scenario.yaml
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/proposal.md
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/roadmap.yaml
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/scenario.yaml
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/proposal.md
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/roadmap.yaml
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/scenario.yaml
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/seed/openspec/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/mpsim/__init__.py
- skills/tests/multiplayer-simulation/mpsim/__main__.py
- skills/tests/multiplayer-simulation/mpsim/agents.py
- skills/tests/multiplayer-simulation/mpsim/applier.py
- skills/tests/multiplayer-simulation/mpsim/clock.py
- skills/tests/multiplayer-simulation/mpsim/errors.py
- skills/tests/multiplayer-simulation/mpsim/fixture.py
- skills/tests/multiplayer-simulation/mpsim/model.py
- skills/tests/multiplayer-simulation/mpsim/oracle.py
- skills/tests/multiplayer-simulation/mpsim/paths.py
- skills/tests/multiplayer-simulation/mpsim/probes/__init__.py
- skills/tests/multiplayer-simulation/mpsim/report.py
- skills/tests/multiplayer-simulation/mpsim/runner.py
- skills/tests/multiplayer-simulation/mpsim/scenarios/__init__.py
- skills/tests/multiplayer-simulation/mpsim/scenarios/blocked.py
- skills/tests/multiplayer-simulation/mpsim/scenarios/collision.py
- skills/tests/multiplayer-simulation/mpsim/world.py
- skills/tests/multiplayer-simulation/test_agents.py
- skills/tests/multiplayer-simulation/test_archive_stability.py
- skills/tests/multiplayer-simulation/test_blocked_scenarios.py
- skills/tests/multiplayer-simulation/test_cli.py
- skills/tests/multiplayer-simulation/test_collision_scenarios.py
- skills/tests/multiplayer-simulation/test_contracts.py
- skills/tests/multiplayer-simulation/test_descriptor_drift.py
- skills/tests/multiplayer-simulation/test_gen_eval_pack.py
- skills/tests/multiplayer-simulation/test_oracle.py
- skills/tests/multiplayer-simulation/test_probes.py
- skills/tests/multiplayer-simulation/test_report.py
- skills/tests/multiplayer-simulation/test_scaffold.py
- skills/tests/multiplayer-simulation/test_world.py
- skills/tests/ownership-runtime/__init__.py
- skills/tests/ownership-runtime/conftest.py
- skills/tests/ownership-runtime/fixtures/humans/invalid/bad_day.json
- skills/tests/ownership-runtime/fixtures/humans/invalid/bad_email.json
- skills/tests/ownership-runtime/fixtures/humans/invalid/bad_github_handle.json
- skills/tests/ownership-runtime/fixtures/humans/invalid/bad_hours.json
- skills/tests/ownership-runtime/fixtures/humans/invalid/duplicate_domains.json
- skills/tests/ownership-runtime/fixtures/humans/invalid/empty_display_name.json
- skills/tests/ownership-runtime/fixtures/humans/invalid/missing_display_name.json
- skills/tests/ownership-runtime/fixtures/humans/invalid/unknown_availability_field.json
- skills/tests/ownership-runtime/fixtures/humans/invalid/unknown_field.json
- skills/tests/ownership-runtime/fixtures/humans/valid/full.json
- skills/tests/ownership-runtime/fixtures/humans/valid/minimal.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/bad_capability_key.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/bad_principal_id.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/bad_roadmap_key.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/duplicate_owners.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/empty_owners.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/missing_default_owner.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/missing_owners.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/path_char_class.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/path_empty_segment.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/path_negation.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/path_whitespace.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/registry_absolute.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/registry_nested_parent_escape.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/registry_parent_escape.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/unknown_assignment_key.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/unknown_assignments_key.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/unknown_root_key.json
- skills/tests/ownership-runtime/fixtures/owners/invalid/wrong_schema_version.json
- skills/tests/ownership-runtime/fixtures/owners/valid/embedded_double_star_schema_ok.json
- skills/tests/ownership-runtime/fixtures/owners/valid/full.json
- skills/tests/ownership-runtime/fixtures/owners/valid/minimal.json
- skills/tests/ownership-runtime/test_check_owners.py
- skills/tests/ownership-runtime/test_codeowners_emit.py
- skills/tests/ownership-runtime/test_codeowners_reconcile.py
- skills/tests/ownership-runtime/test_coordinator_independence.py
- skills/tests/ownership-runtime/test_owners.py
- skills/tests/ownership-runtime/test_principals.py
- skills/tests/ownership-runtime/test_repository_invariant.py
- skills/tests/ownership-runtime/test_schema_copies.py
- skills/tests/parallel-infrastructure/test_review_ledger.py
- skills/tests/shared/test_committed_dispatch_scope.py
- skills/tests/shared/test_dispatch_contract.py
- skills/tests/state-artifacts/test_state_artifacts_guide.py
- skills/tests/supervise/test_execution.py
- skills/tests/supervise/test_execution_contract.py
- skills/tests/supervise/test_gate_router.py

Same standard as scripts/tests/: verify the test would fail if the behavior it targets were broken. Check that fixture paths use openspec_paths.change_dir rather than a literal openspec/changes/<id>/ path where the guide requires it.

### Spec excerpts
#### specs/model-routing/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

#### specs/parallel-infrastructure/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

#### specs/skill-workflow/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

#### specs/supervise/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

### Open ledger items
- [19] Since commit 62590065 a metered lane is refused (spend_context_missing) unless dispatch_and_wait receives a SpendContext, and converge() builds one only when its caller passes the new optional `phase`. The only caller that passes `phase` is agent_lane.py (task 5.6). The host inline converge() call in skills/autopilot/SKILL.md (PLAN_REVIEW fallback, about line 567) and the other host review phases pass no phase, and task 6.4 edits only the cloud review-section text. On a host where D5 selects the metered lane (one non-metered lane), every host converge() round therefore refuses the openrouter lane and ends capability_unavailable. The 'A host-path metered review is recorded' scenario can only pass in a unit test that calls dispatch_and_wait directly. Fix: add a task (or extend 6.4) that makes every host converge() caller in skills/autopilot/SKILL.md pass phase=<PLAN_REVIEW|IMPL_REVIEW|VAL_REVIEW>, or have converge() derive a SpendContext from change_id plus review_type and round when phase is None (accepting the IMPL/VAL collision only for that fallback).
- [20] Task 5.6 bullet 1 still says converge() 'passes work_unit_ref=<change_id>:<phase>:round-<n> to dispatch_and_wait (via _accepts_kwarg)'. After commit 62590065 the design's interface contract table, D4 and task 3.10 define the keyword as `spend_context: SpendContext(change_id, work_unit_ref)`. Groups 3 and 5 implement the two sides of this keyword in separate packages, so an implementer following 5.6 literally would pass a keyword that ReviewOrchestrator.dispatch_and_wait does not accept, and _accepts_kwarg would silently drop it, which leaves every metered dispatch spend_context_missing.
- [21] The D4 per-round budget re-check reads metered_usd_used from GET /routing/usage, which counts only ledger rows. Rows that spooled because POST /routing/spend failed are invisible to it. D4 says 'the key's credit limit bounds spend while rows sit in the spool', but when the key limit is null and the coordinator ceiling is the only source, a worker whose GET succeeds while its POST fails (the partly-forbidden coordinator case D4 itself cites: coordinator_projection_forbidden) keeps passing the re-check while every round's spend spools. The bound then fails exactly in the degraded mode that motivated the spool. The Cost abuse bullet in Security and the Risks row on concurrent overspend do not cover it.

Do not emit findings for issues already in the ledger except to re-verify the open items listed above.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 1. Focus on remaining issues.