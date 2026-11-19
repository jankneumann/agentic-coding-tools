# Architecture Impact

Commit: 7f4fa50
Branch: claude/eloquent-edison-tn8alg
Base: f8a7da6 (merge-base against main)

## Changed Files

Files belonging to this change:

- `.claude/settings.json`
- `CLAUDE.md`
- `docs/guides/lead-session-sandbox.md`, `docs/guides/documentation.md`
- `skills/session-bootstrap/scripts/sandbox_probe.py`
- `skills/tests/session-bootstrap/test_sandbox_probe.py`,
  `test_lead_session_sandbox_settings.py`, `test_lead_session_sandbox_docs.py`,
  `test_irreversible_set_gated.py`
- `openspec/changes/sandbox-the-interactive-lead-session/`

The branch also carries roadmap files, other scaffolded changes and refreshed
architecture artifacts, 46 files in total. None is under `agent-coordinator/`.

## Structural Diff

`make architecture-diff BASE_SHA=f8a7da6`: +150/-40 nodes, +43/-3 edges,
0 new cycles, 2 new high-impact modules, 3 new routes without tests, 2 new
database tables.

Routes and tables can only come from coordinator code, which this branch does
not change. The baseline graph at the merge-base was older than `main`, so the
diff measures that staleness. The one module this change adds is
`sandbox_probe.py`.

### New Cross-Layer Flows

None. The probe is a standalone script; it imports
`shared.environment_profile.detect` and nothing imports it.

### Broken Cross-Layer Flows

None.

### New High-Impact Nodes

None from this change.

## Validation Findings

`validate_flows.py` scoped to the 46 changed files: 0 entrypoints checked,
0 findings.

`run_architecture_linters.py`:

| Severity | Category | Description | File |
|----------|----------|-------------|------|
| critical (advisory) | architecture | Canonical `skills/` path in a string, lines 75, 88, 89. The strings are command text used as test data and are never executed | `skills/tests/session-bootstrap/test_irreversible_set_gated.py` |
| nit | size | Six generated artifacts exceed 500 lines | `docs/architecture-analysis/*` |

## Parallel Zone Impact

None. No zones merged and none formed.

## Recommendations

Safe to merge as far as structure is concerned. The linter findings need no
change. Merging should still wait for the host checklist in
`docs/guides/lead-session-sandbox.md`.
