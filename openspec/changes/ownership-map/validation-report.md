# Validation Report: ownership-map

**Date**: 2026-10-09
**Validated commit**: 77542c7 (openspec/ownership-map)
**Base**: 0a4659f
**Deployable surface**: none (`deployable: false` in work-packages.yaml) - library/CLI skill, registry schema extension, config and docs.

## Phase Results

| Phase | Result | Notes |
|---|---|---|
| Spec Compliance | pass | 37 spec scenarios traced to passing tests (below) |
| Evidence | pass | `check_owners.py --codeowners --strict --json` clean on the real repo |
| Deploy | skipped | no deployable service |
| Smoke | skipped | replaced by CLI-level smoke (below) |
| Security | skipped (scanners) | ZAP/Dependency-Check need docker and network; docker daemon unavailable. Offline static checks pass |
| E2E | skipped | no deployable surface |
| Test suites | pass | no regressions vs base (below) |

## Spec Compliance

**Status**: pass

Requirement and scenario coverage. All tests live in `skills/tests/ownership-runtime/` (233 pass), `agent-coordinator/tests/` (test_human_principals.py, test_registry_projection.py) or `skills/tests/state-artifacts/`.

### agent-identity
- Human principal declared without agent projection: test_human_principals.py::TestHumansBlock::test_humans_block_validates_and_loads, TestHumanProjectionInvariant::test_no_declared_human_is_projected_as_an_agent
- Human id colliding with an agent name rejected: TestHumansBlock::test_human_id_colliding_with_agent_name_rejected, test_collision_is_also_detected_by_load_human_principals
- Human entry missing display name rejected: test_missing_display_name_rejected_naming_entry_and_field
- Registry without humans unchanged: TestRegistryWithoutHumansUnchanged (both tests)
- Schema mirror pinned: TestSchemaMirror (three tests)
- Invariant catches a human projected as an agent: TestHumanProjectionInvariant::test_human_named_profile_row_is_reported, test_human_named_assignment_is_reported

### ownership-map: Ownership Map Schema
- Minimal valid map loads: test_owners.py::TestLoading::test_minimal_map_loads
- Missing default owner rejected: test_missing_default_owner_rejected
- Unknown key rejected: test_unknown_assignment_key_names_the_path, test_schema_copies.py unknown-key fixtures
- Unregistered owner fails closed: test_unregistered_owner_fails_closed
- Agent named as owner rejected: test_agent_named_as_owner_rejected
- Unsupported glob syntax rejected: test_unsupported_glob_syntax_rejected
- Embedded double-star rejected: test_embedded_double_star_rejected
- Registry path escaping the repository rejected: test_registry_escape_rejected_by_schema, test_registry_symlink_escape_rejected

### ownership-map: Owner Resolution
- Explicit capability assignment: TestCapabilityAndRoadmapResolution::test_explicit_capability_with_distinct_acceptance
- Unassigned capability falls back to default owner: test_unassigned_capability_falls_back_to_default
- Most specific path rule wins: TestPathResolution::test_most_specific_rule_wins
- Single-segment directory rule at any depth: test_single_segment_directory_rule_matches_at_any_depth
- Equal specificity resolved by file order: test_equal_specificity_resolved_by_file_order
- Roadmap item resolution: test_roadmap_item_explicit_and_fallback
- Capability assignment governs spec and contract paths: test_capability_assignment_governs_spec_and_contract_paths
- Explicit path rule overrides implied rule: test_explicit_path_rule_overrides_implied_capability_rule

### ownership-map: Ownership Check
- Unowned capability reported: test_check_owners.py::TestAdvisoryFindingsInTeamMode::test_unowned_capability_reported_as_warning
- Unregistered owner reported as error: TestErrors::test_unregistered_owner
- Team registry without a map is an error: TestErrors::test_team_registry_without_map
- Solo mode emits no unowned findings: TestSoloModeSuppression::test_solo_mode_emits_no_unowned_findings
- Dangling capability assignment reported: TestDanglingKeys::test_dangling_capability_reported_in_every_mode
- Clean repository passes: TestJsonContract::test_clean_repository_has_empty_findings, test_repository_invariant.py::test_check_owners_is_clean_on_the_real_repository

### ownership-map: Solo Mode
- Single declared human is the sole principal: test_principals.py::TestSoloDerivation, test_owners.py::TestSoloAndMode
- Git identity derived when registry has no humans: test_git_identity_when_registry_has_no_humans
- Sentinel when no identity is available: test_sentinel_without_any_identity, test_sentinel_outside_a_git_checkout
- One-principal repository with a map stays solo: test_one_principal_repository_with_a_map_stays_solo (owners and repository invariant)
- Existing suites unchanged with the map absent: full skills and coordinator suites (below)

### ownership-map: Coordinator Independence
- Resolution with the coordinator unreachable: test_coordinator_independence.py::test_resolution_with_the_coordinator_unreachable, test_solo_resolution_..., test_cli_runs_...
- Consumer repository registry at the root: test_owners.py::test_consumer_repository_registry_at_root, test_principals.py::test_consumer_repository_registry_at_root
- No private coordinator imports: test_no_private_coordinator_imports, test_no_path_walk_into_the_coordinator, test_no_network_libraries_imported

### ownership-map: CODEOWNERS Projection
- Emit ordering yields agreement: test_codeowners_reconcile.py::TestReconcile::test_emit_ordering_yields_agreement
- Hand-edited line that disagrees is reported: test_hand_edited_conflicting_line_is_a_disagreement
- Missing GitHub handle fails emission: test_codeowners_emit.py::TestFailClosed::test_missing_github_handle_fails_without_modifying_the_file
- Stale block reported and unmanaged text preserved: test_stale_block_reported_with_diff, TestPreservation
- Emit without a map fails closed: test_no_map_exits_1_and_creates_nothing
- Orphaned managed block reported: test_orphaned_managed_block_is_a_warning_with_exit_zero
- Repository CODEOWNERS reconciles: test_repository_invariant.py::test_repository_codeowners_reconciles

### ownership-map: Durable Artifact Registration
- Inventory row present: state-artifacts test_inventory_row_for_ownership_map_covers_every_cell, test_ownership_row_names_codeowners_as_derived_projection
- Guide tests still pass: skills/tests/state-artifacts all pass

### ownership-map: Portable Distribution
- Install payload validates: `bash skills/install.sh --check` prints "Skill install portability validation passed"; the manifest, reference and asset-drift checks pass for ownership-runtime. Its final "installed skill mirror validation failed" line is environmental (runtime mirrors `.agents/skills`, `agents/*` are not installed in this ephemeral worktree) and names no ownership-runtime violation.
- Schema copies pinned: test_schema_copies.py::test_schema_copies_are_byte_identical

## Evidence

**Status**: pass

- `check_owners.py --repo-root . --codeowners --strict --json`: mode solo, exit 0, findings [].
- `codeowners.py emit` (dry run, no --write): exit 0, managed block rendered, working tree untouched.
- `codeowners.py reconcile --json`: disagreements 0, stale false, exit 0.

## CLI Smoke (replaces Deploy / Smoke / E2E)

- Solo-mode check with `openspec/owners.yaml` moved aside (done in a scratch copy of HEAD outside the repo; the real file was never touched): `check_owners.py --strict --json` gives mode solo, exit 0, no findings.
- `codeowners.py emit` in that scratch copy fails closed: `no_ownership_map`, exit 1, nothing written.
- Coordinator independence: resolver and CLI run in tests with no coordinator env or config; no network or coordinator imports (tests above).

## Security

**Status**: skipped

OWASP Dependency-Check and ZAP require the docker daemon and network; the daemon is unavailable here (`docker ps` fails). Not faked. Offline checks run instead: `ruff check` on the new scripts, tests and `agents_config.py` passes; `yaml.safe_load` only; the two `subprocess.run` uses pass list arguments (no shell); no network libraries imported (enforced by test_no_network_libraries_imported); registry and map paths are guarded against repo escape (tests above).

## Test Suites

**Status**: pass

- skills/tests/ownership-runtime: 233 passed.
- agent-coordinator unit (`-m "not e2e and not integration"`): 2937 passed, 11 skipped, 139 deselected, 0 failed.
- skills/tests full: 7133 passed, 36 skipped, 24 failed. All 24 failures sit in the known pre-existing environmental groups, none touch ownership-map files, and none are regressions: cleanup-feature/test_submodule_teardown (6), project-context-refresh checkpoint/refresh (2), supervise/test_workflow_contract (1), validate-feature/test_validation_worktree (7), worktree/test_branch_freshness (4) and test_setup_prototype (4). Base comparison relied on the operator-supplied statement that these are identical on base 0a4659f; they were not re-run on base.
