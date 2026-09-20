# Judge multi-vendor review eligibility for pull requests

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `judge-multi-vendor-review-eligibility-for-pull-requests`
> Effort: M
> Priority: 3

## Why

`vendor_review.check_review_eligibility` (`skills/merge-pull-requests/scripts/vendor_review.py:38,103`)
skips multi-vendor review for PRs under 50 changed lines or 3 files. A
40-line change to `guardrails.py` or a Cedar policy is "small" by this rule;
a 300-line docs move is "large." The size threshold routes review effort by
the wrong variable — line count is not a proxy for risk.

## What Changes

- **MODIFIED**: `check_review_eligibility` asks a calibrated judgment —
  `Noul("This PR warrants independent multi-vendor review")` plus
  `Score(risk, ["docs/config only", "internal refactor", "behaviour change",
  "security or data path"])` — over the PR's title, body, file list and diff
  stat (never the diff itself), before falling back to the existing
  size-threshold rule when the judgment is unavailable.
- The deterministic origin-provenance skip (`SKIP_ORIGINS`:
  dependabot/renovate/Jules subtypes) and the draft-PR skip stay
  deterministic and run **before** any judgment call — those are facts, not
  judgments.
- `SMALL_PR_MAX_CHANGED_LINES` and `SMALL_PR_MAX_FILES` move to an optional
  config sidecar (`vendor-review-judgment.json`), mirroring the
  threshold-loading precedent from `gatekeeper_shadow`, `triage`, and
  `implementation_strategy_selector`, and remain the fallback when the
  judgment helper returns `None`.
- The eligibility record's `details` carries `evidence_class: "judgment"`,
  the risk score, and its probability when the judged path drove the
  decision.

## Impact

- Affected capability: `merge-pull-requests` (MODIFIED requirement: "Vendor
  Review Artifact Resilience").
- Affected code: `skills/merge-pull-requests/scripts/vendor_review.py`
  (`check_review_eligibility`, `compute_pr_size`), consumed unchanged by
  `execute_plan.py`'s `_default_vendor_review`.
- No change to the existing-reviews check (fresh approval / unresolved
  change requests), which stays deterministic and still short-circuits
  eligibility independently of the judgment.

## Non-Goals

- Not changing `SKIP_ORIGINS` or the draft-PR skip — those remain
  deterministic facts about provenance, per the parent proposal
  (`docs/proposals/jev-system-one-integration-assessment.md` A4).
- Not sending the PR diff itself to the judgment — only title, body, file
  list and diff stat, to keep the eligibility check cheap and within the
  32K-token budget `system_one_decisions.decide()` already enforces.
- Not changing `dispatch_vendor_reviews` or the review prompt/consensus
  machinery — only the eligibility gate that decides whether to call it.
