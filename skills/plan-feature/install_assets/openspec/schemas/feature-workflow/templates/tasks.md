# Tasks: <change-id>

<!-- Task ordering: TDD test-first. Within each phase, list test tasks BEFORE
     the implementation tasks they verify. Implementation tasks depend on
     their corresponding test tasks, ensuring tests are written (RED) before
     code is written to make them pass (GREEN).

     Test tasks MUST reference the artifacts they validate:
     - Spec scenarios: which WHEN/THEN scenarios the tests encode
     - Contracts: which API endpoints, schemas, or event payloads the tests assert against
     - Design decisions: which architectural choices the tests verify -->

## 1. <phase name>

- [ ] 1.1 Write tests for <component> — <test scenarios>
  **Spec scenarios**: <capability>.<N> (<scenario summary>)
  **Contracts**: <contract file paths, if applicable>
  **Design decisions**: <D# references from design.md, if applicable>
  **Dependencies**: None
  **Files**: <test file paths>

- [ ] 1.2 Implement <component> — <task description>
  **Dependencies**: 1.1
  **Files**: <file paths>

