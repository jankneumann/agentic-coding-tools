# Make setup-coordinator script-backed

## Why

`skills/setup-coordinator/SKILL.md` is 359 lines of narrated bash that is not
executable code. Fragments like

```bash
PROFILE=local   # Parse --profile from $ARGUMENTS, or read COORDINATOR_PROFILE env var
```

are instructions to a model wearing a code fence, not a script. There is no
runnable entrypoint, no `scripts/` directory, and no test suite — making it one
of the few substantive skills in this repo that never made the transition (~30
skills have `scripts/`, 53 have suites under `skills/tests/`). It has no tests
precisely because there is nothing testable in it.

Three concrete consequences:

1. **A spec violation on main.** `openspec/specs/setup-coordinator/spec.md`
   requires the skill to "read `agents.yaml` to determine which agents to
   configure." No code does this. The requirement has never been satisfied.
2. **Four defects in the permission-allowlist step** (`SKILL.md:211-232`), where
   Python source is nested inside a bash string inside a markdown fence:
   - **relative path** — `SETTINGS_FILE=".claude/settings.local.json"` makes
     behavior depend on cwd, while the skill is explicitly designed to run from
     consumer repos
   - **whole-file reformat** — `json.dumps(settings, indent=2)` rewrites the
     entire file to append one array element. The live file has a sibling
     top-level key (`disabledMcpjsonServers`) that this reformats
   - **non-atomic write** — plain `p.write_text`; any concurrent writer loses
   - **deny-list false positive** — the `grep -q 'mcp__coordination__\*'` guard
     matches the string *anywhere* in the file, so an entry in a `deny` list
     makes the skill conclude the permission is already allowed and silently
     skip the add. This one fails **silently**, which is the worst shape.
3. **No detection of which harnesses are actually present**, so the operator
   configures vendors that are not installed and discovers it later.

Every genuinely hard operation in this skill is already delegated elsewhere
(`make -C $COORDINATOR_DIR mcp-setup`, `make hooks-setup`,
`coordination_bridge.py detect`, `docker compose up`). The skill's real job is
orchestration, verification, and reporting — exactly the three things
markdown-narrated bash is worst at, because each run re-improvises the glue and
nothing is testable.

## What Changes

- **ADD** `skills/setup-coordinator/scripts/setup_coordinator.py` — a portable
  entrypoint with four subcommands: `detect-harnesses`, `check`, `configure`,
  `report`. Module scope imports only the standard library and sibling skill
  modules; the single third-party dependency, `pyyaml`, is reached lazily inside
  `vendor_health.load_agents_yaml` and its absence degrades detection rather
  than breaking import.
- **ADD** presence-only harness detection: CLI on PATH plus a home-directory
  config artifact, with four states (`ready`, `cli_missing`, `config_missing`,
  `unknown`). Authentication and login remain the operator's responsibility.
- **FIX** all four permission-allowlist defects via an atomic, minimal-diff,
  deny-aware settings writer.
- **ADD** `skills/tests/setup-coordinator/` and register it in `testpaths`.
- **MODIFY** `skills/setup-coordinator/SKILL.md` — reduce from 359 to ~120-150
  lines: knowledge content stays, improvised glue becomes script invocations.
- **MODIFY** the `Profile-Aware Setup` requirement to reflect script-backed
  execution and to finally satisfy the `agents.yaml` clause.

### Non-goals

- Installing vendor CLIs or automating interactive logins (`grok login`,
  `codex login` are browser OAuth device flows a skill cannot complete).
- Probing vendors with billed inference calls to verify credential validity.
  Presence is reported as presence, never as verified readiness.
- Any change to `agent-coordinator/`, or to `vendor_health.py` itself.

## Approaches Considered

### Approach 1 — Self-contained subcommand CLI in `setup-coordinator` **(Recommended)**

One `scripts/setup_coordinator.py` owning all four subcommands, living in the
skill it serves. Reuses `vendor_health.check_all_vendors()` unmodified for the
CLI-on-PATH and env-var layers, and adds the home-directory presence layer
locally.

**Pros**
- The skill stays independently packageable — the hard constraint stated twice
  in `SKILL.md` ("never assumes `agent-coordinator/` was bundled").
- No modification to `vendor_health.py`, so the `vendor-ux` spec's 8
  requirements over that file are untouched and no second delta is needed.
- Follows the established subcommand shape (`worktree.py`), so reviewers and
  future maintainers meet a familiar structure.
- Resolves the existing overlap: `setup-coordinator` already *claims* to read
  `agents.yaml`, so detection belongs here rather than in a sibling skill.

**Cons**
- Adds two entries to `cross_skill_dependencies` (`parallel-infrastructure`,
  `project-context-runtime`).
- The home-dir detection layer lives in a different file from the CLI-on-PATH
  layer it complements, so a reader must look in two places.

**Effort**: M

### Approach 2 — Extend `vendor_health.py`, keep `setup-coordinator` thin

Push harness detection into `skills/parallel-infrastructure/scripts/vendor_health.py`
so `/vendor-status` gains it too, and let `setup-coordinator` invoke it — the
literal `vendor-status` shape.

**Pros**
- Single source of truth for all vendor detection; `/vendor-status` improves for
  free.
- Thinnest possible `SKILL.md`.

**Cons**
- Pulls the change into `vendor-ux` spec territory: 8 requirements own that
  file, including `Health Check Dimensions` (which already specifies a
  model-access probe) and `Probe Cost`. A second delta spec is required, and
  presence-only detection must be reconciled with a requirement set built around
  probing.
- `vendor_health.py` carries an explicit design constraint at lines 99-101
  ("D6 still holds: this is env-var resolution, not an inference probe").
  Adding filesystem inspection to it needs that decision revisited, not assumed.
- Does not fix the permission-allowlist defects, which have no home in a vendor
  health module — so this approach cannot stand alone.

**Effort**: L

### Approach 3 — Two scripts: `harness_detect.py` + `setup_coordinator.py`

Split detection from configuration into sibling scripts in the same skill.

**Pros**
- Sharpest separation of concerns; detection is independently reusable.
- Detection has no write capability at all, which is easy to argue about.

**Cons**
- Two entrypoints, two test suites, two smoke registrations for what is one
  operator workflow.
- The phase split that actually matters is *host* (detect where you are) vs
  *credential-holder* (configure), and that is a runtime concern a subcommand
  models just as well as a separate file.
- Premature: there is no second consumer of `harness_detect.py` today.

**Effort**: M

### Selected Approach

**Approach 1 — self-contained subcommand CLI in `setup-coordinator`.** Selected
by the operator at Gate 1, unmodified.

Four sub-decisions were fixed at the same gate and bind all downstream artifacts:

| ID | Decision | Consequence |
|----|----------|-------------|
| D1 | Hybrid detection — call `vendor_health.check_all_vendors()` unmodified, layer home-directory presence locally | No `vendor-ux` delta; `parallel-infrastructure` joins `cross_skill_dependencies` |
| D2 | Import `atomic.py` from `project-context-runtime`, with an inline fallback when unbundled | Second `cross_skill_dependencies` entry; follows the `refresh-architecture` precedent |

Planning refined two of these without reopening the gate decision:

- **D1a/D1b** — "call it unmodified" means *with an explicitly resolved path*.
  Called with no argument, `load_agents_yaml` reaches the network and falls back
  to a cwd-relative roster, and fails open with an empty result; and its output
  includes `claude-remote`/`codex-remote`, which are not host-local harnesses.
  Resolution, existence-checking, and `-local` filtering are therefore owned by
  this skill. See design D1a, D1b.
- **D2** — the correct import is `atomic_write_bytes`, **not**
  `atomic_write_json`. The latter canonicalizes (`sort_keys=True`), which would
  re-sort the settings file's top-level keys and so reintroduce the whole-file
  reformat this change exists to remove, while also breaking the idempotent
  re-run. See design D2.
| D3 | `configure` mutates **only** the settings file; MCP/hooks registration stays as narrated `make` invocations | Skill remains usable without a coordinator checkout |
| D4 | `SKILL.md` reduced to ~120-150 lines — knowledge content stays, improvised glue goes | Transport table, HTTP guidance, and troubleshooting survive |

Approaches 2 and 3 are retained above as rejected alternatives with their
rationale; neither is revisited by this change.

### Recommendation (as presented at Gate 1)

**Approach 1.** It is the only option that satisfies the hard portability
constraint while fixing the allowlist defects, and it avoids reopening the
`vendor-ux` probe-vs-presence decision that Approach 2 would force. Approach 2's
"single source of truth" benefit is real but is bought with a second delta spec
against a requirement set built on a different detection philosophy; Approach 3
splits a workflow that has only one consumer.

## Impact

- **Affected specs**: `setup-coordinator` (1 MODIFIED requirement, several ADDED)
- **Affected code**: `skills/setup-coordinator/**`, `skills/tests/setup-coordinator/**`,
  `skills/pyproject.toml` (`testpaths`), `skills/install-manifest.json`
  (`cross_skill_dependencies`, `smoke_entrypoints`)
- **Not affected**: `agent-coordinator/**`, `skills/parallel-infrastructure/**`
  (read-only reuse), runtime mirrors (untracked — `git ls-files` returns zero
  entries under `.claude/skills/` and `.agents/skills/`)
- **Risk**: low and reversible. No DB migration, no external service mutation,
  no persisted state. The one mutating operation (settings-file write) is
  strictly safer than what ships today.
