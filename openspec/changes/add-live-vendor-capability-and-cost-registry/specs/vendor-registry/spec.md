## ADDED Requirements

### Requirement: Live Vendor Registry

The coordinator SHALL expose a vendor registry combining static capabilities from agents.yaml with live availability, rate-limit state, and versioned cost data.

#### Scenario: Registry endpoint

WHEN a client requests `GET /vendors`
THEN the response SHALL include, per vendor, its capabilities, current availability, any known limit-reset time, and the cost table version.

#### Scenario: Limit visibility within one probe interval

WHEN a vendor rate limit is observed by any dispatcher
THEN the registry SHALL reflect the limited state within one probe interval.

### Requirement: Registry-Driven Vendor Enumeration

Consumers SHALL enumerate available vendors from the registry rather than hardcoded lists.

#### Scenario: Orchestrator uses registry

WHEN the roadmap orchestrator evaluates vendor policy
THEN the eligible vendor set SHALL come from the registry filtered by required capability
AND real cost and wait estimates from the registry SHALL replace stubbed values.
