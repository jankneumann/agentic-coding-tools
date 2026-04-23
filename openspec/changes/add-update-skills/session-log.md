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
