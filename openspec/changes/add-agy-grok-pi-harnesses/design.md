# Design — add-agy-grok-pi-harnesses

## Scope inventory

The proposal enumerated ~15 edit sites. The measured live surface is **68 files** plus the
repo-root `.gemini/` directory. The authoritative inventory command:

```bash
grep -rl "gemini\|Gemini\|GEMINI" \
  --include="*.py" --include="*.ts" --include="*.tsx" \
  --include="*.yaml" --include="*.yml" --include="*.sh" --include="*.json" . \
 | sed 's|^\./||' \
 | grep -vE "^(\.claude|\.agents|\.codex|\.gemini|node_modules|openspec/changes|openspec/specs|openspec/roadmaps|docs/feature-discovery)/"
```

Task 10.2 requires this command to return empty. The exclusions are deliberate:

- `.claude/`, `.agents/`, `.codex/` are generated mirrors — `install.sh` overwrites them (task 10.1).
- `openspec/changes/archive/` is history and is intentionally left intact.
- Other active `openspec/changes/*` directories belong to in-flight proposals; their review
  artifacts and handoffs are records of past dispatches, not live configuration.
- `openspec/specs/` is handled by the spec deltas, not by code edits.
- `docs/feature-discovery/` holds generated discovery output, refreshed by `make architecture`.

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

> Populated by Phase 2. Until then, no package may hardcode an antigravity or grok tier slug.

| Fact | Task | Status |
|---|---|---|
| `agy --model` slug strings | 2.1 | pending |
| `grok --prompt-file /dev/stdin` under subprocess pipe | 2.2 | pending |
| `pi` `OPENROUTER_API_KEY` env passthrough | 2.3 | pending |
| `agy` / `pi` re-login commands | 2.4 | pending |
| `grok login` | — | confirmed during planning |

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
