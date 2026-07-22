# Design — add-agy-grok-pi-harnesses

## Scope inventory

> **Corrected in PLAN_REVIEW round 1** (findings C1, C3, C7, confirmed by both claude and
> codex). The original inventory command and its "68 files" figure were both wrong. See
> § Why the first inventory was wrong.

The authoritative inventory command uses `git grep` over **tracked files only**:

```bash
EXCL='^(\.claude|\.agents|\.codex|\.gemini|openspec/changes|openspec/specs|openspec/roadmaps|docs/feature-discovery|docs/archive|docs/merge-logs|docs/decisions|agent-coordinator/database/migrations)/'
git grep -lI "gemini\|Gemini\|GEMINI" | grep -vE "$EXCL"
```

`git grep` is required, not a stylistic preference:

- It searches **tracked files only**, so virtualenvs, `node_modules`, and build output are
  excluded structurally rather than by an ever-growing exclusion list.
- `-lI` skips binary files, so stale `__pycache__/*.pyc` carrying old strings cannot trip the
  gate (finding U6).
- It is deterministic across environments. A plain `grep -r` returns **240** files here (171
  inside `.venv`), so any gate built on it fails everywhere except a shell whose `grep` happens
  to honour `.gitignore`.

### Measured surface

| Set | Count | Handling |
|---|---|---|
| Tracked live files referencing gemini | **133** | — |
| Code / config (`.py .ts .tsx .yaml .yml .sh .json`) | **69** | Phases 3–8, all packages |
| User-facing docs, templates, Makefile | **11** (see below) | Phase 9, `wp-docs` |
| Remaining narrative/historical prose | 53 | **Out of scope** — follow-up change |

### In-scope user-facing set (operator decision, PLAN_FIX)

Scope is "anything that instructs a human or a script to invoke gemini". That set is:

| File | Why it must change |
|---|---|
| `agent-coordinator/Makefile` | `gemini-mcp-setup` / `gemini-wrapper-install` targets; `mcp-setup` depends on the former, and task 8.1 deletes the wrapper the latter symlinks |
| `agent-coordinator/README.md` | documents those make targets |
| `agent-coordinator/CLAUDE.md` | supported-vendor roster |
| `agent-coordinator/.secrets.yaml.example` | `GEMINI_API_KEY` entry; must gain `OPENROUTER_API_KEY` for pi |
| `agent-coordinator/config.yaml.example` | `One of: claude_code, codex, gemini` and a gemini tier example |
| `skills/collect-transcripts/config.yaml.example` | `gemini_cli` adapter block |
| `skills/setup-coordinator/SKILL.md` | coordinator setup instructions naming the gemini CLI |
| `docs/openbao-secret-management.md` | `GEMINI_API_KEY` secret provisioning |
| `README.md` | supported-vendor roster |
| `docs/agent-coordinator.md` | runtime / transport matrix |
| `docs/skills-workflow.md`, `docs/autopilot-provider-smoke.md` | roster prose |

### Carve-outs — files that MUST NOT be edited

These contain gemini references that are **correct as historical record**. Editing them is a
defect, not a completion. The terminal gate excludes them by construction.

| Path | Reason |
|---|---|
| `agent-coordinator/database/migrations/*.sql` | **Applied migrations.** `001_core_schema.sql`, `018_agent_profile_assignments.sql`, and `019_standardize_profile_names.sql` seed `gemini_local` profile rows. Rewriting an applied migration desynchronizes every deployed database from its history. The `agent-identity` spec delta already states that retiring a harness leaves its seeded rows intact. |
| `docs/merge-logs/**`, `docs/decisions/**` | Historical records. `docs/decisions/` is *generated* from `openspec/changes/archive/` via `make decisions`; hand-editing it is overwritten on the next regen. |
| `docs/archive/**` | Archived exploration documents. |
| `openspec/changes/archive/**` | Change history. |
| `.claude/`, `.agents/`, `.codex/` | Generated mirrors — `install.sh` rewrites them (task 10.1). `.codex/` is **not** written by `install.sh` (it holds only `hooks.json`); it is excluded because it carries no live roster config, not because it is regenerated (finding U11). |
| Review-provenance annotations | `apps/kanban-viz/src/hooks/useCoordinator.ts:244`, `src/__tests__/useCoordinator.test.tsx:278`, and `src/lib/coordinator-types.ts:266` name the vendor that raised a past finding (`IMPL_REVIEW claude#4/gemini#1`). These are history, not roster data — rewriting them falsifies the record (finding U9). Task 7.3 reclassifies them. |
| `openspec/specs/` | Handled by the spec deltas, not by code edits. |

### Why the first inventory was wrong

The original command was `grep -rl` with an `--include` allow-list and a directory exclusion
regex, and it was measured in a shell whose `grep` is a wrapper around `ugrep` invoked with
`--ignore-files --hidden -I`. That wrapper silently honoured `.gitignore` and skipped binaries,
so it reported **68**. The same command under system `grep` reports **240**. `git grep -lI`
reports **69** — the one extra file being `apps/kanban-viz/src/lib/coordinator-types.ts`.

Three consequences, all now fixed:

1. Task 10.2's gate (`test -z "$(...)"`) could never pass outside that one shell (C1).
2. The `--include` list omitted `*.md` and extensionless files, hiding 64 tracked files
   including `agent-coordinator/Makefile` (C2, C3).
3. The measured scope was off by one file (C7).

The lesson is recorded because it generalizes: **a scope measurement is only as trustworthy as
the tool that produced it**, and a search tool that filters by default will under-report. Gates
must use `git grep`, never bare `grep -r`.

## Decisions

### D1 — Spec delta covers the full gemini surface

37 requirements across 8 specs mention gemini. Roughly a third are normative (they declare the
roster contractually); the rest use gemini as an example vendor in scenario prose. Both are
rewritten. Leaving the illustrative prose would keep a discontinued CLI presented as a live
dispatch target across the spec tree.

### D2 — No per-vendor runtime directories

See `contracts/roster.md` § Runtime skill directories. `.gemini/` is deleted and nothing
replaces it.

This surfaced a **pre-existing spec drift**, corrected here rather than deferred:
`skill-workflow`'s *Canonical Skill Distribution* named runtime trees `.claude/skills/`,
`.codex/skills/`, `.gemini/skills/` and an `install.sh --agents claude,codex,gemini` invocation.
`install.sh` supports only `claude` → `.claude/skills` and `agents` → `.agents/skills`
(`skills/install.sh:188-189`), and `.gemini/` has only ever contained `commands/opsx` — no
skills tree existed there to sync.

### D3 — `antigravity` is the single canonical provider key

See `contracts/roster.md` § Canonical strings. Follows the existing `claude_code`-for-`claude`
precedent. Roadmap `ri-01`'s acceptance wording said `agy`; it is updated to match.

### D4 — Eval backends reach full roster parity in this change

`evaluation-framework`'s *Agent Backend Abstraction* enumerates a backend per first-class
provider. Shipping the roster without backends would land spec and code in disagreement — the
same drift class D3 exists to prevent.

### D5 — `VendorSwimlanes.tsx` is not modified

The proposal claimed the component holds a "vendor color/label map" needing three additions and
one removal. **It holds no such map.** It extracts the vendor from the `agent_id` suffix after
`--` and renders it as text (`VendorSwimlanes.tsx:28,124`), so it is already roster-agnostic and
correct. The kanban work is confined to the seeder and to test fixtures.

The spec delta was adjusted accordingly: rather than mandating a recognized-vendor list in the
UI — which would introduce the very allow-list pattern this change removes — it now requires the
component to keep deriving vendors dynamically.

### D6 — User-facing docs are in scope; narrative prose is not (PLAN_FIX, operator decision)

133 tracked files reference gemini. Including all of them would roughly double an already-XL
change and would drag in review-provenance annotations and applied SQL migrations that must not
be rewritten.

**Decision**: scope is "anything that instructs a human or a script to invoke gemini" — the
11-file set in § In-scope user-facing set, of which `agent-coordinator/Makefile` is mandatory
because task 8.1 actively breaks it. The remaining 53 narrative files are a tracked follow-up.

Consequently the terminal gate asserts zero references **in a defined set**, not repo-wide. A
repo-wide assertion would be unsatisfiable without editing history (see § Carve-outs).

### D7 — Pre-existing broken gates are repaired here (PLAN_FIX, operator decision)

Three work-package verification commands could never pass, for reasons predating this change:

| Gate | Failure today | Repair |
|---|---|---|
| `wp-dispatch` → `pytest skills/tests/vendor-neutral-autopilot` | **5 failed** — `test_contracts.py:10` resolves `openspec/changes/vendor-neutral-autopilot`, archived to `openspec/changes/archive/2026-05-16-vendor-neutral-autopilot` | Repoint the constant at the archived path (task 4.12) |
| `wp-cleanup` → `skills/.venv … pytest packages/agent-scenarios/tests` | **6 collection errors** — that venv lacks agent-scenarios' dependencies | Run through the package's own environment (task 8.8) |
| `wp-integration` → `pytest skills/tests` | **collection interrupted** — `skills/tests/agent-coordinator/test_kanban_viz_endpoints.py:31` imports `fastapi.testclient`, absent from `skills/.venv` | Add the dependency to the skills venv (task 10.5) |

The alternative — scoping gates around the breakage — was rejected: it reintroduces exactly the
vacuous-verification problem the review flagged. A gate nobody expects to pass carries no signal.

## PLAN_REVIEW round 1 — findings resolution

26 findings from 2 vendors (claude 18, codex 8); 7 confirmed by both. Every load-bearing claim
was independently verified by the orchestrator before acceptance. Verdict: **not converged**,
resolved by PLAN_FIX.

| ID | Confirmed by | Resolution |
|---|---|---|
| C1 | both | Inventory rewritten to `git grep -lI`; § Why the first inventory was wrong |
| C2 | both | `agent-coordinator/Makefile` added to tasks 8.1a/8.1b and to `wp-cleanup` scope |
| C3 | both | Doc set defined (D6); `wp-docs` scope and Phase 9 expanded |
| C4 | both | Empirical table expanded 4 → 8 facts; tasks 2.6–2.9 added |
| C5 | both | `wp-empirical` gate now requires evidence per row plus a PATH precondition |
| C6 | both | `wp-kanban` gate runs both Python endpoint suites and the seeder check |
| C7 | both | `coordinator-types.ts` added to task 7.3 as a carve-out, not a rewrite |
| U1 | claude | Task 4.12 repoints `test_contracts.py` (D7) |
| U2 | claude | Task 3.16 bumps `DEFAULT_PROVIDER_MODEL_MAP` to `schema_version: 2` + fixture |
| U3 | codex | Schema gains `required` for all five provider keys |
| U4 | claude | Task 8.8 fixes the agent-scenarios environment (D7) |
| U5 | claude | Task 10.5 adds `fastapi.testclient` to `skills/.venv` (D7) |
| U6 | claude | All grep gates now use `git grep -lI` |
| U7 | claude | `wp-dispatch` gate scoped to exclude `SKILL.md` (owned by `wp-docs`) |
| U8 | claude | Templates added to `wp-docs` scope; task 9.6 adds `OPENROUTER_API_KEY` |
| U9 | claude | Review-provenance annotations declared a carve-out |
| U10 | claude | `test_vendor_diversity.py` added to task 4.1's Files list |
| U11 | claude | `.codex/` rationale corrected in § Carve-outs |
| U12 | claude | `coordinator-kanban-viz` delta drops the unsatisfiable colour clause |

## Why 4.1 stays L

Task 4.1 writes failing tests across 8 test files in one package. The sizing table says L should
be decomposed into 2–3 M tasks where that reduces risk. Here it does not: every one of those
files asserts against the same roster constant, so splitting them creates 3 tasks that must land
together to keep the suite green, and an agent holding only a third of the surface cannot tell
whether the roster is consistently applied. The risk being managed is *inconsistency across the
dispatch surface*, and that risk is lowest when one agent sees all of it at once.

It is flagged rather than split, per the sizing table's "keep but flag" instruction for L.

## Why the empirical phase runs before config

Phase 2 produces facts — `agy --model` slugs, whether `grok --prompt-file /dev/stdin` survives a
subprocess pipe, whether `pi` resolves `OPENROUTER_API_KEY` from the subprocess environment,
and the re-login commands. Phases 3–7 consume them.

Ordering these last would mean writing `agents.yaml` entries against guessed flags and
discovering the mistake during VALIDATE, after the config has propagated into tier maps,
adapters, and tests. The proposal already flagged two of these as "verified empirically"; this
plan makes that verification a gating task rather than a hope.

`grok login` was confirmed during planning ("Sign in to Grok"). `agy` and `pi` show no login
subcommand in `--help`; `_RELOGIN_COMMANDS` already falls back to `f"{command} login"`
(`review_dispatcher.py:271`), so task 2.4 confirms rather than invents.

## Empirical CLI findings

**Operator authorization (recorded 2026-07-22):** live dispatch against `agy`, `grok`,
and `pi` is approved. Tasks 2.1-2.4 may invoke these CLIs with real prompts, which
consumes subscription quota (agy, grok) and OpenRouter tokens (pi). No further approval
is required for the Phase 2 verification calls.

> Populated by Phase 2. Until every row below reads `confirmed` or `refuted` with evidence,
> **no package may hardcode a CLI flag, model slug, or output-parsing assumption.**

> **Expanded in PLAN_REVIEW round 1** (finding C4, confirmed by both vendors). The original
> table covered 4 facts while Phases 3, 5, and 6 consumed 8. The four added rows are marked ✚.

Each row MUST be filled with `confirmed` or `refuted` **plus the observed evidence** (the exact
command run and the relevant output excerpt). `pending`, `unknown`, `n/a`, and a deleted table
are all failures — `wp-empirical`'s gate checks for evidence, not for the absence of the word
"pending" (finding C5).

| # | Fact | Consumed by | Task | Status | Evidence |
|---|---|---|---|---|---|
| E1 | `agy --model` slug strings for premium/standard/economy | 3.5, 3.8 | 2.1 | pending | |
| E2 | `grok --prompt-file /dev/stdin` survives a subprocess pipe | 3.2 | 2.2 | pending | |
| E3 | `pi` resolves `OPENROUTER_API_KEY` from the subprocess env | 3.2, 8.5 | 2.3 | pending | |
| E4 | `agy` / `pi` re-login commands | 4.7 | 2.4 | pending | |
| E5 ✚ | `grok` model slugs for premium/standard/economy | 3.5, 3.8 | 2.6 | pending | |
| E6 ✚ | `grok --output-format json` + `--json-schema` emit a conforming envelope | 5.2, 3.2 | 2.7 | pending | |
| E7 ✚ | `agy --print` + stdin + `--mode plan` behave Claude-shaped | 3.2, 5.3 | 2.8 | pending | |
| E8 ✚ | `pi` accepts the prompt as a trailing positional; output shape | 3.2, 5.5 | 2.9 | pending | |
| — | `grok login` | 4.7 | — | **confirmed** | `grok --help` → `login  Sign in to Grok` |

**Operator authorization is on record** (above), so these tasks may make live billed calls.

## Merge-order coupling

Three roadmap items edit surfaces this change touches. `ri-01` is the DAG root precisely so it
lands first and fixes the roster before anything else reads it.

| Roadmap item | Overlap | Handling |
|---|---|---|
| `ri-02` add-live-vendor-capability-and-cost-registry | Deletes `orchestrator.py`'s vendor list; replaces `policy.py`'s cost stub | Keep both structures stable (tasks 4.5, 4.6) so `ri-02` is a clean removal |
| `ri-04` add-adaptive-model-router | Touches `agents.yaml` / `archetypes.yaml` tiers; adds `openai_compat_adapter.py` | Roster additions are additive to tier maps; no schema change |
| `ri-06` build-structured-vendor-result-channel | Switches every CLI adapter to structured JSON envelopes | grok already emits `--output-format json`; this change aligns rather than conflicts |

The `provider-model-map.schema.json` bump to `schema_version: 2` closes the provider key set via
`propertyNames.enum`. Version 1 used open `additionalProperties`, which would have accepted a
reintroduced `gemini` key silently — the failure mode this change exists to remove.
