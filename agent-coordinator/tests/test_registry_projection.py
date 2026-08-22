"""Registry-projection invariant (agent-identity spec, task 4.1).

Every agent declared in ``agents.yaml`` must fully materialize its runtime
projections. This test exists because the opposite failed silently: three
harnesses (``antigravity-local``, ``grok-local``, ``pi-local``) were added to
the registry with ``trust_level: 3`` while nobody created their profile rows
or identities, and ``resolve_trust_level()`` quietly served the default of 2
for two shipped changes. A fourth (``codex-local``) was found during this
change: migration 019's rename of ``codex_local_worker`` is a no-op because
migration 007 never seeded that name.

The rules asserted here (spec: "Registry Projection Invariant") are therefore
about the *registry as it actually is*, not a fixture:

1. every registry agent gets an **enabled** profile row carrying its declared
   trust level (:func:`_profile_row_violations`);
2. every registry agent contributes an identity map entry, or its ``api_key``
   is absent / an unresolved ``${VAR}`` in this environment — and no entry ever
   maps to a different agent (:func:`_identity_violations`);
3. the ``profile`` name each entry references resolves after sync
   (:func:`_profile_resolution_violations`);
4. every enabled row post-sync is registry-declared or named in
   ``UNMANAGED_PROFILES`` (:func:`_unclassified_profile_violations`);
5. every agent *resolves* — the way ``get_agent_profile()`` resolves, assignment
   first and ``agent_type`` + ``created_at`` fallback second — to a profile
   carrying its declared trust level (:func:`_resolution_violations`).

Rule 5 exists because rules 1 and 3 look rows up **by name**, which proves a row
exists but not that the agent reaches it. That blind spot let a second defect
survive this very invariant: ``agent_profile_assignments`` was not projected, so
any agent sharing an ``agent_type`` with an older profile row silently resolved
to that older row instead (design D11).

Each rule is a checker returning human-readable violations, so the negative
tests at the bottom feed the *same* checkers a broken world and prove the
invariant has teeth. Without those, a green run here would only mean the tree
happens to be consistent today.

No live Postgres: sync runs against the ``FakeDb`` / ``FakeAudit`` seams from
``tests/test_profile_sync.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents_config import (
    ASSIGNMENT_ASSIGNED_BY,
    UNMANAGED_PROFILES,
    AgentEntry,
    DuplicateApiKeyError,
    ProfileSyncError,
    get_api_key_identities,
    load_agents_config,
    sync_profiles,
)
from src.config import reset_config
from src.profile_loader import _INTERPOLATION_RE
from tests.test_profile_sync import (
    FakeAudit,
    FakeDb,
    _agent,
    _assignment,
    _row,
)

#: The ``agent_profiles`` rows a freshly migrated database holds, so the sync
#: under test runs against the state a real coordinator boots into rather than
#: an empty table. Names are post-019: 007 seeded ``claude_code_cli``,
#: ``claude_code_web_reviewer``, ``claude_code_web_implementer``,
#: ``codex_cloud_worker`` and ``strands_orchestrator``; 019 renamed them. 019's
#: other renames (``codex_local_worker``, ``gemini_local_worker``,
#: ``gemini_cloud_worker``) matched nothing — that gap is exactly what rule 1
#: below now catches. 026 added ``evaluator``.
MIGRATION_SEEDED_ROWS: list[dict[str, Any]] = [
    _row("claude_code_local", agent_type="claude_code", trust_level=3),
    _row("claude_code_remote", agent_type="claude_code", trust_level=2),
    _row("claude_code_reviewer", agent_type="claude_code", trust_level=1),
    _row("codex_remote", agent_type="codex", trust_level=2),
    _row("strands_local", agent_type="strands", trust_level=3),
    _row(
        "evaluator",
        agent_type="evaluator",
        trust_level=2,
        allowed_operations=["read", "review", "evaluate"],
    ),
]


@pytest.fixture(autouse=True)
def _sync_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """The invariant describes the enforced projection, not the rollback lever."""
    monkeypatch.delenv("PROFILE_SYNC_ENABLED", raising=False)
    reset_config()


@pytest.fixture
def registry() -> list[AgentEntry]:
    """The real ``agents.yaml`` — the point is to track the actual registry."""
    return load_agents_config()


async def _synced_db(
    agents: list[AgentEntry],
    seed: list[dict[str, Any]] | None = None,
    assignments: list[dict[str, Any]] | None = None,
) -> FakeDb:
    """Run the registry projection and return the resulting database."""
    db = FakeDb(
        seed if seed is not None else MIGRATION_SEEDED_ROWS,
        assignments=assignments,
    )
    await sync_profiles(agents, db=db, audit=FakeAudit())
    return db


async def _synced_rows(
    agents: list[AgentEntry],
    seed: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run the registry projection and return the resulting profile table."""
    return (await _synced_db(agents, seed)).rows


# ---------------------------------------------------------------------------
# Invariant checkers — shared by the positive and the negative tests
# ---------------------------------------------------------------------------


def _report(violations: list[str]) -> str:
    return "\n  - ".join(["Registry projection invariant violated:", *violations])


def _profile_row_violations(
    agents: list[AgentEntry],
    rows: list[dict[str, Any]],
) -> list[str]:
    """Rule 1 — enabled row with the declared trust level, for every agent."""
    by_name = {str(r.get("name")): r for r in rows}
    violations: list[str] = []
    for agent in agents:
        row = by_name.get(agent.profile)
        if row is None:
            violations.append(
                f"agent {agent.name!r} declares profile {agent.profile!r} but sync "
                f"produced no enabled row — the harness is half-onboarded. Check its "
                f"entry in agent-coordinator/agents.yaml and sync_profiles() in "
                f"src/agents_config.py."
            )
            continue
        if not row.get("enabled", False):
            violations.append(
                f"agent {agent.name!r} declares profile {agent.profile!r} but that row "
                f"is disabled after sync — the agent would authenticate and then be "
                f"refused. Fix the registry entry or re-enable the row."
            )
        if row.get("trust_level") != agent.trust_level:
            violations.append(
                f"agent {agent.name!r} declares trust_level {agent.trust_level} but "
                f"profile {agent.profile!r} carries {row.get('trust_level')!r} after "
                f"sync — this is the silent trust downgrade the projection exists to "
                f"prevent."
            )
    return violations


def _identity_violations(
    agents: list[AgentEntry],
    identities: dict[str, dict[str, str]],
) -> list[str]:
    """Rule 2 — an identity entry, or an explicitly unresolvable key.

    CI has no ``.secrets.yaml``, so most ``${VAR}`` placeholders do not resolve.
    The rule asserted is therefore the *disjunction*, plus the part that must
    hold either way: no agent's key may map to some other agent's identity.
    """
    by_agent: dict[str, list[str]] = {}
    for key, identity in identities.items():
        by_agent.setdefault(identity["agent_id"], []).append(key)

    known = {agent.name for agent in agents}
    violations: list[str] = []

    for agent_id in sorted(set(by_agent) - known):
        violations.append(
            f"identity map contains agent_id {agent_id!r}, which no agents.yaml entry "
            f"declares — identities must be a projection of the registry, never "
            f"independently authored."
        )

    for agent in agents:
        mapped = by_agent.get(agent.name, [])
        key = agent.api_key
        resolvable = bool(key) and not _INTERPOLATION_RE.search(key or "")
        if resolvable:
            if key not in identities:
                violations.append(
                    f"agent {agent.name!r} has a resolvable api_key but contributes no "
                    f"identity entry — get_api_key_identities() dropped it."
                )
            elif identities[key or ""]["agent_id"] != agent.name:
                violations.append(
                    f"agent {agent.name!r}'s api_key maps to "
                    f"{identities[key or '']['agent_id']!r} — one agent's key must "
                    f"never authenticate as another."
                )
        elif mapped:
            violations.append(
                f"agent {agent.name!r} declares no resolvable api_key yet owns identity "
                f"entries {mapped!r} — the map and the registry disagree."
            )
        for mapped_key in mapped:
            if identities[mapped_key]["agent_type"] != agent.type:
                violations.append(
                    f"agent {agent.name!r} is type {agent.type!r} in agents.yaml but "
                    f"{identities[mapped_key]['agent_type']!r} in the identity map."
                )
    return violations


def _profile_resolution_violations(
    agents: list[AgentEntry],
    rows: list[dict[str, Any]],
) -> list[str]:
    """Rule 3 — the referenced ``profile`` name resolves to *this* agent's type."""
    by_name = {str(r.get("name")): r for r in rows}
    violations: list[str] = []
    for agent in agents:
        row = by_name.get(agent.profile)
        if row is None:
            violations.append(
                f"agent {agent.name!r} references profile {agent.profile!r}, which does "
                f"not resolve to any agent_profiles row after sync."
            )
            continue
        if row.get("agent_type") != agent.type:
            violations.append(
                f"agent {agent.name!r} (type {agent.type!r}) references profile "
                f"{agent.profile!r}, which resolves to a row of type "
                f"{row.get('agent_type')!r} — two agents are sharing one profile row."
            )
    return violations


def _resolve_profile_row(
    agent_id: str,
    agent_type: str,
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    """Resolve a profile the way ``get_agent_profile()`` does (migration 007).

    Two steps, in this order:

    1. the ``agent_profile_assignments`` row for *agent_id*, joined to an
       **enabled** profile (the SQL join carries ``p.enabled = true``, so an
       assignment pointing at a disabled row yields nothing and falls through);
    2. otherwise the enabled profile of *agent_type* with the smallest
       ``created_at`` — ``ORDER BY created_at ASC LIMIT 1``.

    Returns the resolved row (or ``None``) and the source, matching the
    ``'assignment'`` / ``'default'`` labels the SQL function returns.
    """
    by_id = {r.get("id"): r for r in rows}
    for assignment in assignments:
        if assignment.get("agent_id") != agent_id:
            continue
        row = by_id.get(assignment.get("profile_id"))
        if row is not None and row.get("enabled"):
            return row, "assignment"

    candidates = [
        r for r in rows if r.get("agent_type") == agent_type and r.get("enabled")
    ]
    # Stable sort: rows with equal (or absent) created_at keep insertion order,
    # which is creation order in the fake.
    candidates.sort(key=lambda r: str(r.get("created_at") or ""))
    if candidates:
        return candidates[0], "default"
    return None, "none"


def _resolution_violations(
    agents: list[AgentEntry],
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> list[str]:
    """Rule 5 — every agent *resolves* to a profile with its declared trust.

    Stronger than rule 1: rule 1 asks whether a row with the right trust exists
    somewhere in the table, this one asks whether the agent actually reaches it.
    """
    violations: list[str] = []
    for agent in agents:
        row, source = _resolve_profile_row(agent.name, agent.type, rows, assignments)
        if row is None:
            violations.append(
                f"agent {agent.name!r} resolves to no profile at all — "
                f"get_agent_profile({agent.name!r}, {agent.type!r}) would return "
                f"no_profile_found and the agent is refused every operation."
            )
            continue
        if str(row.get("name")) != agent.profile:
            violations.append(
                f"agent {agent.name!r} declares profile {agent.profile!r} but "
                f"resolves to {str(row.get('name'))!r} via {source} — a row bearing "
                f"the declared name is not the same thing as the agent reaching it. "
                f"Project agent_profile_assignments in sync_profiles()."
            )
        if row.get("trust_level") != agent.trust_level:
            violations.append(
                f"agent {agent.name!r} declares trust_level {agent.trust_level} but "
                f"resolves via {source} to profile {str(row.get('name'))!r} carrying "
                f"trust_level {row.get('trust_level')!r} — the created_at tiebreak "
                f"decided this agent's trust, exactly the defect migration 018 fixed "
                f"by hand for the roster of its day."
            )
    return violations


def _unclassified_profile_violations(
    agents: list[AgentEntry],
    rows: list[dict[str, Any]],
) -> list[str]:
    """Rule 4 — every enabled row is registry-declared or explicitly unmanaged."""
    declared = {agent.profile for agent in agents}
    violations: list[str] = []
    for row in rows:
        name = str(row.get("name"))
        if not row.get("enabled", False):
            continue
        if name in declared or name in UNMANAGED_PROFILES:
            continue
        violations.append(
            f"profile row {name!r} (agent_type {row.get('agent_type')!r}) is enabled "
            f"after sync but is neither declared in agents.yaml nor listed in "
            f"UNMANAGED_PROFILES — classify it: give it a registry entry if it is a "
            f"harness identity, or add it to UNMANAGED_PROFILES if it is a role."
        )
    return violations


# ---------------------------------------------------------------------------
# The invariant, against the real registry
# ---------------------------------------------------------------------------


class TestRegistryProjectionInvariant:
    """Every agents.yaml entry materializes every runtime projection."""

    async def test_every_registry_agent_has_enabled_profile_with_declared_trust(
        self, registry: list[AgentEntry]
    ) -> None:
        """Rule 1 — the silent-trust-downgrade guard."""
        rows = await _synced_rows(registry)
        violations = _profile_row_violations(registry, rows)
        assert not violations, _report(violations)

    async def test_every_registry_agent_profile_name_resolves_after_sync(
        self, registry: list[AgentEntry]
    ) -> None:
        """Rule 3 — a `profile:` value pointing at nothing is a dangling reference."""
        rows = await _synced_rows(registry)
        violations = _profile_resolution_violations(registry, rows)
        assert not violations, _report(violations)

    def test_every_registry_agent_has_identity_or_unresolvable_key(
        self, registry: list[AgentEntry]
    ) -> None:
        """Rule 2 — identity present, or key explicitly absent/unresolved here."""
        violations = _identity_violations(registry, get_api_key_identities(registry))
        assert not violations, _report(violations)

    async def test_no_enabled_profile_row_is_unclassified(
        self, registry: list[AgentEntry]
    ) -> None:
        """Rule 4 — a row nobody classified fails CI instead of lingering."""
        rows = await _synced_rows(registry)
        violations = _unclassified_profile_violations(registry, rows)
        assert not violations, _report(violations)

    async def test_migration_seeded_orphans_are_disabled_not_left_enabled(
        self, registry: list[AgentEntry]
    ) -> None:
        """Rows migrations seeded but the registry dropped end up disabled, not deleted.

        ``claude_code_reviewer`` and ``strands_local`` are the live examples: 007/019
        seeded them, no agents.yaml entry claims them, and neither is a role profile.
        Rule 4 passes only because sync disabled them — assert that mechanism rather
        than trusting a coincidence.
        """
        rows = await _synced_rows(registry)
        by_name = {str(r["name"]): r for r in rows}
        for orphan in ("claude_code_reviewer", "strands_local"):
            assert orphan in by_name, f"{orphan} must be retained, never deleted"
            assert by_name[orphan]["enabled"] is False, (
                f"{orphan} is not declared in agents.yaml and is not in "
                f"UNMANAGED_PROFILES, so sync must disable it"
            )
        assert by_name["evaluator"]["enabled"] is True, (
            "evaluator is in UNMANAGED_PROFILES and must survive sync untouched"
        )

    async def test_invariant_holds_on_a_fresh_database(
        self, registry: list[AgentEntry]
    ) -> None:
        """First boot against an empty table satisfies every rule too."""
        db = await _synced_db(registry, seed=[])
        violations = [
            *_profile_row_violations(registry, db.rows),
            *_profile_resolution_violations(registry, db.rows),
            *_unclassified_profile_violations(registry, db.rows),
            *_resolution_violations(registry, db.rows, db.assignments),
        ]
        assert not violations, _report(violations)

    async def test_every_registry_agent_resolves_to_its_declared_trust(
        self, registry: list[AgentEntry]
    ) -> None:
        """Rule 5 — resolution, not row existence.

        Against the migration-seeded table this fails without the assignment
        projection: ``claude_code_local`` (trust 3) is the oldest enabled row of
        type ``claude_code``, so ``claude-remote`` (declared trust 2) reaches it
        through the ``created_at`` fallback.
        """
        db = await _synced_db(registry)
        violations = _resolution_violations(registry, db.rows, db.assignments)
        assert not violations, _report(violations)

    async def test_every_registry_agent_resolves_through_its_own_assignment(
        self, registry: list[AgentEntry]
    ) -> None:
        """The `created_at` tiebreak must be unreachable, not merely unlucky."""
        db = await _synced_db(registry)
        for agent in registry:
            _, source = _resolve_profile_row(
                agent.name, agent.type, db.rows, db.assignments
            )
            assert source == "assignment", (
                f"agent {agent.name!r} resolves via {source!r}, so its trust level "
                f"depends on which profile row of type {agent.type!r} is oldest"
            )

    async def test_stale_projected_assignments_are_removed_and_foreign_rows_kept(
        self, registry: list[AgentEntry]
    ) -> None:
        """The sync removes only stale rows it wrote; everything else survives.

        ``gemini-local`` left the registry after an earlier boot's sync stamped
        its assignment — a stale projected pointer, removed (design D11; the
        profile itself is retained and disabled). ``gemini-remote``'s row is
        hand-written (migration 018 wrote ``assigned_by`` NULL), and
        ``claude-gx10`` is a per-host enrollment row
        (scripts/add_agent_keys.py): agent *instances* the registry
        deliberately does not enumerate. Sweeping those on every startup would
        return them to the oldest-row-of-type fallback that 018 eliminated.
        """
        stale = [
            _assignment(
                "gemini-local", "gemini_local_worker",
                assigned_by=ASSIGNMENT_ASSIGNED_BY,
            ),
            _assignment("gemini-remote", "gemini_cloud_worker"),
            _assignment(
                "claude-gx10", "claude_code_local", assigned_by="add_agent_keys.py"
            ),
        ]
        db = await _synced_db(
            registry,
            seed=[
                *MIGRATION_SEEDED_ROWS,
                _row("gemini_local_worker", agent_type="gemini", trust_level=3),
                _row("gemini_cloud_worker", agent_type="gemini", trust_level=2),
            ],
            assignments=stale,
        )
        surviving = sorted(a["agent_id"] for a in db.assignments)
        assert surviving == sorted(
            [*(a.name for a in registry), "gemini-remote", "claude-gx10"]
        )
        for name in ("gemini_local_worker", "gemini_cloud_worker"):
            row = next(r for r in db.rows if r["name"] == name)
            assert row["enabled"] is False, "the profile is retained, only disabled"


# ---------------------------------------------------------------------------
# Negative cases — a test that only passes on today's tree proves nothing
# ---------------------------------------------------------------------------


class TestInvariantCatchesHalfOnboardedHarness:
    """Spec scenario: "Half-onboarded harness caught in CI"."""

    async def test_unprojectable_harness_fails_sync_naming_the_agent(
        self, registry: list[AgentEntry]
    ) -> None:
        """A harness whose capabilities cannot be mapped fails the boot-time sync."""
        broken = _agent(
            "warp-local",
            profile="warp_local",
            agent_type="warp",
            capabilities=["teleport"],
        )
        with pytest.raises(ProfileSyncError, match="warp-local"):
            await sync_profiles(
                [*registry, broken],
                db=FakeDb(MIGRATION_SEEDED_ROWS),
                audit=FakeAudit(),
            )

    async def test_harness_without_a_materialized_row_fails_rules_1_and_3(
        self, registry: list[AgentEntry]
    ) -> None:
        """Adding an agent whose projection never ran is a red run, not a downgrade.

        This is the perturbation that proves the invariant has teeth: the profile
        table is the one the *current* registry produces, while the registry gains
        a harness — exactly what a half-finished onboarding PR looks like.
        """
        rows = await _synced_rows(registry)
        newcomer = _agent("warp-local", profile="warp_local", agent_type="warp")
        agents = [*registry, newcomer]

        row_violations = _profile_row_violations(agents, rows)
        assert any(
            "warp-local" in v and "warp_local" in v and "no enabled row" in v
            for v in row_violations
        ), _report(row_violations)

        resolution_violations = _profile_resolution_violations(agents, rows)
        assert any("does not resolve" in v for v in resolution_violations)

    async def test_silently_downgraded_trust_level_fails_rule_1(
        self, registry: list[AgentEntry]
    ) -> None:
        """The original bug: declared trust 3, row serving 2, nothing complains."""
        rows = await _synced_rows(registry)
        agent = next(a for a in registry if a.trust_level == 3)
        for row in rows:
            if row["name"] == agent.profile:
                row["trust_level"] = 2

        violations = _profile_row_violations(registry, rows)
        assert any(
            agent.name in v and "silent trust downgrade" in v for v in violations
        ), _report(violations)

    async def test_disabled_row_for_declared_agent_fails_rule_1(
        self, registry: list[AgentEntry]
    ) -> None:
        """A declared harness whose row is disabled authenticates and then fails."""
        rows = await _synced_rows(registry)
        agent = registry[0]
        for row in rows:
            if row["name"] == agent.profile:
                row["enabled"] = False

        violations = _profile_row_violations(registry, rows)
        assert any(agent.name in v and "disabled after sync" in v for v in violations)

    def test_agent_without_identity_or_declared_key_gap_is_reported(
        self, registry: list[AgentEntry]
    ) -> None:
        """A resolvable key that produced no identity entry fails rule 2."""
        keyed = AgentEntry(
            name="warp-local",
            type="warp",
            profile="warp_local",
            trust_level=3,
            transport="mcp",
            capabilities=["lock"],
            description="synthetic harness with a concrete key",
            api_key="warp-secret-key",
        )
        violations = _identity_violations([*registry, keyed], identities={})
        assert any(
            "warp-local" in v and "contributes no identity entry" in v
            for v in violations
        ), _report(violations)

    def test_identity_entry_mapping_to_another_agent_is_reported(
        self, registry: list[AgentEntry]
    ) -> None:
        """One harness's key must never authenticate as a different harness."""
        keyed = AgentEntry(
            name="warp-local",
            type="warp",
            profile="warp_local",
            trust_level=3,
            transport="mcp",
            capabilities=["lock"],
            description="synthetic harness with a concrete key",
            api_key="warp-secret-key",
        )
        identities = {"warp-secret-key": {"agent_id": "pi-local", "agent_type": "pi"}}
        violations = _identity_violations([*registry, keyed], identities)
        assert any("never authenticate as another" in v for v in violations)

    def test_shared_api_key_is_rejected_before_any_identity_map_exists(self) -> None:
        """Two agents resolving to one key is identity confusion, not a warning."""
        first = _agent("warp-local", profile="warp_local", agent_type="warp")
        second = _agent("zap-local", profile="zap_local", agent_type="zap")
        first.api_key = "shared-key"
        second.api_key = "shared-key"

        with pytest.raises(DuplicateApiKeyError, match="warp-local"):
            get_api_key_identities([first, second])


class TestInvariantCatchesResolutionByCreatedAt:
    """The future-``grok-remote`` case: two agents of one type, no assignments.

    This is the permanent regression guard for design D11. Migration 018 fixed
    this by hand for the six-agent roster of 2026-05 and nothing extended the
    fix to ``antigravity-local`` / ``grok-local`` / ``pi-local``; they resolve
    correctly today only because each is the sole profile of its type.
    """

    async def test_missing_assignment_resolves_to_the_older_wrong_trust_row(
        self,
    ) -> None:
        older = _agent(
            "grok-local", profile="grok_local", agent_type="grok", trust_level=3
        )
        newer = _agent(
            "grok-remote", profile="grok_remote", agent_type="grok", trust_level=2
        )
        agents = [older, newer]
        db = await _synced_db(agents, seed=[])

        # The pre-fix world: profile rows projected, assignments never written.
        violations = _resolution_violations(agents, db.rows, assignments=[])
        assert any(
            "grok-remote" in v and "created_at tiebreak" in v for v in violations
        ), _report(violations)

        # ...and rule 1, which looks rows up by name, sees nothing wrong. That
        # gap is the whole reason rule 5 exists.
        assert not _profile_row_violations(agents, db.rows)

    async def test_projected_assignments_make_the_same_pair_resolve_correctly(
        self,
    ) -> None:
        agents = [
            _agent("grok-local", profile="grok_local", agent_type="grok",
                   trust_level=3),
            _agent("grok-remote", profile="grok_remote", agent_type="grok",
                   trust_level=2),
        ]
        db = await _synced_db(agents, seed=[])

        assert not _resolution_violations(agents, db.rows, db.assignments)
        row, source = _resolve_profile_row(
            "grok-remote", "grok", db.rows, db.assignments
        )
        assert source == "assignment"
        assert row is not None and row["name"] == "grok_remote"

    async def test_assignment_to_a_disabled_profile_falls_back_and_is_reported(
        self,
    ) -> None:
        """``get_agent_profile()`` joins on ``p.enabled = true``, so a pointer at
        a disabled row is not resolution — it silently degrades to the fallback.
        """
        agents = [
            _agent("grok-local", profile="grok_local", agent_type="grok",
                   trust_level=3),
            _agent("grok-remote", profile="grok_remote", agent_type="grok",
                   trust_level=2),
        ]
        db = await _synced_db(agents, seed=[])
        for row in db.rows:
            if row["name"] == "grok_remote":
                row["enabled"] = False

        row, source = _resolve_profile_row(
            "grok-remote", "grok", db.rows, db.assignments
        )
        assert source == "default"
        assert row is not None and row["name"] == "grok_local"
        assert any(
            "grok-remote" in v for v in _resolution_violations(agents, db.rows, db.assignments)
        )

    async def test_outdated_pointer_beats_the_type_fallback(self) -> None:
        """``UNIQUE (agent_id)`` means one pointer per agent, and the pointer wins.

        A hand-written assignment left aimed at the wrong row therefore outranks
        every profile the type fallback would have found — which is why the
        projection repoints rather than only inserting missing rows.
        """
        agents = [
            _agent("grok-local", profile="grok_local", agent_type="grok",
                   trust_level=3),
            _agent("grok-sandbox", profile="grok_sandbox", agent_type="grok",
                   trust_level=0),
        ]
        outdated = [_assignment("grok-local", "grok_sandbox")]
        db = await _synced_db(agents, seed=[], assignments=[dict(outdated[0])])

        violations = _resolution_violations(agents, db.rows, outdated)
        assert any(
            "grok-local" in v and "grok_sandbox" in v for v in violations
        ), _report(violations)
        # The projection repointed it, so the synced world is clean.
        assert not _resolution_violations(agents, db.rows, db.assignments)


class TestInvariantCatchesGhostProfile:
    """Spec scenario: "Ghost profile caught in CI"."""

    async def test_enabled_non_registry_profile_row_fails_rule_4(
        self, registry: list[AgentEntry]
    ) -> None:
        """A migration seeding an enabled row for an absent type is a red run.

        Modelled by injecting the row into the post-sync table: whether it slipped
        past the sync (a migration running after boot) or the sync could not reach
        it, an enabled row nobody classified must not be silently tolerated.
        """
        rows = await _synced_rows(registry)
        rows.append(_row("gemini_local", agent_type="gemini", trust_level=3))

        violations = _unclassified_profile_violations(registry, rows)
        assert any(
            "gemini_local" in v and "UNMANAGED_PROFILES" in v for v in violations
        ), _report(violations)

    async def test_unmanaged_allowlist_is_what_makes_role_profiles_pass(
        self, registry: list[AgentEntry]
    ) -> None:
        """`evaluator` passes rule 4 only because it is explicitly classified."""
        rows = await _synced_rows(registry)
        assert not _unclassified_profile_violations(registry, rows)

        without_allowlist = [
            r for r in rows if r.get("enabled") and str(r["name"]) == "evaluator"
        ]
        assert without_allowlist, "evaluator must still be enabled after sync"
        # Re-run rule 4 with the allowlist emptied: the role profile is then the
        # unclassified row the rule is designed to surface.
        declared = {a.profile for a in registry}
        unclassified = [
            str(r["name"])
            for r in rows
            if r.get("enabled") and str(r["name"]) not in declared
        ]
        assert unclassified == ["evaluator"]
