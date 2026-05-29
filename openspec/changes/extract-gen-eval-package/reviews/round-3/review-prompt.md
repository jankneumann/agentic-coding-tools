# Plan Review Round 3 — extract-gen-eval-package

This is round 3 of multi-vendor plan review. Round 2 surfaced 4 unique blocking findings (2 from Codex, 2 from Gemini — one shared root cause). Commit `233de0b` ("plan(fix): adopt Strategy A (repo-root build context) + 6 PLAN_REVIEW advisories") applied the following fixes:

## What changed in commit 233de0b

### Strategy A — Railway repo-root build context (replaces the Option B wheel prebuild story)

The round-2 critical blocker was that `railway.toml [build] buildCommand` only fires under the Nixpacks builder, NOT under the Dockerfile builder — making Option B's prebuild step silently inert on Railway. Strategy A discards the prebuild story entirely:

- **D8 rewritten**: Docker build context = repo root (`.`), not `agent-coordinator/`. `agent-coordinator/Dockerfile` gets `COPY agent-coordinator/...` and `COPY packages/gen-eval ./packages/gen-eval`. `[tool.uv.sources]` path-dep resolves naturally at build time. **No `--no-sources`, no `UV_FIND_LINKS`, no Makefile build-image target, no `dist/` `.gitignore`, no `railway.toml [build] buildCommand`.**
- **Railway dashboard change documented**: Source > Root Directory changes from `agent-coordinator` to `/`; Build > Dockerfile Path changes from `Dockerfile` to `agent-coordinator/Dockerfile`. This is a one-time human action (not git-trackable), and is explicitly called out as a known cost of the chosen strategy.
- **railway.toml** keeps no `[build] buildCommand`. A comment in the file points operators to the dashboard change requirement.
- **README.md** gains a `## Deployment` section explaining the Railway configuration.

### 6 advisory fixes (round-2 nits + targeted hardening)

1. **D2 uv_build pin widened** from `>=0.9,<0.10` to `>=0.9,<1.0` (less maintenance churn, same compatibility guarantee).
2. **Task 2.4.1 metrics surface test tightened** — uses an explicit set-equality allowlist (`{n for n in dir(gen_eval.metrics) if not n.startswith("_")} == {"GenEvalMetrics"}`) with a self-diagnosing failure message, not a weaker contains-check.
3. **Spec scenario split**: "Documented consumer adoption contract" now has two sub-scenarios — (a) automated shape checks (uv add invocation present, both install profiles referenced, descriptor-template parses, relative links resolve) and (b) a manual release-gate end-to-end walkthrough recorded in CHANGELOG.
4. **Task 5.5 new** — repo-wide stale-reference sweep across `CLAUDE.md`, `README.md`, `docs/`, `.github/`, `apps/` to catch any `evaluation.gen_eval` / `evaluation/gen_eval` references not handled by task 5.C.
5. **Task 4.3** — explicit `__all__` removal in `agent-coordinator/evaluation/__init__.py` alongside the `from . import gen_eval` deletion (addresses Gemini round-2 nit).
6. **Task 4.1** — new test file pinned to specific name `agent-coordinator/tests/test_gen_eval_extraction.py`, allowing `wp-coordinator-migrate` `scope.write_allow` to list specific files instead of the broad `agent-coordinator/tests/**` glob (resolves scope-overlap with wp-package-tests).

### Scope ownership rebalance to fix overlaps

- `agent-coordinator/Dockerfile`, `agent-coordinator/docker-compose.yml`, `agent-coordinator/railway.toml`, `agent-coordinator/README.md` → owned by **wp-coordinator-migrate**.
- `.github/workflows/ci.yml` gen-eval-tests matrix step → owned by **wp-package-tests**.
- `.github/workflows/ci.yml` coordinator-docker-build step repoint → owned by **wp-integration** (new task 7.6).
- New verification step in wp-integration: `ci step matches Strategy A` greps for `context: .` and the absence of `context: agent-coordinator`.

### Task 7.4 (docker smoke)

Docker smoke now uses `docker build -f agent-coordinator/Dockerfile -t agent-coordinator-smoke .` (repo-root context), aligning with Strategy A. The prior round-2 command that built from `agent-coordinator/` is gone.

## Your job in round 3

Verify the round-2 blockers are resolved and identify any new blockers introduced. Specifically check:

1. **Railway story coherence** — does the plan internally agree that Strategy A (dashboard reconfig + no buildCommand) is the only path? Are there any lingering references to `[build] buildCommand`, `UV_FIND_LINKS`, `--no-sources`, or the Makefile `build-image` target that contradict Strategy A?
2. **CI step repoint** — does task 7.6 cover what Codex round-2 finding #3 raised about `evaluation.gen_eval.mcp_service` in the smoke-import list? Is the wp-integration `verification` step strong enough to catch the contradiction Codex caught (a CI step that says `context: agent-coordinator/` after Strategy A)?
3. **Scope overlap residual** — does any pair of work packages still write to the same file under the new ownership map? (The parallel-zones validator passes; do you spot anything it misses?)
4. **uv_build pin widening** — is `>=0.9,<1.0` safe given uv's release cadence and that uv_build versions track uv minor versions?
5. **Manual release-gate scenario** — is the carve-out (automated shape checks + manual walkthrough recorded in CHANGELOG) a reasonable compromise, or does it leave too much unverified?
6. **Anything else** — any new blocker the Strategy A pivot introduced. E.g., does the deeper Dockerfile COPY paths change image-cache behavior or build performance materially?

Do not re-raise findings already addressed by commit 233de0b unless the fix is incorrect or incomplete. A clean round-3 review (no critical, only nit/fyi/none) means the plan is ready to proceed to IMPLEMENT — and that is the expected outcome here. **If it's true, say so explicitly.**

## Artifacts to read

- `openspec/changes/extract-gen-eval-package/proposal.md`
- `openspec/changes/extract-gen-eval-package/design.md` (D2 pin widened; D8 fully rewritten for Strategy A)
- `openspec/changes/extract-gen-eval-package/tasks.md` (2.4.1, 4.1, 4.3, 4.5 rewritten; 5.5, 7.6 new; 7.4 updated)
- `openspec/changes/extract-gen-eval-package/specs/gen-eval-framework/spec.md` (quickstart scenario split into automated + manual)
- `openspec/changes/extract-gen-eval-package/contracts/README.md`
- `openspec/changes/extract-gen-eval-package/work-packages.yaml` (wp-coordinator-migrate scope+locks tightened; wp-integration scope expanded to include ci.yml)
- `openspec/changes/extract-gen-eval-package/reviews/round-2/findings-codex-plan.json` (round-2 codex blockers)
- `openspec/changes/extract-gen-eval-package/reviews/round-2/findings-gemini-plan.json` (round-2 gemini blockers)

## Output format

Emit STRICTLY a single JSON object conforming to `openspec/schemas/review-findings.schema.json`:

```json
{
  "review_type": "plan",
  "target": "extract-gen-eval-package",
  "reviewer_vendor": "<your-vendor-name>",
  "findings": [
    {
      "id": 1,
      "axis": "correctness|readability|architecture|security|performance",
      "severity": "critical|nit|optional|fyi|none",
      "type": "spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure",
      "criticality": "low|medium|high|critical",
      "description": "<prefix-matching-severity>: <one or two sentences>",
      "resolution": "<concrete fix>",
      "disposition": "fix|regenerate|accept|escalate",
      "file_path": "<optional>",
      "line_range": {"start": <int>, "end": <int>}
    }
  ]
}
```

DO NOT emit a bare array. The dispatcher will discard unparsable output.

## Severity prefix discipline

Every `description` MUST begin with the prefix matching its `severity` enum value: `Critical:`, `Nit:`, `Optional:`, `FYI:`, or nothing for `none`. If you find nothing material, emit at least one `severity: none` positive observation naming what the plan got right.
