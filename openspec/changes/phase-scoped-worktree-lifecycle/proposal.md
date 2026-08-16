# Change: phase-scoped-worktree-lifecycle

## Why

Managed worktrees currently use a permanent `pinned` Boolean for both garbage-collection retention and active-writer protection. Standalone planning can therefore finish, push its artifacts, and still block merge triage indefinitely, while later implementation, iteration, validation, interrupted runs, and proposal-only merges lack a symmetric, crash-tolerant lifecycle.

The durable handoff should be the pushed branch and pull request, not an idle local checkout. Standalone phases need disposable worktrees, autopilot needs one explicitly owned continuous lease through validation, and merge triage needs to distinguish proposal delivery from completed implementation before it validates or archives an OpenSpec change.

## What Changes

- **BREAKING**: replace the registry's overloaded `pinned` activity semantics with schema-v2 retention plus owner-scoped, expiring activity leases. Legacy `pinned=true` remains readable as retention, while only a fresh legacy heartbeat is transitional evidence of activity.
- Serialize registry updates and add controller-bound acquire/resume/assert/renew/release, owner/session release, status, recovery-adoption, and inspection/migration-report operations. Persist each entry's exact durability target, key process evidence by entry plus lease, and require stale-process proof before takeover. Use a 30-minute default lease renewed every 5 minutes; recovery quarantine prevents silent adoption of legacy or preserved work, and expiry never deletes a dirty worktree.
- Reconcile automatic checkout creation through generation-fenced setup reservations, bind durability to remote name plus credential-safe URL digest plus exact tracking ref, and retain append-only force-adoption audit after quarantine or entry removal.
- Make standalone planning create `openspec/<change-id>--proposal`, open a proposal-only PR after strict validation, then finalize through live-lease teardown or atomic quarantine-plus-clear.
- Give standalone implementation, plan iteration, implementation iteration, and validation independent phase worktrees and leases across sequential, local-parallel, and coordinated tiers. Each phase pushes durable output before exact-triple-and-generation-checked teardown.
- Persist one `autopilot:<run-id>` owner across PLAN through SUBMIT_PR, keep resumable run state outside disposable worktrees, let only its controller renew while nested phases assert ownership, and recreate a removed checkout only from a verified durable checkpoint before resuming.
- Release leases owned by the terminating session through best-effort session hooks without requiring coordinator connectivity and without releasing another run's lease.
- Add a deterministic delivery-stage classifier using changed files plus proposal state on the PR base: `proposal`, `implementation`, `mixed`, or `ambiguous`. Corroborate it with an `OpenSpec-Delivery` PR-body marker; conflicting or incomplete evidence fails safe as ambiguous.
- Keep OpenSpec origin, delivery stage, GitHub author, and author vendor as independent fields. Claude-authored OpenSpec PRs receive configured Codex, Grok, and Pi review with stage-appropriate planning/code context and explicit unavailable-vendor reporting.
- Route proposal PRs through strict OpenSpec validation at the PR head and once-per-pass main-context convergence, but skip implementation-only validation, holdout/rework gates, cleanup, and archival. Implementation and mixed PRs retain full validation and archival; only the latest ambiguous classification permits an operator override, bound to live SHAs/ruleset and an RFC-8785 canonical evidence digest.
- Update coordinator sync-point and worktree projections so retained-idle worktrees remain GC-protected without appearing active, and carry delivery-stage evidence through merge-plan orchestration.
- Check in and test a complete mutating-workflow/registry-consumer inventory so package, prototype, roadmap, cleanup, update, and sync-point entrypoints cannot retain stale pin-or-heartbeat activity semantics.
- Gate overlapping implementation packages through an executable authoritative-PR preflight whose shared-feature-worktree completion barrier records the exact dependent base before dispatch, and scope formatting checks to changed Python files recorded from that reconciled baseline.
- Regenerate runtime skill mirrors from canonical `skills/` and update operator recovery, lifecycle, and merge documentation.

Affected architecture layers: Execution (worktrees and hooks), Coordination (leases, guards, and coordinator projections), Trust (independent vendor review and validation routing), and Governance (OpenSpec delivery-stage and archival rules).

## Approaches Considered

### Approach 1: Repository-owned lifecycle contract (Recommended)

Extend the existing worktree registry into a locked schema-v2 state machine. Keep lifecycle authority local to the repository, pass explicit owner/mode context between workflow phases, and add a pure delivery-stage classifier beside the existing portable GitHub origin classifier.

**Pros:**

- Preserves offline and coordinator-degraded operation.
- Builds on existing worktree, active-agent, OpenSpec, and merge workflow boundaries.
- Supports deterministic clock-injected tests and backward-compatible registry reads.
- Keeps author identity, PR origin, delivery stage, retention, and activity as separate concepts.
- Makes crash recovery operator-visible without making deletion a side effect of expiry.

**Cons:**

- Touches several canonical skills plus coordinator/UI compatibility consumers.
- Requires careful file locking and schema migration to prevent concurrent lost updates.
- Markdown workflows still need executable finalization helpers and session-hook backstops.

**Effort:** L

### Approach 2: Sidecar leases and checked-in delivery manifest

Leave the v1 registry mostly intact, store leases in separate owner-named files, and require a checked-in delivery-stage manifest to drive merge behavior.

**Pros:**

- Reduces direct migration of the existing registry shape.
- Makes individual leases easy to inspect and remove.
- Gives PR classification an explicit durable declaration.

**Cons:**

- Splits lifecycle truth across registry entries and sidecar files.
- Requires atomic coordination across multiple files and creates orphan cleanup problems.
- A manifest can disagree with the actual diff/base state, so deterministic classification is still required.
- Leaves more legacy consumers interpreting `pinned` inconsistently.

**Effort:** L

### Approach 3: Coordinator-authoritative leases and merge metadata

Move activity ownership and delivery-stage decisions into the coordinator. Local workflows acquire remote leases and merge triage consumes coordinator records as authoritative state.

**Pros:**

- Centralizes observability and ownership arbitration.
- Avoids local registry write contention for connected agents.
- Can integrate naturally with coordinator queues and dashboards.

**Cons:**

- Breaks or complicates offline, headless, and degraded operation.
- Makes local sync-point safety depend on network availability and remote state freshness.
- Expands coordinator coupling and recovery scope beyond the triggering lifecycle problem.
- Still needs a local fallback, producing two authorities instead of one.

**Effort:** L

### Recommended

Choose Approach 1. It directly separates activity from retention without introducing a second source of truth, preserves the repository's local-first execution model, and allows the PR classifier to treat metadata as corroboration rather than trusting a declaration that may contradict the diff. Its broader touch surface is justified because current coordinator/UI and merge-plan consumers otherwise keep incompatible `pinned` or delivery-stage semantics.

### Selected Approach

The user selected Approach 1, Repository-owned lifecycle contract, with the
recommended defaults: registry file locking; a 30-minute activity lease renewed
every 5 minutes; changed-file plus base-state PR classification corroborated by
an `OpenSpec-Delivery` PR-body marker; and inclusion of coordinator/UI consumers
and merge-plan orchestration integration.

## Impact

### Affected specification capabilities

- `worktree` -> `specs/worktree/spec.md`: schema-v2 registry, leases, retention, expiry, inspection, compatibility, and cloud behavior.
- `skill-workflow` -> `specs/skill-workflow/spec.md`: standalone proposal, phase lifecycle, continuous autopilot ownership, hooks, and generated-mirror requirements.
- `merge-pull-requests` -> `specs/merge-pull-requests/spec.md`: stage/author classification, vendor routing, validation matrix, ambiguity, cleanup, and convergence.
- `coordinator-kanban-viz` -> `specs/coordinator-kanban-viz/spec.md`: active-versus-retained worktree projection and status fields.

### Major implementation areas

- `skills/worktree/scripts/worktree.py`, `skills/shared/active_agents.py`, and worktree tests.
- Canonical lifecycle workflow definitions under `skills/{plan-feature,implement-feature,iterate-on-plan,iterate-on-implementation,validate-feature,autopilot}/` plus autopilot orchestration code.
- Session-end/stop hooks under `skills/session-bootstrap/` and their coordinator-installed compatibility entry points.
- `skills/shared/github_classifier.py` only where proposal-branch change-ID parsing must remain backward compatible; delivery-stage logic lives in merge workflow code.
- `skills/merge-pull-requests/` discovery, vendor-review, validation, merge-plan, and post-merge cleanup paths.
- `agent-coordinator/src/{sync_points.py,worktrees_view.py}` and matching API/UI tests so local and coordinator activity semantics agree.
- `skills/shared/{worktree_lifecycle.py,phase_lifecycle.py}` plus the coordinator runtime image so CLI, installed-skill, source, and container consumers share one interpreter.
- Canonical guides and generated runtime mirrors via `skills/install.sh`.

### Coordination and compatibility

- Block `wp-pr-delivery` dispatch until active change `add-merge-plan-orchestration` is merged/rebased; extend its file-tier durable plan in place and leave its deferred coordinator system-of-record deferred.
- Block `wp-phase-lifecycle` dispatch until active change `validate-feature-findings-gate` is merged/rebased; wrap its selected validation worktree rather than layering a duplicate scratch lifecycle.
- Preserve isolation posture, branch override, prototype retention, main-context convergence, dirty-worktree safety, and existing implementation/mixed PR behavior.

### Rollback

The schema-v2 reader continues accepting v1 entries and `pin`/`unpin` remain retention aliases during migration. Rollback must retain the dual reader/v2 writer while higher-level workflow routing is disabled; a pre-v2 reader cannot safely interpret the disjoint shape. Proposal/mixed uncertainty defaults to ambiguous rather than archival, and no rollback path force-deletes dirty or non-durable worktrees.
