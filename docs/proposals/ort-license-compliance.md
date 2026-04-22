# ORT + SCANOSS License Compliance Integration

## Context and Goals

The project is MIT-licensed. Two Python sub-projects (`agent-coordinator/`, `skills/`) use uv for dependency management. Code-generation agents operate in worktrees and commit to feature branches. Today there is no defense against (a) a model emitting verbatim copyrighted snippets, or (b) a new dependency with an incompatible license entering `pyproject.toml`.

This proposal layers license-compliance checks across the generation pipeline using **ORT** for supply-chain/manifest scanning and **SCANOSS** for snippet matching.

## Guiding Principles

- Everything reachable from this repo is harness-level. The model's inference is outside our control; Bedrock `ApplyGuardrail` would be the only true inline seam and is out of scope here.
- Fail open during warm-up. First rollout is warn-only to avoid alert fatigue.
- Cache-backed ORT. Cold scans take hours; a Postgres scan-result cache (reusing the coordinator's Postgres instance) drops incremental runs to minutes.
- ORT for supply chain, SCANOSS for snippets. Different tools for different attack surfaces.

## Phase 0 — Pre-work and CI Warm-up

### Capability: SPDX License Identifier Headers

Add `# SPDX-License-Identifier: MIT` headers to Python source under `skills/` and `agent-coordinator/src/`. Provide a check gate that fails CI if a new `.py` file is missing the header.

Acceptance outcomes:
- All `.py` files under `skills/` and `agent-coordinator/src/` must carry an SPDX header.
- CI must fail when a new `.py` file is missing the header.

### Capability: uv-to-Requirements Materialization Helper

ORT has no first-class uv analyzer plugin. Provide a helper script that invokes `uv pip compile` (or generates a CycloneDX SBOM) per sub-project and produces an input the ORT Analyzer can consume. Called from both the CI workflow and the local validate-feature phase.

Acceptance outcomes:
- Script must emit `requirements.txt` (or SBOM) for both `agent-coordinator/` and `skills/`.
- Must complete in under 60 seconds on a cached uv workspace.
- Must be invoked by both the CI workflow and the validate-feature `license` phase.

### Capability: Evaluator Rules Overlay

Fork `oss-review-toolkit/ort-config` into a repo-local overlay under `.ort/config/`. Declare project license MIT. DENY on GPL\*, AGPL\*, SSPL\*, BUSL\*, CC-BY-NC\*. WARN on Apache-2.0 (NOTICE obligation), MPL-2.0, LGPL\*. Starts from the OSADL license-compatibility matrix ruleset.

Acceptance outcomes:
- `evaluator.rules.kts` must load without syntax error.
- `license-classifications.yml` must assign OSADL categories.
- A fixture manifest with a seeded GPL dep must produce the expected violation.

### Capability: Postgres Scan Cache Provisioning

Provision a new `ort_scan_cache` schema on the existing coordinator Postgres instance. Configure repo secrets `ORT_DB_URL`, `ORT_DB_USER`, `ORT_DB_PASSWORD` for the `ort-ci-github-action` cache inputs.

Acceptance outcomes:
- Schema must exist on the coordinator Postgres instance and be documented in `docs/openbao-secret-management.md`.
- The second CI run for an unchanged PR must complete in under 10 minutes, proving cache hits work.

### Capability: License-Compliance CI Workflow

Create `.github/workflows/license-compliance.yml` using `oss-review-toolkit/ort-ci-github-action@main`. Runs on `push` to main and on `pull_request`. Uploads SPDX and CycloneDX SBOM artifacts. Depends on the materialization helper, evaluator rules overlay, and Postgres scan cache. Uses `fail-on: violations` with `severeRuleViolationThreshold: WARNING` initially.

Acceptance outcomes:
- Workflow must trigger on every PR targeting main.
- SBOM artifacts must attach to the PR for review.
- First run must produce a baseline `.ort.yml` curations file capturing known-benign findings.
- Workflow must complete in under 15 minutes with a warm cache.

## Phase 1 — Validate-Feature Phase and Regeneration Loop

### Capability: validate-feature License Phase

Add `skills/validate-feature/scripts/phase_license.py` as a sibling to `phase_deploy.py`, `phase_smoke.py`, etc. Wire into `gate_logic.py` under phase key `license`. Consumes the same `evaluator.rules.kts` as the CI workflow. Depends on the uv materialization helper, evaluator rules overlay, and Postgres scan cache.

Acceptance outcomes:
- `validate-feature --phase license` must return a structured pass/fail verdict.
- `/implement-feature` must invoke `--phase spec,evidence,license` by default.
- `/cleanup-feature` must invoke `--phase deploy,smoke,security,e2e,license`.
- CLAUDE.md must document the new phase.

### Capability: License-Violation Regeneration Loop

Normalize ORT Evaluator violations and SCANOSS findings to the existing `review-findings.schema.json` format. Add a `license-violation` finding category with sub-types `snippet` (prompt the agent to rewrite from scratch) and `dependency` (prompt the agent to find an alternative package). Extend `/iterate-on-implementation` to iterate on these findings until clean. Depends on the validate-feature license phase.

Acceptance outcomes:
- A seeded GPL-licensed fixture file must trigger iterate-on-implementation, which must rewrite it, and the license phase must re-run to green.
- A test fixture adding an LGPL dependency must produce a remediation suggestion with an MIT alternative.

## Phase 2 — Per-Turn Stop Hook

### Capability: Stop Hook Snippet Scanner

Add a Claude Code `Stop` hook (and `SubagentStop`) that scans files written during the turn using `scanoss-py scan`. Blocks with non-zero exit when a match crosses a severity threshold. Also runs a manifest-delta ORT Analyzer pass when `pyproject.toml` or `uv.lock` changed. Structured stderr enters the agent's next-turn context so it can self-correct.

Acceptance outcomes:
- Hook must fire on Stop and SubagentStop.
- Hook must complete in under 5 seconds for a 10-file turn using the hosted SCANOSS API.
- A seeded GPL paste in a turn must be blocked; the agent must self-correct on the next turn.
- Hook must be disabled when `SCANOSS_OFFLINE=1` is set.

## Phase 3 — PostToolUse Pre-Emission Hook

### Capability: PostToolUse Write/Edit Guard

Add a `PostToolUse` hook matching Write, Edit, and MultiEdit tool calls. Runs `scanoss-py scan` against the new content with a local bloom-filter cache. Short timeout (2 seconds); hard-block on match. Gated on false-positive tuning from Phase 2.

Acceptance outcomes:
- Hook latency p95 must be under 500 ms with cache warm.
- False-positive rate measured over a one-week warm-up must be below 1% before the hook is enabled as a hard block.
- A configurable allowlist must exist for known-benign short snippets.

## Phase 4 — Hardening and Documentation

### Capability: Switch CI Gate to Strict

After a two-week warm-up and curation pass, flip the CI workflow from `severeRuleViolationThreshold: WARNING` to `ERROR`. Document the resolution path via `.ort.yml` for accepted findings. Depends on the CI workflow and the evaluator rules overlay.

Acceptance outcomes:
- CI must block merges on `ERROR`-severity findings.
- The on-call playbook must document how to add a resolution for an accepted finding.

### Capability: License-Compliance Documentation

Author `docs/license-compliance.md` covering: architecture, ORT-vs-SCANOSS split, conditional Bedrock `ApplyGuardrail` section for the company use case, curation process, on-call playbook. Update CLAUDE.md with the new `license` phase. Add a workflow badge to `README.md`.

Acceptance outcomes:
- `docs/license-compliance.md` must exist and link from CLAUDE.md.
- CLAUDE.md's phase list must include `license`.
- README must reference the license-compliance workflow badge.

## Constraints

- The project must remain MIT-licensed; no deliverable shall introduce a dependency that violates MIT outbound compatibility.
- Deliverables shall not require new infrastructure beyond the existing Postgres instance.
- Interactive code generation must not accrue more than 5 seconds of added latency per turn on the median path.
- Deliverables shall reuse the existing validate-feature phase orchestration rather than introduce a parallel framework.

## Out of Scope

- Bedrock `ApplyGuardrail` integration (belongs to a separate company-use-case roadmap).
- FossID commercial snippet scanner integration.
- Retiring pip-audit from `.github/workflows/security.yml` in favor of ORT's Advisor.
