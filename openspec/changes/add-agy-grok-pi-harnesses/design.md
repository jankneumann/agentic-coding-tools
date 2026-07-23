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

> Counts re-measured 2026-07-22 (plan revision 2). They are **informational** — the package
> gates, not these numbers, are authoritative (D8.1). Round 2 found the previous figures
> (133/69/11/53) mutually inconsistent across three artifacts; keeping derived numbers out of
> gates removes that failure class.

| Set | Count | Handling |
|---|---|---|
| Tracked live files referencing gemini | **124** | — |
| Code / config edited (`.py .ts .tsx .yaml .yml .sh .json`, Makefile) | **66** | Phases 2–4, `wp-coordinator` / `wp-skills` / `wp-frontend` |
| User-facing docs, templates | **12** (see below) | Phase 5, `wp-docs-finalize` |
| SKILL.md files in scope (8 spec-named lifecycle + setup-coordinator + collect-transcripts) | **10** | Phase 5, `wp-docs-finalize` (D8.3) |
| Review-provenance annotations (untouched by design) | 3 | Carve-out |
| Remaining narrative/historical prose | ~33 | **Out of scope** — follow-up change (task 6.4 records the list) |

### In-scope user-facing set (operator decision, PLAN_FIX)

Scope is "anything that instructs a human or a script to invoke gemini". That set is:

| File | Why it must change |
|---|---|
| `agent-coordinator/Makefile` | `gemini-mcp-setup` / `gemini-wrapper-install` targets; `mcp-setup` depends on the former, and task 2.8 deletes the wrapper the latter symlinks |
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
| `.claude/`, `.agents/`, `.codex/` | Generated mirrors — `install.sh` rewrites them (task 6.1). `.codex/` is **not** written by `install.sh` (it holds only `hooks.json`); it is excluded because it carries no live roster config, not because it is regenerated (finding U11). |
| Review-provenance annotations | `apps/kanban-viz/src/hooks/useCoordinator.ts:244`, `src/__tests__/useCoordinator.test.tsx:278`, and `src/lib/coordinator-types.ts:266` name the vendor that raised a past finding (`IMPL_REVIEW claude#4/gemini#1`). These are history, not roster data — rewriting them falsifies the record (finding U9). Tasks 4.1/4.3 leave them unchanged and `wp-frontend` denies writes to them. |
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
doc set in § In-scope user-facing set (Makefile is mandatory because task 2.8 actively
changes what it documents), **plus** the 10 SKILL.md files added by D8.3. The remaining ~33
narrative files are a tracked follow-up (task 6.4 records the list).

Consequently residue gates assert zero references **in trees or file lists each package
owns**, not repo-wide. A repo-wide assertion would be unsatisfiable without editing history
(see § Carve-outs).

### D7 — Pre-existing broken gates are repaired here (PLAN_FIX, operator decision)

Three work-package verification commands could never pass, for reasons predating this change:

| Gate | Failure today | Repair (revision 2) |
|---|---|---|
| `pytest skills/tests/vendor-neutral-autopilot` | **5 failed** — `test_contracts.py:10` resolves `openspec/changes/vendor-neutral-autopilot`, archived to `openspec/changes/archive/2026-05-16-vendor-neutral-autopilot`; plus a missing `write_capable` field in `test_model_resolution.py` | **Absorbed by `add-frontier-model-tier` (PR #262)**: schema promoted to `openspec/schemas/`, paths repointed, fixture fixed. Phase 0 task 0.2 is now a rebase-and-verify; task 3.6 only closes the provider key set |
| `pytest packages/agent-scenarios/tests` via `skills/.venv` | **6 collection errors** — that venv lacks agent-scenarios' dependencies | Run through the package's own environment with an explicit path: `uv run --project packages/agent-scenarios pytest packages/agent-scenarios/tests` (`--project` does not change cwd — round 2 caught the pathless form collecting the repo-root `tests/`) |
| `pytest skills/tests` | **collection interrupted** — `skills/tests/agent-coordinator/test_kanban_viz_endpoints.py:31` imports `fastapi.testclient`, absent from `skills/.venv` | Phase 0 task 0.1 adds `fastapi`/`httpx` to `skills/pyproject.toml` (the venv is regenerated by `uv sync`, so a venv-only install would be discarded — round 2) |

The alternative — scoping gates around the breakage — was rejected: it reintroduces exactly the
vacuous-verification problem the review flagged. A gate nobody expects to pass carries no signal.
These repairs are grouped in Phase 0 and labeled as baseline repair, not laundered into roster
tasks (D8.4).

### D8 — Plan revision 2: less apparatus, not better apparatus (ESCALATE resolution, 2026-07-22)

Autopilot halted at ESCALATE after PLAN_REVIEW round 2 with a rising findings trend
`[26, 29]`; 21 of 29 round-2 findings targeted the plan's own verification machinery rather
than the roster work. The structural cause: each PLAN_FIX **grew the reviewable surface faster
than it removed defects** — 20 inserted tasks, 2 bespoke gate scripts, a manifest, and fact
tables duplicated across three artifacts, each duplication a consistency finding waiting to
happen. The four escalated decisions (REVIEW-PACKAGE § 4) were resolved as follows:

**D8.1 (was D-A) — 9 work packages collapse to 5** along venv/test-suite boundaries
(`wp-empirical`, `wp-coordinator`, `wp-skills`, `wp-frontend`, `wp-docs-finalize`), with
coarse directory-level `write_allow` plus explicit `deny` lists. Hand-maintained per-file
scopes over a cross-cutting rename guaranteed scope conflicts (a task with nowhere to write,
a gate sweeping another package's files); ownership by tree eliminates the class. Gates are
existing test suites plus inline one-line `git grep` checks — no derived numbers, no scripts.

**D8.2 (was D-B) — both gate scripts and the manifest are deleted.**
`check_empirical_facts.py` and `check_roster_residue.py` were each defeated by both review
vendors; each was a second-order instance of the vacuous-gate defect they were written to fix.
What is mechanically checkable is now checked inline (`git grep -lI` over owned trees, dep
absence, `make -n`). What is not mechanically checkable — "were the CLIs genuinely invoked" —
is now an explicit **human checkpoint** (task 1.4, `kind: manual`), because two scripted
attempts at it failed and a third would fail the same way.

**D8.3 (was D-C) — the spec delta stands; the 8 lifecycle SKILL.md files come into scope.**
The `skill-workflow` delta names them explicitly, so deferring them made the spec
unsatisfiable by this change. The edits are mechanical provider-prose swaps (task 5.5).
`setup-coordinator` and `collect-transcripts` SKILL.md join them; the ~12 remaining SKILL.md
files with narrative mentions stay deferred under D6.

**D8.4 (was D-D) — one change, not a split.** Splitting into `ri-01a`/`ri-01b` would double
the plan apparatus — the very thing failing review — for a change whose parts (roster,
backends, adapters, docs) land against one spec delta set. The three pre-existing test
repairs stay in this change but are quarantined as **Phase 0 — baseline repair**, explicitly
labeled, because the package gates cannot go green without them.

Two further round-2 resolutions folded in: the provider-model-map schema moves to
`openspec/schemas/provider-model-map.schema.json` (task 3.6) so contract tests never resolve
a change directory that later archives (the round-2 `const: 1` contradiction); and the
`google-generativeai` dependency — invisible to any gemini-grep — is an explicit task with an
explicit inline check in both trees (tasks 2.9, 3.11).

### D9 — The residue gate enforces harness migration, not substring eradication (operator-directed, 2026-07-23)

The `wp-coordinator` / `wp-skills` / `wp-frontend` gates originally asserted
`test -z "$(git grep -lIi gemini -- <tree> <excludes>)"` — zero case-insensitive occurrences
of the substring "gemini" in the owned tree. **That gate is unpassable and conceptually wrong**,
and this was missed through six PLAN_FIX rounds because § "Why the first inventory was wrong"
focused the reviewers on tool-correctness (`git grep` vs `grep -r`) and the gate was never
re-run against the post-task-2.3 tree. Two classes of legitimate "gemini" survive migration:

1. **Model slugs.** Antigravity *is* Google's harness; its operator-signed model family (E1) is
   literally `gemini-3.6-flash-{high,medium,low}` (`agy models`). These name a live MODEL reached
   through the `agy` harness — renaming them would break dispatch. They appear in `agents.yaml`,
   `archetypes.yaml`, and `DEFAULT_PROVIDER_MODEL_MAP`.
2. **Retirement-assertion tests.** `test_agents_config.py` / `test_agents_config_isolation.py`
   contain the word "gemini" precisely to assert its *absence* (`assert "gemini" not in vendors`).
   The word is the proof of migration, not a violation of it.

The functional contract the operator wants enforced is: **it is clear to a reader that the
primary Gemini harness moved from the Gemini CLI to Antigravity (`agy`), and no skill or config
invokes a harness that no longer exists.** That is a harness contract, not a lexical one, so the
gate is now two-part:

- **Semantic (pytest, config-derived).** `test_harness_migration.py` parses the real config: no
  `agents.yaml` harness has `cli.command` in `{gemini, jules}`; the local roster is exactly
  `antigravity/grok/pi` (+ claude/codex); the eval-backend `build_backend` factory rejects
  `gemini`/`jules` with a structured `UnknownBackendError` naming the roster. This derives from
  config (tests-derive-from-config), so it cannot drift from the roster it guards.
- **Structural (residue grep, artifact tokens).** The grep now targets retired-harness ARTIFACT
  tokens only — `gemini_jules`, `GeminiJulesBackend`, `gemini-mcp-setup`, `gemini-wrapper-install`,
  `gemini_wrapper`, `gemini-coord`, `gemini-local`, `gemini-remote` — never the bare substring.
  Model slugs and prose pass by construction. Verified to still FAIL on the pre-2.6 tree
  (`gemini_jules`, the Makefile targets, the wrapper are all present), satisfying
  gates-must-fail-before-work.

This generalizes the migration architecture: harnesses are pluggable adapters behind the
`AgentBackend` protocol and per-provider `agents.yaml` config; adding, retiring, or reflagging a
harness is a config + adapter change, and the gate proves the config no longer points at a dead
one — it does not police vocabulary.

## PLAN_REVIEW round 6 — findings resolution (plan revision 2)

**Findings trend: 26 → 29 → 13 → 9 → 4 → (converged).** Operator-directed close of the
convergence loop after the round-5 review (past the 3-iteration budget). Re-checking round 5's
four findings against HEAD, three were already resolved by round-5's own PLAN_FIX — R5-2 (the
integration gate now enumerates all five skills paths at `work-packages.yaml:382`), R5-3 (the
carve-out `git diff` is folded into `wp-docs-finalize`'s first gate), and R5-4 (the invariant
was narrowed to *gates*, so task-body *action* commands no longer violate it). One residual
survived:

| ID | Criticality | Finding | Resolution |
|---|---|---|---|
| R5-1 (codex) | high | Round 5 made `wp-frontend`'s gate **run** `test_kanban_viz_endpoints.py`, but running a parametrized `agent_id_cases` test passes for whatever rows exist — it never **asserts** the new roster is present, so a fixture with only an `antigravity` row (grok/pi omitted) still passes. The gate greps the full roster on the `.tsx` fixture but not on the `.py` one, so it does not mechanically cover task 4.3's "roster present in **both** fixture files" claim. | `wp-frontend`'s gate now also greps `antigravity`/`grok`/`--pi` in `test_kanban_viz_endpoints.py` (portable `grep -qe '--pi'`, verified to fail on the unmodified tree per the gates-must-fail-before-work rule); task 4.3 additionally requires `test_vendor_extraction_from_agent_id` to add rows for all three so `pytest` fails on omission — presence-assertion backing the residue-grep. |

This is the fixture-symmetry class round 4 first surfaced (a fix reaching one twin, not both):
round 5 taught the gate to *run* the Python fixture; round 6 teaches it to *assert the roster*
in that fixture, closing the last mechanical gap between what the gate checks and what task 4.3
claims. Proceeding to IMPLEMENT — the design is unchanged and sound.

## PLAN_REVIEW round 5 — findings resolution (plan revision 2)

**Findings trend: 26 → 29 → 13 → 9 → 4** (claude 2, codex 2). Full 2/2 quorum, both with
Bash. **Not one finding is about the substance of the change** — all four are consistency gaps
in round 4's own gate-dedup work, two of them coverage gaps in the two gates round 4 rewrote.
This is the convergence signal: the plan describes correct work; what remains is whether its
gates fully cover that work, and the answer this round was "two of them didn't yet."

| ID | Criticality | Finding | Resolution |
|---|---|---|---|
| R5-1 (codex) | high | `wp-frontend`'s gate **grepped** `test_kanban_viz_endpoints.py` for `antigravity` but never **ran** it — presence-of-string, not test-passes, the same anti-pattern round 3/4 killed elsewhere | Gate now runs the endpoint test (`pytest … -q`); `wp-frontend` gains `depends_on: wp-skills` for the fastapi-equipped venv (task 0.1) |
| R5-2 (claude) | medium | The integration full-suite gate (`wp-docs-finalize` step 2) ran `pytest skills/tests` only, missing the four dirs `wp-skills`' gate expanded to after R4-C3 — the R4-C3 fix propagated to one gate, not both | Integration gate expanded to the same five-path set |
| R5-3 (claude) | low | Checkpoint 5.7 carried an executable `git diff --name-only main...HEAD` clause — a verification command living only in `tasks.md`, violating round 4's own invariant | The carve-out diff is folded into `wp-docs-finalize`'s first gate; 5.7 now references it |
| R5-4 (codex) | medium | Executable verification gates still sat in `tasks.md` (`0.5`, `6.2`) after round 4 claimed they didn't — and R5-1/R5-2 prove such duplication drifts | `0.5` and `6.2` converted to gate references; the design.md invariant narrowed to the true, valuable form (see below) |

### What round 5 actually measured

Rounds 1–2 were about the plan being wrong. Round 3 was about gates that could not work. Round
4 was about my fixes reaching one artifact and not its twin. Round 5 is about my *round-4 fix*
being asserted more broadly than it was performed — the design.md text claimed "no verification
command appears anywhere except work-packages.yaml" while `0.5` and `6.2` still held suite
commands, one already drifted. The correction was twofold: finish the dedup (two more gates
referenced) **and** narrow the claim to what is both true and worth enforcing — no *gate* is
duplicated; *action* commands may live in task bodies.

That the review keeps finding my fixes rather than the plan is itself the answer to whether the
plan is sound. The remaining findings have shrunk in blast radius every round (critical → high
→ high → high → high-but-narrow) and in count (26 → 4). The two coverage gaps this round (R5-1,
R5-2) are the last substantive gate defects; R5-3/R5-4 are bookkeeping.

## PLAN_REVIEW round 4 — findings resolution (plan revision 2)

**Findings trend: 26 → 29 → 13 → 9** (claude 7, codex 2). Full 2/2 quorum, both vendors
granted Bash so both could execute. Every finding cites a command its author ran.

The round has one dominant theme, and it is not about the change: **7 of 9 findings are
round-3 fixes that were applied to one artifact and not its counterpart.** Gate commands were
written in *both* `tasks.md` (as checkpoint prose) and `work-packages.yaml` (as verification
steps). Round 3 corrected the YAML and left the prose stale, so `tasks.md` still instructed
the implementer to run the exact vacuous and self-contradictory checks the round had just
removed.

| ID | Criticality | Finding | Resolution |
|---|---|---|---|
| R4-C1 | critical | **`wp-skills`' gate was unpassable by `wp-skills`.** Round-3 fix #7 moved `skills/tests/agent-coordinator/**` to `wp-frontend` and denied it to `wp-skills`, but `wp-skills`' residue grep still covered `skills` broadly — demanding a file be clean that the package may not write | Added `':!skills/tests/agent-coordinator'` to the grep. Verified: 45 → 44 matches, denied path excluded, still non-zero so the gate still fails before the work |
| R4-C2 | high | Task 4.3's checkpoint contradicted both `wp-frontend`'s gate and the *Historical vendor still renders* scenario — round-3 fix #4 landed in the YAML only | Checkpoint rewritten as a reference to the package gate, with the gemini-fixture requirement stated explicitly |
| R4-C3 | high | **No gate executes three of the test directories tasks 3.1/3.4/3.8 write.** `pytest skills/tests` collects 1249 tests and zero from `skills/parallel-infrastructure/scripts/tests`, `skills/collect-transcripts/tests`, `skills/autopilot/scripts/tests` | All four directories added to `wp-skills`' gate |
| R4-C4 / R4-X1 | high | **The frontend gate was decoration.** Round-3 fix #4 replaced a hardcoded count with an expected-**set** `diff` — but the set was built *from the current tree*, so it asserted "nothing changed" and passed unmodified | Replaced with a gate asserting what the work **produces**: the new roster present in both fixture files, carve-outs and `VendorSwimlanes.tsx` unmodified. Verified it now **fails** on the unmodified tree |
| R4-C5 | medium | Round-3 fixes #3 and #9 added tasks and write-scopes but no verification — the session-log templates and `docs/cross-repo-setup.md` were ungated | All three paths added to `wp-docs-finalize`'s residue file list |
| R4-C6 | medium | Round-3 fix #10 was incomplete **within the paragraph it repaired**: the first sentence was renumbered to "Tasks 1.1-1.3", the second still read "Phase 2 verification calls" | Corrected to Phase 1 |
| R4-C7 | low | Task 5.6 named no target file while its gate greps `docs/` only — satisfying the prose by writing into a SKILL.md would fail the gate | Task now names `docs/skills-workflow.md` and says why |
| R4-X2 | medium | Task 6.1 still instructed the vacuous `git grep` over gitignored mirror dirs after the YAML was fixed in round 3 | Rewritten as a gate reference, with the `git grep`-is-vacuous reason recorded inline |

### The structural fix — one command, one home

Patching each drifted copy would have guaranteed a round 5 with the same shape. The
duplication itself was the defect: a verification command written in two places is a
consistency finding waiting to happen, which is exactly what round 2 said about task ranges
in package descriptions. The same lesson arrived twice because it was only applied where it
was first noticed.

**Every checkpoint in `tasks.md` is now a reference to its package's verification step**
("run `wp-coordinator`'s verification step and confirm it exits 0"). Checkpoints keep the
*reasoning* that prose is good at — why the gemini fixture must survive, why the mirror check
cannot use `git grep` — and delegate the executable text to its single home.

The precise invariant (narrowed after round 5, findings R5-3/R5-4): **no package verification
gate is written in more than one place; `work-packages.yaml` is its single home.** Task bodies
still name *action* commands the implementer runs to perform the work — `uv sync --all-extras`,
`npm ci`, `bash skills/install.sh …` — because those are steps, not gates, and duplicating a
gate is what drifts (a `git diff` check restated in a checkpoint, or a `pytest skills/tests`
that a package gate had already expanded past). Round 5 found two such gates that round 4's
sweep missed — checkpoint `0.5` and task `6.2` both restated package suites, and one had
already drifted (R5-1). Both are now references.

### The invariant this round establishes

Round 3 killed two gates that were decoration. Round 4 killed a third — **and it was the
replacement written for one of the first two.** A gate rewritten under time pressure inherits
the defect it was meant to remove unless someone runs it.

So: **a gate must be executed against an unmodified tree before it is committed, and it must
fail there.** A gate that passes before the work is done cannot detect the work not being
done. Both new gates in this round were checked that way — `wp-frontend`'s now fails on
`grep -q antigravity` (absent until task 4.1), and `wp-skills`' still reports 44 files.

## PLAN_REVIEW round 3 — findings resolution (plan revision 2)

First review round against the restructured plan. **Findings trend: 26 → 29 → 13**
(codex 3, claude 10). Every accepted finding was empirically verified by its author with a
command actually run, and independently reproduced by the orchestrator before acceptance.

The character of the findings changed completely, which is the signal that matters: round 2
had 21 of 29 findings pointed at the plan's own apparatus. Round 3 has **zero**. Every
round-3 finding is about whether the described work will actually succeed.

### Dispatch note — a harness defect nearly lost half the round

Claude's first dispatch was recorded as `[FAIL] Invalid JSON output`. It had not failed: it
wrote a well-formed findings file to `review-findings-plan.json` — the path
`parallel-review-plan/SKILL.md` documents — while `review_dispatcher.py` reads **stdout
only** and discards the raw text on parse failure. 13 findings sat on disk, reported as a
vendor failure. Re-dispatched with an explicit stdout-only contract and raw capture, claude
returned 10 findings as valid JSON.

Two things follow, both filed rather than fixed here:

1. The dispatcher's contract and the review skill's instructions disagree about where
   findings go. Either the dispatcher should read the documented file path as a fallback, or
   the skill should stop telling vendors to write one.
2. Claude's configured `review` dispatch mode allows only `Read,Grep,Glob` — **no Bash** — so
   it physically cannot run the verification commands that produced codex's strongest
   findings. The re-dispatch granted Bash, and the difference is stark: 8 of its 10 findings
   open with `VERIFIED:` and name the command run. This also casts doubt on
   verification-flavored claims in rounds 1–2, which were made without the ability to execute
   anything.

| ID | Criticality | Finding | Resolution |
|---|---|---|---|
| R3-1 | high | `wp-coordinator`'s gate runs the full non-e2e coordinator suite, **3 failed** before any roster work | Task **0.3** repairs the tests; gate left strict (D7 forbids scoping around breakage) |
| R3-2 | high | `npm test -- --run` exits `127` in a fresh worktree — no `node_modules` | Task **0.4** (`npm ci`); `npm ci &&` prepended to both gates invoking `npm test` |
| R3-3 | medium | Both session-log templates carry `gemini` at line 52; **no package owned either** | Task **5.5a**; both paths added to `wp-docs-finalize` |
| R3-C1 | high | **The frontend gate contradicts the spec delta.** `coordinator-kanban-viz`'s *Historical vendor still renders* scenario requires `VendorSwimlanes.test.tsx` to keep a gemini fixture (proving D5's roster-agnosticism), but the gate asserted exactly 3 gemini-bearing files in `apps/kanban-viz` when there are **4**. Passing it required deleting the evidence for the scenario | Numeric count replaced with an explicit expected-**set** `diff`, naming all four files. Removes the derived-number gate D8.1 rejected |
| R3-C2 | medium | **Vacuous gate (orchestrator-authored, revision 2).** The mirror-residue check greps `.claude/skills` / `.agents/skills` with `git grep` — both are **gitignored** (`.gitignore:271-272`), so it searched zero tracked files and passed unconditionally, even if `install.sh` did nothing | Switched to plain `grep -rIl`. Verified non-vacuous: it now returns 4 real files, so it can fail |
| R3-C3 | high | **Task 0.1's own remediation would break what it repairs.** `pytest` lives in the `test` extra, not `[project] dependencies`, so the prescribed bare `uv sync` **removes pytest from `skills/.venv`** | Task 0.1 now specifies the `test` extra and `uv sync --all-extras`, with the reasoning inline |
| R3-C7 | medium | Task 4.2 sat in `wp-skills` (`depends_on: [wp-empirical]`) but depends on task 2.7 in `wp-coordinator` — an edge the package DAG never expressed | Task 4.2 moved to `wp-frontend`, which already depends on `wp-coordinator`; path granted there and denied in `wp-skills` |
| R3-C8 | medium | `agent-identity` was the only one of 8 spec deltas **no task referenced**; its seeding scenarios name `grok-local`'s `profile`/`trust_level`, which nothing created | Task 2.2 now requires `profile:` + `trust_level:` on each new `agents.yaml` entry, and cites `agent-identity.1` |
| R3-C9 | medium | `docs/cross-repo-setup.md` documents `install-mcp.sh`'s `--no-gemini` flag and a `~/.gemini/settings.json` target — it meets D6's own inclusion criterion but was out of scope, while task 3.9 edits the script it documents | Added to task 5.3, with a dependency on 3.9 so the doc follows the script |
| R3-C10 | low | Revision-1 task numbers survive in **live** design.md sections (outside the labeled historical table). Most seriously, the operator live-billing authorization named "Tasks 2.1-2.4" — now the *coordinator config* tasks — granting billing authority to the wrong tasks and withholding it from the CLI-invoking ones | All live references renumbered (1.1-1.3, Phase 1, 2.8, 6.1). The historical round-1 table is left alone by design |

### R3-1 diagnosis — the docker failures are a test defect, not the environment

Worth recording because it was mischaracterized twice during this session, including by the
orchestrator, on nothing more than the failures' shape:

`TestDetectRuntime.test_auto_falls_back_to_podman` patches `shutil.which` with
`lambda name: f"/usr/bin/{name}"` — which returns a path for **every** binary, including
`colima`. So `is_colima_installed()` returns True, `detect_runtime` takes the macOS Colima
branch (`docker_manager.py:152-162`) and returns `"docker"` where the test expects
`"podman"`. Proven by re-running the same call with `is_colima_installed` forced False: it
returns `"podman"`. **The production code is correct; the test mock is over-broad.** Linux CI
passes only because `sys.platform != "darwin"` skips the branch, which is why this reads as
"environmental" — it is deterministic on macOS and deterministic on Linux, in opposite
directions.

The general lesson, and the reason the fix is a task rather than a deselect: *a failure that
reproduces on main is not automatically out of scope.* It is out of scope only once someone
has read it. "Pre-existing" describes provenance, not triviality.

### The two gates this round killed were both authored in revision 2

R3-C1 and R3-C2 were introduced by the restructuring that was meant to eliminate exactly this
class — a hardcoded derived count and a gate that searches nothing. D8.2's claim was that
inline one-liners are safer than bespoke scripts; that remains true, but the round shows the
real invariant is narrower: **a gate is only worth having if you have watched it fail.** Both
defects were invisible to reading and obvious to running. Every gate in this plan should be
run against an unmodified tree at least once, and one that passes there is not a gate.

| ID | Criticality | Finding | Resolution |
|---|---|---|---|
| R3-1 | high | `wp-coordinator`'s gate runs the full non-e2e coordinator suite, which is **3 failed, 2027 passed** before any roster work — an unpassable gate | Task **0.3** repairs the tests. The gate is left strict: scoping it around the breakage is what D7 rejects |
| R3-2 | high | `npm test -- --run` exits `127 sh: vitest: command not found` in a fresh worktree — no `node_modules`. Phases 4 and 6 invoke it with no install step, so gates fail on setup, not roster behavior | Task **0.4** (`npm ci`); `npm ci &&` prepended in both gates that invoke `npm test` |
| R3-3 | medium | Both session-log templates carry `gemini` in the agent-type roster at line 52, and **no package owned either file** — `wp-skills` allows only two specific `openspec/schemas/` files and denies `plan-feature/install_assets/**` | Task **5.5a**; both paths added to `wp-docs-finalize`'s `write_allow` |

### R3-1 diagnosis — the docker failures are a test defect, not the environment

Worth recording because it was mischaracterized twice during this session, including by the
orchestrator, on nothing more than the failures' shape:

`TestDetectRuntime.test_auto_falls_back_to_podman` patches `shutil.which` with
`lambda name: f"/usr/bin/{name}"` — which returns a path for **every** binary, including
`colima`. So `is_colima_installed()` returns True, `detect_runtime` takes the macOS Colima
branch (`docker_manager.py:152-162`) and returns `"docker"` where the test expects
`"podman"`. Proven by re-running the same call with `is_colima_installed` forced False: it
returns `"podman"`. **The production code is correct; the test mock is over-broad.** Linux CI
passes only because `sys.platform != "darwin"` skips the branch, which is why this reads as
"environmental" — it is deterministic on macOS and deterministic on Linux, in opposite
directions.

The general lesson, and the reason the fix is a task rather than a deselect: *a failure that
reproduces on main is not automatically out of scope.* It is out of scope only once someone
has read it. "Pre-existing" describes provenance, not triviality.

### Phase 0 ownership

Baseline repair is no longer a single block — each package repairs the baseline **inside its
own tree** before its own gate runs (0.1 → `wp-skills`, 0.3 → `wp-coordinator`,
0.4 → `wp-frontend`). This keeps every repair inside an existing `write_allow` with no
cross-package writes, and each package's gate becomes passable by that package's own work.

## PLAN_REVIEW round 1 — findings resolution

> **Historical record.** Task numbers in this table refer to **plan revision 1**, which
> revision 2 (D8) replaced wholesale. The substantive findings all survive in revision 2's
> tasks; the apparatus the resolutions built (gate scripts, manifest, fact-consumer wiring)
> was deleted by D8.2.

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

## Why 3.1 (and 2.6, 3.8) stay L

Task 3.1 writes failing tests across ~9 test files in one package. The sizing table says L
should be decomposed into 2–3 M tasks where that reduces risk. Here it does not: every one of
those files asserts against the same roster constant, so splitting them creates tasks that must
land together to keep the suite green, and an agent holding only a third of the surface cannot
tell whether the roster is consistently applied. The risk being managed is *inconsistency
across the dispatch surface*, and that risk is lowest when one agent sees all of it at once.
The same argument covers 2.6 (three eval backends against one suite) and 3.8 (three adapters
against one event schema).

They are flagged rather than split, per the sizing table's "keep but flag" instruction for L.

## Why the empirical phase runs before config

Phase 1 produces facts — `agy --model` slugs, whether `grok --prompt-file /dev/stdin` survives a
subprocess pipe, whether `pi` resolves `OPENROUTER_API_KEY` from the subprocess environment,
and the re-login commands. Phases 2–3 consume them.

Ordering these last would mean writing `agents.yaml` entries against guessed flags and
discovering the mistake during VALIDATE, after the config has propagated into tier maps,
adapters, and tests. The proposal already flagged two of these as "verified empirically"; this
plan makes that verification a gating task rather than a hope.

`grok login` was confirmed during planning ("Sign in to Grok"). `agy` and `pi` show no login
subcommand in `--help`; `_RELOGIN_COMMANDS` already falls back to `f"{command} login"`
(`review_dispatcher.py:271`), so tasks 1.1/1.3 confirm rather than invent.

## Empirical CLI findings

**Operator authorization (recorded 2026-07-22):** live dispatch against `agy`, `grok`,
and `pi` is approved. **Tasks 1.1-1.3** may invoke these CLIs with real prompts, which
consumes subscription quota (agy, grok) and OpenRouter tokens (pi). No further approval
is required for the Phase 1 verification calls.

> Populated by Phase 1. Until every row below reads `confirmed` or `refuted` with evidence,
> **no package may hardcode a CLI flag, model slug, or output-parsing assumption.**

> **Expanded in PLAN_REVIEW round 1** (finding C4, confirmed by both vendors). The original
> table covered 4 facts while Phases 3, 5, and 6 consumed 8. The four added rows are marked ✚.

Each row MUST be filled with `confirmed` or `refuted` **plus the observed evidence** (the exact
command run and the relevant output excerpt). `pending`, `unknown`, `n/a`, and a deleted table
are all failures. Whether the evidence is genuine is checked by a **human** at checkpoint 1.4
(`wp-empirical`'s manual verification step) — not by a script (D8.2).

| # | Fact | Consumed by | Task | Status | Evidence (see evidence log below) |
|---|---|---|---|---|---|
| E1 | `agy` model slug strings for premium/standard/economy | 2.3 | 1.1 | **confirmed** | `agy models` → catalog (§L1); tiers = `gemini-3.6-flash-high` / `-medium` / `-low` (operator-signed 2026-07-22) |
| E2 | grok delivers a prompt under a subprocess pipe | 2.2 | 1.2 | **confirmed** | `printf … \| grok --prompt-file /dev/stdin -m grok-4.5 --reasoning-effort low` → `42`, exit 0 (§L6). `--prompt-file` **does** exist (mid-`--help`); one-shot alt is `-p/--single <PROMPT>` |
| E3 | `pi` resolves `OPENROUTER_API_KEY` from the subprocess env | 2.2, 5.4 | 1.3 | **confirmed** | `pi -p --provider openrouter --model moonshotai/kimi-k3 "<prompt>"` succeeded with real usage/cost, `provider":"openrouter"` (§L7); key inherited from subprocess env |
| E4 | `agy` / `pi` re-login commands | 3.4 | 1.1, 1.3 | **confirmed (both)** | agy: **no `agy login`** — auto-auth on launch, `/logout` resets (§L3). pi: env-var key, no login subcommand (§L7). grok: real `login`/`logout` (§L6). Dispatcher `{command} login` fallback is **valid only for grok**; invalid for agy & pi |
| E5 | `grok` model slugs / tiers for premium/standard/economy | 2.3 | 1.2 | **confirmed** | `grok models` (authed) → **single model `grok-4.5`**; tiers via `--reasoning-effort {low,medium,high}` (`low` accepted, §L6). No per-tier slugs |
| E6 | grok structured-output envelope (`--json-schema`, implies `--output-format json`) | 2.6, 2.2 | 1.2 | **confirmed** | Envelope emitted; conforming payload under **`.structuredOutput`**, jsonschema-validated PASS vs `review-findings.schema.json` (§L6) |
| E7 | `agy` non-interactive print + `--mode plan` behave Claude-shaped | 2.2, 2.6, 3.8 | 1.1 | **confirmed w/ correction** | `agy -p "<prompt>" --model …` → text (§L2). **stdin refuted** — prompt must be the `--print`/`--prompt`/`-p` *value*, not stdin, not a trailing positional |
| E8 | `pi` accepts the prompt as a trailing positional; output shape | 2.2, 2.6, 3.8 | 1.3 | **confirmed** | Positional prompt → `42` (§L7). `--mode json` output is an **NDJSON event stream**; final text is in the `agent_end`/`message_end` assistant `content[]` where `type=="text"` (not a single envelope) |
| — | `grok login` exists | 3.4 | — | **confirmed** | `grok --help` → `login  Sign in to Grok`; also `logout` |
| — | pi frontier model slug (Kimi 3) | 5.x | 1.3 | **confirmed** | `pi --list-models` → `openrouter  moonshotai/kimi-k3  1.0M  131.1K  yes  yes` (§L5) |

**Routing decision (operator, 2026-07-22):** grok routes through the **`grok` binary (xAI subscription)**, *not* `pi --provider openrouter`. OpenRouter/`pi` is reserved for the frontier **Kimi 3** (`moonshotai/kimi-k3`) that the xAI subscription does not cover. The `x-ai/grok-*` slugs on OpenRouter are therefore **not** used for grok routing.

**Operator authorization is on record** (above), so these tasks may make live billed calls.

### Phase 1 evidence log (recorded 2026-07-22, live probes)

- **§L1 — E1 `agy models`** (`agy models </dev/null`, non-billed catalog read):
  `gemini-3.6-flash-{high,medium,low}`, `gemini-3.5-flash-{high,medium,low}`,
  `gemini-3.1-pro-{high,low}`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`,
  `gpt-oss-120b-medium`. Note the effort suffix is baked into the slug (`-high/-medium/-low`),
  so agy encodes reasoning effort in the model id rather than a separate `--effort` value for
  the gemini family. **Tier map (operator-signed 2026-07-22):** premium `gemini-3.6-flash-high`,
  standard `gemini-3.6-flash-medium`, economy `gemini-3.6-flash-low` — one model
  (`gemini-3.6-flash`) across three effort levels, consumed by task 2.3.
- **§L2 — E7 agy prompt delivery** (billed, `gemini-3.6-flash-low`):
  `agy --prompt "What is 17 plus 25? Reply with ONLY the number." --model gemini-3.6-flash-low --print-timeout 90s` → `42` (exit 0). `-p` alias identical → `42`.
  **Refuted forms:** `printf '<prompt>' | agy --print …` (stdin) and `agy --print … "<prompt>"`
  (trailing positional) both produced generic self-description output — the prompt was ignored.
  `--mode plan` accepted without error; output is plain Claude-shaped markdown prose to stdout.
  **Dispatcher consequence:** the current `build_command` (`prompt_via_stdin` or bare positional
  append) cannot feed agy; the prompt must attach to `--prompt`/`-p` as its value. Handle in
  task 2.2 (adapter shaping) — agy needs a `prompt_flag`-style attachment, not `prompt_via_stdin`.
- **§L3 — E4a agy re-login** (authoritative, https://antigravity.google/docs/cli/install):
  There is **no `agy login` command**. Auth is automatic on launch (OS keyring → browser
  sign-in; over SSH a paste-back auth code). Re-auth is the interactive `/logout` slash command
  (clears creds + cache) followed by relaunch. `agy --help` subcommands confirm no login/auth
  entry. **Dispatcher consequence:** `_RELOGIN_COMMANDS` fallback `f"{command} login"` yields an
  invalid `agy login`; agy needs either an explicit "manual re-auth required" sentinel or omission
  from auto-relogin (task 3.4).
- **§L4 — grok (blocked)** `grok models </dev/null` → `You are not authenticated. Default model: grok-4.5`.
  `grok --help`: `--json-schema <SCHEMA>` "Implies --output-format json"; `--model`/`-m`;
  `--reasoning-effort`/`--effort`; real `login`/`logout` subcommands. (Superseded below once
  authenticated — the mid-`--help` non-interactive flags were found in §L6.)
- **§L5 — pi flag surface** `pi --list-models </dev/null` returns the OpenRouter catalog
  including `moonshotai/kimi-k3` (frontier target) and `moonshotai/kimi-k2*` variants. `pi --help`:
  `--provider <name>` (default google), `--model`, `--mode text|json|rpc`, `--print`/`-p`, prompt
  as trailing `[messages...]` positional, `--api-key` defaults to env vars. pi has no login
  subcommand (env-var key model).
- **§L6 — grok E2/E5/E6** (authenticated `grok.com`, billed). Non-interactive flags (found
  mid-`--help`): `-p, --single <PROMPT>` (single-turn, prints to stdout + exits),
  `--prompt-file <PATH>` (so `/dev/stdin` **is** valid — corrects §L4), `--prompt-json <JSON>`,
  `--output-format <plain|json|streaming-json>` (default plain).
  - **E2:** `printf 'What is 17 plus 25? Reply with ONLY the number.' | grok --prompt-file /dev/stdin -m grok-4.5 --reasoning-effort low` → `42`, exit 0. Subprocess pipe delivery works.
  - **E5:** `grok models` (authed) lists **only `grok-4.5`** (default). No premium/standard/economy
    slugs — tiers come from `--reasoning-effort {low,medium,high}` (`low` accepted above). `-m grok-4.5`
    bills internally as `grok-4.5-build` (see `modelUsage`).
  - **E6:** same call + `--output-format json --json-schema "$(cat review-findings.schema.json)"`
    returned a **single envelope** with keys `text, thought, stopReason, sessionId, requestId,
    usage, num_turns, total_cost_usd, modelUsage, structuredOutput`. The schema-conforming object
    is at **`.structuredOutput`** (jsonschema.validate PASS vs `review-findings.schema.json`).
    Cost $0.0276 for the call. **Parser (task 2.6) must read `.structuredOutput`, not top-level.**
- **§L7 — pi E3/E8** (billed, `moonshotai/kimi-k3` via OpenRouter). `pi -p --provider openrouter
  --model moonshotai/kimi-k3 --mode json "What is 17 plus 25? Reply with ONLY the number."`
  → answered `42`, exit 0, cost $0.00275.
  - **E3:** the call resolved `OPENROUTER_API_KEY` from the inherited subprocess environment
    (no `--api-key` passed); events show `"provider":"openrouter","model":"moonshotai/kimi-k3"`
    with real token usage/cost. Confirmed.
  - **E8:** prompt delivered as a **trailing positional**. `--mode json` output is an **NDJSON
    event stream** — one JSON object per line (`session`, `agent_start`, `turn_start`,
    `message_start/update/end`, `turn_end`, `agent_end`, `agent_settled`). The final answer is the
    last assistant message's `content[]` entry with `type=="text"` (kimi also emits a `thinking`
    block). **Parser (task 2.6) must stream-parse NDJSON and pull the final `type=="text"` content
    — pi's shape is entirely unlike grok's single envelope.**

## Merge-order coupling

Three roadmap items edit surfaces this change touches. `ri-01` is the DAG root precisely so it
lands first and fixes the roster before anything else reads it.

| Roadmap item | Overlap | Handling |
|---|---|---|
| `ri-02` add-live-vendor-capability-and-cost-registry | Deletes `orchestrator.py`'s vendor list; replaces `policy.py`'s cost stub | Keep both structures stable (task 3.3) so `ri-02` is a clean removal |
| `ri-04` add-adaptive-model-router | Touches `agents.yaml` / `archetypes.yaml` tiers; adds `openai_compat_adapter.py` | Roster additions are additive to tier maps; no schema change |
| `ri-06` build-structured-vendor-result-channel | Switches every CLI adapter to structured JSON envelopes | grok already emits `--output-format json`; this change aligns rather than conflicts |

The `provider-model-map.schema.json` bump to `schema_version: 2` closes the provider key set via
`propertyNames.enum` and requires all five keys. Version 1 used open `additionalProperties`,
which would have accepted a reintroduced `gemini` key silently — the failure mode this change
exists to remove. The schema's runtime home is `openspec/schemas/provider-model-map.schema.json`
(task 3.6): contract tests must never resolve schemas inside change directories, because those
move on archive.
