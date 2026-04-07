# Software Factory Tooling

Guide for external projects adopting software-factory practices with gen-eval scenario packs, DTU scaffolds, and validation-driven rework.

## Scenario Pack Management

### Manifest Structure

Scenario-pack manifests classify scenarios by visibility and provenance:

```yaml
version: 1
entries:
  - scenario_id: lock-acquire-basic
    visibility: public          # Available during implementation
    source: spec                # Derived from spec requirement
    determinism: deterministic
    owner: agent-coordinator
    promotion_status: approved

  - scenario_id: lock-contention-race
    visibility: holdout         # Only visible to validation/cleanup gates
    source: incident
    incident_ref: INC-42
    determinism: bounded-nondeterministic
    owner: oncall
    promotion_status: candidate
```

### Visibility Fields

| Field | Values | Description |
|-------|--------|-------------|
| `visibility` | `public`, `holdout` | Controls which workflow phases can see the scenario |
| `source` | `spec`, `contract`, `doc`, `incident`, `archive`, `manual` | How the scenario was created |
| `determinism` | `deterministic`, `bounded-nondeterministic`, `exploratory` | Execution predictability |
| `promotion_status` | `draft`, `candidate`, `approved` | Maturity level |

### Directory Layout

```
evaluation/gen_eval/
  scenarios/
    public/          # Implementation-visible scenarios
      lock-lifecycle/
      memory-ops/
    holdout/         # Validation-only scenarios
      regression/
      contention/
  manifests/
    manifest.yaml    # Combined manifest
```

### Visibility Enforcement

Three reinforcing layers (Design Decision D2):

1. **Directory structure**: `public/` and `holdout/` directories make intent visible
2. **Manifest metadata**: Machine-readable visibility classification
3. **Runtime filtering**: Skill logic enforces the boundary at execution time

## DTU Scaffold From Public Docs

### Bootstrap Flow

1. Collect public SDK/API docs, examples, auth guidance, error tables
2. Run the scaffold generator to produce:
   - `descriptor.seed.yaml` — gen-eval descriptor template
   - `fixtures/` — placeholder response fixtures
   - `error-catalog.json` — documented error modes
   - `unsupported-surfaces.json` — surfaces that need live probes
3. Generate a fidelity report
4. Use the scaffold for public scenarios immediately
5. Add live probes to reach holdout eligibility

### Fidelity Report

The fidelity report determines holdout eligibility:

- **Conformance score**: 0.0 to 1.0 based on doc coverage and probe results
- **Holdout threshold**: 0.7 (configurable)
- **Without probes**: Max score capped at 0.6 (docs alone cannot reach holdout)
- **With probes**: Full score range; probes weigh 70% of the combined score
- **Operator override**: Explicit approval bypasses the score threshold

### Quick Start

```python
from evaluation.gen_eval.dtu_scaffold import (
    PublicDocInput, EndpointDoc, AuthDoc, generate_scaffold, write_scaffold
)
from evaluation.gen_eval.fidelity import compute_fidelity, write_fidelity_report

# 1. Describe the external system
docs = PublicDocInput(
    system_name="my-api",
    base_url="https://api.example.com",
    auth=AuthDoc(type="bearer", header="Authorization"),
    endpoints=[
        EndpointDoc(path="/users", method="GET", response_schema={"type": "array"}),
    ],
)

# 2. Generate scaffold
scaffold = generate_scaffold(docs)
write_scaffold(scaffold, Path("evaluation/gen_eval/dtu/my-api"))

# 3. Compute fidelity
report = compute_fidelity(
    system_name="my-api",
    sources=["api-docs-v2"],
    unsupported_surfaces=scaffold.unsupported_surfaces,
    total_endpoints=len(docs.endpoints),
)
write_fidelity_report(report, Path("evaluation/gen_eval/dtu/my-api/fidelity-report.json"))
```

## Validation-Driven Rework

### Rework Report

`/validate-feature` produces `rework-report.json` mapping failed scenarios to owners and recommended actions:

```json
{
  "failures": [
    {
      "scenario_id": "lock-contention-race",
      "visibility": "holdout",
      "requirement_refs": ["Lock Acquisition"],
      "implicated_files": ["src/locks.py"],
      "likely_owner": "wp-scenario-packs",
      "recommended_action": "iterate"
    }
  ],
  "summary": {
    "total_failures": 1,
    "public_failures": 0,
    "holdout_failures": 1,
    "recommended_action": "iterate"
  }
}
```

### Actions

| Action | Meaning |
|--------|---------|
| `iterate` | Fix and re-validate |
| `revise-spec` | Spec needs updating |
| `defer` | Non-blocking, track for later |
| `block-cleanup` | Holdout failure blocks merge |
| `none` | All scenarios passed |

### Workflow Integration

- `/implement-feature`: Runs **public** scenarios as soft gate
- `/iterate-on-implementation`: Consumes `rework-report.json` for prioritization
- `/validate-feature`: Runs both public and holdout; produces rework report
- `/cleanup-feature`: Holdout failures block merge
- `/merge-pull-requests`: Checks holdout gate status

## Archive Intelligence

### Archive Miner

Indexes completed OpenSpec changes into reusable artifacts:

- **Scenario seeds**: Patterns from successful validations
- **Repair patterns**: Fix strategies from rework history
- **DTU edge cases**: Boundary behaviors from real usage
- **Implementation exemplars**: Reference implementations

### Integration

- `/explore-feature`: Uses archive index for feature discovery
- `/plan-feature`: References exemplars for estimation
- `/gen-eval-scenario`: Seeds scenarios from archive patterns

## Getting Started

For projects adopting software-factory practices:

1. **Enable gen-eval** if not already configured
2. **Create manifests** in your scenario directories
3. **Bootstrap scenarios** from your spec deltas and contracts
4. **Add DTU scaffolds** for external system boundaries
5. **Run validation** to generate initial rework and process analysis artifacts
