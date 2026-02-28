# Lessons Learned

Accumulated patterns and conventions from building and operating this project.

## Skill Design Patterns

- **Match skills to approval gates**: Each skill should end at a natural handoff point where human approval is needed. This creates clean boundaries and supports async workflows.

- **Separate creative from mechanical work**: Planning and implementation are creative; cleanup/archival is mechanical. Different skills for different work types allows delegation and automation.

- **Use consistent frontmatter format**: Skills should have `name`, `description`, `category`, `tags`, and `triggers` in YAML frontmatter.

- **Flat skill directory structure**: Claude Code skills don't support nested directories. Each skill must be `<skill-name>/SKILL.md`. For namespaced skills, use hyphens: `openspec-proposal/SKILL.md` not `openspec/proposal/SKILL.md`. Symlink to `~/.claude/skills/` for global availability.
- **Keep skill executables in skill-local scripts/**: Any executable used by a skill must live under `<skill-name>/scripts/` for portability and install consistency.

- **Iterate at both creative stages**: Plans and implementations both benefit from structured iteration loops with domain-specific finding types and quality checks. `/iterate-on-plan` refines proposals before approval; `/iterate-on-implementation` refines code before PR review.

- **Plan for parallel execution**: Task decomposition in proposals should explicitly identify dependencies and maximize independent work units. This enables `/parallel-implement` to spawn isolated agents without merge conflicts.

## Task() Parallelization Patterns

- **Use Task() for parallel work**: The native Task() tool with `run_in_background=true` replaces external CLI spawning (`claude -p`) and git worktrees. Send multiple Task() calls in a single message to run them concurrently.

- **Parallel quality checks**: Run pytest, mypy, ruff, and openspec validate concurrently. Collect all results before reporting—don't fail-fast on first error. This gives users a complete picture of issues.

- **Parallel exploration**: Use Task(Explore) agents to gather context from multiple sources concurrently. This is read-only and safe to parallelize unconditionally.

- **File scope isolation**: For parallel implementation tasks, each agent's prompt must explicitly list which files it may modify. Tasks with overlapping file scope must run sequentially, not in parallel.

- **No worktrees needed**: Task() agents are orchestrator-coordinated. The old worktree pattern was needed because external `claude -p` processes had no coordination. With Task(), logical file scoping via prompts replaces physical isolation via worktrees.

- **Result aggregation**: After parallel tasks complete, the orchestrator collects results via TaskOutput, verifies work, and commits. Don't let agents commit directly—the orchestrator should control the commit.

## OpenSpec Integration

- **Agent-native OpenSpec first**: For planning/implementation/validation/archive internals, prefer generated OpenSpec assets for the active runtime:
  Claude: `.claude/commands/opsx/*.md` or `.claude/skills/openspec-*/SKILL.md`
  Codex: `.codex/skills/openspec-*/SKILL.md`
  Gemini: `.gemini/commands/opsx/*.toml` or `.gemini/skills/openspec-*/SKILL.md`
- **CLI fallback always available**: If a runtime asset is missing or incompatible, use direct commands (`openspec new change`, `openspec status`, `openspec instructions ...`, `openspec archive`).

- **Spec deltas over ad-hoc docs**: Put requirements and scenarios in `openspec/changes/<id>/specs/` rather than separate planning documents. This ensures specs stay updated.

- **Archive after merge**: Always archive completed changes with runtime-native archive flow or CLI fallback `openspec archive <change-id> --yes`.

## Local Validation Patterns

- **Parameterize docker-compose host ports**: Coordination stacks frequently run alongside other local services. Use env-driven host port mappings (for example `AGENT_COORDINATOR_REST_PORT`) instead of hardcoded ports so validation can run without stopping unrelated containers.

- **Keep E2E base URL configurable**: End-to-end tests should read `BASE_URL` and never hardcode `localhost:3000`. This allows validation against remapped ports (for example `BASE_URL=http://localhost:13000`).

- **Validate with remapped ports as a first-class path**: When defaults are occupied, run `docker compose` with `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, and `AGENT_COORDINATOR_REALTIME_PORT`, then execute e2e with matching `BASE_URL`.

## Language & Architecture Choices

- **Python for I/O-bound coordination services**: Despite Go/Rust being faster, Python is the right choice for services that spend most time waiting on databases and HTTP calls. FastMCP and Supabase SDKs are mature.

- **MCP for local agents, HTTP for cloud**: Local agents (Claude Code CLI) use MCP via stdio. Cloud agents can't use MCP and need HTTP API endpoints.

## Cross-Skill Python Patterns

- **Shared models via sys.path**: When skills need to share Python modules (e.g., fix-scrub importing bug-scrub's `models.py`), use `sys.path.insert(0, path)` at module top level plus `importlib` for dynamic loading. The canonical models live in `bug-scrub/scripts/models.py`; fix-scrub imports them via `fix_models.py` which handles the path resolution.

- **Skills tests use agent-coordinator venv**: Skills under `skills/` don't have their own venvs. Run their tests via the agent-coordinator venv: `/Users/jankneumann/Coding/agentic-coding-tools/agent-coordinator/.venv/bin/python -m pytest skills/bug-scrub/tests/ skills/fix-scrub/tests/`.

- **Normalize external tool output paths**: Tools like ruff return absolute paths in JSON output, but internal finding IDs use relative paths. Always normalize with `Path(abs_path).relative_to(project_dir)` before comparison. This was a critical bug caught in iteration — all findings were falsely reported as resolved.

## Two-Level Parallel Development Patterns

- **Layer services on existing metadata**: The merge queue stores queue state in the feature registry's metadata JSONB column rather than adding a separate table. This avoids migration overhead and keeps the data model cohesive — query one table to get feature + queue state.

- **AsyncMock for service-layer tests**: When a service depends on another service (merge queue → feature registry), mock the dependency at the service layer using `unittest.mock.AsyncMock` rather than HTTP-level mocking with `respx`. This tests the actual service logic without coupling to transport details.

- **datetime.now(UTC) over datetime.utcnow()**: Python 3.12+ deprecates `datetime.utcnow()`. Use `from datetime import UTC, datetime` and `datetime.now(UTC)` to avoid deprecation warnings in tests.

- **Discover actual source layout before implementing**: Tasks.md may specify paths like `agent_coordinator/services/feature_registry.py` but the actual layout is flat at `agent-coordinator/src/feature_registry.py`. Always read the real directory structure before creating files.

- **Property-based tests catch API mismatches**: Hypothesis tests against real modules revealed: `check_scope_compliance` returns `compliant` not `passed`, uses `deny` not `write_deny` parameter, `EscalationHandler` requires `contracts_revision`/`plan_revision`, and `handle()` returns dataclass not dict. Unit tests with full mocks would miss these.

- **Formal verification as documentation**: Even without TLC/Lake installed locally, TLA+ models and Lean proofs serve as precise, machine-checkable documentation of invariants. The abstract model in `ParallelCoordination.lean` clearly defines what "lock exclusivity" and "dependency safety" mean.

- **Feasibility thresholds need tuning**: The `SEQUENTIAL_THRESHOLD = 0.5` for determining when features must run sequentially vs. partially parallel is a policy knob. Starting conservative (50% overlap → sequential) is safer; teams can relax it as they gain confidence in the conflict resolution mechanisms.
