# Handoff — resume `project-context-refresh-lifecycle` at ri-05

**Written:** 2026-07-24 · **Prev item:** ri-04 (DONE, PR #270) · **Next item:** ri-05

Resume command: `/autopilot-roadmap project-context-refresh-lifecycle continue with ri-05`

---

## 1. Where things stand

Roadmap workspace: `openspec/roadmaps/project-context-refresh-lifecycle/` inside the
worktree `.git-worktrees/roadmap-project-context-refresh-lifecycle`
(branch `openspec/roadmap-project-context-refresh-lifecycle`, meta-only).

Checkpoint (`checkpoint.json`): `current_item_id: ri-05`, phase `implementing`,
`completed_items = [ri-01, ri-02, ri-03, ri-06, ri-04]`.

| Item | Change id | State |
|------|-----------|-------|
| ri-06 | `add-durable-context-refresh-records` | **PR #269 OPEN** (base main). Ships `skills/project-context-runtime/` — the shared runtime. |
| ri-04 | `make-architecture-refresh-revision-aware` | **PR #270 OPEN**, base = **ri-06 branch** (stacked). 288 skills + 48 coord tests green. |
| **ri-05** | `add-deterministic-context-producer-checks` | **approved, ready, NOT started.** deps: ri-06 ✓ |

### ⚠️ Critical: stacked-PR dependency chain
Roadmap "completed" ≠ merged. ri-06's `project-context-runtime` is **only on the
unmerged #269 branch**, not on `main`. Every later item that imports it (ri-04 did;
ri-05 will) must be **branched off the dependency branch, not `main`**.
Merge order: **#269 → #270 → …**; retarget/rebase each onto `main` as its parent lands.
(Memory: `project_context_refresh_lifecycle_stacked_prs`.)

---

## 2. ri-05 scope — `add-deterministic-context-producer-checks` (effort L, priority 5)

Add reproducible **generate + check** modes for the deterministic context producers:
documentation inventories, API contracts / generated bindings, decision timelines, and
OpenSpec projections. **Reuse** `update-specs`, `documentation-and-adrs`, and existing
documentation-sync work — do not duplicate their domain logic.

Acceptance outcomes (from `roadmap.yaml`):
- Each configured deterministic producer can regenerate output and report a precise list
  of **stale artifacts without relying on mtimes**.
- Generated artifacts carry source revision + producer metadata; hand-authored docs
  outside managed regions stay unchanged.
- The `add-update-documentation-skill` proposal is explicitly **absorbed / superseded /
  declared a prerequisite** — no competing refresh lifecycle may remain.
- API, decision, documentation, and OpenSpec checks are independently runnable + testable
  through their canonical owners.

**Plan artifacts already exist** at `openspec/changes/add-deterministic-context-producer-checks/`
(proposal, tasks, design, specs, contracts, work-packages) — committed on the **roadmap
branch only**. Read them first; the item is planned/approved, so this is an implement run.

### Direct guidance carried forward (from ri-06 → ri-05, in learnings/ri-06.md)
> ri-05: emit a canonical ri-06 `ProducerResult` with **safe repo-relative artifact paths +
> sha256** and validations; **never embed content or absolute paths.**

Follow the ri-04 pattern: producer-specific provenance/fingerprint stays local; durability,
locking, and the `ProducerResult`/operation model come from `project-context-runtime`.

---

## 3. Exact setup for ri-05 (repeat of the ri-04 recipe)

```bash
cd /Users/jankneumann/Coding/agentic-coding-tools
# 1. Branch ri-05 off the runtime it imports (ri-06), NOT main:
git branch openspec/add-deterministic-context-producer-checks openspec/add-durable-context-refresh-records
# (If ri-06 has since merged to main, branch from main instead and skip the stacking.)

# 2. Managed worktree (honors the pre-created branch):
eval "$(python3 skills/worktree/scripts/worktree.py setup add-deterministic-context-producer-checks --no-bootstrap)"
cd "$WORKTREE_PATH"

# 3. Graft the planning artifacts from the roadmap branch:
git checkout openspec/roadmap-project-context-refresh-lifecycle -- openspec/changes/add-deterministic-context-producer-checks
git add -A && git commit -m "docs: base ri-05 plan on ri-06 runtime branch"

# 4. Fast test toolchain — symlink the self-contained main-repo venvs:
MAIN=/Users/jankneumann/Coding/agentic-coding-tools
ln -sfn "$MAIN/skills/.venv" skills/.venv
ln -sfn "$MAIN/agent-coordinator/.venv" agent-coordinator/.venv

# 5. Mutation gate:
skills/.venv/bin/python skills/shared/checkout_policy.py require-mutation
```

---

## 4. Environment gotchas (all verified this session)

- **Two venvs, both self-contained** (no editable installs leak the main-repo path, so
  symlinking is safe): `skills/.venv` has pytest + jsonschema; **`ruff`/`mypy` live ONLY
  in `agent-coordinator/.venv`.**
- Determinism: the refresh runner exports **`SOURCE_DATE_EPOCH`** (analyzed commit ts) so
  producers stamp reproducibly → byte-identical reruns. ri-05 producers should do the same
  (reuse `arch_utils/determinism.generated_at_iso` pattern or an inline `SOURCE_DATE_EPOCH`
  helper for standalone scripts).
- ri-06 runtime facade to reuse (import from `skills/project-context-runtime/scripts`, flat
  imports): `store.OperationStore` (`create_or_load`, `begin_attempt`,
  `record_producer_result`; do **not** call `finalize` from a single producer),
  `models.ProducerResult/RepositoryArtifact/ChangeKind/ValidationResult/…`,
  `atomic.canonical_json_bytes / atomic_write_json / sha256_hex`.
- **ri-06's append-only store rejects duplicate `producer_id`** → record each producer once
  per `(repo, revision)`; make the adapter idempotent, not update-in-place.
- Tests go in `skills/tests/<skill>/` OR `skills/<skill>/scripts/tests/`. For flat-import
  modules, add `sys.path` in a `conftest.py` (see the ri-04 contract-test conftest).
- `openspec` = npm CLI: `npx --yes @fission-ai/openspec@latest validate <change-id> --strict`.

## 5. Verification matrix that must stay green

```bash
# ri-05's own new suites, plus the ri-06 runtime regression it builds on:
skills/.venv/bin/python -m pytest skills/tests/project-context-runtime -q          # ri-06 unchanged
agent-coordinator/.venv/bin/ruff check <ri-05 files>
MYPYPATH="<skill>/scripts:skills/project-context-runtime/scripts" agent-coordinator/.venv/bin/mypy <core modules>
npx --yes @fission-ai/openspec@latest validate add-deterministic-context-producer-checks --strict
```

## 6. Landing the plane (same as ri-04)

1. Push branch; open **draft PR with `--base openspec/add-durable-context-refresh-records`**
   (or `main` if #269 merged). 2. In the roadmap worktree: `learning.write_entry` for ri-05,
   `CheckpointManager.complete_item("ri-05")` + `advance_to_next` (next ready will be **ri-08**,
   deps [] — ri-07 still blocked until ri-05 done). 3. Commit ONLY the roadmap workspace path
   (leave ri-06's stray untracked `skills/project-context-runtime/` out of the meta-commit).
   4. Push roadmap branch.

## 7. Downstream consumers of ri-04 (context, not ri-05 work)
- ri-07: consume `context_runtime_adapter.ArchitectureAdapter.read_architecture_result` /
  `project_status`; call runtime `finalize` only after ALL producers report.
- ri-10: `make architecture-check` is the deterministic drift gate (exit≠0 = drift).
- Bump `arch_utils/provenance.PRODUCER_VERSION` when analyzer output changes (invalidates
  architecture freshness on purpose).
