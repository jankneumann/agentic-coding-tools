# Spec Delta: Codebase Analysis — Build Graph and Affected-Test Analysis

**Change ID**: `speculative-merge-trains`
**Capability**: `codebase-analysis`

## ADDED Requirements

### Requirement: Test Node Extraction

The architecture analysis pipeline SHALL extract test functions and test classes from Python test files and represent them as nodes in the architecture graph.

#### Scenario: Discover test functions from naming convention

WHEN analyzing Python files matching `test_*.py` or `*_test.py` patterns
THEN all functions named `test_*` SHALL be added as nodes with `kind: "test_function"`
AND all classes named `Test*` SHALL be added as nodes with `kind: "test_class"`
AND each test node SHALL include `file`, `span` (line range), and `tags: ["test"]`

#### Scenario: Discover parametrized tests

WHEN a test function is decorated with `@pytest.mark.parametrize`
THEN the function SHALL still be represented as a single test node (not expanded per parameter)
AND the node SHALL include `tags: ["test", "parametrized"]`

### Requirement: Test Coverage Edge Creation (Import-Level — Phase 1)

The architecture pipeline SHALL create `TEST_COVERS` edges from test nodes to source nodes based on import analysis.

#### Scenario: Direct import creates TEST_COVERS edge

WHEN `test_billing.py` contains `from src.billing import BillingService`
THEN a `TEST_COVERS` edge SHALL be created from the test module node to the `src.billing` module node
AND the edge SHALL have `confidence: "high"` and `evidence: "direct_import"`

#### Scenario: No edge for standard library imports

WHEN a test file imports only standard library modules (e.g., `import os`, `import json`)
THEN no `TEST_COVERS` edges SHALL be created for those imports
AND only project-internal imports SHALL produce edges

### Requirement: Affected-Test Query

The architecture pipeline SHALL provide a function `affected_tests(changed_files: list[str]) -> list[str]` that returns test file paths affected by the given source file changes.

#### Scenario: Single file change with direct test

WHEN `affected_tests(["src/billing.py"])` is called
AND `test_billing.py` imports from `src.billing`
THEN the result SHALL include `tests/test_billing.py`

#### Scenario: File change with no covering tests

WHEN `affected_tests(["src/orphan_module.py"])` is called
AND no test file imports from `src.orphan_module`
THEN the result SHALL be an empty list
AND a warning SHALL be logged identifying the uncovered module

#### Scenario: Stale graph fallback

WHEN `affected_tests()` is called and the architecture graph is older than 24 hours
THEN the function SHALL return `None` (signaling "run all tests")
AND a warning SHALL be logged recommending `refresh-architecture`

#### Scenario: Traversal bound on large graphs

WHEN `affected_tests()` performs reverse BFS from changed files
THEN the traversal SHALL stop at test nodes (not traverse further through test-to-test edges)
AND the traversal SHALL implement cycle detection (visited set)
AND the traversal SHALL visit at most 10,000 nodes per query
AND if the bound is exceeded, the function SHALL return `None` (signaling "run all tests") with a warning
AND the target query latency SHALL be under 100ms for graphs with up to 10,000 nodes

### Requirement: Transitive Affected-Test Analysis (Phase 2)

The architecture pipeline SHALL extend affected-test analysis to include tests that transitively depend on changed files through the call graph.

#### Scenario: Transitive dependency through call graph

WHEN `src/utils.py` is changed
AND `src/billing.py` calls a function in `src/utils.py`
AND `test_billing.py` imports from `src.billing`
THEN `affected_tests(["src/utils.py"])` SHALL include `tests/test_billing.py`
AND the edge SHALL have `confidence: "medium"` and `evidence: "transitive_call"`

## MODIFIED Requirements

### Requirement: Architecture Graph Schema (Extended)

The architecture graph schema SHALL support new node kinds and edge types for test analysis.

#### Scenario: New node kinds are valid

WHEN graph validation runs on a graph containing nodes with `kind: "test_function"` or `kind: "test_class"`
THEN validation SHALL pass without errors

#### Scenario: New edge types are valid

WHEN graph validation runs on a graph containing edges with `type: "TEST_COVERS"`
THEN validation SHALL pass without errors
AND the edge SHALL require `confidence` (high/medium/low) and `evidence` (string) fields
