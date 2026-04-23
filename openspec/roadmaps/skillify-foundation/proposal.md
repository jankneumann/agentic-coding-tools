# Skillify Foundation — Roadmap Proposal

## Summary

Adopt the **skillify pattern** (every reproducible failure becomes a tested skill) inside `agentic-coding-tools` while respecting the existing OpenSpec / multi-agent / worktree workflow. The pattern composes into two changes that must land in order:

1. **`add-update-skills`** — closes the canonical-skills → runtime-dirs sync gap and establishes the `CLAUDE.md ≡ AGENTS.md` invariant. This is prerequisite plumbing: without a reliable sync+commit+push loop, any skill produced by the next change cannot reach the runtime directories Claude Code and Codex actually read from.
2. **`add-skillify-and-resolver-audit`** — adds the `/skillify` skill that promotes a failure into a SKILL.md + scripts + tests + OpenSpec change, plus a resolver audit that detects dark skills (shipped but unreachable), overlapping triggers, and missing scripts.

The roadmap connects them with an explicit dependency — `ri-02 depends_on [ri-01]` — so `autopilot-roadmap` (or a manual operator) executes them in the safe order.

## Why This Is a Roadmap, Not a Single Change

The two changes have different blast radii and different reviewers:

- **Change A** touches the runtime-sync layer (`install.sh`, `.claude/`, `.agents/`, pre-commit hooks). Failures here break every agent's ability to discover skills. It needs careful review and should land cleanly before anything depends on it.
- **Change B** introduces a new operator workflow (`/skillify`) and a new validation phase (`/validate-feature --phase resolver`). Failures here only affect the new mechanism, not existing skill discovery.

Bundling them risks a long-running PR where a hold-up on B blocks A's value (sync hygiene), and where a sync regression in A taints the review of B's mechanism.

## Capabilities

### Capability 1 — Skill Runtime Sync (Change A)

**What it delivers:**
- A `/update-skills` skill that runs `install.sh`, regenerates `AGENTS.md` from `CLAUDE.md`, commits regenerated files (skipping empty commits), and pushes with rebase-on-conflict retry.
- A `sync-agents-md` script (Python) that copies `CLAUDE.md` → `AGENTS.md` byte-for-byte and exits non-zero on drift (for use as a pre-commit check).
- An opt-in SessionStart hook that runs `git pull --rebase --autostash` on the current branch when `AGENTIC_AUTO_PULL=1`, gated to no-op on dirty trees and silent on network failure.

**Why it matters:** The current workflow requires manual `bash skills/install.sh` after every skill edit. Edits to canonical `skills/` don't propagate to `.claude/skills/` or `.agents/skills/` automatically, and the runtime copies aren't committed automatically. This means agent-discovery state can silently lag the source-of-truth state. Codex specifically reads from `.agents/skills/` and an empty `AGENTS.md` (which is the current state) means Codex has no project context.

### Capability 2 — Skillify Promotion + Resolver Audit (Change B)

**What it delivers:**
- A `/skillify` skill accepting `--target-repo {coding-tools,content-analyzer,assistant}` (default: infer from `git remote get-url origin`). It scaffolds a skill directory (SKILL.md + `scripts/` + `tests/`) and creates a draft OpenSpec change that goes through the existing `plan-feature` → `implement-feature` gates.
- A resolver audit (`skills/resolver-audit/scripts/resolver_audit.py`) that walks every `skills/*/SKILL.md`, parses the `triggers:` frontmatter, and reports: (a) skills with no triggers (dark skills), (b) skills whose triggers overlap with another skill's triggers (ambiguous routing), (c) `scripts/` paths referenced in SKILL.md that don't exist (broken references).
- A new `/validate-feature --phase resolver` selector that runs the audit and fails CI if any of the three categories has findings.

**Why it matters:** At ~45 skills and growing, the article's observation that "15% of capabilities were dark" at 40+ skills is a near-term risk. Adding an audit before that risk materializes is much cheaper than discovering it in production. The `/skillify` skill itself converts the team's existing failure-postmortem habit into a structured artifact-producing flow.

## Constraints

- **Single repo for this initiative**: both changes target `agentic-coding-tools` only. Cross-repo rollout to `agentic-content-analyzer` and `agentic-assistant` is explicitly deferred to a future roadmap.
- **No bypass of existing gates**: `/skillify` produces an OpenSpec change (it does not directly write a SKILL.md without going through `plan-feature` and `implement-feature`). This preserves the team's review discipline.
- **Branch mandate**: in cloud-harness sessions, the operator-mandated branch (e.g. `claude/implement-skillify-pattern-BK8JO`) must be respected by the new sync loop's push logic.
- **No auto-pull by default**: the SessionStart `git pull` hook is opt-in via `AGENTIC_AUTO_PULL=1`. Auto-pull on a dirty branch can corrupt in-progress work.

## Phases

### Phase 1 — Sync Infrastructure (Change A)
Land `add-update-skills` first. Verify the `CLAUDE.md ≡ AGENTS.md` invariant holds across at least one merge cycle. Verify Codex picks up project context from the now-populated `AGENTS.md`.

### Phase 2 — Promotion Mechanism (Change B)
Land `add-skillify-and-resolver-audit`. Run the resolver audit against the current `skills/` tree to surface any existing dark skills or trigger overlaps; fix findings as a separate housekeeping change if material.

## Non-Goals

- LLM-as-judge evals for skills (deferred — depends on `gen-eval` framework integration, separate roadmap).
- Cross-repo `/skillify` dispatch (v1 requires running from inside the target repo; cross-repo cd is a later enhancement).
- Brain-filing rules from Garry Tan's checklist (only relevant to `agentic-content-analyzer`, not this repo).
- Replacing `install.sh` itself — the new skill calls into it, doesn't replace it.

## Acceptance Outcomes

- After both changes land, `bash skills/install.sh` is no longer required as a manual step after a skill edit; `/update-skills` handles it.
- `AGENTS.md` exists, is byte-identical to `CLAUDE.md`, and is enforced by a pre-commit check.
- `/validate-feature --phase resolver` runs in CI on every PR and blocks merges that introduce dark skills or trigger overlaps.
- The team can convert a failure into a permanent structural fix in one command (`/skillify <name>`) that produces a reviewable OpenSpec change.
