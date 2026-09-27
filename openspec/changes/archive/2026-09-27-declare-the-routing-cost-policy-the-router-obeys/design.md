# Design

## D1: Cost policy is an optional overlay

`routing.yaml` declares ordered tiers with exact location and endpoint-kind matchers. The runtime Pydantic model validates the ladder and rejects overlapping matchers. Keeping the section optional preserves behavior for older policy files.

## D2: Feasibility precedes cost preference

The registry and catalog join excludes unavailable, rate-limited, and ineligible lanes. The router keeps candidates from the first nonempty tier and hands only those candidates to DG-00 utility scoring. This avoids a second scoring function and naturally falls through when a subscription window is exhausted.

## D3: Record the served tier

The coordinator response and atomic durable decision payload include `provenance.cost_tier`. Excluded lower-tier candidates retain a machine-readable reason. Existing audit links continue to point to the durable decision.
