# Session Log — add-update-skills

---

## Phase: Plan (2026-04-23)

**Agent**: claude_code | **Session**: skillify-pattern

### Decisions

1. **Single-skill orchestrator over per-step skills.** One `/update-skills` skill wraps the four steps. Splitting into `/sync-skills`, `/sync-agents-md`, `/commit-runtime` was considered. The four steps are tightly coupled. They are never useful independently. One command matches the operator mental model.

2. **Pre-commit hook is independent enforcement, not delegated.** The CLAUDE.md to AGENTS.md byte-identity invariant is enforced by a pre-commit hook. The hook runs `sync_agents_md.py --check`. This makes the invariant robust to forgetfulness. It also protects direct git workflows.

3. **Pre-commit framework over hand-rolled `.git/hooks/` script.** The hook is configured in `.pre-commit-config.yaml` as a `local` entry. The framework handles install, ordering, file filtering, and skip behavior. A separate `install-hooks.sh` at repo root bootstraps the framework. This keeps hook installation explicit and out of `skills/install.sh`. It also lines up with the broader Python ecosystem norm.

4. **Opt-in SessionStart auto-pull via `AGENTIC_AUTO_PULL=1`.** Auto-pulling at SessionStart on dirty trees has known footguns. Default-off opt-in respects user autonomy. The env var is namespaced.

5. **Sequential tier despite coordinator availability.** Coordinator detection returned all capabilities true. The plan-feature rule implies coordinated tier. Deviated to sequential. The change is small. The work is tightly coupled. Parallel decomposition yields no benefit.

6. **Branch override accepted in shared checkout.** The harness mandated branch is already checked out in the shared checkout. The worktree script cannot create a second checkout of the same branch. Proceeded in the shared checkout. This is a known tension between the worktree invariant and the harness branch mandate.

### Alternatives Considered

- Approach 2 (pre-commit hook only, no skill): rejected. The install.sh rsync on every commit is too slow. It also does not solve the push gap.
- Approach 3 (modify install.sh to commit and push): rejected. It violates the no-install.sh-changes non-goal. It also couples installation to git operations.
- Coordinated tier with parallel work-packages: rejected. The work does not decompose into independent units. Serial execution is faster than coordination overhead.

### Trade-offs

- Accepted a new skill (one more thing to maintain) over a hidden hook-only mechanism. Reason: the explicit invocation is discoverable.
- Accepted bounded retry on push (3 attempts) over unbounded retry. Reason: indefinite retry can mask real failures.
- Accepted opt-in auto-pull over default-on. Reason: surprising a user mid-feature-work outweighs always-fresh main.

### Open Questions

- [ ] Should the pre-commit hook also catch direct edits to AGENTS.md? The spec catches drift in either direction. The error message currently only points at the sync script. Defer to implementation.
- [x] Where exactly does the pre-commit hook get installed? Resolved: use the standard pre-commit framework via `.pre-commit-config.yaml`, with a separate `install-hooks.sh` at repo root that runs `pre-commit install`. See decision 3.

### Context

This change closes the manual-sync gap between canonical skills and runtime skill directories. It also populates the currently-empty AGENTS.md by generating it from CLAUDE.md. It is prerequisite plumbing for the next roadmap item (add-skillify-and-resolver-audit). The change is intentionally small and infrastructure-only.

---

## Phase: Plan Iteration 1 (2026-04-23)

**Agent**: claude_code | **Session**: skillify-pattern

### Decisions

1. **Pre-commit installed via `uv sync --all-extras`, not ad-hoc.** Added `pre-commit` as a dev-dependency in `skills/pyproject.toml`. The new `install-hooks.sh` runs `uv sync` + `pre-commit install`. This matches the CLAUDE.md Python-env convention and pins the version in the lockfile.

2. **Auto-pull wired for both Claude Code and Codex.** One shared `auto_pull.py` helper. Two wiring points: `.claude/settings.json` SessionStart hook entry and `skills/session-bootstrap/scripts/bootstrap-cloud.sh` (Codex Maintenance Script). Both paths gated by the same `AGENTIC_AUTO_PULL=1` env var.

3. **Added explicit orchestrator partial-failure scenarios.** Previously the spec only covered the happy path and push retry. Added two scenarios: install.sh failure (abort before sync) and sync-script failure (abort after install.sh, keep install.sh staged for manual recovery).

4. **Specified push-retry output format.** stderr gets human-readable per-attempt summary. stdout gets a single `UNPUSHED_COMMIT=<sha>` line for automation. Backoff timing now explicit: attempt 1 immediately, 1s before attempt 2, 2s before attempt 3. Git push now uses explicit `origin` remote.

5. **Added "Install-hooks bootstrap idempotent" requirement.** New spec requirement with 3 scenarios: first-run install, idempotent re-run, missing-uv error path.

### Alternatives Considered

- `uv pip install pre-commit` ad-hoc install: rejected on user direction. Off-convention. Version unpinned.
- Pipx system-level install: rejected on user direction. Couples repo to global state.
- Wire Claude Code only, defer Codex: rejected on user direction. Asymmetry would surprise.
- Keep the silent-exit scenario unchanged: rejected. The framework prints a status line. The old wording made the test ambiguous.

### Trade-offs

- Accepted a new dev-dependency in `skills/pyproject.toml` over a self-contained install-hooks script. Reason: pinning and convention.
- Accepted touching `bootstrap-cloud.sh` over Claude-only wiring. Reason: symmetric runtime experience.

### Open Questions

- [ ] None remaining at medium-or-above criticality.

### Context

Iteration 1 addressed 8 findings (4 high, 3 medium, 1 low raised to medium during the M6 output-channel rewrite). Two findings required `AskUserQuestion` per the assumption protocol; both received decisive user answers that drove the fixes. All resulting changes pass `openspec validate add-update-skills --strict`. No residual findings at or above the medium threshold — loop terminates after iteration 1.

---

## Phase: Implementation (2026-04-23)

**Agent**: claude_code | **Session**: skillify-pattern

### Decisions

1. **Test fixtures disable commit signing locally.** The session's git is configured with a signing server that only accepts known repo paths. Test repos in tmp dirs can't sign. Fixtures set `commit.gpgsign=false` in the tmp repo only. This is scoped to fixtures and does not bypass signing for real commits on the feature branch.

2. **Propagation via direct cp, not install.sh.** The dev env has no rsync. Both rsync and copy modes refused to run. Switching the whole repo to symlink mode would have deleted many tracked copies. I propagated only the new and modified files directly. Other skills stay as real directories.

3. **AGENTS.md already a symlink.** The repo had AGENTS.md as a symlink to CLAUDE.md from a prior date. The sync script and pre-commit hook work either way. This change formalizes the invariant. It does not pick one representation.

4. **Commit signing for real commits is untouched.** All feature-branch commits were signed normally. Only tmp test fixtures set gpgsign false.

5. **Exit-0 everywhere for auto-pull.** Auto-pull never blocks session start. Network errors, dirty trees, detached HEAD, non-git dir, timeout — all paths log and exit 0.

6. **update_skills.py aborts at each step boundary.** install.sh failure: abort before sync. sync_agents_md failure: abort after install, leave install changes staged for manual recovery. Push retry exhausted: emit `UNPUSHED_COMMIT=<sha>` on stdout for automation + per-attempt summary on stderr, exit 1.

### Alternatives Considered

- **Mock-based orchestrator tests**: rejected. Real-subprocess tests with a tmp repo and a bare origin exercise the actual git + subprocess flow and caught a real issue (commit signing) that mocks would have masked.
- **Commit the symlink install artifacts**: rejected. Would have produced an 851-file PR diff as git saw the pre-existing copies being replaced by symlinks.
- **Deeper install.sh surgery to avoid rsync dependency**: rejected. Out of scope per non-goal "no changes to existing install.sh behavior".

### Trade-offs

- Accepted deferring the `install-hooks.sh` end-to-end uv-sync test over blocking implementation. Reason: dev env can[REDACTED:high-entropy]s suggestion to also auto-register the change-id in the coordinator feature registry (CAN_FEATURE_REGISTRY=true) was deferred as a skillify concern — but the infrastructure is here. Revisit after Change B lands.

### Context

All 17 tasks across 6 phases implemented and verified. 24/24 tests green. `openspec validate add-update-skills --strict` passes. One requirement (skill-runtime-sync.6) has partial evidence — structural test only; full uv-sync behavior needs rsync-capable CI. Ready for PR review.
