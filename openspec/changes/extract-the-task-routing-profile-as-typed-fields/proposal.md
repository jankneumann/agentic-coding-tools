# Extract the task routing profile as typed fields

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `extract-the-task-routing-profile-as-typed-fields`
> Effort: M
> Priority: 4

## Summary

Produce the task router's routing profile from a task description with Score(duration, [minutes, an hour, a day, longer]), Noul("needs interactive human input"), Noul("needs a secret or credential") and Choice(scope, {single_file, package, cross_package, repo_wide}), leaving the routing rules themselves deterministic and versioned.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- The router consumes only typed profile fields and its rule evaluation is unchanged, asserted by routing tests that pass a hand-written profile.
- The routing audit event carries the probabilities for every profile field it was given.
- With the helper returning None the router still resolves using its declared or default profile, covered by a test.
- A fixture set of task descriptions yields the expected profile fields, with duration and scope agreement recorded.

## Rationale

Pilot step 5 and factor 1, natural language to structured data. The active implement-the-task-router-vendor-x-location-x-model change is right that routing rules must stay deterministic and explainable; what produces the profile today is nothing or an LLM. This item must land after that change so the router never needs an LLM at all.
