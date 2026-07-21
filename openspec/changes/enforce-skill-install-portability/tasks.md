# Tasks: enforce-skill-install-portability

The P0–P3 headings and scope below preserve the portability audit accepted by the user. Test tasks precede the behavior they prove.

## P0 — Establish and restore the runtime contract

- [x] 0.1 (M) Add an installer portability regression suite that rsyncs skills into a temporary consumer repository with no `agent-coordinator/` or canonical `skills/` tree, then imports or invokes every registered shipped entry point.
  **Spec scenarios**: skill-workflow "Complete install runs without source checkout", "Known regression entry points are portable"
  **Design decisions**: D1, D5
  **Dependencies**: None
  **Files**: `skills/tests/install_sh/test_consumer_portability.py`

- [x] 0.2 (S) Add a failing regression proving installed `discover_prs.py --help` and classifier imports work without coordinator source.
  **Spec scenarios**: merge-pull-requests "Import discovery without coordinator checkout"; coordinator-kanban-viz "Installed skill runs without coordinator source"
  **Design decisions**: D2, D5
  **Dependencies**: 0.1
  **Files**: `skills/tests/install_sh/test_consumer_portability.py`, `skills/tests/merge-pull-requests/test_classify.py`

- [x] 0.3 (S) Move or vendor PR classification into the shipped boundary and make both `discover_prs.py` and coordinator code depend on the portable canonical module.
  **Spec scenarios**: coordinator-kanban-viz "Coordinator and installed skill share classification behavior"; merge-pull-requests "Discover open PRs"
  **Design decisions**: D2
  **Dependencies**: 0.2
  **Files**: `skills/shared/github_classifier.py`, `skills/merge-pull-requests/scripts/discover_prs.py`, `agent-coordinator/src/github_classifier.py`, related classifier tests

- [x] 0.4 (S) Add a failing regression for installed `parallel-infrastructure/result_validator.py`, then repair its import of the shipped `validate-packages/scripts/validate_work_result.py`.
  **Spec scenarios**: skill-workflow "Known regression entry points are portable"
  **Design decisions**: D3, D5
  **Dependencies**: 0.1
  **Files**: `skills/tests/install_sh/test_consumer_portability.py`, `skills/parallel-infrastructure/scripts/result_validator.py`

- [x] 0.5 (S) Add a failing regression for installed `autopilot/scripts/smoke_provider_dispatch.py`, then remove its coordinator-source import in favor of the public bridge or a shipped helper.
  **Spec scenarios**: skill-workflow "Coordinator internals are referenced directly", "Known regression entry points are portable"
  **Design decisions**: D4, D5
  **Dependencies**: 0.1
  **Files**: `skills/tests/install_sh/test_consumer_portability.py`, `skills/autopilot/scripts/smoke_provider_dispatch.py`

- [x] 0.6 (M) Replace direct `src.agents_config` snippets in `plan-feature`, `implement-feature`, `iterate-on-plan`, `iterate-on-implementation`, and `fix-scrub` with portable public-interface or deterministic fallback instructions.
  **Spec scenarios**: skill-workflow "Coordinator internals are referenced directly", "Optional coordinator integration is unavailable"
  **Design decisions**: D4
  **Dependencies**: 0.1
  **Files**: `skills/{plan-feature,implement-feature,iterate-on-plan,iterate-on-implementation,fix-scrub}/SKILL.md`

- [x] 0.7 (S) Repair the broader clean-consumer import probe failures in `prototype-feature/collect_outcomes.py` and `validate-flows/validate_flows.py` by resolving co-installed sibling modules from the installed skills root.
  **Spec scenarios**: skill-workflow "Known regression entry points are portable", "Claude and agents mirrors resolve the same sibling"
  **Design decisions**: D3, D5
  **Dependencies**: 0.1
  **Files**: `skills/prototype-feature/scripts/collect_outcomes.py`, `skills/validate-flows/scripts/validate_flows.py`, `skills/tests/install_sh/test_consumer_portability.py`

- [x] 0.C **Checkpoint: run P0 consumer tests, classifier suites, review the diff, and verify scope.**
  **Dependencies**: 0.3, 0.4, 0.5, 0.6, 0.7
  **Files**: no writes

## P1 — Remove runtime dependencies on the source-repository layout

- [x] 1.1 (M) Add portability tests for `DockerStackEnvironment`, then decouple port allocation and default compose discovery from `agent-coordinator/.venv`, `src.port_allocator`, and the coordinator compose file.
  **Spec scenarios**: skill-workflow "Explicit consumer configuration is provided", "Source-repository fallback is absent"
  **Design decisions**: D3, D4
  **Dependencies**: 0.C
  **Files**: `skills/validate-feature/scripts/environments/docker_stack.py`, `skills/validate-feature/scripts/{phase_deploy.py,stack_launcher.py}`, `skills/tests/validate-feature/`

- [x] 1.2 (M) Add installed-layout Langfuse hook tests, then vendor or ship the Stop-hook runtime and make `install_stop_hook.py` record a command that exists in `.claude/skills` consumers.
  **Spec scenarios**: skill-workflow "Claude and agents mirrors resolve the same sibling", "Distributable skill has complete closure"
  **Design decisions**: D1, D3
  **Dependencies**: 0.C
  **Files**: `skills/langfuse/scripts/{run_stop_hook.sh,install_stop_hook.py}`, `skills/langfuse/references/stop-hook.md`, `skills/tests/langfuse/`

- [x] 1.3 (S) Add a consumer-worktree regression, then make `worktree.py` locate its co-installed bootstrap script rather than `<repo>/skills/worktree/...`.
  **Spec scenarios**: worktree "Consumer worktree is bootstrapped", "Installed bootstrap script is absent"
  **Design decisions**: D3
  **Dependencies**: 0.C
  **Files**: `skills/worktree/scripts/worktree.py`, `skills/tests/worktree/`

- [x] 1.4 (S) Make session-log coordinator-bridge discovery recognize canonical, `.claude/skills`, and `.agents/skills` layouts.
  **Spec scenarios**: skill-workflow "Claude and agents mirrors resolve the same sibling", "Optional coordinator integration is unavailable"
  **Design decisions**: D3, D4
  **Dependencies**: 0.C
  **Files**: `skills/session-log/scripts/phase_record.py`, `skills/tests/session-log/`

- [x] 1.5 (S) Make `review-artifacts` locate the installed worktree helper through the installed skills root.
  **Spec scenarios**: skill-workflow "Claude and agents mirrors resolve the same sibling"
  **Design decisions**: D3
  **Dependencies**: 0.C
  **Files**: `skills/review-artifacts/scripts/open_artifacts.py`, `skills/tests/review-artifacts/`

- [x] 1.6 (S) Remove or replace the best-effort `src.profile_loader` import from `print_coordinator_env.py` while preserving non-blocking hook behavior.
  **Spec scenarios**: skill-workflow "Coordinator internals are referenced directly", "Optional coordinator integration is unavailable"
  **Design decisions**: D4
  **Dependencies**: 0.C
  **Files**: `skills/session-bootstrap/scripts/hooks/print_coordinator_env.py`, `skills/tests/session-bootstrap/`

- [x] 1.7 (S) Make Bao secrets and agents configuration defaults explicit and portable instead of assuming `<repo>/agent-coordinator/`.
  **Spec scenarios**: skill-workflow "Explicit consumer configuration is provided", "Source-repository fallback is absent"
  **Design decisions**: D4, D6
  **Dependencies**: 0.C
  **Files**: `skills/bao-vault/scripts/bao_seed.py`, `skills/bao-vault/SKILL.md`, `skills/tests/bao-vault/`

- [x] 1.8 (S) Normalize vendor configuration discovery so `AGENTS_YAML` and public HTTP/MCP configuration are primary and local coordinator files are optional compatibility fallbacks.
  **Spec scenarios**: skill-workflow "Explicit consumer configuration is provided", "Source-repository fallback is absent"
  **Design decisions**: D4
  **Dependencies**: 0.C
  **Files**: `skills/parallel-infrastructure/scripts/{review_dispatcher.py,vendor_health.py}`, `skills/vendor-status/SKILL.md`, related tests

- [x] 1.C **Checkpoint: run affected hook, worktree, validation, Bao, vendor, and session-log tests; review installed-path diagnostics.**
  **Dependencies**: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8
  **Files**: no writes

## P2 — Make skill instructions portable

- [x] 2.1 (S) Introduce one documented installed-skill path-resolution convention based on the loaded `SKILL.md`/script directory.
  **Spec scenarios**: skill-workflow "Claude and agents mirrors resolve the same sibling", "Runtime command uses a canonical source path"
  **Design decisions**: D3
  **Dependencies**: 1.C
  **Files**: `docs/guides/skills.md`, `skills/references/skill-path-resolution.md`

- [x] 2.2 (L) Audit and normalize the 26 `SKILL.md` files containing hard-coded `skills/<name>/scripts` or `skills/.venv` runtime commands.
  **Spec scenarios**: skill-workflow "Runtime command uses a canonical source path", "Distributable skill has complete closure"
  **Design decisions**: D3, D6
  **Dependencies**: 2.1
  **Files**: the 26 audited `skills/*/SKILL.md` files containing canonical runtime paths

- [x] 2.3 (M) Rewrite `refresh-architecture` to invoke shipped scripts directly and accept consumer source layouts instead of requiring this repository's Makefile, coordinator venv, and source directories.
  **Spec scenarios**: skill-workflow "Explicit consumer configuration is provided", "Source-repository fallback is absent"
  **Design decisions**: D3, D6
  **Dependencies**: 2.1
  **Files**: `skills/refresh-architecture/SKILL.md`, `skills/refresh-architecture/scripts/refresh_architecture.sh`, related tests

- [x] 2.4 (M) Make `setup-coordinator` operate through configurable external paths and public APIs, or mark it explicitly non-distributable and omit it from consumer installs.
  **Spec scenarios**: skill-workflow "Skill is intentionally repository-scoped", "Explicit consumer configuration is provided"
  **Design decisions**: D4, D6
  **Dependencies**: 2.1
  **Files**: `skills/setup-coordinator/SKILL.md`, `skills/install.sh`, installer tests

- [x] 2.5 (S) Repair the nine Markdown links escaping the shipped tree across `autopilot`, `documentation-and-adrs`, and `expedite` by shipping or relocating their required reference content.
  **Spec scenarios**: skill-workflow "Missing runtime dependency blocks installation validation", "Distributable skill has complete closure"
  **Design decisions**: D1, D3
  **Dependencies**: 2.1
  **Files**: `skills/{autopilot,documentation-and-adrs,expedite}/SKILL.md`, installed reference content

- [x] 2.6 (M) Review bare `scripts/...` commands in the twelve identified skills and explicitly classify or rewrite each path as skill-relative or consumer-project-relative.
  **Spec scenarios**: skill-workflow "Runtime command uses a canonical source path", "Distributable skill has complete closure"
  **Design decisions**: D3
  **Dependencies**: 2.1
  **Files**: the twelve audited skill instructions containing bare `scripts/...` commands

- [x] 2.C **Checkpoint: run the full static reference inventory and verify no unexplained canonical-path commands or escaping links remain.**
  **Dependencies**: 2.2, 2.3, 2.4, 2.5, 2.6
  **Files**: no writes

## P3 — Prevent recurrence

- [x] 3.1 (M) Expand dependency-direction linting to detect coordinator `sys.path` injection, subprocess `src.*` imports, fixed repo-depth assumptions, deleted repo-root scripts, and installed hooks targeting canonical `skills/`.
  **Spec scenarios**: skill-workflow "Coordinator internals are referenced directly", "Missing runtime dependency blocks installation validation"
  **Design decisions**: D5
  **Dependencies**: 2.C
  **Files**: `skills/validate-feature/scripts/linters/dependency_direction.py`, `skills/tests/validate-feature/`

- [x] 3.2 (S) Run dependency-direction and portability linting over the complete install payload in CI rather than only supplied changed files.
  **Spec scenarios**: skill-workflow "A future unchanged-file violation exists"
  **Design decisions**: D5
  **Dependencies**: 3.1
  **Files**: CI/quality-gate configuration and portability test runner

- [x] 3.3 (M) Add install-manifest validation requiring every runtime file reference to resolve inside a synced skill, `shared/`, `references/`, installed OpenSpec assets, or a declared prerequisite.
  **Spec scenarios**: skill-workflow "Distributable skill has complete closure", "Missing runtime dependency blocks installation validation"
  **Design decisions**: D1, D5, D6
  **Dependencies**: 3.1
  **Files**: `skills/install.sh`, `skills/tests/install_sh/`, install-manifest validator

- [x] 3.4 (S) Document and enforce consumer-layout smoke tests for changes that move shared behavior across coordinator and skills boundaries.
  **Spec scenarios**: skill-workflow "Known regression entry points are portable", "A future unchanged-file violation exists"
  **Design decisions**: D2, D5
  **Dependencies**: 3.2, 3.3
  **Files**: `docs/guides/skills.md`, `docs/cross-repo-setup.md`, portability tests

- [x] 3.C **Checkpoint: run the installed-consumer gate against both `.claude` and `.agents` destinations and inspect all diagnostics.**
  **Dependencies**: 3.4
  **Files**: no writes

## Final validation and delivery

- [x] 4.1 (S) Run `openspec validate enforce-skill-install-portability --strict`, work-package validation, affected unit suites, full skill tests, ruff, mypy, and shell syntax checks.
  **Dependencies**: 3.C
  **Files**: `openspec/changes/enforce-skill-install-portability/validation-report.md`

- [x] 4.2 (S) Run `skills/install.sh` from canonical `skills/`, verify both generated mirrors, and re-run the consumer portability suite on the installed output.
  **Dependencies**: 4.1
  **Files**: generated mirrors only through `skills/install.sh`

- [ ] 4.3 (S) Complete implementation review, write validation/session artifacts, commit task checkboxes with their implementation, push the feature branch, and open the autopilot PR.
  **Dependencies**: 4.2
  **Files**: `openspec/changes/enforce-skill-install-portability/`
