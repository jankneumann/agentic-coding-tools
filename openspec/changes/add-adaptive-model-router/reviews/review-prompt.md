Review the OpenSpec plan artifacts in openspec/changes/add-adaptive-model-router/.

Read proposal.md, design.md, tasks.md, work-packages.yaml, change-context.md, and all spec deltas. Focus especially on the Plan Iteration 1 amendment that separates static model-policy ownership:

- agents.yaml owns harness identity, eligibility, transport, credentials, endpoint metadata, and invocation mechanics such as model_flag, but no concrete model IDs or fallback values.
- archetypes.yaml owns exact agent-harness + dispatch-kind ordered ModelSpec chains selected through task/phase -> archetype -> tier.
- tasks 4.7-4.9 and wp-model-config-ownership must safely migrate sync CLI, async CLI, SDK, discovery, bridge/API, and health consumers without ambient defaults.

Evaluate specification completeness, contract consistency, architecture, security, performance, observability, resilience, compatibility, task traceability, migration ordering, and work-package DAG/lock validity.

Output ONLY valid JSON conforming to openspec/schemas/review-findings.schema.json. Include axis and severity on every finding. Prefix descriptions consistently with severity (Critical:, Nit:, Optional:, FYI:; no prefix required for severity none).
