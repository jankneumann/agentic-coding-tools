# Declare the routing cost policy the router obeys

## Why

The DG-04 router ranks feasible assignments by utility, which can send work to metered OpenRouter while a subscription lane is available. The operator's preference for subscription capacity needs to be explicit and auditable.

## What Changes

- Add a validated three-tier cost ladder to the versioned routing policy.
- Select the first tier containing a feasible assignment, then use the existing utility scorer within that tier.
- Persist the selected tier in routing decision provenance.

## Impact

Routing decisions prefer local subscription CLI, then subscription cloud, then metered API. Unavailable and rate-limited lanes are filtered before the ladder runs. Existing deployments without a cost policy retain their current utility ranking.
