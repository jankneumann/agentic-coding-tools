Review the OpenSpec plan artifacts in openspec/changes/specialized-workflow-agents/.
Read proposal.md, design.md, tasks.md, specs/agent-archetypes/spec.md, work-packages.yaml, and contracts/README.md.

Output ONLY valid JSON conforming to the review-findings schema with these fields per finding:
- type: one of spec_gap, correctness, contract_mismatch, architecture, security, performance, style, observability, resilience, compatibility
- severity: one of critical, high, medium, low, info
- file: the file path where the issue is found
- line: approximate line number (or null)
- title: short title
- description: detailed description of the issue
- suggestion: proposed fix

Focus on:
1. Specification completeness — are all requirements testable with measurable criteria?
2. Contract consistency — do tasks, specs, and work-packages align?
3. Architecture alignment — does the design fit the existing codebase patterns?
4. Security — are there input validation gaps, unprotected endpoints, or config injection risks?
5. Work package validity — are scopes non-overlapping, dependencies correct, DAG acyclic?
6. Feasibility — can each task be implemented in a single commit with the declared file scope?
