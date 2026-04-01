Review the OpenSpec plan artifacts in openspec/changes/live-service-testing/.
Read proposal.md, tasks.md, design.md, specs/live-service-testing/spec.md, work-packages.yaml, and all contracts/*.
Output ONLY valid JSON conforming to the review-findings schema.
Focus on: specification completeness, contract consistency, architecture alignment, security, and work package validity.

Key context:
- This feature adds live service testing infrastructure to the validation pipeline
- It supports Docker/Podman local stacks and Neon cloud branches
- There are 9 requirements (LST.1-LST.9) with 43 scenarios
- 6 work packages in a DAG: contracts → (stack-launcher || smoke-tests || seed-data) → neon-branch → integration
- Two gates: soft gate at implement-feature, hard gate at cleanup-feature
