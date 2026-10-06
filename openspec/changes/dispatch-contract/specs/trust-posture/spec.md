## ADDED Requirements

### Requirement: Roadmap-Approval-Scoped Auto Dispositions

The trust posture SHALL let the `proposal_approval` and `replan_required` gate configs declare an optional `unscoped` sub-config (`disposition` of `notify_with_timeout` or `block`, with the same `timeout_seconds` / `default_action` rules as a gate config), defaulting to `{disposition: block}` when absent. When either gate's disposition is `auto`, the approval gate SHALL apply `auto` only if the evaluation context carries a `roadmap_approval_ref` taken from the caller's current, generation-verified launch marker; otherwise it SHALL apply the `unscoped` config and record `scope: unscoped` and a reason naming the fallback in the decision. `unscoped` with disposition `auto`, or on any other gate, SHALL be a validation error. The loader SHALL also expose `posture_digest(posture)`: the SHA-256 of the canonical JSON of the parsed `gates` map, with a fixed value for the absent-posture default.

#### Scenario: Dispatched run with a valid approval reference proceeds
- **WHEN** `proposal_approval` is `auto` and the context's `roadmap_approval_ref` came from the current launch marker
- **THEN** the decision SHALL be `proceed` with `resolution: auto` and `scope: roadmap_approval`

#### Scenario: Standalone run falls back to the unscoped disposition
- **WHEN** `proposal_approval` is `auto`, no `unscoped` is declared, and the context carries no `roadmap_approval_ref`
- **THEN** the decision SHALL be `blocked` with `resolution: posture_block`, `scope: unscoped`, and a reason containing `unscoped fallback`

#### Scenario: Declared notify fallback is used
- **WHEN** `replan_required` is `auto` with `unscoped: {disposition: notify_with_timeout, timeout_seconds: 600, default_action: block}` and no reference is present
- **THEN** the approval gate SHALL file an approval and apply `block` on timeout

#### Scenario: A reference not from the launch marker is ignored
- **WHEN** the context carries a `roadmap_approval_ref` but no launch marker exists for the current generation
- **THEN** the unscoped fallback SHALL apply

#### Scenario: Invalid unscoped config is rejected
- **WHEN** `TRUST_POSTURE.md` declares `unscoped: {disposition: auto}` or declares `unscoped` on `merge`
- **THEN** `validate_posture_file` SHALL return an error naming the gate and field

#### Scenario: Digest ignores prose and key order
- **WHEN** two posture files differ only in Markdown body text and front-matter key order
- **THEN** `posture_digest` SHALL return the same value for both
