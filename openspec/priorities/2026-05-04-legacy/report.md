# Proposal Prioritization Report

**Date**: 2026-05-04 10:20:27 EDT
**Analyzed Range**: `HEAD~50..HEAD`
**OpenSpec Proposals Analyzed**: 1 active change
**Coordinator Issues Analyzed**: 8 open issues; 8 ready; 0 blocked

## Executive Summary

Only one unfinished OpenSpec proposal is active: `harness-engineering-features`, still draft with 0/21 tasks complete. It is valuable, but broad: seven separate harness capabilities spanning coordinator services, validation, review loops, docs, memory conventions, and two new skills.

The coordinator issue tracker has the stronger next-build signal. Two open CI/tooling issues are currently taxing every PR and cleanup flow:

1. `Pip CVE-2026-3219 blocks every PR via dependency-audit jobs` (priority 3 bug)
2. `Sync deferred OpenSpec deltas from cloud-db-source-of-truth archive` (priority 3 task)

Top recommendation: fix the pip-audit CI blocker first. It is ready, small, high-leverage, and directly improves every subsequent feature merge.

## Priority Order

### 1. Coordinator Issue: Pip CVE-2026-3219 blocks dependency-audit jobs

- **Issue ID**: `a6a2f524-6cda-4343-ae39-58ad8ec4d04a`
- **Type / Priority**: bug / P3
- **Status**: ready; no dependencies
- **Relevance**: High. `.github/workflows/security.yml` still installs unpinned `pip-audit` and runs `uv run pip-audit --desc on`; no `CVE-2026-3219` ignore or pip pin is present.
- **Recommendation**: Build next.
- **Next Step**: create a focused OpenSpec change or quick fix for the security workflow. Prefer an explicit, documented `pip-audit` mitigation so dependency audit becomes useful again.

### 2. Coordinator Issue: Sync deferred OpenSpec deltas from cloud-db-source-of-truth archive

- **Issue ID**: `17654fc5-6d42-4cd2-b046-f28f13e83aa9`
- **Type / Priority**: task / P3
- **Status**: ready; no dependencies
- **Relevance**: High. This is spec/source-of-truth debt: archived deltas are not fully reflected under `openspec/specs/`, including net-new `knowledge-graph` and `mcp-http-client` specs.
- **Recommendation**: Do immediately after the CI blocker, or in parallel if a second agent is available.
- **Next Step**: `/openspec-sync-specs` against the archived change, then validate specs.

### 3. Coordinator Issue: Verify pg_cron audit_log retention in Railway production

- **Issue ID**: `b73d6472-7ed0-4b4e-b836-3e25e92ec1d0`
- **Type / Priority**: task / P3
- **Status**: ready; no dependencies
- **Relevance**: Medium-high, but operational. It needs Railway production access and evidence capture rather than much code.
- **Recommendation**: Schedule as an ops verification task, not the next engineering build unless production audit retention is urgent.

### 4. Coordinator Issue: cloud-db-source-of-truth open findings F5/F6/F7/F8/F9

- **Issue ID**: `f46421dc-f7fe-4a1b-89a5-5aa76c898157`
- **Type / Priority**: task / P4
- **Status**: ready; no dependencies
- **Relevance**: Mixed. It contains multiple independent findings, including API response correctness, enum export/import correctness, validation smoke-test portability, pg_cron verification, and docs cleanup.
- **Recommendation**: Split before implementation. The enum export/import bug and graph episode ID API bug are the most build-like subitems.

### 5. OpenSpec Proposal: harness-engineering-features

- **Change ID**: `harness-engineering-features`
- **Status**: Draft; 0/21 tasks complete
- **Relevance**: Still relevant. `CLAUDE.md` is 142 lines, `skills/improve-harness/` does not exist, and `skills/agent-metrics/` does not exist.
- **Readiness**: Partially ready but too broad for one implementation pass.
- **Conflicts / Drift**: Recent commits touched `skills/autopilot`, `skills/parallel-infrastructure`, `skills/merge-pull-requests`, `skills/validate-feature`, `agent-coordinator/src/coordination_api.py`, and `agent-coordinator/src/agents_config.py`. That overlaps several harness work packages and means the plan should be refreshed before implementation.
- **Recommendation**: Do not implement as one feature yet. Decompose into smaller OpenSpec changes; start with `Mechanical Architecture Enforcement` or `Progressive Context Architecture` after CI/spec hygiene is fixed.
- **Next Step**: `/plan-roadmap openspec/changes/harness-engineering-features/proposal.md`

### 6. Coordinator Issue: Register coordination-bridge capability spec

- **Issue ID**: `8e8ff8dd-95c8-41a9-9463-3cd43240647f`
- **Type / Priority**: bug / P5
- **Status**: ready; no dependencies
- **Relevance**: Needs verification, likely partly addressed. `openspec/specs/coordination-bridge/spec.md` now exists, so the remaining work is to run the decision-index check and close or update the issue.
- **Recommendation**: Verify and close if CI is green.

### 7. Coordinator Issue: Add mypy/ruff excludes for OpenSpec archive paths

- **Issue ID**: `3ec0d23c-7df2-4366-82c2-19ba016e0468`
- **Type / Priority**: task / P5
- **Status**: ready; no dependencies
- **Relevance**: Workflow hygiene. This repo currently has `agent-coordinator/pyproject.toml` and `skills/pyproject.toml`, but no root `.pre-commit-config.yaml`; the issue may need adjustment before implementation.
- **Recommendation**: Triage after higher-priority CI/spec issues.

### 8. Coordinator Issue: SonarCloud Code Analysis fails on PR #128

- **Issue ID**: `790a9aad-ec6b-46dc-918c-a3b9dd9eb2a1`
- **Type / Priority**: task / P5
- **Status**: ready; no dependencies
- **Relevance**: Unknown until SonarCloud details are inspected.
- **Recommendation**: Investigate, but not before pip-audit and spec sync.

### 9. Coordinator Issue: merge_pr.py force approval for solo OpenSpec workflows

- **Issue ID**: `53939d4a-2b10-497b-9835-581fbe060b05`
- **Type / Priority**: feature / P6
- **Status**: ready; no dependencies
- **Relevance**: Partly addressed. `skills/merge-pull-requests/scripts/merge_pr.py` now has `--force-approval` and tests, but `skills/cleanup-feature/SKILL.md` still documents only `--force` in the explicit override path.
- **Recommendation**: Update/close after confirming whether `--force-approval` satisfies the issue acceptance criteria.

## Suggested Workstreams

### Start Now

- Fix `Pip CVE-2026-3219 blocks every PR via dependency-audit jobs`.
- Sync deferred OpenSpec deltas from `cloud-db-source-of-truth`.

### Verify / Close

- `Register coordination-bridge capability spec` looks likely addressed by `openspec/specs/coordination-bridge/spec.md`.
- `merge_pr.py: add --operator-approved flag` looks partly addressed by `--force-approval`; update docs or close with rationale.

### Plan Next Feature Work

- Decompose `harness-engineering-features` with `/plan-roadmap`.
- First decomposed feature candidate: architecture validation linters, because it improves every future implementation and aligns with the coordinator issue pattern around CI gates and validation signal quality.

## Final Recommendation

Build the pip-audit CI unblocker next. After that, sync OpenSpec spec drift. Only then start new harness feature work, and start by decomposing `harness-engineering-features` rather than implementing it as a single large change.
