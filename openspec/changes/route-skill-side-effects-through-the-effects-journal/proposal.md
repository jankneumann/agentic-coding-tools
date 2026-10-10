# Route skill side effects through the effects journal

> Parent roadmap: `durable-execution`
> Change ID: `route-skill-side-effects-through-the-effects-journal`
> Effort: L
> Priority: 2

## Summary

Wrap push, PR create/update/merge, deploy/teardown, issue/comment posting, non-idempotent coordinator mutations, and external notifications in /cleanup-feature, /merge-pull-requests, /validate-feature, and the autopilot SUBMIT_PR step with the effects journal, and add a guard test that forbids unwrapped effect-producing calls in skill scripts.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- /cleanup-feature, /merge-pull-requests, /validate-feature (deploy/teardown), and the autopilot SUBMIT_PR step record every listed effect via begin/complete/fail.
- Re-running SUBMIT_PR after a crash with a started entry finds the existing PR for the head branch and records completed without creating a second PR.
- A guard test fails when gh pr create, git push, merge APIs, or deploy entry points are invoked from a skill script outside an effects-journal wrapper.
- Behavior is unchanged in sequential, local-parallel, and coordinated tiers and in cloud-harness environments.

## Rationale

The journal only prevents repeated irreversible actions if the skills that perform them actually use it; the guard test keeps new call sites from regressing the guarantee.
